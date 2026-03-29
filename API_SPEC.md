# AI Resume Screener — API Spec

Base URL: `http://localhost:5000`

---

## Job Openings (Hiring Manager)

### List all jobs
`GET /jobs`

**Response 200**
```json
[{ "id": 1, "title": "ML Engineer", "description": "...", "requirements": "...", "created_at": "..." }]
```

---

### Get a job
`GET /jobs/:id`

**Response 200** — job object
**Response 404** — `{ "error": "Job not found" }`

---

### Create a job
`POST /jobs`
`Content-Type: application/json`

**Body**
```json
{
  "title": "ML Engineer",
  "description": "We are looking for...",
  "requirements": "3+ years Python, PyTorch..."
}
```

**Response 201**
```json
{ "id": 5, "message": "Job created" }
```

---

### Update a job
`PUT /jobs/:id`
`Content-Type: application/json`

**Body** — any subset of `title`, `description`, `requirements`

**Response 200** — `{ "message": "Job updated" }`

---

### Delete a job
`DELETE /jobs/:id`

**Response 200** — `{ "message": "Job deleted" }`
**Note:** Cascades — all applications for this job are also deleted.

---

## Applications (Hiring Manager view)

### List accepted applications for a job
`GET /jobs/:id/applications`

Returns only applications with `filter_status = accepted`.

**Response 200**
```json
[
  {
    "id": 12,
    "job_id": 3,
    "applicant_name": "Jane Doe",
    "applicant_email": "jane@example.com",
    "resume_text": "<full extracted text>",
    "ai_feedback": "Strong Python background and relevant project experience.",
    "filter_status": "accepted",
    "created_at": "2025-04-01T10:30:00"
  }
]
```

---

## Applications (Candidate)

### Submit an application
`POST /applications`
`Content-Type: multipart/form-data`

**Form fields**
| Field | Type | Required | Notes |
|---|---|---|---|
| `job_id` | int | Yes | Must reference an existing job |
| `applicant_name` | string | Yes | |
| `applicant_email` | string | Yes | |
| `resume` | file | Yes | PDF only, max 10 MB |

**Flow**
1. PDF saved to `uploads/`
2. Text extracted via `pdfplumber`
3. Application inserted with `filter_status = pending`
4. Background thread calls Claude API → updates status to `accepted` or `rejected`

**Response 201**
```json
{
  "id": 12,
  "filter_status": "pending",
  "message": "Application submitted. Screening in progress."
}
```

**Error responses**
- `400` — missing fields or non-PDF file
- `404` — job not found
- `422` — PDF text extraction failed

---

### Get application status
`GET /applications/:id`

For candidates to poll their screening result.

**Response 200**
```json
{
  "id": 12,
  "job_id": 3,
  "applicant_name": "Jane Doe",
  "applicant_email": "jane@example.com",
  "filter_status": "accepted",
  "ai_feedback": "Strong match for the role.",
  "created_at": "2025-04-01T10:30:00"
}
```
> `resume_text` is intentionally omitted from this endpoint.

---

## filter_status lifecycle

```
[submission] → pending → (Claude API) → accepted
                                      → rejected
```

---

## Error format (all endpoints)
```json
{ "error": "Human-readable message" }
```
