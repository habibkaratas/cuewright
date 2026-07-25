"""SubRip (SRT) formatting: line wrapping, block splitting, reading and writing.

Two constraints drive everything here:

* A subtitle block should not exceed two lines of ~42 characters. Longer blocks
  either overflow the frame or force the viewer to read faster than they can.
* Splitting a long segment must not break a number from its unit ("400 |
  metre") or strand a conjunction at the end of a block. :func:`split_block`
  scores candidate cut points to avoid both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "Cue",
    "MAX_LINE",
    "MAX_LINES",
    "MAX_BLOCK",
    "format_timestamp",
    "parse_timestamp",
    "wrap",
    "split_block",
    "write_srt",
    "read_srt",
    "to_vtt",
]

MAX_LINE = 42
MAX_LINES = 2
MAX_BLOCK = MAX_LINE * MAX_LINES

# Preference order for a cut: sentence end, then clause, then dash.
BREAKS = (". ", "؟ ", "! ", "? ", "؛ ", "; ", ": ", "، ", ", ", " — ", " - ")

# Words that read badly when left dangling at the end of a block.
FUNCTION_WORDS = frozenset(
    """
    ve ile veya ya ki da de hem için olarak gibi ama fakat çünkü
    and or the a an of to in on at by as for from with that which but
    في من إلى على أن إن عن مع بين التي الذي
""".split()
)

_NUMERIC = re.compile(r"^[\d.,٪%]+$")
_TIMESTAMP = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


@dataclass(frozen=True)
class Cue:
    """A single subtitle block."""

    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


def format_timestamp(seconds: float, sep: str = ",") -> str:
    """Seconds to ``HH:MM:SS,mmm`` (use ``sep='.'`` for WebVTT)."""
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def parse_timestamp(text: str) -> float:
    m = _TIMESTAMP.search(text)
    if not m:
        raise ValueError(f"not a timestamp: {text!r}")
    h, mins, s, frac = m.groups()
    return int(h) * 3600 + int(mins) * 60 + int(s) + int(frac.ljust(3, "0")) / 1000


def wrap(text: str, max_line: int = MAX_LINE, max_lines: int = MAX_LINES) -> str:
    """Wrap on word boundaries into at most ``max_lines`` lines.

    Anything that still does not fit is appended to the final line rather than
    dropped — a subtitle that is slightly too wide beats one missing words.
    """
    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current = ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_line or not current:
            current = candidate
            continue
        lines.append(current)
        if len(lines) == max_lines - 1:
            # Remaining words go on the last line. Index by position (i), not
            # words.index(word): a repeated word would otherwise rewind and
            # duplicate part of the text.
            lines.append(" ".join(words[i:]))
            current = ""
            break
        current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _cut_score(text: str, pos: int, mid: float) -> float:
    """Lower is better. Penalises cuts that separate a number from its unit."""
    score = abs(pos - mid)
    before = text[:pos].split()
    if before:
        last = before[-1].strip(".,;:،؛").lower()
        if _NUMERIC.match(last):
            score += 1000
        elif last in FUNCTION_WORDS:
            score += 500
    return score


def split_block(text: str, start: float, end: float, max_chars: int = MAX_BLOCK) -> list[Cue]:
    """Split an over-long segment into cues, apportioning time by length."""
    text = text.strip()
    if len(text) <= max_chars:
        return [Cue(start, end, text)]

    mid = len(text) / 2
    lo, hi = 0.2 * len(text), 0.8 * len(text)
    cut: int | None = None

    for br in BREAKS:
        positions = [i + len(br) for i in range(len(text)) if text.startswith(br, i)]
        positions = [p for p in positions if lo < p < hi]
        if positions:
            cut = min(positions, key=lambda p: abs(p - mid))
            break

    if cut is None:
        spaces = [i for i, c in enumerate(text) if c == " " and lo < i < hi]
        if not spaces:
            return [Cue(start, end, text)]
        cut = min(spaces, key=lambda p: _cut_score(text, p, mid))

    left, right = text[:cut].strip(), text[cut:].strip()
    if not left or not right:
        return [Cue(start, end, text)]

    boundary = start + (end - start) * (len(left) / (len(left) + len(right)))
    return split_block(left, start, boundary, max_chars) + split_block(
        right, boundary, end, max_chars
    )


def write_srt(cues, path, *, split: bool = True, encoding: str = "utf-8-sig") -> int:
    """Write cues to an SRT file, optionally splitting over-long blocks.

    Returns the number of blocks written.
    """
    blocks: list[Cue] = []
    for cue in cues:
        if not isinstance(cue, Cue):
            cue = Cue(cue["start"], cue["end"], cue["text"])
        blocks.extend(split_block(cue.text, cue.start, cue.end) if split else [cue])

    with open(path, "w", encoding=encoding, newline="\n") as fh:
        for i, cue in enumerate(blocks, 1):
            fh.write(
                f"{i}\n{format_timestamp(cue.start)} --> "
                f"{format_timestamp(cue.end)}\n{wrap(cue.text)}\n\n"
            )
    return len(blocks)


def read_srt(path, encoding: str = "utf-8-sig") -> list[Cue]:
    raw = open(path, encoding=encoding).read().strip()
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_s, end_s = lines[1].split("-->")
        cues.append(Cue(parse_timestamp(start_s), parse_timestamp(end_s), " ".join(lines[2:])))
    return cues


def to_vtt(cues, path, encoding: str = "utf-8") -> int:
    """Write cues as WebVTT, for browser-based players."""
    with open(path, "w", encoding=encoding, newline="\n") as fh:
        fh.write("WEBVTT\n\n")
        blocks = [c for cue in cues for c in split_block(cue.text, cue.start, cue.end)]
        for i, cue in enumerate(blocks, 1):
            fh.write(
                f"{i}\n{format_timestamp(cue.start, '.')} --> "
                f"{format_timestamp(cue.end, '.')}\n{wrap(cue.text)}\n\n"
            )
    return len(blocks)
