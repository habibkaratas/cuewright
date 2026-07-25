"""The writers must accept whatever each pipeline stage actually hands them.

This is a regression guard for a real shipped bug: `write_srt` assumed every
item was either a `Cue` or a mapping and subscripted anything else. The
`transcribe` command passes `Segment` dataclasses, so the project's flagship
command failed with `TypeError: 'Segment' object is not subscriptable` in the
published release.

It survived because the end-to-end test coverage stopped short of the one
command that needs model weights. Unit-testing the type contract costs nothing
and catches the whole class of mistake.
"""

from __future__ import annotations

import pytest

from cuewright.segments import Segment, SegmentFile
from cuewright.srt import Cue, as_cue, read_srt, to_vtt, write_srt

SEGMENTS = [
    Segment(1, 0.0, 2.5, "first segment"),
    Segment(2, 2.5, 5.0, "second segment"),
]
CUES = [Cue(0.0, 2.5, "first segment"), Cue(2.5, 5.0, "second segment")]
MAPPINGS = [
    {"start": 0.0, "end": 2.5, "text": "first segment"},
    {"start": 2.5, "end": 5.0, "text": "second segment"},
]


@pytest.fixture(params=["segments", "cues", "mappings"])
def items(request):
    return {"segments": SEGMENTS, "cues": CUES, "mappings": MAPPINGS}[request.param]


def test_write_srt_accepts_every_cue_like_type(items, tmp_path):
    path = tmp_path / "out.srt"
    assert write_srt(items, path) == 2
    assert [c.text for c in read_srt(path)] == ["first segment", "second segment"]


def test_to_vtt_accepts_every_cue_like_type(items, tmp_path):
    path = tmp_path / "out.vtt"
    assert to_vtt(items, path) == 2
    assert path.read_text(encoding="utf-8").startswith("WEBVTT")


def test_as_cue_preserves_timing_and_text(items):
    cues = [as_cue(i) for i in items]
    assert cues[0].start == 0.0
    assert cues[-1].end == 5.0
    assert cues[0].text == "first segment"


def test_as_cue_rejects_something_unusable():
    with pytest.raises(TypeError, match="start/end/text"):
        as_cue(object())


def test_transcript_round_trips_to_subtitles(tmp_path):
    """The exact path `cuewright transcribe` takes: SegmentFile -> SRT."""
    transcript = SegmentFile(
        source="video.mp4",
        duration=5.0,
        model="tiny",
        language="ar",
        segments=list(SEGMENTS),
    )
    json_path, srt_path = tmp_path / "v.segments.json", tmp_path / "v.srt"

    blocks = write_srt(transcript.segments, srt_path, lang=transcript.language)
    transcript.save(json_path)

    assert blocks == 2
    assert SegmentFile.load(json_path).segments[0].text == "first segment"
    assert len(read_srt(srt_path)) == 2
