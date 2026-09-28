"""Score -> prompt text. Pure, so it is testable without a database driver.

Convention (docs/01-architecture.md §12): anything that only transforms data lives in
its own module beside the agent, never inside the class that needs a session.
"""

from __future__ import annotations

from app.services.ranking import ScoreResult


def render_scores(result: ScoreResult) -> str:
    lines = [
        f"Composite: {result.composite}/100",
        f"  Skills keyword match: {result.lexical} (weight {result.weights.lexical})",
        f"  Overall profile similarity: {result.semantic} (weight {result.weights.semantic})",
        f"  Structured requirements: {result.rules} (weight {result.weights.rules})",
    ]
    if result.coverage.matched_must:
        lines.append("Required skills evidenced: " + ", ".join(result.coverage.matched_must))
    if result.coverage.missing_must:
        lines.append("Required skills with no evidence: " + ", ".join(result.coverage.missing_must))
    lines.extend(f"Note: {note}" for note in result.breakdown.notes)
    return "\n".join(lines)


def render_comparison(result: ScoreResult, neighbour: ScoreResult | None) -> str:
    if neighbour is None:
        return ""
    if not result.is_close_to(neighbour):
        return ""
    factor = result.separating_factor(neighbour)
    detail = f" The difference is mostly {factor}." if factor else ""
    return (
        f"This candidate is within {abs(result.composite - neighbour.composite):.1f} points "
        f"of the adjacent candidate — effectively a tie.{detail} Say so in the summary."
    )
