from __future__ import annotations

from pathlib import Path

import pytest

from cuewright.audio import NoAudioStream
from cuewright.ffmpeg import FFmpegNotFound, ffmpeg_path, run
from cuewright.spectrogram import SpectrogramOptions, default_spectrogram_path, render_spectrogram

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def test_default_path_sits_next_to_the_media():
    path = default_spectrogram_path(Path("day/clip.mp4"), SpectrogramOptions())
    assert path == Path("day/clip.spectrogram.png")


def test_default_path_names_the_window():
    options = SpectrogramOptions(start=72, duration=16)
    assert (
        default_spectrogram_path(Path("clip.mp4"), options).name == "clip.72s-88s.spectrogram.png"
    )


def test_default_path_with_open_ended_window():
    options = SpectrogramOptions(start=30)
    assert (
        default_spectrogram_path(Path("clip.mp4"), options).name == "clip.30s-end.spectrogram.png"
    )


def test_resampling_puts_max_hz_at_nyquist():
    assert "aresample=8000" in SpectrogramOptions(max_hz=4000).filter_graph()


def test_linear_scale_is_selectable():
    assert "scale=lin" in SpectrogramOptions(log_scale=False).filter_graph()


def test_rejects_non_png_output(tmp_path):
    with pytest.raises(ValueError, match="png"):
        render_spectrogram(tmp_path / "clip.wav", tmp_path / "out.jpg")


def _ffmpeg_available() -> bool:
    try:
        ffmpeg_path()
    except FFmpegNotFound:
        return False
    return True


needs_ffmpeg = pytest.mark.skipif(
    not _ffmpeg_available(), reason="ffmpeg not found; set CUEWRIGHT_FFMPEG to run this"
)


@needs_ffmpeg
def test_renders_a_png_for_a_window(tmp_path):
    source = tmp_path / "tone.wav"
    run(["-y", "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=8000:duration=3", str(source)])
    out = render_spectrogram(source, options=SpectrogramOptions(start=1, duration=1, width=320))
    assert out == tmp_path / "tone.1s-2s.spectrogram.png"
    assert out.read_bytes().startswith(PNG_SIGNATURE)


@needs_ffmpeg
def test_refuses_media_without_audio(tmp_path):
    clip = tmp_path / "mute.mp4"
    run(["-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1", str(clip)])
    with pytest.raises(NoAudioStream):
        render_spectrogram(clip)
