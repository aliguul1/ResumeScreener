"""
AI Resume Screener — Flask Application
Stack: Flask · SQLite · pdfplumber · Anthropic Claude API
"""

import os
import sqlite3
import threading
from pathlib import Path

import pdfplumber
import anthropic
from flask import Flask, request, jsonify, g

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).parent
DB_PATH    = BASE_DIR / "screener.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    """Return the per-request DB connection (created lazily)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables from schema.sql if they don't exist yet."""
    schema = (BASE_DIR / "schema.sql").read_text()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(schema)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF using pdfplumber."""
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# AI Screening (async)
# ---------------------------------------------------------------------------

def screen_application_async(application_id: int, resume_text: str, job_description: str):
    """
    Called in a background thread after submission.
    Sends resume text + job description to Claude and writes the decision back.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    prompt = f"""You are an expert recruiter. Evaluate the following resume against the job description.

JOB DESCRIPTION:
{job_description}

RESUME TEXT:
{resume_text}

Respond with a JSON object and nothing else:
{{
  "decision": "accepted" or "rejected",
  "reason": "one concise sentence explaining the decision"
}}"""

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        raw = message.content[0].text.strip()
        result = json.loads(raw)
        decision = result.get("decision", "rejected")
        feedback = result.get("reason", "")
    except Exception as e:
        decision = "rejected"
        feedback = f"Screening error: {e}"

    # Write result back to DB (open a fresh connection — we're off the request thread)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE applications SET filter_status = ?, ai_feedback = ? WHERE id = ?",
            (decision, feedback, application_id),
        )


# ---------------------------------------------------------------------------
# Routes — Job Openings (Hiring Manager)
# ---------------------------------------------------------------------------

@app.route("/jobs", methods=["GET"])
def list_jobs():
    """GET /jobs — list all job openings."""
    db   = get_db()
    rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id):
    """GET /jobs/<id> — get a single job opening."""
    db  = get_db()
    row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/jobs", methods=["POST"])
def create_job():
    """POST /jobs — create a job opening.
    Body: { title, description, requirements? }
    """
    data = request.get_json(force=True)
    if not data.get("title") or not data.get("description"):
        return jsonify({"error": "title and description are required"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO jobs (title, description, requirements) VALUES (?, ?, ?)",
        (data["title"], data["description"], data.get("requirements")),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "message": "Job created"}), 201


@app.route("/jobs/<int:job_id>", methods=["PUT"])
def update_job(job_id):
    """PUT /jobs/<id> — update a job opening."""
    data = request.get_json(force=True)
    db   = get_db()
    row  = db.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return jsonify({"error": "Job not found"}), 404

    db.execute(
        """UPDATE jobs SET title = COALESCE(?, title),
                           description = COALESCE(?, description),
                           requirements = COALESCE(?, requirements)
           WHERE id = ?""",
        (data.get("title"), data.get("description"), data.get("requirements"), job_id),
    )
    db.commit()
    return jsonify({"message": "Job updated"})


@app.route("/jobs/<int:job_id>", methods=["DELETE"])
def delete_job(job_id):
    """DELETE /jobs/<id> — delete a job opening (cascades to applications)."""
    db  = get_db()
    row = db.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return jsonify({"error": "Job not found"}), 404

    db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    db.commit()
    return jsonify({"message": "Job deleted"})


# ---------------------------------------------------------------------------
# Routes — Applications (Hiring Manager view)
# ---------------------------------------------------------------------------

@app.route("/jobs/<int:job_id>/applications", methods=["GET"])
def list_accepted_applications(job_id):
    """GET /jobs/<id>/applications — list accepted applications for a job."""
    db  = get_db()
    job = db.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    rows = db.execute(
        "SELECT * FROM applications WHERE job_id = ? AND filter_status = 'accepted' ORDER BY created_at DESC",
        (job_id,),
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Routes — Applications (Candidate)
# ---------------------------------------------------------------------------

@app.route("/applications", methods=["POST"])
def submit_application():
    """POST /applications — submit a new job application with a PDF resume.

    Form fields:
      - job_id          (int, required)
      - applicant_name  (str, required)
      - applicant_email (str, required)
      - resume          (file, required, PDF only)
    """
    # Validate form fields
    job_id          = request.form.get("job_id")
    applicant_name  = request.form.get("applicant_name")
    applicant_email = request.form.get("applicant_email")
    resume_file     = request.files.get("resume")

    if not all([job_id, applicant_name, applicant_email, resume_file]):
        return jsonify({"error": "job_id, applicant_name, applicant_email and resume are required"}), 400

    if not allowed_file(resume_file.filename):
        return jsonify({"error": "Only PDF files are accepted"}), 400

    db  = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Save PDF to disk
    safe_name  = f"app_{applicant_email.replace('@','_')}_{job_id}.pdf"
    pdf_path   = UPLOAD_DIR / safe_name
    resume_file.save(pdf_path)

    # Extract text from PDF
    try:
        resume_text = extract_text_from_pdf(pdf_path)
    except Exception as e:
        return jsonify({"error": f"Could not extract text from PDF: {e}"}), 422

    # Insert application with status = pending
    cur = db.execute(
        """INSERT INTO applications (job_id, applicant_name, applicant_email, resume_text, filter_status)
           VALUES (?, ?, ?, ?, 'pending')""",
        (job_id, applicant_name, applicant_email, resume_text),
    )
    db.commit()
    application_id = cur.lastrowid

    # Trigger async AI screening
    job_dict = row_to_dict(job)
    job_description = f"{job_dict['title']}\n\n{job_dict['description']}\n\nRequirements:\n{job_dict.get('requirements', '')}"
    thread = threading.Thread(
        target=screen_application_async,
        args=(application_id, resume_text, job_description),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "id": application_id,
        "filter_status": "pending",
        "message": "Application submitted. Screening in progress.",
    }), 201


@app.route("/applications/<int:app_id>", methods=["GET"])
def get_application(app_id):
    """GET /applications/<id> — get application status (for the candidate to poll)."""
    db  = get_db()
    row = db.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    if not row:
        return jsonify({"error": "Application not found"}), 404

    data = row_to_dict(row)
    # Don't expose full resume text to the candidate endpoint
    data.pop("resume_text", None)
    return jsonify(data)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
