"""Base vs tailored diff.

This backs the screen the whole candidate product rests on. The summary leads with
`added: 0` — the visible proof that nothing was invented (docs/03-ux-flows.md, Flow 2).

Lines are matched by the facts they cite rather than by text similarity: the agent's job is
to reword, so matching on wording would report every rewritten line as a delete plus an add
and make the diff useless.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from app.schemas.resume import TailoredLine, TailoredResume


class LineStatus(str, Enum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    REORDERED = "reordered"
    REMOVED = "removed"
    ADDED = "added"


@dataclass(frozen=True, slots=True)
class DiffLine:
    line_id: str
    section: str
    status: LineStatus
    base: str | None
    tailored: str | None
    source_fact_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "status": self.status.value}


@dataclass(frozen=True, slots=True)
class DiffSummary:
    added: int
    modified: int
    removed: int
    reordered: int
    unchanged: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    @property
    def introduces_new_content(self) -> bool:
        """Non-zero `added` means content appeared with no counterpart in the base CV.

        Not proof of fabrication on its own — the validator decides that — but it is the
        signal that something needs looking at.
        """
        return self.added > 0


@dataclass(frozen=True, slots=True)
class ResumeDiff:
    lines: list[DiffLine]
    summary: DiffSummary

    def as_dict(self) -> dict[str, Any]:
        sections: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in self.lines:
            sections[line.section].append(line.as_dict())
        return {
            "sections": [{"name": name, "lines": rows} for name, rows in sections.items()],
            "summary": self.summary.as_dict(),
        }


_WS = re.compile(r"\s+")


def _normalise(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def _key(line: TailoredLine) -> str:
    """Identity of a line: the set of facts it cites.

    Two lines citing the same facts are the same line, however differently they are worded.
    """
    return "|".join(sorted(line.source_fact_ids))


def compute_diff(base: TailoredResume, tailored: TailoredResume) -> ResumeDiff:
    base_content = [line for line in base.lines if not line.is_heading]
    new_content = [line for line in tailored.lines if not line.is_heading]

    base_by_key: dict[str, list[TailoredLine]] = defaultdict(list)
    for line in base_content:
        base_by_key[_key(line)].append(line)

    base_order = {id(line): index for index, line in enumerate(base_content)}
    matched: set[int] = set()
    diff_lines: list[DiffLine] = []
    counts = dict.fromkeys(LineStatus, 0)

    for new_index, line in enumerate(new_content):
        candidates = [c for c in base_by_key.get(_key(line), []) if id(c) not in matched]
        if not candidates:
            status = LineStatus.ADDED
            base_text = None
        else:
            # Prefer an identical wording, so a genuine rewrite is not matched against the
            # wrong sibling when several lines cite the same facts.
            exact = next(
                (c for c in candidates if _normalise(c.text) == _normalise(line.text)), None
            )
            source = exact or candidates[0]
            matched.add(id(source))
            base_text = source.text

            if _normalise(source.text) != _normalise(line.text):
                status = LineStatus.MODIFIED
            elif base_order[id(source)] != new_index:
                status = LineStatus.REORDERED
            else:
                status = LineStatus.UNCHANGED

        counts[status] += 1
        diff_lines.append(
            DiffLine(
                line_id=line.line_id,
                section=line.section,
                status=status,
                base=base_text,
                tailored=line.text,
                source_fact_ids=line.source_fact_ids,
            )
        )

    for line in base_content:
        if id(line) in matched:
            continue
        counts[LineStatus.REMOVED] += 1
        diff_lines.append(
            DiffLine(
                line_id=line.line_id,
                section=line.section,
                status=LineStatus.REMOVED,
                base=line.text,
                tailored=None,
                source_fact_ids=line.source_fact_ids,
            )
        )

    return ResumeDiff(
        lines=diff_lines,
        summary=DiffSummary(
            added=counts[LineStatus.ADDED],
            modified=counts[LineStatus.MODIFIED],
            removed=counts[LineStatus.REMOVED],
            reordered=counts[LineStatus.REORDERED],
            unchanged=counts[LineStatus.UNCHANGED],
        ),
    )
