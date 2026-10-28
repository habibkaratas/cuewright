from __future__ import annotations

import pytest

from cuewright.audio import (
    AudioLevel,
    AudioStream,
    NoAudioStream,
    enhance_audio,
    extract_audio,
    parse_levels,
    probe_audio,
    raw_container_for,
)
from cuewright.cli import is_enhance_output, output_paths
from cuewright.ffmpeg import FFmpegNotFound, ffmpeg_path, probe_duration, run
from cuewright.media_scan import collect_media, mirrored_folder
from cuewright.profiles import TranscribeProfile


def test_filter_chain_carries_every_tunable():
    options = TranscribeProfile(
        highpass_hz=150, noise_reduction_db=9, max_gain_db=20, sample_rate=22050
    )
    chain = options.filter_chain()
    assert chain.count("highpass=f=150") == 2
    assert "afftdn=nr=9" in chain
    assert "m=10.000" in chain
    assert chain.endswith("aresample=22050")


def test_zero_noise_reduction_drops_the_denoiser():
    assert "afftdn" not in TranscribeProfile(noise_reduction_db=0).filter_chain()


def test_zero_highpass_drops_the_filter():
    assert "highpass" not in TranscribeProfile(highpass_hz=0).filter_chain()


def test_raw_container_follows_codec():
    assert raw_container_for(AudioStream("aac", 8000, 1)) == ".m4a"
    assert raw_container_for(AudioStream("pcm_s16le", 44100, 2)) == ".wav"
    assert raw_container_for(AudioStream("truehd", 48000, 6)) == ".mka"


def test_parse_levels_reads_volumedetect_output():
    text = (
        "[Parsed_volumedetect_0 @ 0] mean_volume: -28.1 dB\n"
        "[Parsed_volumedetect_0 @ 0] max_volume: -0.5 dB\n"
    )
    assert parse_levels(text) == AudioLevel(-28.1, -0.5)


def test_parse_levels_without_audio_is_unmeasured():
    assert parse_levels("") == AudioLevel(None, None)


def test_enhance_outputs_are_recognised_by_tag(tmp_path):
    assert is_enhance_output(tmp_path / "clip.clean.wav")
    assert is_enhance_output(tmp_path / "clip.audio.m4a")
    assert is_enhance_output(tmp_path / "clip.listen.flac")
    assert not is_enhance_output(tmp_path / "clip.mp4")


def test_collect_media_scans_directories_and_skips_own_outputs(tmp_path):
    (tmp_path / "a").mkdir()
    for name in ("a/one.mp4", "a/one.clean.wav", "a/one.audio.m4a", "two.MKV", "notes.txt"):
        (tmp_path / name).write_bytes(b"")
    found = [
        media.relative_to(tmp_path).as_posix()
        for _, media in collect_media([str(tmp_path)], exclude=is_enhance_output)
    ]
    assert found == ["a/one.mp4", "two.MKV"]


def test_collect_media_accepts_an_explicit_file_whatever_its_suffix(tmp_path):
    clip = tmp_path / "clip.bin"
    clip.write_bytes(b"")
    assert collect_media([str(clip)]) == [(tmp_path, clip)]


def test_collect_media_rejects_a_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        collect_media([str(tmp_path / "nope.mp4")])


def test_output_paths_mirror_the_scanned_tree(tmp_path):
    media = tmp_path / "day" / "clip.mp4"
    folder = mirrored_folder(media, tmp_path, tmp_path / "out")
    raw, clean = output_paths(media, folder, "flac", ".m4a", "clean")
    assert raw == tmp_path / "out" / "day" / "clip.audio.m4a"
    assert clean == tmp_path / "out" / "day" / "clip.clean.flac"


def test_output_folder_defaults_to_the_media_folder(tmp_path):
    media = tmp_path / "clip.mp4"
    assert mirrored_folder(media, tmp_path, None) == tmp_path


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
def test_enhance_writes_mono_at_the_requested_rate(tmp_path):
    source = tmp_path / "tone.wav"
    run(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=8000:duration=2",
            "-ac",
            "2",
            str(source),
        ]
    )
    clean = enhance_audio(source, tmp_path / "tone.clean.wav", TranscribeProfile(sample_rate=16000))
    assert probe_audio(clean) == AudioStream("pcm_s16le", 16000, 1)
    assert abs(probe_duration(clean) - 2.0) < 0.1


@needs_ffmpeg
def test_media_without_audio_is_refused(tmp_path):
    clip = tmp_path / "mute.mp4"
    run(["-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1", str(clip)])
    assert probe_audio(clip) is None
    with pytest.raises(NoAudioStream):
        extract_audio(clip, tmp_path / "mute.audio.m4a")
