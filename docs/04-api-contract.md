# API Contract

> REST over HTTPS, JSON. Base: `/v1`. OpenAPI served at `/openapi.json`; the web client is
> generated from it, so the schema is the contract.
> Last updated 2026-09-28.

## 1. Conventions

**Auth.** `Authorization: Bearer <clerk_jwt>` on everything except public job reads.
The token carries `sub` (user), `org_id`, and `role`.

**Errors.** RFC 9457 problem details:
```json
{
  "type": "https://hirebridge.dev/errors/validation-failed",
  "title": "Validation failed",
  "status": 422,
  "detail": "must_have_skills cannot be empty for a published job",
  "instance": "/v1/jobs/018f.../publish",
  "errors": [{ "field": "must_have_skills", "code": "empty" }],
  "request_id": "req_018f..."
}
```

**Pagination.** Cursor-based: `?limit=25&cursor=<opaque>` → `{ "data": [...], "next_cursor": "..."|null }`.
Offset pagination is not offered — applicant lists reorder as scores land.

**Idempotency.** `Idempotency-Key` header required on every POST that costs money
(tailor, rank, interview start). Same key → same `run_id`, no second charge.

**Rate limits.** Per-user and per-org token buckets. `429` returns `Retry-After`.

**Versioning.** Path-versioned. Additive changes only within `/v1`; breaking changes open `/v2`.

---

## 2. Async job pattern

Every expensive operation returns `202` with a run handle.

```http
POST /v1/resumes/{resume_id}/tailor
Idempotency-Key: 9f2c...
{ "job_id": "018f...", "template": "modern" }

202 Accepted
{ "run_id": "018f...", "status": "queued", "poll": "/v1/runs/018f...", "events": "/v1/runs/018f.../events" }
```

```http
GET /v1/runs/{run_id}/events        # text/event-stream
event: progress
data: {"step":"retrieving_profile","pct":15}

event: progress
data: {"step":"generating","pct":55}

event: progress
data: {"step":"validating","pct":85}

event: succeeded
data: {"resume_version_id":"018f...","validator_status":"passed"}
```

Terminal events: `succeeded`, `failed` (`{code, message}`), `aborted_budget`.
If the client disconnects, work continues; `GET /v1/runs/{run_id}` returns the final state.

---

## 3. Candidate endpoints

### Profile
```
GET    /v1/me/profile
PATCH  /v1/me/profile
GET    /v1/me/profile/facts                 ?kind=experience
POST   /v1/me/profile/facts
PATCH  /v1/me/profile/facts/{fact_id}
DELETE /v1/me/profile/facts/{fact_id}
POST   /v1/me/profile/facts/{fact_id}/verify     # confirm a parsed fact
GET    /v1/me/profile/completeness
```

### Resumes
```
POST   /v1/files/upload-url                 → { upload_url, file_id }   (signed, direct-to-storage)
POST   /v1/resumes                          { file_id, label }  → 202 parse run
GET    /v1/resumes
GET    /v1/resumes/{id}
GET    /v1/resumes/{id}/versions
POST   /v1/resumes/{id}/tailor              { job_id | job_description_raw, template } → 202
GET    /v1/resume-versions/{id}
GET    /v1/resume-versions/{id}/diff        → base vs tailored, line-level, with citations
POST   /v1/resume-versions/{id}/approve     # required before attaching to an application
GET    /v1/resume-versions/{id}/pdf         → 302 to a signed URL
DELETE /v1/resume-versions/{id}
```

`tailor` accepts a raw JD string so the candidate product works against jobs that are not on
HireBridge — the cold-start hedge from the Product Brief.

**Diff response shape**
```json
{
  "sections": [{
    "name": "experience",
    "lines": [{
      "line_id": "l12",
      "status": "modified",
      "base": "Worked on a chatbot for customer support",
      "tailored": "Built a production RAG chatbot handling customer support queries",
      "source_fact_ids": ["018f...#b1"],
      "validator": "passed"
    }]
  }],
  "summary": { "added": 0, "modified": 7, "removed": 3, "reordered": 4 }
}
```
`added` is expected to be 0 for content lines — a non-zero value means new content appeared
and is a signal to inspect the validator.

### Applications
```
GET    /v1/me/applications                  ?stage=
POST   /v1/applications                     { job_id, resume_version_id, cover_note }
GET    /v1/applications/{id}
POST   /v1/applications/{id}/withdraw
```
`422` if the `resume_version_id` is not approved, or does not belong to the caller.

### Interviews
```
POST   /v1/interviews                       { job_id | job_description_raw, mode } → 202 (question gen)
GET    /v1/interviews/{id}
POST   /v1/interviews/{id}/start
GET    /v1/interviews/{id}/turns
POST   /v1/interviews/{id}/answer           { turn_id, text } → next turn (streamed)
POST   /v1/interviews/{id}/complete         → 202 (evaluation run)
GET    /v1/interviews/{id}/report
POST   /v1/interviews/{id}/report/share     → { share_token, url }
DELETE /v1/interviews/{id}/report/share
GET    /v1/interviews/{id}/report/pdf
WS     /v1/interviews/{id}/voice            # Phase 3
```

**Voice frames (Phase 3)**
```
→ { "type": "audio_chunk", "seq": 1, "data": "<base64 pcm16>" }
→ { "type": "turn_end" }
← { "type": "transcript", "text": "...", "confidence": 0.94 }
← { "type": "question_audio", "seq": 1, "data": "<base64>" }
← { "type": "state", "value": "listening" | "thinking" | "speaking" }
```

---

## 4. Employer endpoints

### Organization
```
GET    /v1/orgs/{id}
PATCH  /v1/orgs/{id}
GET    /v1/orgs/{id}/members
POST   /v1/orgs/{id}/invites
DELETE /v1/orgs/{id}/members/{user_id}
GET    /v1/orgs/{id}/usage                  → tokens, cost, quota remaining
```

### Jobs
```
POST   /v1/jobs                             { description_raw } → 202 (JD parse)
GET    /v1/jobs                             ?status=            (org-scoped)
GET    /v1/jobs/{id}
PATCH  /v1/jobs/{id}                        # edit the structured fields the parser produced
POST   /v1/jobs/{id}/publish                # 422 if red_flags unresolved
POST   /v1/jobs/{id}/pause
POST   /v1/jobs/{id}/close
GET    /v1/jobs/{id}/stats
```

Publishing is blocked while `description_structured.red_flags` contains unacknowledged
discriminatory phrasing; the employer must edit or explicitly dismiss each flag.

### Applicants & ranking
```
GET    /v1/jobs/{id}/applications           ?sort=rank|recent&stage=&limit=&cursor=
POST   /v1/jobs/{id}/rank                   { weights? } → 202 (scores all, justifies top N)
GET    /v1/applications/{id}/score
POST   /v1/applications/{id}/justify        → 202 (on-demand for a candidate outside top N)
PATCH  /v1/applications/{id}/stage          { stage, note }
POST   /v1/applications/{id}/notes
GET    /v1/applications/{id}/events         # audit trail
POST   /v1/jobs/{id}/compare                { application_ids: [...] } → side-by-side
```

`GET /v1/jobs/{id}/applications` **always returns every applicant**. `sort=rank` changes order
only. There is no `min_score` filter parameter, by design — Product Brief §8 rule 2, enforced by
the absence of the capability rather than by policy.

**Applicant list item**
```json
{
  "application_id": "018f...",
  "candidate": { "display_name": "R. Hasan", "headline": "Backend Developer · 2y" },
  "stage": "new",
  "score": {
    "composite": 82.4,
    "lexical": 71.0, "semantic": 88.2, "rules": 80.0,
    "justification": "Strong overlap on Python, FastAPI and vector search from two production projects. Meets the 2-year minimum. No Kubernetes experience found, which the JD lists as a must-have.",
    "matched": [{ "requirement": "FastAPI", "fact_id": "018f...#b3" }],
    "missing": ["Kubernetes"],
    "scoring_version": 3
  },
  "applied_at": "2026-09-27T10:14:00Z"
}
```

---

## 5. Public endpoints (no auth)

```
GET /v1/public/jobs                 ?q=&location=&skills=&seniority=&work_mode=&cursor=
GET /v1/public/jobs/{slug}
GET /v1/public/orgs/{slug}
GET /v1/public/reports/{share_token}
```
Cached at the edge. These back the SSG/ISR pages in the web app and are the SEO surface.

---

## 6. Runs & system

```
GET /v1/runs/{run_id}
GET /v1/runs/{run_id}/events        # SSE
GET /v1/me/runs                     ?agent=&status=
GET /healthz                        # liveness
GET /readyz                         # db + redis + provider reachability
```

---

## 7. Status codes

| Code | Used for |
|---|---|
| 200 | Successful read or synchronous write |
| 201 | Resource created synchronously |
| 202 | Async work accepted — body carries `run_id` |
| 204 | Delete succeeded |
| 400 | Malformed request |
| 401 | Missing or invalid token |
| 403 | Authenticated but not permitted (wrong org, wrong role) |
| 404 | Not found **or** not visible to this tenant — never distinguish the two |
| 409 | Conflict (duplicate application, stage transition not allowed) |
| 422 | Semantic validation failure, including `validator_status=failed` |
| 429 | Rate or quota limit — `Retry-After` set |
| 503 | Provider unavailable, queue saturated |

`404` for cross-tenant access is deliberate: `403` would confirm the resource exists.

---

## 8. Webhooks (outbound, Phase 4)

For employer integrations and n8n:
```
application.created · application.stage_changed · job.published
interview.completed · rank.completed
```
Signed with HMAC-SHA256 in `X-HireBridge-Signature`, 5 retries with exponential backoff,
at-least-once delivery — consumers must be idempotent on `event_id`.
