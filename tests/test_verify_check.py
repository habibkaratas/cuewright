"""Tests for transcript verification, SRT validation and pass comparison.

These run without ffmpeg: :func:`verify` only measures audio levels when it is
handed a media file, so the structural half of it stays unit-testable.
"""

from __future__ import annotations

from cuewright.check import check_srt
from cuewright.compare import compare, normalise
from cuewright.segments import Segment, SegmentFile
from cuewright.verify import verify


def make(segments, duration=60.0):
    return SegmentFile("v.mp4", duration, "large-v3", "ar", [Segment(*s) for s in segments])


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #


def test_reports_coverage_gap():
    report = verify(make([(1, 10.0, 20.0, "hello")], duration=30.0))
    spans = [(g.start, g.end) for g in report.gaps]
    assert (0.0, 10.0) in spans
    assert (20.0, 30.0) in spans


def test_ignores_short_pauses():
    report = verify(make([(1, 0.0, 10.0, "a"), (2, 10.5, 20.0, "b")], duration=20.0))
    assert report.gaps == []


def test_flags_repeated_segment():
    report = verify(make([(1, 0.0, 5.0, "same"), (2, 5.0, 10.0, "same")], duration=10.0))
    assert any(a.kind == "repeat" for a in report.anomalies)


def test_flags_overlong_segment():
    report = verify(make([(1, 0.0, 20.0, "x" * 100)], duration=20.0))
    assert any(a.kind == "long" for a in report.anomalies)


def test_flags_implausible_rate():
    fast = verify(make([(1, 0.0, 1.0, "x" * 100)], duration=1.0))
    assert any(a.kind == "fast" for a in fast.anomalies)

    slow = verify(make([(1, 0.0, 10.0, "hi")], duration=10.0))
    assert any(a.kind == "slow" for a in slow.anomalies)


def test_coverage_fraction():
    report = verify(make([(1, 0.0, 30.0, "x" * 200)], duration=60.0))
    assert report.coverage == 0.5


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #

GOOD = "1\n00:00:00,000 --> 00:00:02,000\nhello\n\n2\n00:00:02,000 --> 00:00:04,000\nthere\n"


def test_accepts_well_formed_srt(tmp_path):
    path = tmp_path / "ok.srt"
    path.write_text(GOOD, encoding="utf-8")
    report = check_srt(path)
    assert report.ok
    assert report.blocks == 2


def test_detects_overlap(tmp_path):
    path = tmp_path / "overlap.srt"
    path.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\na\n\n2\n00:00:02,000 --> 00:00:06,000\nb\n",
        encoding="utf-8",
    )
    assert any("overlaps" in p for p in check_srt(path).problems)


def test_detects_reversed_timing(tmp_path):
    path = tmp_path / "rev.srt"
    path.write_text("1\n00:00:05,000 --> 00:00:02,000\na\n", encoding="utf-8")
    assert any("ends before" in p for p in check_srt(path).problems)


def test_detects_misnumbering(tmp_path):
    path = tmp_path / "num.srt"
    path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\na\n\n7\n00:00:02,000 --> 00:00:04,000\nb\n",
        encoding="utf-8",
    )
    assert any("numbered" in p for p in check_srt(path).problems)


def test_detects_too_many_lines(tmp_path):
    path = tmp_path / "lines.srt"
    path.write_text("1\n00:00:00,000 --> 00:00:02,000\na\nb\nc\n", encoding="utf-8")
    assert any("lines" in p for p in check_srt(path).problems)


# --------------------------------------------------------------------------- #
# compare
# --------------------------------------------------------------------------- #


def test_identical_passes_agree():
    a = make([(1, 0.0, 5.0, "aynı metin burada")])
    b = make([(1, 0.0, 5.0, "aynı metin burada")])
    report = compare(a, b)
    assert report.agrees
    assert report.similarity == 1.0


def test_single_word_divergence_is_reported():
    a = make([(1, 0.0, 5.0, "توفر رمال السلك المحلية")])
    b = make([(1, 0.0, 5.0, "توفر رمال السيليكا المحلية")])
    report = compare(a, b)
    assert len(report.divergences) == 1
    assert report.divergences[0].a_text == "السلك"
    assert report.divergences[0].b_text == "السيليكا"


def test_segment_only_in_second_pass_is_flagged():
    a = make([(1, 10.0, 20.0, "shared text")])
    b = make([(1, 0.0, 5.0, "extra bit"), (2, 10.0, 20.0, "shared text")])
    assert len(compare(a, b).only_in_b) == 1


def test_normalise_folds_arabic_variants():
    assert normalise("أحمد، إبراهيم") == normalise("احمد ابراهيم")
