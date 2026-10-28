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

from dataclasses import dataclass, field

from .audio import audio_level
from .hallucinations import NO_SPEECH_LIMIT, is_boilerplate
from .segments import Segment, SegmentFile

__all__ = ["Gap", "Anomaly", "VerifyReport", "verify"]

MIN_GAP = 1.0  # shorter gaps are ordinary pauses
LOUD_MARGIN = 12.0  # dB below reference that still counts as speech-level
FAST_CPS = 25.0
SLOW_CPS = 3.0
LONG_SEGMENT = 15.0


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
        reference = audio_level(media, first.start, min(20.0, first.end - first.start + 15))
        report.reference_db = reference.mean_db
        for gap in gaps:
            level = audio_level(media, gap.start, gap.duration)
            gap.mean_db, gap.peak_db = level.mean_db, level.peak_db
            if (
                gap.mean_db is not None
                and report.reference_db is not None
                and gap.mean_db > report.reference_db - LOUD_MARGIN
            ):
                gap.suspicious = True
    report.gaps = gaps

    report.anomalies = segment_anomalies(segs)
    return report


def _rate_anomalies(seg: Segment) -> list[Anomaly]:
    duration = seg.end - seg.start
    cps = len(seg.text) / duration if duration > 0 else 0.0
    found: list[Anomaly] = []
    if cps > FAST_CPS:
        found.append(Anomaly(seg.id, "fast", f"{cps:.1f} chars/s — timing may be too tight"))
    if cps < SLOW_CPS and duration > 5:
        found.append(
            Anomaly(seg.id, "slow", f"{cps:.1f} chars/s over {duration:.1f}s — text may be missing")
        )
    if duration > LONG_SEGMENT:
        found.append(Anomaly(seg.id, "long", f"{duration:.1f}s — should be split"))
    return found


def _hallucination_anomalies(seg: Segment) -> list[Anomaly]:
    found: list[Anomaly] = []
    if is_boilerplate(seg.text):
        found.append(
            Anomaly(
                seg.id,
                "boilerplate",
                f"{seg.text!r} is a stock phrase Whisper invents over noise; "
                "listen before trusting it",
            )
        )
    if seg.no_speech_prob is not None and seg.no_speech_prob >= NO_SPEECH_LIMIT:
        found.append(
            Anomaly(
                seg.id,
                "no-speech",
                f"the model rated this {seg.no_speech_prob:.0%} likely to be non-speech",
            )
        )
    return found


def segment_anomalies(segs: list[Segment]) -> list[Anomaly]:
    anomalies: list[Anomaly] = []
    for i, seg in enumerate(segs):
        if i and seg.text == segs[i - 1].text:
            anomalies.append(
                Anomaly(
                    seg.id,
                    "repeat",
                    "identical to the previous segment (possible hallucination loop)",
                )
            )
        anomalies += _rate_anomalies(seg)
        anomalies += _hallucination_anomalies(seg)
    return anomalies
