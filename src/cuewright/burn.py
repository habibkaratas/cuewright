"""Burning subtitles into the picture (hardsub).

ffmpeg's ``subtitles`` filter parses its argument as a filtergraph string, so
Windows paths break it twice over: backslashes read as escapes and the drive
colon as an option separator. Copying the subtitle file into a temporary
directory under a fixed name and running ffmpeg with that directory as its
working directory sidesteps the quoting problem entirely.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import ffmpeg_path

__all__ = ["BurnStyle", "burn"]


@dataclass
class BurnStyle:
    """libass style overrides. Sizes are in the video's own pixel space."""

    font: str = "Arial"
    font_size: int = 22
    outline: int = 2
    shadow: int = 0
    margin_v: int = 28
    primary: str = "&H00FFFFFF"  # white
    outline_colour: str = "&H00000000"  # black
    alignment: int = 2  # bottom-centre

    def to_force_style(self) -> str:
        return (
            f"FontName={self.font},FontSize={self.font_size},"
            f"PrimaryColour={self.primary},OutlineColour={self.outline_colour},"
            f"BorderStyle=1,Outline={self.outline},Shadow={self.shadow},"
            f"MarginV={self.margin_v},Alignment={self.alignment}"
        )


def burn(
    video,
    subtitles,
    output,
    *,
    style: BurnStyle | None = None,
    crf: int = 20,
    preset: str = "medium",
    copy_audio: bool = True,
) -> Path:
    """Render ``subtitles`` onto ``video``.

    The audio stream is copied untouched by default; only the video is
    re-encoded, because drawing text necessarily changes the picture.
    """
    video, subtitles, output = Path(video), Path(subtitles), Path(output)
    for path in (video, subtitles):
        if not path.is_file():
            raise FileNotFoundError(path)
    ffmpeg_path()  # fail early with a helpful message if it is missing

    style = style or BurnStyle()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "subs.srt"
        shutil.copyfile(subtitles, staged)
        vf = f"subtitles=subs.srt:charenc=UTF-8:force_style='{style.to_force_style()}'"

        import subprocess

        proc = subprocess.run(
            [
                ffmpeg_path(),
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stats",
                "-i",
                str(video.resolve()),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                preset,
                "-crf",
                str(crf),
                "-c:a",
                "copy" if copy_audio else "aac",
                str(output.resolve()),
            ],
            cwd=tmp,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed while burning subtitles (exit {proc.returncode})")
    return output
