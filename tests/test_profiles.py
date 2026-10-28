from __future__ import annotations

import pytest

from cuewright.cli import build_parser, build_profile
from cuewright.profiles import ListenProfile, ProfileError, TranscribeProfile


def parse_enhance(*flags: str):
    return build_parser().parse_args(["enhance", "clip.mp4", *flags])


def test_listen_chain_keeps_the_speech_band_and_squashes_bursts():
    chain = ListenProfile().filter_chain()
    assert chain.count("highpass=f=250") == 2
    assert chain.count("lowpass=f=3400") == 2
    assert "anlmdn=" in chain
    assert "acompressor=threshold=-30.0dB:ratio=20.0" in chain
    assert "loudnorm=I=-18.0" in chain
    assert "atempo" not in chain


def test_listen_tempo_is_applied_before_loudness():
    chain = ListenProfile(tempo=0.8).filter_chain()
    assert chain.index("atempo=0.8") < chain.index("loudnorm")


def test_listen_lowpass_can_be_disabled():
    assert "lowpass" not in ListenProfile(lowpass_hz=0).filter_chain()


@pytest.mark.parametrize("tempo", [0.3, 2.5])
def test_listen_rejects_tempo_out_of_range(tempo):
    with pytest.raises(ProfileError, match="tempo"):
        ListenProfile(tempo=tempo)


def test_listen_rejects_a_band_that_is_upside_down():
    with pytest.raises(ProfileError, match="lowpass"):
        ListenProfile(highpass_hz=3000, lowpass_hz=2000)


def test_profiles_write_distinct_tags():
    assert TranscribeProfile.tag != ListenProfile.tag


def test_default_profile_is_transcribe():
    assert build_profile(parse_enhance()) == TranscribeProfile()


def test_flags_override_profile_defaults():
    profile = build_profile(
        parse_enhance("--profile", "listen", "--tempo", "0.8", "--highpass", "300")
    )
    assert profile == ListenProfile(tempo=0.8, highpass_hz=300)


def test_transcribe_only_flag_is_refused_for_listen():
    with pytest.raises(ProfileError, match="--denoise"):
        build_profile(parse_enhance("--profile", "listen", "--denoise", "12"))


def test_listen_only_flag_is_refused_for_transcribe():
    with pytest.raises(ProfileError, match="--tempo"):
        build_profile(parse_enhance("--tempo", "0.8"))
