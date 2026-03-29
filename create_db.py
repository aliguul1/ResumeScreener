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
