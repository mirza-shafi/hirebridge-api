"""Candidate ranking.

**Scoring is deterministic and contains no model call.** The composite is arithmetic over a
lexical score, a vector similarity, and a rules score; an LLM only ever *explains* the
result afterwards (docs/03-agent-specs.md §8). Three reasons this matters:

  * reproducible — the same inputs give the same order, every time, and a recruiter can be
    told exactly why someone ranked where they did;
  * cheap — 400 applicants cost one embedding lookup each, not 400 completions;
  * auditable — if a ranking is ever challenged, the arithmetic is inspectable.

Ranking sorts. It never filters. There is no threshold in this module and no caller may
introduce one (docs/00-product-brief.md §8 rule 2).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.parsing.skills import canonical

SCORING_VERSION = 1

# Two candidates within this many composite points are not meaningfully separated. The
# justification says so rather than implying a precision the score does not have.
CLOSE_CALL_MARGIN = 5.0


@dataclass(frozen=True, slots=True)
class RankingWeights:
    lexical: float = 0.25
    semantic: float = 0.45
    rules: float = 0.30

    def __post_init__(self) -> None:
        total = self.lexical + self.semantic + self.rules
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Ranking weights must sum to 1.0, got {total}.")

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RequirementCoverage:
    matched_must: list[str]
    missing_must: list[str]
    matched_nice: list[str]
    missing_nice: list[str]

    @property
    def must_ratio(self) -> float:
        total = len(self.matched_must) + len(self.missing_must)
        return 1.0 if total == 0 else len(self.matched_must) / total

    @property
    def nice_ratio(self) -> float:
        total = len(self.matched_nice) + len(self.missing_nice)
        return 1.0 if total == 0 else len(self.matched_nice) / total


def cover_requirements(
    candidate_skills: list[str] | set[str],
    *,
    must_have: list[str] | None,
    nice_to_have: list[str] | None,
) -> RequirementCoverage:
    """Compare canonical skill sets. Both sides are canonicalised again defensively —
    a CV saying "Postgres" must match a JD saying "PostgreSQL"."""
    held = {c for s in candidate_skills if (c := canonical(s))}
    must = [c for s in (must_have or []) if (c := canonical(s))]
    nice = [c for s in (nice_to_have or []) if (c := canonical(s))]

    return RequirementCoverage(
        matched_must=sorted({s for s in must if s in held}),
        missing_must=sorted({s for s in must if s not in held}),
        matched_nice=sorted({s for s in nice if s in held}),
        missing_nice=sorted({s for s in nice if s not in held}),
    )


@dataclass(frozen=True, slots=True)
class RulesBreakdown:
    """Component scores with a plain-language note for each.

    The notes exist so the UI and the justification agent can say *what* separated two
    candidates — "ranked below on years of experience; skills coverage is equivalent" is
    the sentence that makes a recruiter trust the tool.
    """

    score: float
    components: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


SENIORITY_BANDS: dict[str, int] = {
    "intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4, "principal": 5,
}


def rules_score(
    *,
    years_experience: float | None,
    min_years: int | None,
    max_years: int | None,
    candidate_seniority: str | None = None,
    job_seniority: str | None = None,
    candidate_city: str | None = None,
    job_location: str | None = None,
    work_mode: str | None = None,
    coverage: RequirementCoverage | None = None,
) -> RulesBreakdown:
    """Structured, non-semantic fit. Returns 0-100."""
    components: dict[str, float] = {}
    notes: list[str] = []

    # --- Experience (40) ---
    if min_years is None and max_years is None:
        components["experience"] = 40.0
    elif years_experience is None:
        # Unknown is not the same as unqualified; a missing figure is the CV's fault.
        components["experience"] = 24.0
        notes.append("Years of experience could not be determined from the CV.")
    else:
        low = min_years if min_years is not None else 0
        if years_experience >= low:
            components["experience"] = 40.0
        else:
            shortfall = low - years_experience
            # Half a year short barely matters; three years short does.
            components["experience"] = max(0.0, 40.0 - shortfall * 12.0)
            notes.append(
                f"{years_experience:g} years of experience against a {low}-year minimum."
            )
        if max_years is not None and years_experience > max_years + 3:
            notes.append(
                f"Substantially more experience ({years_experience:g} years) than the "
                f"role's stated range."
            )

    # --- Seniority band (25) ---
    if job_seniority is None or candidate_seniority is None:
        components["seniority"] = 17.5
    else:
        gap = abs(
            SENIORITY_BANDS.get(candidate_seniority, 2)
            - SENIORITY_BANDS.get(job_seniority, 2)
        )
        components["seniority"] = max(0.0, 25.0 - gap * 8.0)
        if gap >= 2:
            notes.append(
                f"Seniority differs from the role by {gap} bands "
                f"({candidate_seniority} vs {job_seniority})."
            )

    # --- Location (15) ---
    if (work_mode or "").lower() == "remote" or not job_location or not candidate_city:
        components["location"] = 15.0
    elif candidate_city.strip().lower() in job_location.strip().lower():
        components["location"] = 15.0
    else:
        components["location"] = 6.0
        notes.append(
            f"Based in {candidate_city}; the role is {work_mode or 'onsite'} in {job_location}."
        )

    # --- Must-have coverage (20) ---
    if coverage is None:
        components["requirements"] = 14.0
    else:
        components["requirements"] = 20.0 * coverage.must_ratio
        if coverage.missing_must:
            notes.append(
                "No evidence in the CV for: " + ", ".join(coverage.missing_must) + "."
            )

    return RulesBreakdown(
        score=round(sum(components.values()), 2), components=components, notes=notes
    )


@dataclass(frozen=True, slots=True)
class ScoreResult:
    composite: float
    lexical: float
    semantic: float
    rules: float
    weights: RankingWeights
    breakdown: RulesBreakdown
    coverage: RequirementCoverage
    scoring_version: int = SCORING_VERSION

    def as_row(self) -> dict[str, Any]:
        return {
            "composite": self.composite,
            "lexical": self.lexical,
            "semantic": self.semantic,
            "rules": self.rules,
            "weights": self.weights.as_dict(),
            "missing_requirements": self.coverage.missing_must,
            "scoring_version": self.scoring_version,
        }

    def is_close_to(self, other: ScoreResult) -> bool:
        return abs(self.composite - other.composite) <= CLOSE_CALL_MARGIN

    def separating_factor(self, other: ScoreResult) -> str | None:
        """Which component accounts for most of the gap between two candidates."""
        gaps = {
            "skills coverage": abs(self.lexical - other.lexical) * self.weights.lexical,
            "overall profile match": abs(self.semantic - other.semantic) * self.weights.semantic,
            "structured requirements": abs(self.rules - other.rules) * self.weights.rules,
        }
        top, value = max(gaps.items(), key=lambda kv: kv[1])
        return top if value > 1.0 else None


def score(
    *,
    lexical: float,
    semantic: float,
    coverage: RequirementCoverage,
    breakdown: RulesBreakdown,
    weights: RankingWeights | None = None,
) -> ScoreResult:
    """Combine the three signals. Every input is already 0-100."""
    w = weights or RankingWeights()
    lexical = _clamp(lexical)
    semantic = _clamp(semantic)
    rules = _clamp(breakdown.score)

    composite = round(
        lexical * w.lexical + semantic * w.semantic + rules * w.rules, 2
    )
    return ScoreResult(
        composite=composite,
        lexical=round(lexical, 2),
        semantic=round(semantic, 2),
        rules=round(rules, 2),
        weights=w,
        breakdown=breakdown,
        coverage=coverage,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def similarity_to_score(cosine_distance: float) -> float:
    """pgvector's `<=>` returns cosine *distance* in [0, 2]. Convert to a 0-100 similarity.

    Getting this backwards silently inverts the entire ranking, which is why it is one
    named function with a test rather than an inline expression.
    """
    return _clamp((1.0 - cosine_distance) * 100.0)


def rank(results: list[tuple[Any, ScoreResult]]) -> list[tuple[Any, ScoreResult]]:
    """Sort by composite, descending.

    Returns every input. There is no threshold parameter and no caller may add one — the
    recruiter sees all applicants, ordered (product rule 2).
    """
    return sorted(results, key=lambda pair: pair[1].composite, reverse=True)
