# hirebridge-api

Backend for HireBridge — FastAPI + ARQ workers + Postgres/pgvector + Redis.

## Progress

[`PROGRESS.md`](PROGRESS.md) — the task tracker. Start there to see what is done and what is next.

## Documentation

| Doc | Read it for |
|---|---|
| [`docs/00-product-brief.md`](docs/00-product-brief.md) | What we are building and why. **Start here.** |
| [`docs/01-architecture.md`](docs/01-architecture.md) | System topology, request patterns, agent execution, security |
| [`docs/02-data-model.md`](docs/02-data-model.md) | Tables, ranking SQL, protected-attribute exclusion, retention |
| [`docs/03-agent-specs.md`](docs/03-agent-specs.md) | Every agent: contract, guardrails, evals |
| [`docs/04-api-contract.md`](docs/04-api-contract.md) | Endpoints, async run pattern, error shapes |
| [`docs/05-roadmap.md`](docs/05-roadmap.md) | Phases and exit criteria |
| [`docs/06-decisions.md`](docs/06-decisions.md) | ADRs — why things are the way they are |

`00`, `05`, and `06` are shared with `hirebridge-web/docs/`. Edit one, copy to the other in
the same commit.

## Rules that are not negotiable

1. No LLM call inside a request handler — it runs in the worker.
2. No model call without an `agent_runs` row.
3. The CV tailoring agent ships with its fabrication validator, never without.
4. Scoring inputs come from an allowlist; protected attributes never reach a model.
5. Ranking sorts, it never filters. There is no threshold parameter and there will not be one.

See `docs/00-product-brief.md` §8 for the full list.

## Stack

FastAPI · ARQ · Postgres 16 + pgvector · Redis · SQLAlchemy + Alembic · Clerk (auth) ·
S3-compatible object storage · pydantic-settings · ruff + mypy + pytest

## Status

Pre-Phase 0. Docs first, then the skeleton — see `docs/05-roadmap.md`.
