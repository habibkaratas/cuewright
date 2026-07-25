# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-07-25

First release.

### Added

- `transcribe` — speech to timestamped segments plus an SRT, via faster-whisper.
  Runs with voice-activity filtering and `condition_on_previous_text=False`, which
  together suppress hallucination over silence and repetition loops.
- `template` / `build` — a translation workflow that keeps timing and wording in
  separate files, so multiple language tracks share one set of timestamps and an
  edited translation costs nothing to re-render.
- `export` — subtitles in the source language, SRT or WebVTT.
- `burn` — hardsubbing that copies the audio stream untouched, working around
  ffmpeg's filter-string parsing of Windows paths.
- `verify` — coverage-gap detection with ffmpeg audio-level measurement, plus
  per-segment anomaly checks (repetition loops, implausible speaking rates,
  over-long segments).
- `compare` — cross-checks two transcription passes and reports word-level
  disagreements, which locate the model's uncertainty.
- `check` — structural validation of an SRT: numbering, overlaps, reversed timings,
  line counts and block widths.
- Cue formatting that splits over-long segments at sentence and clause boundaries,
  scoring fallback cut points so a number is never separated from its unit and a
  conjunction is never stranded at the end of a block.

[Unreleased]: https://github.com/habibkaratas/subforge/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/habibkaratas/subforge/releases/tag/v0.1.0
