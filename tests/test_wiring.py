"""The app boots, and the generated contract still honours the product rules.

These assert against the OpenAPI schema rather than against intent: a capability that must
not exist is checked by its absence from the contract, which is the thing clients actually
see. Needs the full stack installed, so it lives outside tests/agents/.
"""

from __future__ import annotations

import pytest

from app.main import app
from app.workers.settings import WorkerSettings


@pytest.fixture(scope="module")
def paths() -> dict:
    return app.openapi()["paths"]


def _params(paths: dict, path: str, method: str) -> set[str]:
    op = paths.get(path, {}).get(method, {})
    return {p["name"] for p in op.get("parameters", [])}


@pytest.mark.parametrize("banned", ["min_score", "threshold", "min_composite", "score_gte"])
def test_applicant_list_cannot_filter_by_score(paths: dict, banned: str) -> None:
    """Product rule 2. The capability is absent from the contract, not merely discouraged —
    a parameter that does not exist cannot be used by a client or added by accident."""
    assert banned not in _params(paths, "/v1/jobs/{job_id}/applications", "get")


def test_applicant_list_offers_sorting(paths: dict) -> None:
    assert "sort" in _params(paths, "/v1/jobs/{job_id}/applications", "get")


def test_tailored_cv_has_an_explicit_approval_step(paths: dict) -> None:
    """Product rule 1: nothing generated reaches an employer without a human action."""
    assert "/v1/resume-versions/{version_id}/approve" in paths


@pytest.mark.parametrize(
    "path", ["/v1/runs/{run_id}", "/v1/runs/{run_id}/events"]
)
def test_async_runs_expose_both_stream_and_reconcile(paths: dict, path: str) -> None:
    """A client that reconnects must be able to ask for state; a stream alone would hang."""
    assert path in paths


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/v1/resumes/{resume_id}/tailor", "post"),
        ("/v1/jobs/{job_id}/rank", "post"),
        ("/v1/jobs", "post"),
        ("/v1/resumes", "post"),
    ],
)
def test_expensive_posts_accept_an_idempotency_key(paths: dict, path: str, method: str) -> None:
    """Re-posting one of these costs real money."""
    assert "Idempotency-Key" in _params(paths, path, method)


def test_every_agent_task_is_registered_with_the_worker() -> None:
    expected = {"parse_resume", "parse_job", "tailor_cv", "rank_job", "embed_profile"}
    assert expected <= {fn.__name__ for fn in WorkerSettings.functions}


def test_queues_are_separated() -> None:
    """A backlog of 400 CV parses must not starve a live interview session."""
    from app.workers.settings import QUEUE_GENERATE, QUEUE_INTERVIEW, QUEUE_PARSE

    assert len({QUEUE_PARSE, QUEUE_GENERATE, QUEUE_INTERVIEW}) == 3
