from __future__ import annotations

import pytest

from cuewright.hallucinations import is_boilerplate, normalise_phrase
from cuewright.segments import Segment, SegmentFile
from cuewright.verify import verify


def kinds_for(segment: Segment) -> set[str]:
    report = verify(SegmentFile("v.wav", 40.0, "large-v3", "tr", [segment]))
    return {anomaly.kind for anomaly in report.anomalies}


def test_normalise_folds_case_accents_and_punctuation():
    assert (
        normalise_phrase("İzlediğiniz için teşekkür ederim.") == "izlediginiz icin tesekkur ederim"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Altyazı M.K.",
        "İzlediğiniz için teşekkür ederim.",
        "Thank you.",
        "God bless you.",
        "Продолжение следует...",
        "Субтитры сделал DimaTorzok",
        "Дякую за перегляд!",
        "Terima kasih telah menonton.",
    ],
)
def test_stock_phrases_seen_over_camera_noise_are_recognised(text):
    assert is_boilerplate(text)


@pytest.mark.parametrize(
    "text",
    [
        "Thank you for the glass samples, they arrived today.",
        "Toplantı odası şu an boş, birazdan gelir.",
        "Он сказал спасибо и ушёл.",
    ],
)
def test_real_sentences_containing_thanks_are_not_flagged(text):
    assert not is_boilerplate(text)


def test_verify_flags_boilerplate_segment():
    assert "boilerplate" in kinds_for(Segment(1, 0.0, 30.0, "Altyazı M.K."))


def test_verify_flags_segment_the_model_rated_as_non_speech():
    segment = Segment(1, 0.0, 3.0, "hello there", no_speech_prob=0.78, avg_logprob=-0.4)
    assert "no-speech" in kinds_for(segment)


def test_verify_trusts_confident_speech():
    segment = Segment(1, 0.0, 3.0, "hello there friend", no_speech_prob=0.02, avg_logprob=-0.2)
    assert kinds_for(segment) == set()


def test_segment_files_without_scores_still_load(tmp_path):
    path = tmp_path / "old.segments.json"
    path.write_text(
        '{"duration": 5.0, "segments": [{"id": 1, "start": 0.0, "end": 2.0, "text": "hi"}]}',
        encoding="utf-8",
    )
    segment = SegmentFile.load(path).segments[0]
    assert segment.no_speech_prob is None
    assert segment.avg_logprob is None


def test_scores_survive_a_round_trip(tmp_path):
    path = tmp_path / "v.segments.json"
    original = SegmentFile("v.wav", 5.0, "tiny", "en", [Segment(1, 0.0, 2.0, "hi", 0.12, -0.31)])
    original.save(path)
    assert SegmentFile.load(path).segments[0] == original.segments[0]
