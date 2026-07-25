"""Tests for wrapping, splitting and SRT round-tripping.

The property that matters most: text goes in and the *same* text comes out.
A real bug once duplicated words here — ``words.index(word)`` returned the
first occurrence rather than the current position, so any repeated word made
the wrapper rewind and copy part of the line again. The repeated-word cases
below exist to keep that from coming back.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from cuewright.srt import (
    MAX_BLOCK,
    MAX_LINES,
    Cue,
    format_timestamp,
    parse_timestamp,
    read_srt,
    split_block,
    to_vtt,
    wrap,
    write_srt,
)

REPEATED_WORDS = [
    "it begins with pure silica sand and ends with high-quality glass sheets",
    "reducing the import bill and strengthening the national product",
    "والتي تحتاج ما يقارب إلى 20 مليون متر مربع والتي تغطي إنشاء 400 ألف وحدة سكنية",
    "ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve ve",
]

LONG_TEXTS = REPEATED_WORDS + [
    "Modern inşaatın kalbinde düz cam en hayati malzemelerden biridir; sadece yapı "
    "elemanı olduğu için değil, şeffaflık, mühendislik hassasiyeti ve estetiği "
    "birleştirdiği için.",
    "short one",
]


@pytest.mark.parametrize("text", LONG_TEXTS)
def test_wrap_preserves_every_word(text):
    assert wrap(text).split() == text.split()


@pytest.mark.parametrize("text", LONG_TEXTS)
def test_wrap_respects_line_budget(text):
    assert len(wrap(text).split("\n")) <= MAX_LINES


@pytest.mark.parametrize("text", LONG_TEXTS)
def test_split_preserves_every_word(text):
    cues = split_block(text, 0.0, 10.0)
    joined = " ".join(" ".join(c.text.split()) for c in cues)
    assert joined == " ".join(text.split())


@pytest.mark.parametrize("text", LONG_TEXTS)
def test_split_keeps_time_span_and_order(text):
    cues = split_block(text, 5.0, 15.0)
    assert cues[0].start == 5.0
    assert cues[-1].end == pytest.approx(15.0)
    for a, b in pairwise(cues):
        assert a.end <= b.start + 1e-9


def test_split_bounds_block_length():
    text = " ".join(f"kelime{i}" for i in range(60))
    for cue in split_block(text, 0.0, 30.0):
        assert len(cue.text) <= MAX_BLOCK


def test_split_does_not_separate_a_number_from_its_unit():
    text = (
        "bunun 80 bin metrekaresi depolama alanı ve 400 metre uzunluğunda "
        "üretim hattıyla öne çıkar."
    )
    cues = split_block(text, 0.0, 8.0)
    for cue in cues:
        assert not cue.text.rstrip().endswith("400")


def test_timestamp_round_trip():
    assert format_timestamp(3725.456) == "01:02:05,456"
    assert parse_timestamp("01:02:05,456") == pytest.approx(3725.456)
    assert format_timestamp(-1.0) == "00:00:00,000"
    assert format_timestamp(0.0, ".") == "00:00:00.000"


def test_write_then_read_srt(tmp_path):
    cues = [Cue(0.0, 2.5, "first line"), Cue(2.5, 5.0, "second line")]
    path = tmp_path / "out.srt"
    assert write_srt(cues, path) == 2

    parsed = read_srt(path)
    assert [c.text for c in parsed] == ["first line", "second line"]
    assert parsed[0].start == pytest.approx(0.0)
    assert parsed[1].end == pytest.approx(5.0)


def test_write_srt_accepts_mappings(tmp_path):
    path = tmp_path / "out.srt"
    assert write_srt([{"start": 0.0, "end": 1.0, "text": "hi"}], path) == 1


def test_vtt_has_header(tmp_path):
    path = tmp_path / "out.vtt"
    to_vtt([Cue(0.0, 1.0, "hello")], path)
    body = path.read_text(encoding="utf-8")
    assert body.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.000" in body
