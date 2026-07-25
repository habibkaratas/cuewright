# Contributing

Thanks for taking the time. This project is small enough that a short guide covers it.

## Setup

```bash
git clone https://github.com/habibkaratas/subforge
cd subforge
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

You do not need ffmpeg or model weights to run the test suite — the structural half
of every feature is unit-testable on its own. You *do* need ffmpeg to exercise
`burn` and the audio-level measurement in `verify`.

## Before opening a pull request

```bash
pytest
ruff check .
ruff format --check .
```

## What to be careful about

Most of this codebase has an unusual property: **a mistake produces plausible output
rather than an error.** A subtitle that is one cue out of sync, or missing a sentence,
looks entirely normal until someone watches the video. Bear that in mind:

- **Never let bad input through silently.** `load_translation` refuses a file whose
  ids do not match the segments exactly, because a single skipped line would slide
  every later cue onto the wrong shot. Preserve that strictness in anything similar.
- **Text must survive the round trip.** Wrapping and splitting may only change where
  the line breaks fall, never which words are present. There is a regression test for
  this: a real bug once duplicated words because `words.index(word)` returned the
  first occurrence of a repeated word instead of the current position.
- **Timing is a contract.** Cues are derived from `segments.json`; a translation
  supplies text only. If you add a stage, keep it that way — it is what lets multiple
  language tracks stay frame-accurate with each other.

## Adding a check

Verification features are welcome, with one condition: be explicit about what the
check *cannot* catch. `compare` finds words where two decoding passes disagree, but
both passes usually share a model, so a consistent mishearing survives it. That
limitation is documented in the module, the README and the CLI output — a check that
oversells itself is worse than no check, because it invites misplaced confidence.

## Style

- Ruff enforces formatting and lint; there is nothing to argue about.
- Comments should explain *why*, not restate the code. If a line encodes a
  non-obvious trade-off (a threshold, a disabled model option, a workaround for
  ffmpeg's filter parser), say so.
- User-facing strings are English.

## Releasing

Maintainers: bump `__version__` in `src/subforge/__init__.py`, update `CHANGELOG.md`,
then tag `vX.Y.Z`. The release workflow verifies the tag matches the version, builds
the sdist and wheel, and drafts a GitHub release with them attached.

There is no PyPI step: `subforge` is taken on PyPI by an unrelated package, so the
distribution channel is GitHub releases and `pip install git+https://…`. Publishing
would mean renaming the project first.
