from __future__ import annotations

from app.schemas.resume import TailoredLine, TailoredResume
from app.services.resume_diff import LineStatus, compute_diff


def _line(line_id: str, text: str, facts: list[str], section: str = "experience") -> TailoredLine:
    return TailoredLine(line_id=line_id, section=section, text=text, source_fact_ids=facts)


def _resume(*lines: TailoredLine) -> TailoredResume:
    return TailoredResume(lines=list(lines))


def test_reworded_line_is_modified_not_add_plus_remove() -> None:
    """The point of the product is rewording; text-similarity matching would break here."""
    base = _resume(_line("l1", "Worked on a chatbot for customer support", ["f1#b1"]))
    tailored = _resume(_line("l1", "Built a RAG chatbot handling support queries", ["f1#b1"]))

    diff = compute_diff(base, tailored)
    assert diff.summary.added == 0
    assert diff.summary.removed == 0
    assert diff.summary.modified == 1
    assert diff.lines[0].status is LineStatus.MODIFIED
    assert diff.lines[0].base == "Worked on a chatbot for customer support"


def test_identical_line_moved_up_is_reordered() -> None:
    base = _resume(
        _line("l1", "First thing", ["f1#b1"]),
        _line("l2", "Second thing", ["f2#b1"]),
    )
    tailored = _resume(
        _line("l2", "Second thing", ["f2#b1"]),
        _line("l1", "First thing", ["f1#b1"]),
    )
    diff = compute_diff(base, tailored)
    assert diff.summary.reordered == 2
    assert diff.summary.modified == 0


def test_dropped_line_is_removed() -> None:
    base = _resume(
        _line("l1", "Relevant thing", ["f1#b1"]),
        _line("l2", "Irrelevant thing", ["f2#b1"]),
    )
    tailored = _resume(_line("l1", "Relevant thing", ["f1#b1"]))
    diff = compute_diff(base, tailored)
    assert diff.summary.removed == 1
    assert [line.status for line in diff.lines if line.line_id == "l2"] == [LineStatus.REMOVED]


def test_new_content_shows_up_as_added() -> None:
    """`added > 0` is the signal the diff view surfaces for scrutiny."""
    base = _resume(_line("l1", "Built a chatbot", ["f1#b1"]))
    tailored = _resume(
        _line("l1", "Built a chatbot", ["f1#b1"]),
        _line("l2", "Deployed on Kubernetes", ["f9#b1"]),
    )
    diff = compute_diff(base, tailored)
    assert diff.summary.added == 1
    assert diff.summary.introduces_new_content is True


def test_a_clean_tailoring_reports_zero_added() -> None:
    """The line the diff view leads with."""
    base = _resume(
        _line("l1", "Built a retrieval chatbot", ["f1#b1"]),
        _line("l2", "Migrated a REST API", ["f2#b1"]),
        _line("l3", "Automated lead capture", ["f3#b1"]),
    )
    tailored = _resume(
        _line("l2", "Migrated a REST API to async handlers", ["f2#b1"]),
        _line("l1", "Built a RAG chatbot for support", ["f1#b1"]),
    )
    diff = compute_diff(base, tailored)
    assert diff.summary.added == 0
    assert diff.summary.introduces_new_content is False
    assert diff.summary.modified == 2
    assert diff.summary.removed == 1


def test_headings_are_excluded_from_the_diff() -> None:
    base = _resume(
        TailoredLine(line_id="h1", section="experience", text="Experience", is_heading=True),
        _line("l1", "Built a chatbot", ["f1#b1"]),
    )
    tailored = _resume(
        TailoredLine(line_id="h1", section="experience", text="Experience", is_heading=True),
        _line("l1", "Built a chatbot", ["f1#b1"]),
    )
    diff = compute_diff(base, tailored)
    assert len(diff.lines) == 1
    assert diff.summary.unchanged == 1


def test_siblings_citing_the_same_fact_match_by_wording_first() -> None:
    base = _resume(
        _line("l1", "Handled retrieval quality", ["f1"]),
        _line("l2", "Handled deployment", ["f1"]),
    )
    tailored = _resume(
        _line("l2", "Handled deployment", ["f1"]),
        _line("l1", "Improved retrieval quality", ["f1"]),
    )
    diff = compute_diff(base, tailored)
    # The identical line pairs with its twin, leaving the genuine rewrite as the modification.
    assert diff.summary.modified == 1
    assert diff.summary.added == 0
    assert diff.summary.removed == 0


def test_serialisation_groups_by_section() -> None:
    base = _resume(
        _line("l1", "Built a chatbot", ["f1#b1"], section="experience"),
        _line("l2", "B.Sc. Computer Science", ["f2"], section="education"),
    )
    payload = compute_diff(base, base).as_dict()
    assert {s["name"] for s in payload["sections"]} == {"experience", "education"}
    assert payload["summary"]["added"] == 0
