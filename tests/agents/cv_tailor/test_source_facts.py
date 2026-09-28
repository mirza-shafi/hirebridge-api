from __future__ import annotations

from datetime import date

from app.agents.cv_tailor.source_facts import build_source_facts, render_for_prompt

ROWS = [
    {
        "id": "f1",
        "kind": "experience",
        "payload": {
            "company": "Autofy Solution",
            "title": "AI Engineer",
            "tech": ["python", "fastapi"],
            "bullets": [
                {"id": "b1", "text": "Built a retrieval chatbot"},
                {"id": "b2", "text": "Cut support response time by 40%"},
            ],
        },
        "start_date": date(2024, 3, 1),
        "end_date": None,
    }
]


def test_every_bullet_is_separately_citable() -> None:
    ids = {fact.fact_id for fact in build_source_facts(ROWS)}
    assert ids == {"f1", "f1#b1", "f1#b2"}


def test_a_bullet_fact_carries_its_role_context() -> None:
    facts = {f.fact_id: f for f in build_source_facts(ROWS)}
    assert "AI Engineer at Autofy Solution" in facts["f1#b1"].text
    assert "Built a retrieval chatbot" in facts["f1#b1"].text
    # The other bullet's figure must NOT be in scope for this one.
    assert "40%" not in facts["f1#b1"].text


def test_bullet_level_citation_narrows_what_can_justify_a_claim() -> None:
    """The reason bullets are addressable at all.

    Citing the whole role would let a figure stated in bullet 2 validate a claim rewritten
    from bullet 1.
    """
    facts = {f.fact_id: f for f in build_source_facts(ROWS)}
    assert "40%" in facts["f1"].text, "the parent fact aggregates every bullet"
    assert "40%" in facts["f1#b2"].text
    assert "40%" not in facts["f1#b1"].text


def test_dates_are_carried_onto_bullet_facts() -> None:
    facts = {f.fact_id: f for f in build_source_facts(ROWS)}
    assert facts["f1#b1"].start_date == date(2024, 3, 1)
    assert facts["f1#b1"].end_date is None


def test_prompt_rendering_exposes_the_ids() -> None:
    rendered = render_for_prompt(build_source_facts(ROWS))
    assert "[f1#b1]" in rendered and "[f1#b2]" in rendered
    assert "2024-03-01 to present" in rendered
