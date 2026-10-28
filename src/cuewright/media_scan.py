from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

__all__ = ["MEDIA_SUFFIXES", "collect_media", "mirrored_folder"]

MEDIA_SUFFIXES = frozenset(
    {
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".m4v",
        ".ts",
        ".wav",
        ".mp3",
        ".m4a",
        ".flac",
        ".ogg",
        ".opus",
        ".mka",
    }
)


def _scan(folder: Path, exclude: Callable[[Path], bool]) -> list[Path]:
    return sorted(
        candidate
        for candidate in folder.rglob("*")
        if candidate.is_file()
        and candidate.suffix.lower() in MEDIA_SUFFIXES
        and not exclude(candidate)
    )


def collect_media(
    inputs: Iterable[str | Path], exclude: Callable[[Path], bool] = lambda _: False
) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            found.extend((path, candidate) for candidate in _scan(path, exclude))
        elif path.is_file():
            found.append((path.parent, path))
        else:
            raise FileNotFoundError(path)
    return found


def mirrored_folder(media: Path, root: Path, out_dir: Path | None) -> Path:
    if out_dir is None:
        return media.parent
    return out_dir / media.parent.relative_to(root)
