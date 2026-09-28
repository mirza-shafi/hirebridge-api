# Architecture Decision Records

> Shared document. One entry per non-obvious decision, written when it is made.
> Format: context → decision → consequences. Never delete an entry; supersede it.

---

## ADR-0001 — Two repositories, not a monorepo
**Date:** 2026-09-28 · **Status:** Accepted

**Context.** API is Python, web is TypeScript. A monorepo (Turborepo/Nx) would share types and CI, but adds tooling weight for a solo developer.

**Decision.** Two sibling folders/repos: `hirebridge-api`, `hirebridge-web`. Types are shared by generating a TypeScript client from FastAPI's OpenAPI schema, not by a shared package.

**Consequences.** Independent deploys (Vercel vs VPS) stay simple. Cost: the product docs must be kept in sync manually — do it in the same commit. Revisit if a third surface (mobile, admin) appears.

---

## ADR-0002 — FastAPI over Django for the backend
**Date:** 2026-09-28 · **Status:** Accepted

**Context.** The HR side is ATS-shaped CRUD, where Django's admin, auth, and permissions would save weeks. The AI side is streaming, long-running, and concurrent, where Django's sync-first design fights back.

**Decision.** FastAPI, with the Django-shaped gap filled by buying rather than building: Clerk for auth/orgs/roles, SQLAlchemy + Alembic for the ORM, and a purpose-built internal admin later rather than a generic one.

**Consequences.** Native async for SSE streaming and WebSocket voice. No free admin UI — Phase 5 must budget for one. Do not hand-roll auth; that is the decision's whole premise.

---

## ADR-0003 — Postgres + pgvector as the only datastore
**Date:** 2026-09-28 · **Status:** Accepted

**Context.** Ranking needs vector similarity. A dedicated vector DB (Qdrant, Weaviate) is the reflex choice.

**Decision.** pgvector inside the primary Postgres until vector count exceeds ~1M or p95 search exceeds 200 ms.

**Consequences.** One database to back up, one transaction boundary — a job and its embedding are written atomically. Hybrid search uses Postgres `tsvector` alongside vectors, no second system to keep consistent. Migration path to Qdrant stays open behind a repository interface.

---

## ADR-0004 — Ranking sorts, never filters
**Date:** 2026-09-28 · **Status:** Accepted

**Context.** Auto-rejecting low scores is the obvious way to save recruiter time and the obvious way to cause discriminatory outcomes at scale.

**Decision.** The recruiter always sees 100% of applicants. AI controls order and attaches a reason; it never removes, hides, or auto-rejects. Every stage change is attributed to a named user and audit-logged.

**Consequences.** Slightly less "magic" in the demo. Enormously smaller legal surface, and the audit log is a feature when an employer asks how a decision was made. This constraint is load-bearing — see Product Brief §8.

---

## ADR-0005 — Text-first interviews, voice deferred to Phase 3
**Date:** 2026-09-28 · **Status:** Accepted

**Context.** Voice is the feature people react to in a demo. It is also the most expensive and operationally fragile part of the concept.

**Decision.** Ship the full question → conduct → evaluate → improve pipeline in text first. Add STT/TTS only once question relevance and rubric validity are measured.

**Consequences.** Voice becomes a transport swap over a proven pipeline rather than a rewrite. If interview content turns out to be weak, that is discovered for near-zero cost.

---

## ADR-0006 — No third-party job scraping, ever
**Date:** 2026-09-28 · **Status:** Accepted

**Context.** Seeding the board by scraping LinkedIn/BDJobs would solve the cold-start problem instantly.

**Decision.** Job content enters only from the employer who owns it or via an official, authorized API.

**Consequences.** Slower supply growth; the candidate-side tools (tailoring, interview) are built to work against *any* pasted JD so they retain value with an empty board. Avoids ToS breach, IP bans, and an unfixable diligence problem later.

---

## ADR-0007 — Both LLM providers implemented, chosen by environment
**Date:** 2026-09-28 · **Status:** Accepted

**Context.** Picking a provider was blocking Phase 1: the parser agents cannot be written
against an interface that has no implementation. But the choice depends on pricing, latency
from Dhaka, and payment access — none of which should hold up building the agents.

**Decision.** Implement `LLMClient` for both Anthropic (structured output via a forced tool
call) and OpenAI (strict `json_schema`), selected by `LLM_PROVIDER`. Both are built on httpx
rather than a vendor SDK, so provider errors map onto `TransientProviderError` in one place
and the runner's retry policy behaves identically either way. Pricing lives in
`config/model_pricing.json`, not in source.

**Consequences.** The provider is now an environment change, which also makes A/B comparison
on the same eval suite possible. Cost: two adapters to maintain, and `strictify()` exists
solely to reshape Pydantic schemas for OpenAI's strict mode. An unpriced model reports $0
with a warning rather than a guess, so the gap is visible in the cost dashboard.
