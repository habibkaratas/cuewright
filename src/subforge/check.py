"""Structural validation of a finished SRT file.

Catches the mistakes that survive a good transcript but ruin playback:
out-of-order numbering, reversed or overlapping timings, blocks with too many
lines, and text too wide for the frame.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .srt import MAX_BLOCK, MAX_LINE, MAX_LINES, parse_timestamp

__all__ = ["SrtReport", "check_srt"]


@dataclass
class SrtReport:
    path: str
    blocks: int = 0
    max_line: int = 0
    max_block: int = 0
    min_duration: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and self.max_block <= MAX_BLOCK

    @property
    def wide_lines(self) -> bool:
        return self.max_line > MAX_LINE


def check_srt(path, encoding: str = "utf-8-sig") -> SrtReport:
    report = SrtReport(path=str(path))
    raw = open(path, encoding=encoding).read().strip()
    if not raw:
        report.problems.append("file is empty")
        return report

    blocks = re.split(r"\n\s*\n", raw)
    report.blocks = len(blocks)
    previous_end = -1.0
    shortest = float("inf")

    for n, block in enumerate(blocks, 1):
        lines = block.split("\n")
        if len(lines) < 3:
            report.problems.append(f"block {n}: truncated")
            continue

        index, timing = lines[0].strip(), lines[1]
        text = [ln for ln in lines[2:] if ln.strip()]

        if index != str(n):
            report.problems.append(f"block {n}: numbered {index}")
        if "-->" not in timing:
            report.problems.append(f"block {n}: missing timing line")
            continue

        try:
            start, end = (parse_timestamp(part) for part in timing.split("-->"))
        except ValueError:
            report.problems.append(f"block {n}: unparseable timing {timing.strip()!r}")
            continue

        if end <= start:
            report.problems.append(f"block {n}: ends before it starts")
        if start < previous_end - 1e-3:
            report.problems.append(
                f"block {n}: overlaps the previous block ({start:.2f}s < {previous_end:.2f}s)"
            )
        previous_end = end
        shortest = min(shortest, end - start)

        if len(text) > MAX_LINES:
            report.problems.append(f"block {n}: {len(text)} lines (max {MAX_LINES})")
        for line in text:
            report.max_line = max(report.max_line, len(line))
        report.max_block = max(report.max_block, sum(len(ln) for ln in text))

    report.min_duration = 0.0 if shortest == float("inf") else shortest
    if report.max_block > MAX_BLOCK:
        report.problems.append(f"longest block is {report.max_block} chars (max {MAX_BLOCK})")
    return report
