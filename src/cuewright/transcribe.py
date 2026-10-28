"""Speech-to-text with faster-whisper, producing timestamped segments.

Two non-default options matter enough to hard-code:

``vad_filter=True``
    Whisper hallucinates confidently over silence and music. Voice-activity
    detection removes those stretches before they reach the decoder.
``condition_on_previous_text=False``
    Feeding the previous text back in makes the model prone to repetition
    loops, which is especially visible in Arabic. Losing a little cross-segment
    context is the cheaper trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .segments import Segment, SegmentFile
from .srt import format_timestamp

__all__ = ["TranscribeOptions", "transcribe"]


@dataclass
class TranscribeOptions:
    model: str = "large-v3"
    language: str | None = None  # None => autodetect
    task: str = "transcribe"  # or "translate" (to English)
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    cpu_threads: int = 0  # 0 => let CTranslate2 decide
    vad: bool = True
    min_silence_ms: int = 500


def transcribe(media, options: TranscribeOptions | None = None, progress=None) -> SegmentFile:
    """Transcribe ``media`` and return its segments.

    ``progress`` is called as ``progress(fraction, segment)`` after each
    segment, so callers can render whatever status display they like.
    """
    from faster_whisper import WhisperModel  # imported lazily: heavy

    options = options or TranscribeOptions()
    media = Path(media)
    if not media.is_file():
        raise FileNotFoundError(media)

    model = WhisperModel(
        options.model,
        device=options.device,
        compute_type=options.compute_type,
        cpu_threads=options.cpu_threads,
    )

    raw_segments, info = model.transcribe(
        str(media),
        language=options.language,
        task=options.task,
        beam_size=options.beam_size,
        vad_filter=options.vad,
        vad_parameters={"min_silence_duration_ms": options.min_silence_ms},
        condition_on_previous_text=False,
    )

    segments: list[Segment] = []
    for raw in raw_segments:
        text = raw.text.strip()
        if not text:
            continue
        segment = Segment(
            id=len(segments) + 1,
            start=raw.start,
            end=raw.end,
            text=text,
            no_speech_prob=raw.no_speech_prob,
            avg_logprob=raw.avg_logprob,
        )
        segments.append(segment)
        if progress:
            fraction = min(raw.end / info.duration, 1.0) if info.duration else 0.0
            progress(fraction, segment)

    if not segments:
        raise RuntimeError("no speech detected — check the audio track")

    return SegmentFile(
        source=str(media.resolve()),
        duration=info.duration,
        model=options.model,
        language=info.language,
        segments=segments,
    )


def describe(segment: Segment) -> str:
    """One-line rendering used by the CLI progress display."""
    return f"{format_timestamp(segment.start)}  {segment.text[:60]}"
