"""SubRip (SRT) formatting: line wrapping, block splitting, reading and writing.

Two constraints drive everything here:

* A subtitle block should not exceed two lines. Longer blocks either overflow
  the frame or force the viewer to read faster than they can.
* Splitting a long segment must not break a number from its unit ("400 |
  metre") or strand a conjunction at the end of a block. :func:`split_block`
  scores candidate cut points to avoid both.

Both constraints are language-dependent, so the formatting functions take a
``lang`` hint:

* **Line budget.** 42 characters suits Latin, Cyrillic, Arabic and similar
  scripts. CJK glyphs are full-width, so roughly half as many fit — the budget
  drops to 20 for those.
* **Word boundaries.** Chinese, Japanese, Thai and their neighbours do not put
  spaces between words. Wrapping them on spaces yields one endless line, so
  those scripts wrap on characters instead, preferring to break after
  punctuation.
* **Function words.** Which conjunctions and particles read badly at the end of
  a block is per-language; see :data:`FUNCTION_WORDS`.

When ``lang`` is omitted the script is guessed from the text, which covers the
common case without the caller threading a language code through. Passing it
explicitly is still more reliable.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "Cue",
    "as_cue",
    "MAX_LINE",
    "MAX_LINES",
    "MAX_BLOCK",
    "CJK_MAX_LINE",
    "NO_SPACE_LANGS",
    "FUNCTION_WORDS",
    "format_timestamp",
    "parse_timestamp",
    "line_budget",
    "wrap",
    "split_block",
    "write_srt",
    "read_srt",
    "to_vtt",
]

MAX_LINE = 42
MAX_LINES = 2
MAX_BLOCK = MAX_LINE * MAX_LINES

# CJK glyphs occupy roughly two Latin character widths, so a line holds fewer.
CJK_MAX_LINE = 20

# Scripts written without spaces between words. Wrapping these on whitespace
# yields a single unbreakable line, so they are wrapped per character.
NO_SPACE_LANGS = frozenset({"zh", "yue", "ja", "th", "lo", "my", "km", "bo"})

# Languages whose glyphs are full-width.
WIDE_LANGS = frozenset({"zh", "yue", "ja", "ko"})

# Preference order for a cut: sentence end, then clause, then dash.
BREAKS = (
    ". ",
    "! ",
    "? ",
    "。",  # CJK sentence end — no trailing space
    "！",
    "？",
    "؟ ",  # Arabic
    "۔ ",  # Urdu
    "; ",
    ": ",
    "؛ ",
    "、",
    "；",
    "：",
    ", ",
    "، ",
    " — ",
    " - ",
)

# Words that read badly when left dangling at the end of a block. Kept per
# language: a Turkish list applied to English would strand the wrong words.
FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "tr": frozenset(
        """
        ve ile veya ya ki da de hem için olarak gibi ama fakat çünkü ancak
        yani ise diye kadar göre üzere rağmen
        """.split()
    ),
    "en": frozenset(
        """
        and or the a an of to in on at by as for from with that which but
        into over under about between during than then so if because while
        """.split()
    ),
    "ar": frozenset(
        """
        في من إلى على أن إن عن مع بين التي الذي ما لا و أو ثم بل لكن حتى
        عند بعد قبل خلال حول ضد نحو منذ
        """.split()
    ),
    "de": frozenset(
        """
        und oder der die das ein eine von zu in an auf mit für als bei aus
        nach über unter durch gegen ohne um dass weil aber
        """.split()
    ),
    "fr": frozenset(
        """
        et ou le la les un une de du des à au aux en dans sur pour par avec
        que qui mais donc car ni comme sans sous entre
        """.split()
    ),
    "es": frozenset(
        """
        y o el la los las un una de del a en con por para que quien pero
        como sin sobre entre desde hasta
        """.split()
    ),
    "ru": frozenset(
        """
        и или в на с по для от до из за под над о об к у не что как но
        если чтобы при между через
        """.split()
    ),
}

# Used when the language is unknown: the union. A blunt instrument, but still
# better than stranding a conjunction.
_ALL_FUNCTION_WORDS = frozenset().union(*FUNCTION_WORDS.values())

_NUMERIC = re.compile(r"^[\d.,٪%]+$")
_TIMESTAMP = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")

# CJK ideographs, kana, Hangul, Thai, Lao, Myanmar, Khmer, Tibetan.
_WIDE_SCRIPT = re.compile("[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯฀-๿຀-໿က-႟ក-៿ༀ-࿿]")

# Characters it is acceptable to break immediately after in a space-less script.
_CJK_BREAK_AFTER = frozenset("。！？、；：，)）」』】〉》…・")


@dataclass(frozen=True)
class Cue:
    """A single subtitle block."""

    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


def format_timestamp(seconds: float, sep: str = ",") -> str:
    """Seconds to ``HH:MM:SS,mmm`` (use ``sep='.'`` for WebVTT)."""
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def parse_timestamp(text: str) -> float:
    m = _TIMESTAMP.search(text)
    if not m:
        raise ValueError(f"not a timestamp: {text!r}")
    h, mins, s, frac = m.groups()
    return int(h) * 3600 + int(mins) * 60 + int(s) + int(frac.ljust(3, "0")) / 1000


def _looks_spaceless(text: str) -> bool:
    """Guess whether the text is written without word spaces."""
    stripped = text.strip()
    if not stripped:
        return False
    wide = len(_WIDE_SCRIPT.findall(stripped))
    return wide >= max(4, len(stripped) * 0.3) and text.count(" ") < len(stripped) / 8


def _spaceless(text: str, lang: str | None) -> bool:
    return lang in NO_SPACE_LANGS if lang else _looks_spaceless(text)


def line_budget(lang: str | None = None, text: str = "") -> int:
    """How many characters fit on one line for this language."""
    if lang:
        return CJK_MAX_LINE if lang in WIDE_LANGS or lang in NO_SPACE_LANGS else MAX_LINE
    return CJK_MAX_LINE if _looks_spaceless(text) else MAX_LINE


def _function_words(lang: str | None) -> frozenset[str]:
    if lang and lang in FUNCTION_WORDS:
        return FUNCTION_WORDS[lang]
    return _ALL_FUNCTION_WORDS


def _wrap_spaceless(text: str, max_line: int, max_lines: int) -> str:
    """Wrap a space-less script on characters, preferring to break after
    punctuation so a clause is not severed mid-phrase."""
    text = text.strip()
    lines: list[str] = []
    rest = text
    while rest and len(lines) < max_lines - 1 and len(rest) > max_line:
        window = rest[:max_line]
        cut = max_line
        floor = max(1, int(max_line * 0.4))
        for i in range(len(window) - 1, floor - 1, -1):
            if window[i] in _CJK_BREAK_AFTER:
                cut = i + 1
                break
        lines.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        lines.append(rest)
    return "\n".join(lines)


def wrap(
    text: str,
    max_line: int | None = None,
    max_lines: int = MAX_LINES,
    *,
    lang: str | None = None,
) -> str:
    """Wrap into at most ``max_lines`` lines.

    Anything that still does not fit is appended to the final line rather than
    dropped — a subtitle that is slightly too wide beats one missing words.
    """
    if max_line is None:
        max_line = line_budget(lang, text)

    if _spaceless(text, lang):
        return _wrap_spaceless(text, max_line, max_lines)

    words = text.split()
    if not words:
        return text
    lines: list[str] = []
    current = ""
    for i, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_line or not current:
            current = candidate
            continue
        lines.append(current)
        if len(lines) == max_lines - 1:
            # Remaining words go on the last line. Index by position (i), not
            # words.index(word): a repeated word would otherwise rewind and
            # duplicate part of the text.
            lines.append(" ".join(words[i:]))
            current = ""
            break
        current = word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _cut_score(text: str, pos: int, mid: float, lang: str | None) -> float:
    """Lower is better. Penalises cuts that separate a number from its unit."""
    score = abs(pos - mid)
    before = text[:pos].split()
    if before:
        last = before[-1].strip(".,;:،؛").lower()
        if _NUMERIC.match(last):
            score += 1000
        elif last in _function_words(lang):
            score += 500
    return score


def split_block(
    text: str,
    start: float,
    end: float,
    max_chars: int | None = None,
    *,
    lang: str | None = None,
) -> list[Cue]:
    """Split an over-long segment into cues, apportioning time by length."""
    text = text.strip()
    if max_chars is None:
        max_chars = line_budget(lang, text) * MAX_LINES
    if len(text) <= max_chars:
        return [Cue(start, end, text)]

    mid = len(text) / 2
    lo, hi = 0.2 * len(text), 0.8 * len(text)
    cut: int | None = None

    for br in BREAKS:
        positions = [i + len(br) for i in range(len(text)) if text.startswith(br, i)]
        positions = [p for p in positions if lo < p < hi]
        if positions:
            cut = min(positions, key=lambda p: abs(p - mid))
            break

    if cut is None:
        if _spaceless(text, lang):
            # No spaces to cut on: prefer a punctuation mark, else the midpoint.
            marks = [i + 1 for i, c in enumerate(text) if c in _CJK_BREAK_AFTER and lo < i < hi]
            cut = min(marks, key=lambda p: abs(p - mid)) if marks else int(mid)
        else:
            spaces = [i for i, c in enumerate(text) if c == " " and lo < i < hi]
            if not spaces:
                return [Cue(start, end, text)]
            cut = min(spaces, key=lambda p: _cut_score(text, p, mid, lang))

    left, right = text[:cut].strip(), text[cut:].strip()
    if not left or not right:
        return [Cue(start, end, text)]

    boundary = start + (end - start) * (len(left) / (len(left) + len(right)))
    return split_block(left, start, boundary, max_chars, lang=lang) + split_block(
        right, boundary, end, max_chars, lang=lang
    )


def as_cue(item) -> Cue:
    """Coerce a cue-like object into a :class:`Cue`.

    Callers hand in whatever they have: a ``Cue``, a ``Segment`` from a
    transcript, or a plain mapping. Accepting all three keeps the writers
    usable from every stage of the pipeline — an earlier version only handled
    the first two and broke ``transcribe``, which passes ``Segment`` objects.
    """
    if isinstance(item, Cue):
        return item
    if isinstance(item, Mapping):
        return Cue(item["start"], item["end"], item["text"])
    try:
        return Cue(item.start, item.end, item.text)
    except AttributeError as exc:  # pragma: no cover - defensive
        raise TypeError(
            f"expected a Cue, a mapping, or an object with start/end/text; "
            f"got {type(item).__name__}"
        ) from exc


def write_srt(
    cues,
    path,
    *,
    split: bool = True,
    encoding: str = "utf-8-sig",
    lang: str | None = None,
) -> int:
    """Write cues to an SRT file, optionally splitting over-long blocks.

    Returns the number of blocks written.
    """
    blocks: list[Cue] = []
    for item in cues:
        cue = as_cue(item)
        blocks.extend(split_block(cue.text, cue.start, cue.end, lang=lang) if split else [cue])

    with open(path, "w", encoding=encoding, newline="\n") as fh:
        for i, cue in enumerate(blocks, 1):
            fh.write(
                f"{i}\n{format_timestamp(cue.start)} --> "
                f"{format_timestamp(cue.end)}\n{wrap(cue.text, lang=lang)}\n\n"
            )
    return len(blocks)


def read_srt(path, encoding: str = "utf-8-sig") -> list[Cue]:
    raw = open(path, encoding=encoding).read().strip()
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_s, end_s = lines[1].split("-->")
        cues.append(Cue(parse_timestamp(start_s), parse_timestamp(end_s), " ".join(lines[2:])))
    return cues


def to_vtt(cues, path, encoding: str = "utf-8", *, lang: str | None = None) -> int:
    """Write cues as WebVTT, for browser-based players."""
    blocks: list[Cue] = []
    for item in cues:
        cue = as_cue(item)
        blocks.extend(split_block(cue.text, cue.start, cue.end, lang=lang))
    with open(path, "w", encoding=encoding, newline="\n") as fh:
        fh.write("WEBVTT\n\n")
        for i, cue in enumerate(blocks, 1):
            fh.write(
                f"{i}\n{format_timestamp(cue.start, '.')} --> "
                f"{format_timestamp(cue.end, '.')}\n{wrap(cue.text, lang=lang)}\n\n"
            )
    return len(blocks)
