"""Tests for language-aware formatting.

Subtitle formatting is not language-neutral. Three assumptions in the naive
version were wrong outside Latin script:

* 42 characters per line assumes half-width glyphs. CJK text at that width
  overflows the frame.
* Wrapping on spaces assumes there are spaces. Chinese, Japanese and Thai have
  none, so a whole segment would come out as one unbreakable line.
* The list of conjunctions that must not end a block is per-language; applying
  the Turkish list to English strands the wrong words.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from cuewright.srt import (
    CJK_MAX_LINE,
    MAX_LINE,
    MAX_LINES,
    line_budget,
    split_block,
    wrap,
)

JAPANESE = "現代の建設産業の中心において、板ガラスは最も重要な材料の一つです。"
CHINESE = "在现代建筑业的核心，平板玻璃是最重要的材料之一，因为它兼具透明度和精度。"
THAI = "ในใจกลางอุตสาหกรรมการก่อสร้างสมัยใหม่กระจกแผ่นเรียบเป็นวัสดุที่สำคัญที่สุด"
TURKISH = "Modern inşaatın kalbinde düz cam en hayati malzemelerden biridir ve çok önemlidir."
ENGLISH = "At the heart of modern construction flat glass is one of the most vital materials."


# --------------------------------------------------------------------------- #
# line budget
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lang", ["ja", "zh", "yue", "ko", "th"])
def test_wide_scripts_get_a_narrower_line(lang):
    assert line_budget(lang) == CJK_MAX_LINE


@pytest.mark.parametrize("lang", ["tr", "en", "ar", "ru", "de"])
def test_other_scripts_keep_the_full_line(lang):
    assert line_budget(lang) == MAX_LINE


def test_budget_is_guessed_from_the_text_when_language_is_unknown():
    assert line_budget(None, JAPANESE) == CJK_MAX_LINE
    assert line_budget(None, TURKISH) == MAX_LINE


# --------------------------------------------------------------------------- #
# wrapping without spaces
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("text", "lang"), [(JAPANESE, "ja"), (CHINESE, "zh"), (THAI, "th")])
def test_spaceless_text_actually_wraps(text, lang):
    lines = wrap(text, lang=lang).split("\n")
    assert len(lines) > 1, "space-less text must break across lines, not run on"
    assert len(lines) <= MAX_LINES


@pytest.mark.parametrize(("text", "lang"), [(JAPANESE, "ja"), (CHINESE, "zh"), (THAI, "th")])
def test_spaceless_wrapping_preserves_every_character(text, lang):
    assert wrap(text, lang=lang).replace("\n", "") == text.strip()


def test_spaceless_wrap_prefers_breaking_after_punctuation():
    text = "これは最初の文です。そしてこれは二番目の文になります。"
    first = wrap(text, lang="ja").split("\n")[0]
    assert first.endswith("。")


def test_spaceless_detection_without_a_language_hint():
    assert len(wrap(JAPANESE).split("\n")) > 1


# --------------------------------------------------------------------------- #
# splitting
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("text", "lang"), [(JAPANESE, "ja"), (CHINESE, "zh"), (THAI, "th")])
def test_spaceless_split_preserves_text_and_time(text, lang):
    cues = split_block(text, 0.0, 10.0, lang=lang)
    assert "".join(c.text for c in cues).replace(" ", "") == text.replace(" ", "")
    assert cues[0].start == 0.0
    assert cues[-1].end == pytest.approx(10.0)
    for a, b in pairwise(cues):
        assert a.end <= b.start + 1e-9


def test_spaceless_split_bounds_block_length():
    text = "".join(f"文字{i}" for i in range(40))
    for cue in split_block(text, 0.0, 30.0, lang="ja"):
        assert len(cue.text) <= CJK_MAX_LINE * MAX_LINES


def test_cjk_blocks_are_shorter_than_latin_ones():
    latin = split_block(ENGLISH * 3, 0.0, 20.0, lang="en")
    cjk = split_block(CHINESE * 3, 0.0, 20.0, lang="zh")
    assert max(len(c.text) for c in cjk) < max(len(c.text) for c in latin)


# --------------------------------------------------------------------------- #
# per-language function words
# --------------------------------------------------------------------------- #


def test_english_conjunction_is_not_stranded():
    text = (
        "the plant supplies windows facades and large architectural projects and "
        "assorted manufacturing industries across the region today"
    )
    for cue in split_block(text, 0.0, 8.0, lang="en"):
        assert not cue.text.rstrip().endswith(" and")


def test_turkish_conjunction_is_not_stranded():
    text = (
        "tesis pencere cepheleri ve büyük mimari projeleri ve çeşitli imalat "
        "sanayilerini kapsayan bir üretim yapmaktadır bugün"
    )
    for cue in split_block(text, 0.0, 8.0, lang="tr"):
        assert not cue.text.rstrip().endswith(" ve")


def test_number_stays_with_its_unit_in_any_language():
    text = (
        "bunun 80 bin metrekaresi depolama alanı ve 400 metre uzunluğunda "
        "üretim hattıyla öne çıkar."
    )
    for lang in ("tr", None, "en"):
        for cue in split_block(text, 0.0, 8.0, lang=lang):
            assert not cue.text.rstrip().endswith("400")
