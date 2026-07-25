"""Locating and running the ffmpeg toolchain.

ffmpeg is an external dependency, not a Python package, so it has to be found
at runtime. Resolution order:

1. ``SUBFORGE_FFMPEG`` / ``SUBFORGE_FFPROBE`` environment variables
2. ``ffmpeg`` / ``ffprobe`` on ``PATH``
3. A ``tools/`` directory next to the project root (where a downloaded static
   build is commonly unpacked on Windows)

Raising a clear error here is worth the effort: "ffmpeg not found" with install
instructions saves far more time than a stray ``FileNotFoundError`` from
``subprocess``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import cache
from pathlib import Path

__all__ = ["ffmpeg_path", "ffprobe_path", "run", "probe_duration", "FFmpegNotFound"]


class FFmpegNotFound(RuntimeError):
    """Raised when neither ffmpeg nor ffprobe can be located."""


_INSTALL_HINT = """\
ffmpeg is required but was not found.

  Windows : winget install Gyan.FFmpeg   (or unpack a static build into tools/)
  macOS   : brew install ffmpeg
  Debian  : sudo apt install ffmpeg

Alternatively set SUBFORGE_FFMPEG=/path/to/ffmpeg (and SUBFORGE_FFPROBE)."""


def _search_tools_dir(name: str) -> str | None:
    """Look for a static build unpacked under <project>/tools/."""
    root = Path(__file__).resolve().parents[2]
    tools = root / "tools"
    if not tools.is_dir():
        return None
    for candidate in tools.rglob(name):
        if candidate.is_file():
            return str(candidate)
        # rglob on Windows matches "ffmpeg" against "ffmpeg.exe" only if the
        # suffix is given, so try both spellings explicitly.
    for candidate in tools.rglob(name + ".exe"):
        if candidate.is_file():
            return str(candidate)
    return None


@cache
def _resolve(name: str, env_var: str) -> str:
    override = os.environ.get(env_var)
    if override:
        if not Path(override).is_file():
            raise FFmpegNotFound(f"{env_var} points at a missing file: {override}")
        return override

    found = shutil.which(name) or _search_tools_dir(name)
    if not found:
        raise FFmpegNotFound(_INSTALL_HINT)
    return found


def ffmpeg_path() -> str:
    return _resolve("ffmpeg", "SUBFORGE_FFMPEG")


def ffprobe_path() -> str:
    return _resolve("ffprobe", "SUBFORGE_FFPROBE")


def run(
    args: list[str], *, probe: bool = False, capture: bool = True, stdin_bytes: bytes | None = None
) -> subprocess.CompletedProcess:
    """Invoke ffmpeg/ffprobe, raising with captured stderr on failure."""
    exe = ffprobe_path() if probe else ffmpeg_path()
    proc = subprocess.run(
        [exe, *args],
        input=stdin_bytes,
        capture_output=capture,
        text=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        tool = "ffprobe" if probe else "ffmpeg"
        raise RuntimeError(f"{tool} failed (exit {proc.returncode}):\n{err[-2000:]}")
    return proc


def probe_duration(path: str | os.PathLike[str]) -> float:
    """Container duration in seconds."""
    out = run(
        ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        probe=True,
    ).stdout
    return float(out.decode().strip())
