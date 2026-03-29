# AI Resume Screener

A Flask + SQLite API that accepts PDF resumes, extracts the text, and uses Claude to automatically screen candidates against job descriptions.

## Tech stack

- **Flask** — API framework
- **SQLite** — lightweight persistence
- **pdfplumber** — PDF → text extraction
- **Anthropic Claude API** — async resume screening
- **threading** — fire-and-forget background screening task

## Quick start

```bash
# 1. Clone and install
git clone <your-repo-url>
cd ai-resume-screener
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Run (creates screener.db automatically)
python app.py
```

## Project structure

```
ai-resume-screener/
├── app.py            # Flask application (all routes + AI screening)
├── schema.sql        # SQLite schema (auto-applied on startup)
├── requirements.txt
├── API_SPEC.md       # Full endpoint reference
├── uploads/          # Uploaded PDF files (git-ignored)
└── screener.db       # SQLite database (git-ignored)
```

## Scenarios

### Hiring manager
- `POST   /jobs`                          Create a job opening
- `GET    /jobs`                          List all openings
- `GET    /jobs/:id`                      Get one opening
- `PUT    /jobs/:id`                      Update an opening
- `DELETE /jobs/:id`                      Delete an opening
- `GET    /jobs/:id/applications`         View accepted applications only

### Candidate
- `POST   /applications`                  Submit application + PDF resume
- `GET    /applications/:id`              Poll screening status

## Screening flow

```
Candidate submits PDF
    → text extracted (pdfplumber)
    → stored in DB (filter_status = pending)
    → background thread fires
        → Claude API: resume vs job description
        → DB updated: accepted | rejected
```
