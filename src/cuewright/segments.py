"""The segment file: the pivot between transcription and every later stage.

Transcription writes ``<name>.segments.json``; translation, subtitle building
and verification all read it. Keeping timestamps in one place is what lets
several language tracks stay frame-accurate with each other — a translation
never invents its own timing, it only supplies text for an existing id.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = ["Segment", "SegmentFile", "load_translation", "TranslationError"]

_LINE = re.compile(r"^\s*\[(\d+)\]\s*(.*)$")


class TranslationError(ValueError):
    """Raised when a translation file does not line up with the segments."""


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    no_speech_prob: float | None = None
    avg_logprob: float | None = None


@dataclass
class SegmentFile:
    source: str
    duration: float
    model: str
    language: str
    segments: list[Segment]

    @classmethod
    def load(cls, path) -> SegmentFile:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            source=data.get("source", ""),
            duration=float(data["duration"]),
            model=data.get("model", ""),
            language=data.get("language", ""),
            segments=[Segment(**s) for s in data["segments"]],
        )

    def save(self, path) -> None:
        payload = asdict(self)
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    def limit_of(self, index: int) -> float:
        """Where segment ``index`` must yield to the next one."""
        if index + 1 < len(self.segments):
            return self.segments[index + 1].start
        return self.duration


def load_translation(path, expected_ids) -> dict[int, str]:
    """Read a ``[id] text`` translation file and check it against the segments.

    Any mismatch raises rather than silently producing shifted subtitles: one
    skipped line would slide every later cue onto the wrong shot, which is far
    harder to notice than an error at build time.
    """
    translations: dict[int, str] = {}
    duplicates: list[int] = []

    with open(path, encoding="utf-8-sig") as fh:
        for lineno, line in enumerate(fh, 1):
            if not line.strip():
                continue
            match = _LINE.match(line)
            if not match:
                raise TranslationError(
                    f"{path}:{lineno} expected '[id] text', got: {line.strip()!r}"
                )
            seg_id, text = int(match.group(1)), match.group(2).strip()
            if seg_id in translations:
                duplicates.append(seg_id)
            translations[seg_id] = text

    expected = set(expected_ids)
    problems = []
    if missing := sorted(expected - translations.keys()):
        problems.append(f"{len(missing)} missing id(s): {missing[:20]}")
    if extra := sorted(translations.keys() - expected):
        problems.append(f"{len(extra)} unknown id(s): {extra[:20]}")
    if duplicates:
        problems.append(f"{len(duplicates)} duplicate id(s): {sorted(set(duplicates))[:20]}")
    if empty := sorted(i for i, t in translations.items() if not t):
        problems.append(f"{len(empty)} empty translation(s): {empty[:20]}")
    if problems:
        raise TranslationError("; ".join(problems))

    return translations
