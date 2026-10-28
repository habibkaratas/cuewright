from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audio import FIRST_AUDIO_STREAM, QUIET_FLAGS, require_audio
from .ffmpeg import run

__all__ = ["SpectrogramOptions", "default_spectrogram_path", "render_spectrogram"]

SPECTROGRAM_TAG = "spectrogram"
SPECTROGRAM_SUFFIX = ".png"
PICTURE = "picture"


@dataclass(frozen=True)
class SpectrogramOptions:
    start: float | None = None
    duration: float | None = None
    max_hz: int = 4000
    width: int = 1600
    height: int = 400
    log_scale: bool = True

    def filter_graph(self) -> str:
        scale = "log" if self.log_scale else "lin"
        return (
            f"[{FIRST_AUDIO_STREAM}]aresample={self.max_hz * 2},"
            f"showspectrumpic=s={self.width}x{self.height}:legend=1:scale={scale}[{PICTURE}]"
        )

    def window_args(self) -> list[str]:
        window: list[str] = []
        if self.start is not None:
            window += ["-ss", f"{self.start:.3f}"]
        if self.duration is not None:
            window += ["-t", f"{self.duration:.3f}"]
        return window


def default_spectrogram_path(media: Path, options: SpectrogramOptions) -> Path:
    window = ""
    if options.start is not None or options.duration is not None:
        start = options.start or 0.0
        end = "end" if options.duration is None else f"{start + options.duration:g}s"
        window = f".{start:g}s-{end}"
    return media.with_name(f"{media.stem}{window}.{SPECTROGRAM_TAG}{SPECTROGRAM_SUFFIX}")


def render_spectrogram(
    media: str | Path, output: str | Path | None = None, options: SpectrogramOptions | None = None
) -> Path:
    media = Path(media)
    options = options or SpectrogramOptions()
    target = Path(output) if output else default_spectrogram_path(media, options)
    if target.suffix.lower() != SPECTROGRAM_SUFFIX:
        raise ValueError(f"spectrogram output must be a {SPECTROGRAM_SUFFIX} file, got {target}")
    require_audio(media)
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "-y",
            *QUIET_FLAGS,
            *options.window_args(),
            "-i",
            str(media),
            "-filter_complex",
            options.filter_graph(),
            "-map",
            f"[{PICTURE}]",
            "-frames:v",
            "1",
            str(target),
        ]
    )
    return target
