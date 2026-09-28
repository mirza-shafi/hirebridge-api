from __future__ import annotations

import pytest

from app.agents.ranker.rendering import render_comparison, render_scores
from app.services.ranking import cover_requirements, rules_score, score
from app.services.scoring_payload import ScoringPayloadError, assert_allowlisted


def _result(lexical: float, semantic: float, held: list[str], must: list[str], years: float):
    cov = cover_requirements(held, must_have=must, nice_to_have=[])
    breakdown = rules_score(years_experience=years, min_years=3, max_years=None, coverage=cov)
    return score(lexical=lexical, semantic=semantic, coverage=cov, breakdown=breakdown)


def test_rendered_scores_name_matched_and_missing_requirements() -> None:
    rendered = render_scores(_result(70, 80, ["python"], ["python", "kubernetes"], 4))
    assert "Required skills evidenced: python" in rendered
    assert "Required skills with no evidence: kubernetes" in rendered
    assert "Composite:" in rendered


def test_rendered_scores_carry_the_weights_so_the_agent_can_explain_them() -> None:
    rendered = render_scores(_result(70, 80, ["python"], ["python"], 4))
    assert "weight 0.45" in rendered


def test_close_candidates_produce_a_tie_instruction() -> None:
    a = _result(80, 80, ["python"], ["python"], 5)
    b = _result(79, 79, ["python"], ["python"], 5)
    comparison = render_comparison(a, b)
    assert "effectively a tie" in comparison
    assert "Say so in the summary" in comparison


def test_distant_candidates_produce_no_comparison_noise() -> None:
    a = _result(95, 95, ["python"], ["python"], 8)
    b = _result(10, 10, [], ["python"], 0)
    assert render_comparison(a, b) == ""
    assert render_comparison(a, None) == ""


def test_a_contaminated_payload_is_refused_at_the_agent_boundary() -> None:
    """The last place a protected attribute could reach a model and shape a hiring
    decision. The payload builder already blocks it; this is the second lock."""
    with pytest.raises(ScoringPayloadError):
        assert_allowlisted({"skills": ["python"], "full_name": "Someone", "age": 24})
