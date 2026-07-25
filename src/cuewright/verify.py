"""Checks that catch the two ways a transcript goes wrong.

**Dropped speech.** Voice-activity detection can mistake quiet speech for
silence. Any stretch the segments do not cover is measured with ffmpeg's
``volumedetect``; a gap carrying speech-level audio is reported for review.

**Bad segments.** Repetition loops, implausible speaking rates and over-long
blocks are all detectable from the segment data alone.

Neither check can prove a transcript correct — a model that mishears the same
word consistently will pass both. They narrow down where a human should listen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ffmpeg import run
from .segments import SegmentFile

__all__ = ["Gap", "Anomaly", "VerifyReport", "verify"]

MIN_GAP = 1.0  # shorter gaps are ordinary pauses
LOUD_MARGIN = 12.0  # dB below reference that still counts as speech-level
FAST_CPS = 25.0
SLOW_CPS = 3.0
LONG_SEGMENT = 15.0

_MEAN = re.compile(r"mean_volume:\s*(-?[\d.]+) dB")
_MAX = re.compile(r"max_volume:\s*(-?[\d.]+) dB")


@dataclass
class Gap:
    start: float
    end: float
    mean_db: float | None
    peak_db: float | None
    next_id: int | None
    suspicious: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Anomaly:
    segment_id: int
    kind: str
    detail: str


@dataclass
class VerifyReport:
    speech_seconds: float
    total_seconds: float
    reference_db: float | None
    gaps: list[Gap] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return self.speech_seconds / self.total_seconds if self.total_seconds else 0.0

    @property
    def suspicious_gaps(self) -> list[Gap]:
        return [g for g in self.gaps if g.suspicious]

    @property
    def ok(self) -> bool:
        return not self.suspicious_gaps and not self.anomalies


def _measure(media: str, start: float, duration: float):
    """Mean and peak level of an interval, in dBFS."""
    stderr = run(
        [
            "-hide_banner",
            "-nostats",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(media),
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
    ).stderr.decode("utf-8", "replace")
    mean = _MEAN.search(stderr)
    peak = _MAX.search(stderr)
    return (float(mean.group(1)) if mean else None, float(peak.group(1)) if peak else None)


def verify(segments: SegmentFile, media: str | None = None) -> VerifyReport:
    """Inspect a transcript; measures audio levels when ``media`` is given."""
    segs = segments.segments
    speech = sum(s.end - s.start for s in segs)
    report = VerifyReport(speech_seconds=speech, total_seconds=segments.duration, reference_db=None)

    # --- coverage ---
    gaps: list[Gap] = []
    previous = 0.0
    for seg in segs:
        if seg.start - previous >= MIN_GAP:
            gaps.append(Gap(previous, seg.start, None, None, seg.id))
        previous = max(previous, seg.end)
    if segments.duration - previous >= MIN_GAP:
        gaps.append(Gap(previous, segments.duration, None, None, None))

    if media and gaps:
        first = segs[0]
        report.reference_db, _ = _measure(
            media, first.start, min(20.0, first.end - first.start + 15)
        )
        for gap in gaps:
            gap.mean_db, gap.peak_db = _measure(media, gap.start, gap.duration)
            if (
                gap.mean_db is not None
                and report.reference_db is not None
                and gap.mean_db > report.reference_db - LOUD_MARGIN
            ):
                gap.suspicious = True
    report.gaps = gaps

    # --- per-segment anomalies ---
    for i, seg in enumerate(segs):
        duration = seg.end - seg.start
        cps = len(seg.text) / duration if duration > 0 else 0.0
        if i and seg.text == segs[i - 1].text:
            report.anomalies.append(
                Anomaly(
                    seg.id,
                    "repeat",
                    "identical to the previous segment (possible hallucination loop)",
                )
            )
        if cps > FAST_CPS:
            report.anomalies.append(
                Anomaly(seg.id, "fast", f"{cps:.1f} chars/s — timing may be too tight")
            )
        if cps < SLOW_CPS and duration > 5:
            report.anomalies.append(
                Anomaly(
                    seg.id, "slow", f"{cps:.1f} chars/s over {duration:.1f}s — text may be missing"
                )
            )
        if duration > LONG_SEGMENT:
            report.anomalies.append(Anomaly(seg.id, "long", f"{duration:.1f}s — should be split"))

    return report
