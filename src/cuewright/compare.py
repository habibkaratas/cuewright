"""Cross-checking two transcription passes against each other.

Decoding the same audio twice with different settings — typically with and
without the VAD filter — gives an independent second opinion. Where the passes
agree the transcript is dependable; where they diverge the model was unsure,
and those are exactly the places worth listening to.

The limit is worth stating plainly: both passes usually share a model, so a
mistake the model makes *consistently* survives this check. It finds
uncertainty, not truth.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .segments import Segment, SegmentFile

__all__ = ["Divergence", "CompareReport", "compare", "normalise"]

_DIACRITICS = re.compile(r"[ً-ْٰـ]")
_PUNCT = re.compile(r"[.,،؛:!؟?\"'()\-—…]")

# Orthographic variants that should not count as disagreements.
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def normalise(text: str) -> list[str]:
    text = _DIACRITICS.sub("", text)
    text = _PUNCT.sub(" ", text)
    return text.translate(_FOLD).split()


@dataclass
class Divergence:
    kind: str  # "replace" | "delete" | "insert"
    context: str
    a_text: str
    b_text: str


@dataclass
class CompareReport:
    a_words: int
    b_words: int
    similarity: float
    divergences: list[Divergence] = field(default_factory=list)
    only_in_b: list[Segment] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return not self.divergences and not self.only_in_b


def compare(a: SegmentFile, b: SegmentFile) -> CompareReport:
    """Compare pass ``a`` (the one you intend to keep) against pass ``b``."""
    words_a, words_b = (normalise(" ".join(s.text for s in f.segments)) for f in (a, b))
    matcher = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)

    report = CompareReport(len(words_a), len(words_b), matcher.ratio())
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        report.divergences.append(
            Divergence(
                kind=tag,
                context=(
                    " ".join(words_a[max(0, i1 - 4) : i1]) + " … " + " ".join(words_a[i2 : i2 + 4])
                ),
                a_text=" ".join(words_a[i1:i2]) or "(nothing)",
                b_text=" ".join(words_b[j1:j2]) or "(nothing)",
            )
        )

    # Speech that pass B found where pass A has no coverage at all.
    spans = [(s.start, s.end) for s in a.segments]
    for seg in b.segments:
        overlap = sum(max(0.0, min(seg.end, e) - max(seg.start, s)) for s, e in spans)
        if overlap < (seg.end - seg.start) * 0.5:
            report.only_in_b.append(seg)

    return report
