from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

__all__ = ["PROFILES", "ListenProfile", "Profile", "ProfileError", "TranscribeProfile"]

MIN_TEMPO = 0.5
MAX_TEMPO = 2.0


class ProfileError(ValueError):
    pass


def _highpass(hz: int, stages: int) -> list[str]:
    return [f"highpass=f={hz}"] * stages if hz > 0 else []


@dataclass(frozen=True)
class TranscribeProfile:
    tag: ClassVar[str] = "clean"

    highpass_hz: int = 200
    highpass_stages: int = 2
    noise_reduction_db: float = 18.0
    noise_floor_db: float = -45.0
    compressor_threshold_db: float = -20.0
    compressor_ratio: float = 3.0
    compressor_attack_ms: float = 5.0
    compressor_release_ms: float = 120.0
    normaliser_frame_ms: int = 500
    normaliser_window: int = 31
    target_peak: float = 0.95
    target_rms: float = 0.2
    max_gain_db: float = 26.0
    sample_rate: int = 16000

    @property
    def max_gain_factor(self) -> float:
        return 10 ** (self.max_gain_db / 20)

    def filter_chain(self) -> str:
        stages = _highpass(self.highpass_hz, self.highpass_stages)
        if self.noise_reduction_db > 0:
            stages.append(f"afftdn=nr={self.noise_reduction_db}:nf={self.noise_floor_db}:tn=1")
        stages.append(
            f"acompressor=threshold={self.compressor_threshold_db}dB"
            f":ratio={self.compressor_ratio}"
            f":attack={self.compressor_attack_ms}:release={self.compressor_release_ms}"
        )
        stages.append(
            f"dynaudnorm=f={self.normaliser_frame_ms}:g={self.normaliser_window}"
            f":p={self.target_peak}:m={self.max_gain_factor:.3f}:r={self.target_rms}"
        )
        stages.append(f"aresample={self.sample_rate}")
        return ",".join(stages)


@dataclass(frozen=True)
class ListenProfile:
    tag: ClassVar[str] = "listen"

    highpass_hz: int = 250
    lowpass_hz: int = 3400
    filter_stages: int = 2
    denoise_strength: float = 0.003
    denoise_patch_s: float = 0.002
    denoise_research_s: float = 0.006
    burst_threshold_db: float = -30.0
    burst_ratio: float = 20.0
    burst_attack_ms: float = 1.0
    burst_release_ms: float = 200.0
    presence_boosts: tuple[tuple[int, float], ...] = ((1000, 2.0), (2000, 3.0))
    loudness_lufs: float = -18.0
    true_peak_db: float = -1.5
    loudness_range: float = 7.0
    tempo: float = 1.0
    sample_rate: int = 16000

    def __post_init__(self) -> None:
        if not MIN_TEMPO <= self.tempo <= MAX_TEMPO:
            raise ProfileError(
                f"tempo {self.tempo} is out of range; use {MIN_TEMPO}-{MAX_TEMPO} "
                "(0.8 plays at 80% speed)"
            )
        if 0 < self.lowpass_hz <= self.highpass_hz:
            raise ProfileError(
                f"lowpass {self.lowpass_hz} Hz must be above highpass {self.highpass_hz} Hz"
            )

    def filter_chain(self) -> str:
        stages = _highpass(self.highpass_hz, self.filter_stages)
        if self.lowpass_hz > 0:
            stages += [f"lowpass=f={self.lowpass_hz}"] * self.filter_stages
        stages.append(
            f"anlmdn=s={self.denoise_strength}:p={self.denoise_patch_s}:r={self.denoise_research_s}"
        )
        stages.append(
            f"acompressor=threshold={self.burst_threshold_db}dB:ratio={self.burst_ratio}"
            f":attack={self.burst_attack_ms}:release={self.burst_release_ms}"
        )
        stages += [f"equalizer=f={hz}:t=q:w=1.0:g={gain}" for hz, gain in self.presence_boosts]
        if self.tempo != 1.0:
            stages.append(f"atempo={self.tempo}")
        stages.append(
            f"loudnorm=I={self.loudness_lufs}:TP={self.true_peak_db}:LRA={self.loudness_range}"
        )
        stages.append(f"aresample={self.sample_rate}")
        return ",".join(stages)


Profile = TranscribeProfile | ListenProfile

PROFILES: dict[str, type[TranscribeProfile] | type[ListenProfile]] = {
    "transcribe": TranscribeProfile,
    "listen": ListenProfile,
}
