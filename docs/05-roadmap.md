# HireBridge — Roadmap

> Shared document. Identical copy lives in `hirebridge-web/docs/05-roadmap.md`.
> Last updated 2026-09-28.

## Principle

Five pillars built in parallel produces five half-products. Each phase below has
**exit criteria**; the next phase does not start until they pass. The order is chosen by
*value delivered per unit of infrastructure risk*, not by the order the ideas were written down.

Note that the original concept note's item 1 (automatic job posting) is scheduled **last**,
because it depends on external platforms and partnerships, while items 3 and 5 are scheduled
**first**, because they are pure data + LLM work with no external dependency and are the
two features someone would pay for on day one.

---

## Phase 0 — Foundation (week 1)

Nothing user-facing. This is the layer everything else assumes exists.

- [ ] Monorepo-adjacent structure: `hirebridge-api`, `hirebridge-web`, shared docs
- [ ] FastAPI skeleton: settings via pydantic-settings, health endpoint, structured JSON logging, request-id middleware
- [ ] Postgres + pgvector + Redis via docker-compose; Alembic wired
- [ ] ARQ worker process with one dummy job end-to-end
- [ ] Clerk auth: JWT verification dependency in FastAPI, middleware in Next.js
- [ ] Next.js App Router skeleton, Tailwind + shadcn/ui, the public/candidate/HR route groups stubbed
- [ ] CI: ruff + mypy + pytest on the API, eslint + tsc + build on the web
- [ ] One deploy each to staging (Vercel + VPS) — prove the pipeline before there is anything to lose

**Exit:** a logged-in user hits an authenticated `/me` from the web app in staging, and a queued background job writes a row.

---

## Phase 1 — The paid wedge (weeks 2–5)

Pillars **P3 (Adaptive CV)** and **P5 (HR Copilot)**. This is the smallest slice that is
independently sellable to both sides.

### Backend
- [ ] File upload → object storage, PDF/DOCX text extraction
- [ ] Resume Parser Agent → structured `candidate_profile` with stable fact IDs
- [ ] JD Parser Agent → structured `job`
- [ ] Embeddings for job and profile; pgvector indexes
- [ ] CV Tailoring Agent + **fabrication validator** (the validator ships with the agent, never after)
- [ ] PDF renderer for the tailored CV (2 templates)
- [ ] Ranking Agent: hybrid lexical + semantic + rules, with per-candidate evidence citations
- [ ] Async job pattern: 202 + job id + SSE progress

### Frontend
- [ ] Candidate: onboarding upload, profile editor, tailor-to-JD flow with **diff view**, PDF download
- [ ] Employer: create job from pasted JD, applicant list ranked with reasons, side-by-side compare, pipeline stages
- [ ] Public: job listing + job detail pages (SSG/ISR, SEO-complete)

### Exit criteria
- 3 design-partner companies have each run one real role through the ranking flow
- Precision@10 ≥ 60% measured against what the recruiter actually advanced
- Fabrication validator blocks 100% of a 30-case seeded adversarial set
- Tailored CV p95 under 90 s
- At least one recruiter says the reason text is usable without explanation from you

---

## Phase 2 — Interview Studio, text (weeks 6–8)

Pillar **P4**, without any audio infrastructure. Proves question quality and rubric
validity at a fraction of the cost.

- [ ] Question Generation Agent — JD + profile + seniority → calibrated question set
- [ ] Interview Conductor — turn-based text session, adaptive follow-ups on thin answers
- [ ] Evaluation Agent — per-answer rubric scoring, competency rollup
- [ ] Improvement Suggestion Agent — prioritized, concrete practice plan
- [ ] Session persistence + resumable sessions
- [ ] Interview report page, shareable link, PDF export
- [ ] Web: chat-style session UI with streaming, timer, progress, report view

**Exit:** 20 real candidates complete a session; ≥ 70% rate the questions "relevant to the actual job"; report generation under 60 s.

---

## Phase 3 — Voice (weeks 9–12)

Only after Phase 2's content quality is proven. Voice is a delivery channel for questions
that already work, not a fix for questions that don't.

- [ ] STT (Whisper-class) + TTS integration, turn-based
- [ ] WebSocket session transport; audio chunk upload, barge-in handling
- [ ] Audio retention policy + explicit recording consent
- [ ] Transcript alignment with the existing evaluation pipeline (same rubric, same report)
- [ ] Web: mic permission flow, waveform/state indicator, network-drop recovery
- [ ] Evaluate LiveKit before attempting real-time conversational mode

**Exit:** turn latency under 2.5 s p95; cost per 20-minute session under $0.60; a session survives a 10-second network drop without losing state.

---

## Phase 4 — Job Intelligence + distribution (weeks 13+)

Pillar **P1**, last on purpose.

- [ ] Company profile pages
- [ ] Cross-post to the employer's own LinkedIn / Facebook page via official APIs (OAuth, employer-authorized)
- [ ] Job alerts + candidate job-match feed (reverse ranking: jobs ranked for a candidate)
- [ ] Employer ATS email ingestion — forward an applications inbox into the pipeline
- [ ] **Never:** scraping third-party boards (Product Brief §8 rule 6)

---

## Phase 5 — Commercial (parallel with Phase 4)

- [ ] Billing (local gateway: bKash/SSLCommerz; Stripe for international)
- [ ] Plan limits and quota enforcement
- [ ] Per-org cost dashboard and budget ceilings
- [ ] Admin console: prompt versions, agent run inspector, cost per run
- [ ] Data retention automation, export and delete endpoints

---

## Deliberately deferred

| Item | Revisit when |
|---|---|
| Mobile apps | Web MRR is recurring and mobile traffic exceeds 60% |
| Bangla UI | A design partner asks for it in writing |
| Coding assessments | An employer says ranking alone is not enough to shortlist |
| Real-time conversational voice | Turn-based voice retains users for 3+ sessions |
| Recruiter marketplace / agency workspaces | Two agencies are paying for the Growth plan |

---

## Cadence

- Phase reviews on the phase boundary, against the exit criteria — not against a date.
- Any scope item added mid-phase must displace an item of equal size in the same phase.
- ADRs recorded in `docs/06-decisions.md` at the moment the decision is made, not retroactively.
