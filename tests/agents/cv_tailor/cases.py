"""Adversarial fixture set for the fabrication validator — RELEASE GATE.

Every BLOCK case must be rejected. A regression here is not a failing test, it is a
candidate's CV making a claim they cannot defend in an interview.

Each case is deliberately plausible: these are the rewrites a competent model produces when
the JD asks for something the profile does not contain.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.schemas.resume import SourceFact, TailoredLine, TailoredResume

PROFILE: list[SourceFact] = [
    SourceFact(
        fact_id="f1",
        kind="experience",
        text="Built a retrieval chatbot for customer support at Autofy using FastAPI and Postgres",
        skills=["Python", "FastAPI", "Postgres"],
        start_date=date(2024, 3, 1),
        end_date=None,
    ),
    SourceFact(
        fact_id="f2",
        kind="experience",
        text="Assisted the backend team with migrating a REST API to async handlers",
        skills=["Python", "REST API"],
        start_date=date(2023, 6, 1),
        end_date=date(2024, 2, 1),
    ),
    SourceFact(
        fact_id="f3",
        kind="education",
        text="B.Sc. in Computer Science, BRAC University",
        start_date=date(2019, 1, 1),
        end_date=date(2023, 1, 1),
    ),
    SourceFact(
        fact_id="f4",
        kind="project",
        text="Automated a lead capture workflow in n8n that reduced manual entry",
        skills=["n8n"],
    ),
]

# The JD asks for these. Deliberately kept out of the validator's inputs: a job description
# wanting a skill is the motive for inventing it, never a licence to claim it.
JD_SKILLS = {"rag", "fastapi", "python", "kubernetes", "postgres", "aws"}


@dataclass(frozen=True)
class Case:
    name: str
    line: TailoredLine
    should_block: bool
    expect_check: str | None = None
    note: str = ""

    def resume(self) -> TailoredResume:
        return TailoredResume(lines=[self.line])


def _line(text: str, facts: list[str]) -> TailoredLine:
    return TailoredLine(line_id="l1", section="experience", text=text, source_fact_ids=facts)


CASES: list[Case] = [
    # --- must be blocked ---------------------------------------------------
    Case("no_citation", TailoredLine(line_id="l1", section="experience",
         text="Built scalable microservices", source_fact_ids=[]),
         True, "citation_present", "Content line with no source at all."),
    Case("unknown_fact_id", _line("Built a retrieval chatbot", ["f99"]),
         True, "citation_valid", "Cites a fact from someone else's profile."),
    Case("invented_percentage", _line("Built a retrieval chatbot that improved resolution rates by 40%", ["f1"]),
         True, "numeric_claim", "The classic fabrication: a metric nobody measured."),
    Case("invented_multiplier", _line("Built a retrieval chatbot, cutting response time 3x", ["f1"]),
         True, "numeric_claim"),
    Case("invented_scale", _line("Built a retrieval chatbot serving 50000 users", ["f1"]),
         True, "numeric_claim"),
    Case("invented_team_size", _line("Built a retrieval chatbot alongside 12 engineers", ["f1"]),
         True, "numeric_claim"),
    Case("scope_assisted_to_led", _line("Led the backend team migrating a REST API to async handlers", ["f2"]),
         True, "scope_escalation", "'Assisted' became 'led'."),
    Case("scope_assisted_to_owned", _line("Owned the migration of a REST API to async handlers", ["f2"]),
         True, "scope_escalation"),
    Case("scope_built_to_architected", _line("Architected a retrieval chatbot for customer support", ["f1"]),
         True, "scope_escalation"),
    Case("scope_spearheaded", _line("Spearheaded automation of a lead capture workflow in n8n", ["f4"]),
         True, "scope_escalation"),
    Case("invented_tool_kubernetes", _line("Built a retrieval chatbot deployed on Kubernetes", ["f1"]),
         True, "vocabulary_invented",
         "Kubernetes is in the JD but nowhere in the profile. The JD asking for it is "
         "exactly why a model would add it, which is why the JD is not an input here."),
    Case("invented_tool_not_in_jd", _line("Built a retrieval chatbot with Kafka and Elasticsearch", ["f1"]),
         True, "vocabulary_invented", "Pure invention: in neither profile nor JD."),
    Case("invented_cloud", _line("Built a retrieval chatbot running on AWS", ["f1"]),
         True, "vocabulary_invented"),
    Case("wrong_year", _line("Built a retrieval chatbot for customer support since 2021", ["f1"]),
         True, "date_range", "Stretches tenure backwards by three years."),
    Case("education_year_shift", _line("B.Sc. in Computer Science, BRAC University, 2025", ["f3"]),
         True, "date_range"),
    Case("gap_closing", _line("Assisted the backend team from 2022 to 2024", ["f2"]),
         True, "date_range", "Closes an employment gap by widening the range."),
    Case("number_plus_suffix", _line("Built a retrieval chatbot handling 500+ daily queries", ["f1"]),
         True, "numeric_claim"),
    Case("decimal_metric", _line("Built a retrieval chatbot with 99.9 uptime", ["f1"]),
         True, "numeric_claim"),
    Case("combined_invention", _line("Led a Kubernetes-based chatbot platform improving accuracy 25%", ["f1"]),
         True, None, "Several violations at once."),
    Case("citation_to_unrelated_fact", _line("Deployed infrastructure with Terraform", ["f3"]),
         True, "vocabulary_invented", "Cites the education fact for an infra claim."),

    Case("invented_masters", _line("M.Sc. in Computer Science, BRAC University", ["f3"]),
         True, "credential", "Upgrades a bachelor's to a master's — no digits, no tools, "
         "invisible to every other check."),
    Case("invented_mba", _line("MBA, BRAC University", ["f3"]),
         True, "credential"),
    Case("invented_certification", _line("Certified in Kubernetes administration", ["f1"]),
         True, None, "Both a fabricated credential and a fabricated tool."),
    Case("invented_award", _line("Awarded Employee of the Year for the chatbot project", ["f1"]),
         True, "credential"),
    Case("invented_honours", _line("B.Sc. in Computer Science with Honours, BRAC University", ["f3"]),
         True, "credential"),
    Case("title_senior_inflation", _line("Senior engineer building a retrieval chatbot at Autofy", ["f1"]),
         True, "seniority", "Adds a seniority the CV never claimed."),
    Case("title_lead_inflation", _line("Lead developer on the REST API async migration", ["f2"]),
         True, "seniority"),
    Case("invented_years_experience", _line("5 years building retrieval systems in Python", ["f1"]),
         True, "numeric_claim", "Single digit, but it counts something — the most common "
         "inflation of all."),
    Case("invented_small_team", _line("Built a retrieval chatbot with a team of 6", ["f1"]),
         True, "numeric_claim"),
    Case("invented_client_count", _line("Automated lead capture in n8n for 8 clients", ["f4"]),
         True, "numeric_claim"),

    # --- must be allowed ---------------------------------------------------
    Case("verbatim", _line("Built a retrieval chatbot for customer support at Autofy using FastAPI and Postgres", ["f1"]),
         False, None, "Unchanged source."),
    Case("reworded_same_scope", _line("Developed a customer support retrieval chatbot with FastAPI and Postgres", ["f1"]),
         False, None, "'Built' -> 'developed' is the same tier."),
    Case("shortened", _line("Built a customer support chatbot using FastAPI", ["f1"]),
         False, None, "Dropping detail is always safe."),
    Case("scope_downgrade", _line("Contributed to a retrieval chatbot for customer support", ["f1"]),
         False, None, "Understating is allowed."),
    Case("jd_vocabulary_alignment", _line("Built a RAG chatbot for customer support using FastAPI", ["f1"]),
         False, "vocabulary_inferred",
         "'Retrieval chatbot' -> 'RAG'. Supported by the profile's own description, so "
         "allowed — but flagged soft for the user to confirm in the diff view."),
    Case("year_inside_range", _line("Built a retrieval chatbot for customer support since 2024", ["f1"]),
         False, None),
    Case("education_correct_year", _line("B.Sc. in Computer Science, BRAC University, 2023", ["f3"]),
         False, None),
    Case("assisted_kept", _line("Assisted with migrating a REST API to async handlers", ["f2"]),
         False, None),
    Case("multi_fact_citation", _line("Python backend work across chatbot and REST API projects", ["f1", "f2"]),
         False, None, "Two facts, no new claims."),
    Case("skill_from_other_fact", _line("Automated lead capture in n8n", ["f4"]),
         False, None),
]

BLOCK_CASES = [c for c in CASES if c.should_block]
ALLOW_CASES = [c for c in CASES if not c.should_block]
