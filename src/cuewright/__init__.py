"""cuewright — transcribe speech, translate it, and produce verified subtitles.

The pipeline keeps timing and wording in separate files. Transcription writes
timestamps once; every language track then supplies only text, keyed by segment
id. That is what lets several subtitle tracks stay frame-accurate with each
other, and what makes a translation edit cost nothing to re-render.
"""

from __future__ import annotations

__version__ = "0.2.0"

from .burn import BurnStyle, burn
from .check import SrtReport, check_srt
from .compare import CompareReport, compare
from .segments import Segment, SegmentFile, TranslationError, load_translation
from .srt import Cue, line_budget, read_srt, split_block, to_vtt, wrap, write_srt
from .transcribe import TranscribeOptions, transcribe
from .verify import VerifyReport, verify

__all__ = [
    "__version__",
    "BurnStyle",
    "burn",
    "SrtReport",
    "check_srt",
    "CompareReport",
    "compare",
    "Segment",
    "SegmentFile",
    "TranslationError",
    "load_translation",
    "Cue",
    "line_budget",
    "read_srt",
    "split_block",
    "to_vtt",
    "wrap",
    "write_srt",
    "TranscribeOptions",
    "transcribe",
    "VerifyReport",
    "verify",
]
