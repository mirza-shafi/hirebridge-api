"""The fabrication validator — release gate.

Runs after generation, before the user ever sees the output. Deterministic first; a model is
consulted only for semantic equivalence, and only on lines that survive the hard checks
(docs/03-agent-specs.md §3).

Severity decides what happens:
  HARD  -> ValidationFailure. The runner gets one repair attempt, then the run fails and
           no PDF is rendered.
  SOFT  -> recorded as a warning. The diff view makes the user acknowledge each one
           individually before approve unlocks.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Protocol

from app.agents.errors import ValidationFailure
from app.schemas.enums import Severity, ValidatorStatus
from app.schemas.resume import SourceFact, TailoredLine, TailoredResume
from app.services.parsing.skills import (
    canonical,
    extract_implied_skills,
    extract_known_skills,
)


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    severity: Severity
    line_id: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "severity": self.severity.value}


class EntailmentChecker(Protocol):
    """Does the source text entail the rewrite? Optional; skipped when not configured."""

    async def __call__(self, *, source: str, rewrite: str) -> bool: ...


# Numbers that carry a claim. Bare years go to the date check instead.
_NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(%|x|k|m|\+)?(?![\w.])", re.I)
_YEAR = re.compile(r"^(?:19|20)\d{2}$")

# A small number is noise on its own but a claim when it counts something. "5 years of
# experience" and "a team of 6" are among the most common CV inflations, and both would
# slip past a digit-length heuristic.
_UNIT_WORDS = (
    r"years?|months?|users?|customers?|clients?|engineers?|developers?|people|members?|"
    r"teams?|projects?|countries|languages?|requests?|queries|records?|stores?|branches"
)
_NUMBER_UNIT = re.compile(rf"(\d+(?:\.\d+)?)\s*\+?\s*(?:{_UNIT_WORDS})\b", re.I)
_UNIT_OF_NUMBER = re.compile(r"\b(?:team|group|squad|cohort)\s+of\s+(\d+)\b", re.I)

# Credentials and seniority are claims that carry no digits and no tool names, so the
# numeric and vocabulary checks both miss them. A fabricated degree is as damaging as a
# fabricated metric.
_CREDENTIAL = re.compile(
    r"\b(b\.?sc|b\.?s|b\.?a|m\.?sc|m\.?s|m\.?a|mba|ph\.?d|doctorate|bachelors?|"
    r"masters?|diploma|certified|certification|licen[sc]ed|awarded|award|winner|fellow|"
    r"scholarship|honou?rs)\b",
    re.I,
)
_SENIORITY = re.compile(
    r"\b(senior|junior|principal|staff|lead|head|chief|director|vp|founding|intern)\b", re.I
)

# Verb tiers: an output verb may not outrank the verb of the fact it cites.
VERB_TIERS: dict[str, int] = {}
for _tier, _verbs in {
    1: ("assisted", "helped", "supported", "contributed", "participated", "involved",
        "collaborated", "aided", "shadowed"),
    2: ("built", "implemented", "developed", "created", "wrote", "designed", "maintained",
        "delivered", "produced", "integrated", "migrated", "refactored", "automated"),
    3: ("led", "owned", "headed", "directed", "managed", "spearheaded", "founded",
        "architected", "established", "oversaw", "drove", "pioneered"),
}.items():
    for _verb in _verbs:
        VERB_TIERS[_verb] = _tier

_WORD = re.compile(r"[a-z]+")


def _numbers(text: str) -> set[str]:
    out: set[str] = set()
    for value, suffix in _NUMBER.findall(text):
        if _YEAR.match(value):
            continue
        if not suffix and len(value.split(".")[0]) < 2:
            continue
        out.add(f"{value}{(suffix or '').lower()}")
    # Counted quantities count regardless of magnitude.
    out |= {m for m in _NUMBER_UNIT.findall(text) if not _YEAR.match(m)}
    out |= set(_UNIT_OF_NUMBER.findall(text))
    return out


def _stem(token: str) -> str:
    return token.lower().replace(".", "").rstrip("s")


def _credentials(text: str) -> set[str]:
    return {_stem(m) for m in _CREDENTIAL.findall(text)}


def _seniority(text: str) -> set[str]:
    return {_stem(m) for m in _SENIORITY.findall(text)}


def _max_verb_tier(text: str) -> int:
    return max(
        (VERB_TIERS[word] for word in _WORD.findall(text.lower()) if word in VERB_TIERS),
        default=0,
    )


def _years_in(text: str) -> set[int]:
    return {int(match) for match in re.findall(r"(?:19|20)\d{2}", text)}


class FabricationValidator:
    """Callable validator matching the runner's `Validator` protocol."""

    def __init__(
        self,
        facts: list[SourceFact],
        *,
        entailment: EntailmentChecker | None = None,
    ) -> None:
        self.facts = {fact.fact_id: fact for fact in facts}
        self.entailment = entailment

        # Named: the candidate said this word. Implied: their description evidences it but
        # they never used the term. The distinction decides warn-vs-block below.
        self.named_skills: set[str] = set()
        self.implied_skills: set[str] = set()
        for fact in facts:
            self.named_skills |= {canonical(s) for s in fact.skills if s}
            self.named_skills |= extract_known_skills(fact.text)
            self.implied_skills |= extract_implied_skills(fact.text)
        self.implied_skills -= self.named_skills

    async def __call__(self, output: Any, context: dict[str, Any]) -> str:
        if not isinstance(output, TailoredResume):
            raise ValidationFailure("Validator received an unexpected output type.")

        findings: list[Finding] = []
        for line in output.lines:
            if line.is_heading:
                continue
            findings.extend(self._check_line(line))

        for line in output.lines:
            if line.is_heading or self.entailment is None:
                continue
            if any(f.line_id == line.line_id and f.severity is Severity.HARD for f in findings):
                continue  # already failing; do not spend a model call on it
            findings.extend(await self._check_entailment(line))

        context["validator_findings"] = [f.as_dict() for f in findings]

        hard = [f for f in findings if f.severity is Severity.HARD]
        if hard:
            raise ValidationFailure(
                "; ".join(f"{f.line_id}: {f.message}" for f in hard[:5]),
                status=ValidatorStatus.FAILED.value,
            )
        return (
            ValidatorStatus.PASSED_WITH_WARNINGS.value
            if findings
            else ValidatorStatus.PASSED.value
        )

    # --- deterministic checks -------------------------------------------------

    def _check_line(self, line: TailoredLine) -> list[Finding]:
        findings: list[Finding] = []

        if not line.source_fact_ids:
            return [
                Finding("citation_present", Severity.HARD, line.line_id,
                        "Content line cites no source fact.")
            ]

        unknown = [fid for fid in line.source_fact_ids if fid.split("#")[0] not in self.facts]
        if unknown:
            return [
                Finding("citation_valid", Severity.HARD, line.line_id,
                        f"Cites fact ids that are not in this profile: {', '.join(unknown)}.")
            ]

        sources = [self.facts[fid.split("#")[0]] for fid in line.source_fact_ids]
        source_text = " ".join(s.text for s in sources)

        # 1. Numeric claims must exist in the source.
        invented = _numbers(line.text) - _numbers(source_text)
        if invented:
            findings.append(
                Finding("numeric_claim", Severity.HARD, line.line_id,
                        f"States figures absent from the source: {', '.join(sorted(invented))}.")
            )

        # 2. Years must sit inside the cited fact's range.
        findings.extend(self._check_dates(line, sources))

        # 3. Scope escalation.
        out_tier, src_tier = _max_verb_tier(line.text), _max_verb_tier(source_text)
        if out_tier > src_tier:
            findings.append(
                Finding("scope_escalation", Severity.HARD, line.line_id,
                        f"Claims a higher level of ownership (tier {out_tier}) than the "
                        f"source supports (tier {src_tier}).")
            )

        # 4. Credentials — a degree, certification or award must be in the source.
        if invented_creds := _credentials(line.text) - _credentials(source_text):
            findings.append(
                Finding("credential", Severity.HARD, line.line_id,
                        "Claims a qualification the cited fact does not contain: "
                        f"{', '.join(sorted(invented_creds))}.")
            )

        # 5. Seniority — titles may be kept or lowered, never raised.
        if invented_rank := _seniority(line.text) - _seniority(source_text):
            findings.append(
                Finding("seniority", Severity.HARD, line.line_id,
                        "Uses a seniority the source does not support: "
                        f"{', '.join(sorted(invented_rank))}.")
            )

        # 6. Vocabulary.
        findings.extend(self._check_vocabulary(line))
        return findings

    def _check_dates(self, line: TailoredLine, sources: list[SourceFact]) -> list[Finding]:
        years = _years_in(line.text)
        if not years:
            return []
        allowed: set[int] = set()
        for source in sources:
            start = source.start_date or date(1900, 1, 1)
            end = source.end_date or date.today()
            allowed |= set(range(start.year, end.year + 1))
            allowed |= _years_in(source.text)
        if outside := years - allowed:
            return [
                Finding("date_range", Severity.HARD, line.line_id,
                        "Mentions years outside the cited fact's range: "
                        f"{', '.join(str(y) for y in sorted(outside))}.")
            ]
        return []

    def _check_vocabulary(self, line: TailoredLine) -> list[Finding]:
        """A skill the output *names* must be supported by the profile.

        Three outcomes, and the job description is not a factor in any of them — the JD
        wanting a skill is the motive for inventing it, never a licence to claim it:

          named in the profile   -> fine
          implied by the profile -> soft. The agent turned "built a retrieval chatbot" into
                                    "RAG", which the spec allows, but the user confirms it
                                    in the diff view before the CV can be sent.
          neither                -> hard. This is fabrication.
        """
        mentioned = extract_known_skills(line.text)
        unsupported = mentioned - self.named_skills
        if not unsupported:
            return []

        findings: list[Finding] = []
        if invented := unsupported - self.implied_skills:
            findings.append(
                Finding("vocabulary_invented", Severity.HARD, line.line_id,
                        "Claims skills your profile does not support: "
                        f"{', '.join(sorted(invented))}.")
            )
        if inferred := unsupported & self.implied_skills:
            findings.append(
                Finding("vocabulary_inferred", Severity.SOFT, line.line_id,
                        f"Names {', '.join(sorted(inferred))}, which your profile describes "
                        "in different words. Confirm the term is accurate.")
            )
        return findings

    async def _check_entailment(self, line: TailoredLine) -> list[Finding]:
        assert self.entailment is not None
        sources = [self.facts[fid.split("#")[0]] for fid in line.source_fact_ids]
        source_text = " ".join(s.text for s in sources)
        if await self.entailment(source=source_text, rewrite=line.text):
            return []
        return [
            Finding("entailment", Severity.HARD, line.line_id,
                    "The rewritten line is not supported by the source fact it cites.")
        ]
