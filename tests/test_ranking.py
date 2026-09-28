from __future__ import annotations

import pytest

from app.services.ranking import (
    CLOSE_CALL_MARGIN,
    RankingWeights,
    cover_requirements,
    rank,
    rules_score,
    score,
    similarity_to_score,
)


def _coverage(held: list[str], must: list[str], nice: list[str] | None = None):
    return cover_requirements(held, must_have=must, nice_to_have=nice or [])


# --- requirement coverage ---------------------------------------------------

def test_coverage_matches_across_spellings() -> None:
    """The whole point of canonicalisation: a CV saying Postgres matches a JD saying
    PostgreSQL, where a naive keyword filter would drop the candidate."""
    cov = _coverage(["Postgres", "Next.js"], ["PostgreSQL", "NextJS"])
    assert cov.missing_must == []
    assert cov.must_ratio == 1.0


def test_missing_must_haves_are_reported() -> None:
    cov = _coverage(["python"], ["python", "kubernetes"])
    assert cov.missing_must == ["kubernetes"]
    assert cov.must_ratio == 0.5


def test_a_job_with_no_requirements_does_not_penalise_anyone() -> None:
    assert _coverage([], []).must_ratio == 1.0


# --- rules score ------------------------------------------------------------

def test_meeting_the_minimum_scores_full_experience_points() -> None:
    breakdown = rules_score(years_experience=3.0, min_years=3, max_years=None)
    assert breakdown.components["experience"] == 40.0
    assert breakdown.notes == []


def test_being_slightly_short_is_a_small_penalty_not_a_cliff() -> None:
    """Half a year short should not sink a strong candidate."""
    just_short = rules_score(years_experience=2.5, min_years=3, max_years=None)
    far_short = rules_score(years_experience=0.5, min_years=3, max_years=None)
    full = rules_score(years_experience=3.0, min_years=3, max_years=None)

    assert full.components["experience"] > just_short.components["experience"]
    assert just_short.components["experience"] > far_short.components["experience"]
    assert just_short.components["experience"] >= 33.0


def test_unknown_experience_is_not_treated_as_zero() -> None:
    """A CV that did not state years is the CV's failing, not the candidate's."""
    unknown = rules_score(years_experience=None, min_years=3, max_years=None)
    zero = rules_score(years_experience=0.0, min_years=3, max_years=None)
    assert unknown.components["experience"] > zero.components["experience"]
    assert any("could not be determined" in n for n in unknown.notes)


def test_remote_roles_do_not_penalise_location() -> None:
    remote = rules_score(
        years_experience=3, min_years=1, max_years=None,
        candidate_city="Chittagong", job_location="Dhaka", work_mode="remote",
    )
    onsite = rules_score(
        years_experience=3, min_years=1, max_years=None,
        candidate_city="Chittagong", job_location="Dhaka", work_mode="onsite",
    )
    assert remote.components["location"] == 15.0
    assert onsite.components["location"] < 15.0


def test_notes_explain_what_cost_points() -> None:
    breakdown = rules_score(
        years_experience=1.0, min_years=4, max_years=None,
        coverage=_coverage(["python"], ["python", "kubernetes"]),
    )
    joined = " ".join(breakdown.notes)
    assert "4-year minimum" in joined
    assert "kubernetes" in joined


# --- composite --------------------------------------------------------------

def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        RankingWeights(lexical=0.5, semantic=0.5, rules=0.5)


def test_composite_is_the_weighted_sum() -> None:
    cov = _coverage(["python"], ["python"])
    breakdown = rules_score(years_experience=5, min_years=3, max_years=None, coverage=cov)
    result = score(lexical=80.0, semantic=90.0, coverage=cov, breakdown=breakdown)

    expected = 80.0 * 0.25 + 90.0 * 0.45 + breakdown.score * 0.30
    assert result.composite == pytest.approx(round(expected, 2))


def test_scores_are_clamped_to_the_scale() -> None:
    cov = _coverage([], [])
    breakdown = rules_score(years_experience=None, min_years=None, max_years=None)
    result = score(lexical=150.0, semantic=-20.0, coverage=cov, breakdown=breakdown)
    assert result.lexical == 100.0
    assert result.semantic == 0.0


def test_cosine_distance_converts_the_right_way_round() -> None:
    """Inverting this silently reverses the entire ranking."""
    assert similarity_to_score(0.0) == 100.0     # identical
    assert similarity_to_score(1.0) == 0.0       # orthogonal
    assert similarity_to_score(0.2) > similarity_to_score(0.8)


# --- ordering ---------------------------------------------------------------

def _result(lexical: float, semantic: float, rules_years: float):
    cov = _coverage(["python"], ["python"])
    breakdown = rules_score(years_experience=rules_years, min_years=3, max_years=None, coverage=cov)
    return score(lexical=lexical, semantic=semantic, coverage=cov, breakdown=breakdown)


def test_rank_returns_every_candidate() -> None:
    """Ranking sorts; it never filters. A weak candidate is still in the list."""
    candidates = [("weak", _result(5, 5, 0)), ("strong", _result(95, 95, 10))]
    ranked = rank(candidates)
    assert len(ranked) == 2
    assert [name for name, _ in ranked] == ["strong", "weak"]


def test_rank_is_stable_and_descending() -> None:
    entries = [(str(i), _result(i, i, 3)) for i in range(10)]
    ranked = rank(entries)
    composites = [r.composite for _, r in ranked]
    assert composites == sorted(composites, reverse=True)


def test_close_scores_are_detected() -> None:
    a, b = _result(80, 80, 5), _result(79, 79, 5)
    assert a.is_close_to(b)
    assert not a.is_close_to(_result(10, 10, 0))
    assert abs(a.composite - b.composite) <= CLOSE_CALL_MARGIN


def test_separating_factor_names_the_biggest_gap() -> None:
    high_semantic = _result(50, 95, 5)
    low_semantic = _result(50, 40, 5)
    assert high_semantic.separating_factor(low_semantic) == "overall profile match"


def test_score_row_carries_the_weights_used() -> None:
    """Weights are stored per score so a re-rank is explainable after the fact."""
    row = _result(70, 70, 5).as_row()
    assert row["weights"] == {"lexical": 0.25, "semantic": 0.45, "rules": 0.30}
    assert row["scoring_version"] == 1
