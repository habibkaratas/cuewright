# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] — 2026-10-28

### Added

- `enhance` extracts the audio track of a video untouched and writes an enhanced copy
  beside it. Directories are scanned recursively; files without an audio track are
  reported and skipped rather than aborting the run.
- Two enhancement profiles. `transcribe` (default) prepares audio for Whisper: steep
  high-pass, FFT noise reduction with noise tracking, gentle compression and
  RMS-targeted normalisation. `listen` prepares far-field, low-bitrate audio for a
  human ear: speech band only, non-local-means denoising, hard compression that
  squashes door slams to voice level, presence lift, EBU R128 loudness, and an
  optional pitch-preserving `--tempo`. A flag that belongs to the other profile is
  refused instead of silently ignored.
- `spectrogram` renders the audio track, or a window of it, as a PNG. It reveals
  speech that voice-activity detection and transcription both miss.
- `verify` flags likely hallucinations. `boilerplate` marks stock phrases Whisper
  invents over noise ("Altyazı M.K.", "Thank you for watching", "Продолжение
  следует…", "Дякую за перегляд"), matched after folding case and accents.
  `no-speech` marks segments the model itself rated at least 60% likely to be
  non-speech, which catches invented sentences no phrase list could anticipate.
- Segment files carry each segment's `no_speech_prob` and `avg_logprob`. Older files
  without them still load.
- Library API: `probe_audio`, `extract_audio`, `enhance_audio`, `audio_level`,
  `TranscribeProfile`, `ListenProfile`, `render_spectrogram`.

### Fixed

- `transcribe` failed on every fresh install with `TypeError: open() got an unexpected
  keyword argument 'metadata_errors'`. PyAV 19 dropped that argument and
  faster-whisper 1.2.1 still passes it; nothing constrained PyAV, so pip picked the
  incompatible release. PyAV is now held below 19.

### Changed

- `verify` measures audio levels through `cuewright.audio.audio_level`, shared with
  `enhance`, instead of its own private helper.

## [0.2.1] — 2026-07-25

### Fixed

- **`transcribe` did not work at all.** `write_srt` assumed every item was a `Cue`
  or a mapping and subscripted anything else, but the command passes `Segment`
  objects, so it failed with `TypeError: 'Segment' object is not subscriptable`.
  The bug was present in every release to date. `write_srt` and `to_vtt` now accept
  a `Cue`, a `Segment`, or any mapping, via the new `as_cue` helper, and raise a
  useful `TypeError` for anything else.

### Added

- CI transcribes real speech end to end: espeak-ng synthesises a clip, the `tiny`
  model transcribes it, and the resulting SRT and segment file are validated. The
  flagship command shipped broken because nothing in CI ever ran it — the unit
  tests do not touch a model and the burn test does not need one.
- Unit coverage for the writers' type contract, so this class of mistake fails in
  under a second rather than in a release.

## [0.2.0] — 2026-07-25

### Added

- Language-aware subtitle formatting. `wrap`, `split_block`, `write_srt`, `to_vtt`
  and `check_srt` take a `lang` hint, and `build`, `export` and `check` expose it as
  `--lang`. When omitted the script is guessed from the text.
- `docs/LANGUAGES.md`, setting out what each stage actually supports: 100 languages
  for transcription, unlimited for translation, and per-language tuning with
  documented fallbacks for formatting.

### Fixed

- Chinese, Japanese, Cantonese, Thai, Lao, Burmese, Khmer and Tibetan produced one
  unbreakable line per segment. These scripts have no spaces between words, so
  whitespace wrapping never found a break point. They now wrap per character,
  preferring to break after punctuation.
- Full-width scripts were measured against the 42-character budget meant for
  half-width glyphs, so lines overflowed the frame. `zh` `yue` `ja` `ko` and the
  space-less scripts now use a 20-character budget, and `check` reports widths
  against the right limit.
- The list of function words that may not end a block was a single mixed set of
  Turkish, English and Arabic applied to every language. It is now per-language,
  with curated lists for `tr` `en` `ar` `de` `fr` `es` `ru`.

## [0.1.1] — 2026-07-25

### Fixed

- Package metadata declared the licence with `license = { file = "LICENSE" }`, which
  embeds the entire licence text into the metadata field — PyPI rendered the whole MIT
  body where the licence name belongs. It is now the SPDX expression `MIT`, with the
  file carried separately via `license-files`.

### Changed

- Copyright is attributed to Habib Karataş rather than "cuewright contributors", and
  the package declares an author.

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

[Unreleased]: https://github.com/habibkaratas/cuewright/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/habibkaratas/cuewright/releases/tag/v0.2.2
[0.2.1]: https://github.com/habibkaratas/cuewright/releases/tag/v0.2.1
[0.2.0]: https://github.com/habibkaratas/cuewright/releases/tag/v0.2.0
[0.1.1]: https://github.com/habibkaratas/cuewright/releases/tag/v0.1.1
[0.1.0]: https://github.com/habibkaratas/cuewright/releases/tag/v0.1.0
