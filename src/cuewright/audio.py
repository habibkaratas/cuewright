from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import run
from .profiles import Profile, TranscribeProfile

__all__ = [
    "ENHANCED_CODECS",
    "AudioLevel",
    "AudioStream",
    "NoAudioStream",
    "audio_level",
    "enhance_audio",
    "extract_audio",
    "parse_levels",
    "probe_audio",
    "require_audio",
    "raw_container_for",
]

RAW_CONTAINERS = {
    "aac": ".m4a",
    "alac": ".m4a",
    "mp3": ".mp3",
    "flac": ".flac",
    "opus": ".opus",
    "vorbis": ".ogg",
}
RAW_CONTAINER_FALLBACK = ".mka"
PCM_CONTAINER = ".wav"
PCM_CODEC_PREFIX = "pcm_"

LOSSY_BITRATE = "64k"
ENHANCED_CODECS = {
    "wav": ("-c:a", "pcm_s16le"),
    "flac": ("-c:a", "flac"),
    "m4a": ("-c:a", "aac", "-b:a", LOSSY_BITRATE),
}

FIRST_AUDIO_STREAM = "0:a:0"
QUIET_FLAGS = ("-hide_banner", "-loglevel", "error")

_MEAN = re.compile(r"mean_volume:\s*(-?[\d.]+) dB")
_PEAK = re.compile(r"max_volume:\s*(-?[\d.]+) dB")


class NoAudioStream(RuntimeError):
    def __init__(self, media: Path) -> None:
        super().__init__(f"{media} has no audio track, so there is nothing to extract")


@dataclass(frozen=True)
class AudioStream:
    codec: str
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class AudioLevel:
    mean_db: float | None
    peak_db: float | None


def probe_audio(media: str | Path) -> AudioStream | None:
    out = run(
        [
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-of",
            "json",
            str(media),
        ],
        probe=True,
    ).stdout
    streams = json.loads(out.decode("utf-8", "replace")).get("streams", [])
    if not streams:
        return None
    first = streams[0]
    return AudioStream(first["codec_name"], int(first["sample_rate"]), int(first["channels"]))


def raw_container_for(stream: AudioStream) -> str:
    if stream.codec.startswith(PCM_CODEC_PREFIX):
        return PCM_CONTAINER
    return RAW_CONTAINERS.get(stream.codec, RAW_CONTAINER_FALLBACK)


def require_audio(media: Path) -> AudioStream:
    if not media.is_file():
        raise FileNotFoundError(media)
    stream = probe_audio(media)
    if stream is None:
        raise NoAudioStream(media)
    return stream


def extract_audio(media: str | Path, output: str | Path) -> Path:
    media, output = Path(media), Path(output)
    require_audio(media)
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "-y",
            *QUIET_FLAGS,
            "-i",
            str(media),
            "-vn",
            "-map",
            FIRST_AUDIO_STREAM,
            "-c:a",
            "copy",
            str(output),
        ]
    )
    return output


def enhance_audio(media: str | Path, output: str | Path, profile: Profile | None = None) -> Path:
    media, output = Path(media), Path(output)
    profile = profile or TranscribeProfile()
    fmt = output.suffix.lower().lstrip(".")
    if fmt not in ENHANCED_CODECS:
        raise ValueError(
            f"unsupported output format {output.suffix!r}; use one of: "
            + ", ".join(ENHANCED_CODECS)
        )
    require_audio(media)
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "-y",
            *QUIET_FLAGS,
            "-i",
            str(media),
            "-vn",
            "-map",
            FIRST_AUDIO_STREAM,
            "-af",
            profile.filter_chain(),
            "-ac",
            "1",
            *ENHANCED_CODECS[fmt],
            str(output),
        ]
    )
    return output


def audio_level(
    media: str | Path, start: float | None = None, duration: float | None = None
) -> AudioLevel:
    window: list[str] = []
    if start is not None:
        window += ["-ss", f"{start:.3f}"]
    if duration is not None:
        window += ["-t", f"{duration:.3f}"]
    stderr = run(
        [
            "-hide_banner",
            "-nostats",
            *window,
            "-i",
            str(media),
            "-map",
            FIRST_AUDIO_STREAM,
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
    ).stderr
    return parse_levels(stderr.decode("utf-8", "replace"))


def parse_levels(volumedetect_output: str) -> AudioLevel:
    mean = _MEAN.search(volumedetect_output)
    peak = _PEAK.search(volumedetect_output)
    return AudioLevel(
        float(mean.group(1)) if mean else None,
        float(peak.group(1)) if peak else None,
    )
