"""Tests for the segment file and translation validation.

Every failure mode here produces subtitles that are silently out of sync rather
than visibly broken, so the loader is expected to refuse the file outright.
"""

from __future__ import annotations

import pytest

from subforge.segments import Segment, SegmentFile, TranslationError, load_translation


@pytest.fixture
def segments():
    return SegmentFile(
        source="video.mp4",
        duration=12.0,
        model="large-v3",
        language="ar",
        segments=[
            Segment(1, 0.0, 4.0, "first"),
            Segment(2, 4.0, 8.0, "second"),
            Segment(3, 8.0, 11.0, "third"),
        ],
    )


def write(tmp_path, body, name="tr.txt"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_round_trip(tmp_path, segments):
    path = tmp_path / "v.segments.json"
    segments.save(path)
    loaded = SegmentFile.load(path)
    assert loaded.duration == segments.duration
    assert [s.text for s in loaded.segments] == ["first", "second", "third"]


def test_limit_of_uses_next_start_then_duration(segments):
    assert segments.limit_of(0) == 4.0
    assert segments.limit_of(2) == 12.0


def test_accepts_matching_translation(tmp_path, segments):
    path = write(tmp_path, "[1] bir\n[2] iki\n\n[3] üç\n")
    result = load_translation(path, (s.id for s in segments.segments))
    assert result == {1: "bir", 2: "iki", 3: "üç"}


def test_rejects_missing_id(tmp_path, segments):
    path = write(tmp_path, "[1] bir\n[3] üç\n")
    with pytest.raises(TranslationError, match="missing"):
        load_translation(path, (s.id for s in segments.segments))


def test_rejects_unknown_id(tmp_path, segments):
    path = write(tmp_path, "[1] bir\n[2] iki\n[3] üç\n[9] dokuz\n")
    with pytest.raises(TranslationError, match="unknown"):
        load_translation(path, (s.id for s in segments.segments))


def test_rejects_duplicate_id(tmp_path, segments):
    path = write(tmp_path, "[1] bir\n[1] tekrar\n[2] iki\n[3] üç\n")
    with pytest.raises(TranslationError, match="duplicate"):
        load_translation(path, (s.id for s in segments.segments))


def test_rejects_empty_translation(tmp_path, segments):
    path = write(tmp_path, "[1] bir\n[2]\n[3] üç\n")
    with pytest.raises(TranslationError, match="empty"):
        load_translation(path, (s.id for s in segments.segments))


def test_rejects_malformed_line(tmp_path, segments):
    path = write(tmp_path, "[1] bir\nno marker here\n[2] iki\n[3] üç\n")
    with pytest.raises(TranslationError, match="expected"):
        load_translation(path, (s.id for s in segments.segments))
