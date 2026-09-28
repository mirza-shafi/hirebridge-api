# System Architecture

> Scope: backend. Frontend architecture is in `hirebridge-web/docs/01-frontend-architecture.md`.
> Last updated 2026-09-28.

## 1. Topology

```
                    ┌───────────────────────────────┐
   Browser ────────▶│  hirebridge-web (Next.js)     │
                    │  Vercel · App Router          │
                    │  public SSG/ISR + authed CSR  │
                    └───────────┬───────────────────┘
                                │ HTTPS (JWT)  ·  SSE  ·  WS
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                    VPS — docker compose                      │
│                                                              │
│  ┌────────────────────┐        ┌──────────────────────────┐  │
│  │ hirebridge-api     │ enqueue│  ARQ worker(s)           │  │
│  │ FastAPI (uvicorn)  │───────▶│  agent pipelines         │  │
│  │ thin, non-blocking │◀───────│  long-running LLM work   │  │
│  └─────────┬──────────┘ status └────────────┬─────────────┘  │
│            │                                │                │
│      ┌─────▼──────────────┐      ┌──────────▼─────────────┐  │
│      │ Postgres + pgvector│      │ Redis                  │  │
│      │ system of record   │      │ queue · cache · pubsub │  │
│      └────────────────────┘      └────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
            │                    │                   │
            ▼                    ▼                   ▼
   Object storage (R2/S3)   LLM providers      STT / TTS (P3)
   CVs, generated PDFs,     tiered models      voice sessions
   interview audio
```

**Rule:** the API process never calls an LLM inside a request handler. Every model call runs in
the worker. The API validates, enqueues, and streams status. This keeps p99 request latency
independent of provider latency and makes retries free.

## 2. Components

| Component | Responsibility | Not responsible for |
|---|---|---|
| `hirebridge-web` | Rendering, auth session, optimistic UI, SEO | Any LLM call, any business rule |
| `hirebridge-api` | AuthZ, validation, persistence, enqueue, SSE/WS fan-out | Long-running work |
| ARQ worker | Agent pipelines, parsing, embedding, PDF render, scoring | HTTP concerns |
| Postgres | System of record + vector index | Ephemeral state |
| Redis | Job queue, cache, pub/sub for progress events | Durable data |
| Object storage | Files: uploads, generated PDFs, audio | Anything queryable |
| n8n | External glue only — notifications, cross-posting, CRM sync | Anything in the core request path |

**n8n boundary:** it is reached *from* the API by event, never *by* the API synchronously. If n8n
is down, hiring still works; only notifications lag.

## 3. Request patterns

### 3.1 Synchronous (fast, < 500 ms)
CRUD, listings, auth, pipeline stage changes. Plain REST.

### 3.2 Asynchronous with progress (the default for anything AI)

```
POST /v1/resumes/{id}/tailor            → 202 { run_id }
GET  /v1/runs/{run_id}/events  (SSE)    → progress events, then terminal event
GET  /v1/runs/{run_id}                  → final result (also poll-able)
```

Events: `queued → running(step, pct) → succeeded(result_ref) | failed(code, message)`.
SSE is chosen over WebSocket because the flow is one-directional, survives proxies,
and reconnects natively. WebSocket is reserved for the voice session in Phase 3.

Every mutating async endpoint accepts an `Idempotency-Key` header. Re-posting the same key
returns the original `run_id` instead of starting a second run — this matters because
double-submitting a tailor request costs real money.

### 3.3 Streaming text
Where the user watches text appear (interview turns), the worker publishes tokens to a Redis
channel and the API relays them over the same SSE connection.

## 4. Agent execution model

```
enqueue → AgentRun row (pending)
        → worker picks up
        → build context (retrieve profile facts, JD, rubric)
        → model call (tiered, structured output)
        → validate output against schema + guardrails
        → persist result + tokens + cost + latency + prompt_version
        → publish terminal event
```

Every run is a row in `agent_runs`. No agent call happens without one. That table is
simultaneously the audit log, the cost ledger, and the eval dataset.

**Retries:** 3 attempts, exponential backoff, only on transient provider errors. A *validation*
failure is not retried blindly — it retries once with the validator's complaint appended to the
prompt, then fails hard. Silent degradation is worse than an error.

**Budget ceiling:** each run carries a max-token budget from its agent config. Exceeding it aborts
the run. Each org carries a monthly ceiling; crossing it queues rather than drops, and alerts.

## 5. Model tiering

| Tier | Used for | Why |
|---|---|---|
| Small / cheap | Resume parsing, JD parsing, field extraction, embeddings | High volume, schema-constrained, low judgment |
| Mid | Ranking justifications, improvement suggestions | Needs reasoning, tolerates a cheaper model |
| Large | Question generation, interview evaluation | Quality directly visible to the user |

Model choice lives in config per agent, never hardcoded in the agent body, so a tier can be
re-benchmarked without touching pipeline code. Provider is abstracted behind one `LLMClient`
interface — assume you will switch providers at least once.

**Caching:** JD embeddings, profile embeddings, and parsed-resume results are cached by content
hash. Re-ranking the same job against the same CVs must not re-embed anything.

## 6. Data flow — the two critical paths

### 6.1 Tailor a CV
```
JD text ─▶ JD Parser ─▶ structured job ─┐
                                        ├─▶ Tailoring Agent ─▶ draft CV
profile facts (with fact_ids) ──────────┘            │
                                                      ▼
                                          Fabrication Validator
                                   (every claim → source fact_id?)
                                        pass │        │ fail
                                             ▼        ▼
                                      render PDF   retry once → hard fail
                                             │
                                             ▼
                                       diff vs base CV ─▶ user approves
```

### 6.2 Rank applicants
```
for each application:
    profile (protected fields stripped)
        ├─ lexical score  (tsvector vs JD must-have/nice-to-have terms)
        ├─ semantic score (cosine: profile embedding vs job embedding)
        └─ rules score    (years of experience, seniority band, location, work authorization)
                 │
                 ▼
     weighted composite ─▶ Justification Agent (top N only, for cost)
                 │              produces reason + evidence citations (fact_ids)
                 ▼
        ranked list, nothing removed
```

Justifications are generated only for the top N (default 25) plus any candidate the recruiter
opens. Generating 400 justifications up front wastes ~90% of the spend.

## 7. Security

- **AuthN:** Clerk issues JWTs; FastAPI verifies via JWKS, cached. No session state in the API.
- **AuthZ:** every query is scoped by `org_id` from the token. A repository layer enforces it —
  never rely on the route handler remembering. Roles: `candidate`, `recruiter`, `hiring_manager`, `org_admin`, `platform_admin`.
- **Tenant isolation:** org-scoped queries by default; Postgres RLS as a second layer for the
  application and job tables.
- **CV visibility:** an employer sees a candidate's CV only through an application to that org's
  job. There is no global CV search in v1 — a browsable CV bank is a different product with
  different consent requirements.
- **PII to providers:** name, email, phone, photo, address, and NID are stripped or tokenized
  before any scoring model call. Tailoring needs the name; scoring never does.
- **Provider retention:** zero-retention endpoints only. If a provider cannot guarantee it, it
  does not receive CV content.
- **Uploads:** magic-byte type check, 10 MB cap, AV scan, stored under an opaque key, served
  only via short-lived signed URLs.
- **Secrets:** environment-injected, never committed. Rotatable without a redeploy of the web app.

## 8. Observability

| Signal | Implementation |
|---|---|
| Logs | Structured JSON, request-id + run-id on every line, PII-scrubbed |
| LLM tracing | Langfuse (or equivalent): prompt version, inputs, outputs, tokens, cost, latency per run |
| Metrics | Per-agent p50/p95 latency, cost per run, validation-failure rate, queue depth |
| Errors | Sentry on API, worker, and web |
| Product | Ranking precision@10, tailor completion rate, interview completion rate |

**Two alerts that matter from day one:** validator failure rate above threshold (the product
rule is breaking), and cost-per-run above threshold (the unit economics are breaking).

## 9. Environments

| Env | API | Web | Data |
|---|---|---|---|
| Local | docker compose | `next dev` | seeded fixtures, fake LLM client |
| Staging | VPS, separate compose project | Vercel preview | anonymized data, real providers, low ceilings |
| Production | VPS | Vercel prod | real, backed up nightly + PITR |

A `FakeLLMClient` returning fixtures is required for tests and local work. Tests never call a
provider.

## 10. Deployment

- Web: Vercel, on push to `main`.
- API: GitHub Actions builds an image → registry → pull and `docker compose up -d` on the VPS.
- Migrations run as a pre-start step, and must be backward compatible with the running version —
  expand/contract, never a destructive migration in one deploy.
- Worker deploys independently of the API; in-flight jobs drain on SIGTERM before exit.

## 11. Scaling notes

The first bottleneck will be worker concurrency against provider rate limits, not Postgres.
Scale workers horizontally; they are stateless. Split queues (`parse`, `generate`, `interview`)
so a queue of 400 CV parses cannot starve a live interview session — this is the one piece of
future-proofing worth doing in Phase 1, because retrofitting queue separation is invasive.


## 12. Where pure logic lives

An agent class needs a database session and the run store, so importing it pulls in
SQLAlchemy, Redis and a populated environment. The transformations *around* it — schema to
column mapping, score to prompt text, diff computation, validators — need none of that, and
they are where the bugs actually are.

So: **anything that only transforms data lives in its own module, never inside the class
that needs a session.**

| Pure module | Agent module |
|---|---|
| `jd_parser/mapping.py` | `jd_parser/agent.py` |
| `resume_parser/mapping.py` | `resume_parser/agent.py` |
| `cv_tailor/source_facts.py` | `cv_tailor/agent.py` |
| `ranker/rendering.py` | `ranker/agent.py` |
| `validators/fabrication.py`, `services/ranking.py`, `services/resume_diff.py` | — |

The payoff is concrete: the release-gate suites and every mapping test run with nothing but
`pydantic`, `httpx` and `pytest` installed — no database, no Redis, no environment. A gate
that is hard to run is a gate that gets skipped.

Corollaries:
- Plain enums go in `app/schemas/enums.py`, which imports nothing from the framework.
- Agent exceptions go in `app/agents/errors.py` for the same reason.
- A test that genuinely needs a model class (`tests/test_models.py`) lives outside
  `tests/agents/`.
