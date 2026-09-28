# HireBridge API — Progress

> Execution tracker for this repo. Companion file: `hirebridge-web/PROGRESS.md`.
> **What** and **why** live in `docs/` — this file tracks only **where we are**.
> Last updated: 2026-09-28

## How to use

| Marker | Meaning |
|---|---|
| `[ ]` | pending |
| `[x]` | done |
| `[~]` | in progress |
| `[!]` | blocked — see the note beside it |

Rules: a task is only `[x]` when it is merged and working in staging, not when the code is written.
A phase does not start until the previous phase's **exit gate** is fully checked.
Adding a task mid-phase means removing one of equal size from the same phase.

Recount any time with:

```sh
echo "pending: $(grep -c '^- \[ \]' PROGRESS.md)  done: $(grep -c '^- \[x\]' PROGRESS.md)"
```

## Summary

| Phase | Tasks | Done | Pending |
|---|---:|---:|---:|
| Phase 0 — Foundation | 46 | 44 | 2 |
| Phase 1 — CV tailoring + HR ranking (the paid wedge) | 93 | 38 | 55 |
| Phase 2 — Interview Studio (text) | 24 | 0 | 24 |
| Phase 3 — Voice | 12 | 0 | 12 |
| Phase 4 — Job Intelligence & distribution | 8 | 0 | 8 |
| Phase 5 — Commercial & operations | 8 | 0 | 8 |
| Cross-cutting (ongoing — never marked done) | 9 | 0 | 9 |
| Blocked / needs a decision | 8 | 1 | 7 |
| **Total** | **208** | **83** | **125** |

**Current position: Phase 0 44/2 · Phase 1 38/55. Candidate side is built end to end (parse → embed → tailor → validate → diff). Next: ranking, then the API routes that expose all of it.**

---

## Phase 0 — Foundation

Nothing user-facing. Everything below assumes this layer exists.

### Repo & tooling
- [x] `pyproject.toml` (uv or poetry), Python 3.12 pinned
- [x] ruff + mypy strict config
- [x] pre-commit hooks (ruff, mypy, trailing whitespace)
- [x] Package layout: `app/{api,agents,workers,db,services,schemas,core}`
- [x] pytest + coverage config
- [x] `FakeLLMClient` fixture — tests never call a provider

### Config & runtime
- [x] `Settings` via pydantic-settings, validated at boot (fail fast on missing env)
- [x] `.env.example` covering every variable
- [x] Structured JSON logging with request-id + run-id on every line
- [x] Request-id middleware
- [x] Exception handlers emitting RFC 9457 problem details
- [x] `/healthz` (liveness) and `/readyz` (db + redis + provider reachability)
- [x] PII scrubbing filter on the log formatter

### Database
- [x] `docker-compose.yml`: postgres 16 + pgvector, redis
- [x] SQLAlchemy async engine + session dependency
- [x] Alembic init + first migration
- [x] Base model mixin: UUIDv7 pk, `created_at`, `updated_at`
- [x] `organizations` table
- [x] `users` table (mirrors Clerk)
- [x] `memberships` table with roles
- [x] Repository base class enforcing `org_id` scoping
- [x] `audit_logs` table (append-only)

### Queue & async infrastructure
- [x] ARQ worker process + settings
- [x] Separate queues: `parse`, `generate`, `interview` (do this now, not later)
- [x] `agent_runs` table
- [x] `AgentRun` lifecycle helper — no model call happens without a row
- [x] Redis pub/sub channel per run
- [x] SSE endpoint `GET /v1/runs/{id}/events`
- [x] `GET /v1/runs/{id}` reconciliation endpoint
- [x] `Idempotency-Key` middleware + key storage
- [x] Token budget enforcement + `aborted_budget` status
- [x] Retry policy: 3 transient, 1 validation-repair, then hard fail
- [x] Graceful worker shutdown — drain in-flight jobs on SIGTERM

### Auth
- [x] Clerk JWKS verification dependency (cached keys)
- [x] `current_user` / `current_org` dependencies
- [x] Role enforcement (`candidate`, `recruiter`, `hiring_manager`, `org_admin`, `platform_admin`)
- [x] Clerk webhook → local user/org sync
- [x] Cross-tenant access returns 404, never 403

### CI/CD
- [x] GitHub Actions: ruff + mypy + pytest on PR
- [x] Dockerfile (single image, api and worker entrypoints)
- [x] Staging compose project on the VPS
- [x] Deploy workflow: build → registry → pull → `compose up -d`
- [x] Alembic migration as a pre-start step
- [x] Sentry wired on api and worker

### Phase 0 exit gate
- [ ] Authenticated `GET /v1/me` succeeds from the web app in staging
- [ ] A queued dummy job writes a row and emits a terminal SSE event

## Phase 1 — CV tailoring + HR ranking (the paid wedge)

### Files & storage
- [x] `files` table
- [ ] S3/R2 client
- [ ] `POST /v1/files/upload-url` — signed, direct-to-storage
- [ ] Magic-byte type validation + 10 MB cap
- [ ] SHA-256 checksum (doubles as the parse cache key)
- [ ] AV scan hook + `av_scan_status` gate
- [ ] Signed download URLs, short TTL

### Text extraction
- [x] PDF extraction, layout-aware (handles two-column CVs)
- [x] DOCX extraction
- [ ] OCR fallback for scanned image CVs
- [x] Low-yield heuristic → surface "we only found N items" instead of a sparse profile
- [x] Header/footer contamination stripping

### Resume Parser Agent
- [ ] `candidate_profiles` table
- [ ] `profile_facts` table with addressable `fact_id` and `bullet_id`
- [x] `ParsedProfile` schema
- [x] Prompt v1 + agent implementation
- [x] Date normalizer for local formats (`Jan'23-now`, `01/2023 – Present`, `2023-current`)
- [x] Bullet splitting with stable bullet IDs
- [x] Confidence scoring + `needs_review` below 0.7
- [ ] Parse cache keyed on file checksum
- [ ] Eval: 100 anonymized CVs, ≥ 0.92 precision on experience + education

### JD Parser Agent
- [x] `jobs` table + `description_structured` JSONB
- [x] `StructuredJD` schema
- [x] Prompt v1 + agent implementation
- [x] Canonical skill vocabulary + normalizer (`Next.js` → `nextjs`)
- [x] must / nice classification, defaulting to `nice` when unsignalled
- [x] Seniority inference from responsibilities, not just the title
- [x] Discriminatory-phrasing red-flag detection
- [ ] Eval: 50 JDs, ≥ 0.85 agreement on the must/nice split

### Embeddings & search
- [x] Embedding client, model pinned, dimension 1536 recorded per row
- [ ] Profile embedding job
- [ ] Job embedding job
- [x] pgvector HNSW indexes (`vector_cosine_ops`)
- [x] `search_vector` generated columns + GIN indexes
- [x] Embedding cache by content hash
- [ ] Backfill command for an embedding-model change

### CV Tailoring Agent
- [x] `resumes` + `resume_versions` tables
- [x] `TailoredResume` schema with per-line `source_fact_ids`
- [x] Prompt v1 + agent implementation
- [x] Diff computation: base vs tailored, line-level with status
- [ ] `POST /v1/resume-versions/{id}/approve`
- [ ] Enforce approval before a version can attach to an application

### Fabrication Validator (release gate)
- [x] Structural check: every output line cites ≥ 1 `fact_id`
- [x] Ownership check: cited facts exist and belong to this profile
- [x] Numeric claim extraction + set comparison against source facts
- [x] Date range check against the source fact
- [x] Skill/tool vocabulary diff against the profile corpus
- [x] Scope-escalation verb tier comparison ("assisted" → "led")
- [x] Entailment check (small model): does the source entail the rewrite?
- [x] Repair retry: one attempt with the specific complaint appended
- [x] `passed_with_warnings` path → per-line acknowledgement required
- [x] Failed validation never renders a PDF
- [x] **30-case adversarial fixture set — must block 100%**

### PDF rendering
- [ ] HTML → PDF renderer
- [ ] Template 1 (modern)
- [ ] Template 2 (classic)
- [ ] ATS-safe output: selectable text, no tables carrying content
- [ ] Store as a file + serve via signed URL

### Ranking
- [ ] `applications` table with `profile_snapshot`
- [ ] `application_scores` table, versioned not overwritten
- [ ] `application_events` audit table
- [ ] Lexical score: `ts_rank` against must/nice terms
- [ ] Semantic score: cosine against the job embedding
- [ ] Rules score: years, seniority band, location, work authorization
- [ ] Composite with per-job weights stored on the score row
- [x] Protected-attribute allowlist payload builder
- [x] **Allowlist unit test — release gate**
- [ ] Ranking Justification Agent, top 25 lazy generation
- [ ] `POST /v1/applications/{id}/justify` for on-demand justification
- [ ] Evidence citations linking each matched requirement to a `fact_id`
- [ ] Progressive rank run emitting SSE progress ("ranked 240 of 412")
- [ ] Rank failure falls back to recency order with an explicit flag

### Endpoints
- [ ] Candidate profile + facts CRUD + verify
- [ ] Profile completeness endpoint
- [ ] Resumes, versions, tailor, diff, approve, pdf
- [ ] Applications: create, list, withdraw
- [ ] Tailor accepts a raw JD string (works with jobs not on HireBridge)
- [ ] Jobs: create, parse, edit, publish, pause, close
- [ ] Publish blocked while red flags are unresolved
- [ ] Applicants list — **no score-threshold parameter, by design**
- [ ] Stage change, notes, events
- [ ] Compare endpoint (2–4 candidates)
- [ ] Public job endpoints + cache headers
- [ ] Org usage endpoint

### Notifications
- [ ] Transactional email provider integration
- [ ] 5 templates per the notification table in `03-ux-flows.md`
- [ ] Candidate emails never expose a score or rank
- [ ] n8n event emission (fire-and-forget, never in the request path)

### Phase 1 exit gate
- [ ] 3 design-partner companies each ran one real role through ranking
- [ ] Precision@10 ≥ 60% against what the recruiter actually advanced
- [ ] Fabrication validator blocks 30/30 adversarial cases
- [ ] Tailored CV p95 under 90 s
- [ ] One recruiter confirms the reason text is usable without explanation

## Phase 2 — Interview Studio (text)

- [ ] `interview_sessions` table with frozen `question_set`
- [ ] `interview_turns` table
- [ ] `interview_reports` table
- [ ] `QuestionSet` schema with `competency`, `expected_signals`, `followup_triggers`
- [ ] Question Generation Agent + prompt v1
- [ ] Composition ratio enforcement (40 / 25 / 25 / 10)
- [ ] At least 2 questions anchored to a specific profile fact
- [ ] Interview Conductor Agent + turn loop
- [ ] Follow-up trigger rules, max one per question
- [ ] Turn budget cap per session
- [ ] Resume from `current_index` with the frozen question set
- [ ] Abandoned session recoverable for 7 days
- [ ] Evaluation Agent + rubric v1 (5 competencies, 1–5)
- [ ] Evidence-quote requirement enforced on every score
- [ ] Identity fields excluded from the evaluation payload
- [ ] Eval case: no penalty for grammar, accent, or non-native phrasing
- [ ] Unanswered question scores null, not zero
- [ ] Improvement Suggestion Agent, max 5 prioritized items
- [ ] `example_rewrite` built only from what the candidate actually said
- [ ] Report assembly + `share_token` (revocable)
- [ ] Report PDF export
- [ ] Streaming turn responses over SSE
- [ ] Eval: 20 JD/profile pairs, ≥ 70% rated relevant
- [ ] Report generation under 60 s

## Phase 3 — Voice

- [ ] STT integration + chunked audio upload
- [ ] TTS integration + audio cache for repeated question text
- [ ] `WS /v1/interviews/{id}/voice` with the documented frame protocol
- [ ] Barge-in handling
- [ ] Silence detection → "still there?" after 20 s
- [ ] Low-confidence transcript → ask for a repeat rather than scoring noise
- [ ] Recording consent capture + storage
- [ ] Audio retention job (30-day default)
- [ ] Session survives a 10 s network drop
- [ ] Latency instrumentation, p95 turn under 2.5 s
- [ ] Cost per 20-minute session tracked, under $0.60
- [ ] LiveKit evaluation spike before attempting real-time mode

## Phase 4 — Job Intelligence & distribution

- [ ] Company profile endpoints
- [ ] Employer OAuth for LinkedIn / Facebook page posting
- [ ] Cross-post a job to the employer's own channel
- [ ] Reverse ranking: rank jobs for a candidate
- [ ] Job alerts scheduler
- [ ] Email ingestion of applications from an employer inbox
- [ ] Outbound webhooks with HMAC-SHA256 signing
- [ ] Webhook retry with exponential backoff, at-least-once

## Phase 5 — Commercial & operations

- [ ] Billing: bKash / SSLCommerz + Stripe for international
- [ ] Plan limits + quota enforcement middleware
- [ ] Per-org monthly budget ceiling; crossing it queues rather than drops
- [ ] Admin console: agent run inspector
- [ ] Prompt version management UI
- [ ] Data export endpoint (candidate owns their data)
- [ ] Account deletion: cascade, with application anonymization
- [ ] Retention automation job

## Cross-cutting (ongoing — never marked done)

- [ ] Langfuse tracing on every agent run
- [ ] Cost-per-run dashboard
- [ ] Alert: validator failure rate above threshold
- [ ] Alert: cost per run above threshold
- [ ] Postgres RLS on `jobs`, `applications`, `application_scores`
- [ ] Zero-retention confirmed with every LLM provider in use
- [ ] Nightly backup + PITR, verified by an actual restore drill
- [ ] Load test the rank path at 500 applicants
- [ ] Agent eval suites run in CI, regression blocks merge

## Blocked / needs a decision

- [x] Choose LLM provider(s) — both implemented, selected by `LLM_PROVIDER` (ADR-0007)
- [ ] Confirm zero-retention endpoints with whichever provider you enable
- [ ] Fill in `config/model_pricing.json` for the models you configure
- [ ] Choose object storage: Cloudflare R2 vs AWS S3
- [ ] Choose transactional email provider
- [ ] Decide the OCR approach for scanned CVs
- [ ] Run the 100-CV sample study (open question 4 in the product brief)
- [ ] Confirm whether design partners want the full pipeline or ranking only
