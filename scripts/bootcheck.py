"""Boot the app and assert the wiring. No database needed — imports and route table only."""
import os, sys

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CLERK_ISSUER", "https://test.clerk.accounts.dev")
os.environ.setdefault("ENVIRONMENT", "local")

from app.main import app                          # noqa: E402
from app.workers.settings import WorkerSettings   # noqa: E402

schema = app.openapi()
paths = schema["paths"]

print(f"--- {sum(len(ops) for ops in paths.values())} operations across {len(paths)} paths ---")
for path in sorted(paths):
    methods = ",".join(sorted(m.upper() for m in paths[path]))
    print(f"  {methods:22} {path}")

print("\n--- worker functions ---")
for fn in WorkerSettings.functions:
    print(f"  {fn.__name__}")
print(f"  queues: {WorkerSettings.queue_name}")

failures = []

# Product rule 2: ranking sorts, it never filters. Assert against the generated contract,
# not against intent — the capability must be absent, not merely discouraged.
applicants = paths.get("/v1/jobs/{job_id}/applications", {}).get("get", {})
params = {p["name"] for p in applicants.get("parameters", [])}
for banned in ("min_score", "threshold", "min_composite", "score_gte"):
    if banned in params:
        failures.append(f"applicant list exposes {banned!r} — ranking must never filter")
if "sort" not in params:
    failures.append("applicant list has no sort parameter")

# Product rule 1: nothing generated reaches an employer without explicit approval.
if "/v1/resume-versions/{version_id}/approve" not in paths:
    failures.append("no explicit approval endpoint for a tailored CV")

# Async runs need both a stream and a reconcile endpoint, or a reconnecting client hangs.
for path in ("/v1/runs/{run_id}/events", "/v1/runs/{run_id}"):
    if path not in paths:
        failures.append(f"missing {path}")

expected = {"parse_resume", "parse_job", "tailor_cv", "rank_job", "embed_profile"}
actual = {fn.__name__ for fn in WorkerSettings.functions}
if missing := expected - actual:
    failures.append(f"worker is missing tasks: {sorted(missing)}")

# Every expensive POST must accept an idempotency key — re-posting costs real money.
for path, method in (
    ("/v1/resumes/{resume_id}/tailor", "post"),
    ("/v1/jobs/{job_id}/rank", "post"),
    ("/v1/jobs", "post"),
):
    op = paths.get(path, {}).get(method, {})
    names = {p["name"] for p in op.get("parameters", [])}
    if "Idempotency-Key" not in names:
        failures.append(f"{method.upper()} {path} does not accept Idempotency-Key")

print()
if failures:
    for f in failures:
        print(f"  FAIL  {f}")
    sys.exit(1)
print("  All wiring assertions passed.")
