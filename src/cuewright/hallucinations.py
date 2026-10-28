from __future__ import annotations

import re
import unicodedata

__all__ = ["NO_SPEECH_LIMIT", "is_boilerplate", "normalise_phrase"]

NO_SPEECH_LIMIT = 0.6

WHOLE_SEGMENT_PHRASES = (
    "thank you",
    "thank you very much",
    "thanks for watching",
    "thank you for watching",
    "god bless you",
    "you",
    "bye",
    "tesekkur ederim",
    "tesekkurler",
    "izlediginiz icin tesekkur ederim",
    "izlediginiz icin tesekkurler",
    "спасибо",
    "спасибо за просмотр",
    "продолжение следует",
    "дякую",
    "дякую за перегляд",
    "terima kasih telah menonton",
    "vielen dank",
    "merci",
    "شكرا",
    "شكرا للمشاهدة",
)

MARKER_PHRASES = (
    "altyazi m k",
    "subtitles by",
    "subtitled by",
    "please subscribe",
    "like and subscribe",
    "abone olmayi unutmayin",
    "субтитры сделал",
    "субтитры создавал",
    "редактор субтитров",
    "amara org",
)

_NON_WORD = re.compile(r"[^\w]+")
_UNDECOMPOSABLE = str.maketrans({"ı": "i", "ø": "o", "ł": "l", "đ": "d"})


def normalise_phrase(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold().translate(_UNDECOMPOSABLE))
    letters = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(_NON_WORD.sub(" ", letters).split())


_WHOLE = frozenset(normalise_phrase(p) for p in WHOLE_SEGMENT_PHRASES)
_MARKERS = tuple(normalise_phrase(p) for p in MARKER_PHRASES)


def is_boilerplate(text: str) -> bool:
    phrase = normalise_phrase(text)
    padded = f" {phrase} "
    return phrase in _WHOLE or any(f" {marker} " in padded for marker in _MARKERS)
