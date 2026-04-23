import threading
import sqlite3
from flask import Flask, request, jsonify, g
from werkzeug.utils import secure_filename
import config
from services.pdf_service import extract_text_from_pdf
from services.ai_service import screen_application_async

app = Flask(__name__)

# --- Database Management ---

def get_db():
    """Provides a database connection for the current Flask request context."""
    if "db" not in g:
        g.db = sqlite3.connect(config.DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database and ensures upload directories exist."""
    # Ensure upload directory exists
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(config.DB_PATH) as conn:
        # Jobs Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                requirements TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP           
            )""")
        
        # Applications Table (Fixed trailing comma)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                applicant_name TEXT NOT NULL,
                applicant_email TEXT NOT NULL,
                resume_text TEXT,
                filter_status TEXT DEFAULT 'pending'
                    CHECK(filter_status IN ('pending', 'accepted', 'rejected')),
                ai_feedback TEXT,
                prompt_version TEXT,
                ai_model TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""")
        
        # Optimization Indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(filter_status)")

        # Auto-update timestamps
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS jobs_updated_at AFTER UPDATE ON jobs
            BEGIN
                UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;             
            END;""")
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS apps_updated_at AFTER UPDATE ON applications
            BEGIN 
                UPDATE applications SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;""")

# --- Routes ---

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online", "message": "Recruitment API Active."})

@app.route("/jobs", methods=["POST"])
def create_job():    
    title = request.form.get("title")
    file = request.files.get("job_pdf")

    if not title or not file:
        return jsonify({"error": "Title and job_pdf are required"}), 400

    filename = secure_filename(f"job_{title}.pdf")
    path = config.UPLOAD_DIR / filename
    file.save(path)

    job_content = extract_text_from_pdf(path)
    
    db = get_db()
    cur = db.execute(
        "INSERT INTO jobs (title, description) VALUES (?, ?)", 
        (title, job_content)
    )  
    db.commit()
    
    return jsonify({"id": cur.lastrowid, "message": "Job created successfully"}), 201

@app.route("/applications", methods=["POST"])
def submit_application():
    job_id = request.form.get("job_id")
    name = request.form.get("applicant_name")
    email = request.form.get("applicant_email")
    file = request.files.get("resume")

    if not all([job_id, name, email, file]):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Process PDF
    filename = secure_filename(f"cv_{email}_{job_id}.pdf")
    path = config.UPLOAD_DIR / filename
    file.save(path)
    resume_text = extract_text_from_pdf(path)

    db = get_db()
    
    # Validate job existence
    job = db.execute("SELECT description FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return jsonify({"error": "Invalid job_id"}), 404
    
    # Save application
    cur = db.execute(
        "INSERT INTO applications (job_id, applicant_name, applicant_email, resume_text) VALUES (?, ?, ?, ?)",
        (job_id, name, email, resume_text)
    )
    db.commit()
    app_id = cur.lastrowid

    # Background AI Task
    # Note: screen_application_async MUST open its own sqlite3 connection inside the function
    threading.Thread(
        target=screen_application_async,
        args=(app_id, resume_text, job["description"]),
        daemon=True
    ).start()

    return jsonify({"application_id": app_id, "status": "processing"}), 201

@app.route("/jobs/<int:job_id>/applications", methods=["GET"])
def get_accepted_applications(job_id):
    db = get_db()
    apps = db.execute(
        "SELECT * FROM applications WHERE job_id = ? AND filter_status = 'accepted'", 
        (job_id,)
    ).fetchall()
    return jsonify([dict(row) for row in apps])

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
"""
create_db.py — Initialize the SQLite database from schema.sql
Run: python create_db.py
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "screener.db"
SCHEMA   = BASE_DIR / "schema.sql"


def create_database():
    print(f"Creating database at: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA.read_text())

    # Verify
    conn = sqlite3.connect(DB_PATH)
    tables   = conn.execute("SELECT name FROM sqlite_master WHERE type='table'  ORDER BY name").fetchall()
    indexes  = conn.execute("SELECT name FROM sqlite_master WHERE type='index'  ORDER BY name").fetchall()
    triggers = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    conn.close()

    print(f"  Tables   : {[t[0] for t in tables]}")
    print(f"  Indexes  : {[i[0] for i in indexes]}")
    print(f"  Triggers : {[t[0] for t in triggers]}")
    print("Done.")


if __name__ == "__main__":
    create_database()
