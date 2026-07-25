# cuewright

[![CI](https://github.com/habibkaratas/cuewright/actions/workflows/ci.yml/badge.svg)](https://github.com/habibkaratas/cuewright/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cuewright)](https://pypi.org/project/cuewright/)
[![Python](https://img.shields.io/pypi/pyversions/cuewright)](https://pypi.org/project/cuewright/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Transcribe speech, translate it, and produce subtitles you can actually trust.

Built around one idea: **timing and wording live in separate files.** Transcription
establishes timestamps once. Every language track then supplies only text, keyed by
segment id. Editing a translation costs nothing to re-render, and all your subtitle
tracks stay frame-accurate with each other because none of them invents its own timing.

The other half of the project is verification. Machine transcription fails quietly —
a dropped sentence or a misheard word looks exactly like a correct one until someone
watches the whole video. cuewright ships the checks that narrow down where to look.

## Install

```bash
pip install cuewright
```

Requires Python 3.10+ and [ffmpeg](https://ffmpeg.org/) on `PATH`.

```
Windows : winget install Gyan.FFmpeg
macOS   : brew install ffmpeg
Debian  : sudo apt install ffmpeg
```

If ffmpeg lives somewhere unusual, point at it with `CUEWRIGHT_FFMPEG` (and
`CUEWRIGHT_FFPROBE`). A static build unpacked into `tools/` is also found automatically.

## Quick start

Turning an Arabic-language video into Turkish subtitles:

```bash
# 1. Transcribe. Writes video.ar.srt and video.ar.segments.json
cuewright transcribe video.mp4 --language ar

# 2. Emit a translation skeleton, one "[id] text" line per segment
cuewright template video.ar.segments.json -o video.tr.txt --with-source

# 3. Translate the text in video.tr.txt however you like, keeping the [id] markers

# 4. Build the subtitle file — timings come from the segments, text from your file
cuewright build video.ar.segments.json video.tr.txt video.tr.srt

# 5. Optionally render it into the picture
cuewright burn video.mp4 video.tr.srt video.tr.mp4
```

Step 4 refuses to write anything if the ids do not line up exactly. That is
deliberate: one skipped line would slide every later cue onto the wrong shot,
which is far harder to spot than an error at build time.

For subtitles in the source language, skip steps 2–4:

```bash
cuewright export video.ar.segments.json video.ar.vtt
```

## Verifying the result

Machine transcription goes wrong in two distinct ways, and they need different checks.

**Dropped speech.** Voice-activity detection sometimes mistakes quiet speech for
silence. `verify` finds every stretch the segments do not cover and measures its
audio level — a gap carrying speech-level sound is worth listening to.

```bash
cuewright verify video.ar.segments.json video.mp4
```

```
49 segments | speech 242s / 251s (96.5%)

coverage gaps (2)
  reference speech level: -17.8 dB
     0.00s -    5.87s ( 5.87s) | mean -22.3 dB, peak -7.2 dB | before segment 1  <-- speech-level audio, check this
   247.76s -  250.63s ( 2.87s) | mean -32.0 dB, peak -19.2 dB | end of media
```

**Misheard words.** Decode the same audio a second time with different settings,
then compare. Where the passes agree the transcript is dependable; where they
diverge the model was unsure.

```bash
cuewright transcribe video.mp4 --language ar --no-vad --tag check
cuewright compare video.ar.segments.json video.check.segments.json
```

```
word-level agreement: 99.76%

  [replace] … توفر رمال … المحلية عالية الجودة …
      A: السلك
      B: السيليكا
```

That single disagreement was a real transcription error, found without anyone
listening to the audio.

**Be clear about the limit:** both passes usually share a model, so a mistake the
model makes *consistently* survives this check. It finds uncertainty, not truth.
Proper nouns and numbers still deserve a human ear.

Finally, validate the subtitle file itself — numbering, overlaps, line lengths:

```bash
cuewright check video.tr.srt
```

## Subtitle formatting

Cues are wrapped to two lines. Segments longer than that are split into several cues
with time apportioned by length, preferring sentence and clause boundaries. When no
punctuation is available the splitter scores candidate positions so it will not
separate a number from its unit (`400 | metre`) or strand a conjunction at the end of
a block.

Formatting is language-aware, because none of those rules are universal:

- **Line width** is 42 characters for Latin, Cyrillic and Arabic script, and 20 for
  full-width scripts (`zh` `yue` `ja` `ko` `th` `lo` `my` `km` `bo`).
- **Space-less scripts** — Chinese, Japanese, Thai and their neighbours — wrap per
  character rather than per word, breaking after punctuation where possible. Wrapping
  them on spaces would produce one unbreakable line.
- **Function words** that may not end a block are curated for `tr` `en` `ar` `de`
  `fr` `es` `ru`; other languages fall back to the union of those lists.

Tell it the language with `--lang` on `build` and `check`; `transcribe` and `export`
take it from the segment file. Omitting it is safe — the script is guessed from the
text — but an explicit code gives better splits.

See [docs/LANGUAGES.md](docs/LANGUAGES.md) for the full picture, including which
languages the transcriber handles and how to add one to the formatter.

## Using it as a library

```python
from cuewright import SegmentFile, transcribe, verify, write_srt
from cuewright.transcribe import TranscribeOptions

result = transcribe("video.mp4", TranscribeOptions(model="large-v3", language="ar"))
result.save("video.segments.json")
write_srt(result.segments, "video.ar.srt")

report = verify(result, "video.mp4")
print(f"coverage {report.coverage:.1%}, {len(report.anomalies)} anomalies")
```

## Commands

| Command | Purpose |
| --- | --- |
| `transcribe` | Speech to timestamped segments and an SRT |
| `template` | Translation skeleton (`[id] text` per segment) |
| `build` | Segments plus a translation to SRT or VTT |
| `export` | Segments to SRT or VTT in the source language |
| `burn` | Render subtitles into the picture |
| `verify` | Find dropped speech and implausible segments |
| `compare` | Cross-check two transcription passes |
| `check` | Validate SRT structure |

Run `cuewright <command> --help` for the full set of options.

## Notes on quality

- Transcription runs with `condition_on_previous_text=False`. Feeding previous text
  back in makes the model prone to repetition loops; losing a little cross-segment
  context is the cheaper trade.
- `burn` copies the audio stream untouched and re-encodes only the video, because
  drawing text necessarily changes the picture.
- Subtitles are resolution-independent. If you later obtain a higher-resolution
  master, re-run `burn` with a proportionally larger `--font-size` — there is no
  need to transcribe again.

## Development

```bash
git clone https://github.com/habibkaratas/cuewright
cd cuewright
pip install -e ".[dev]"
pytest
ruff check .
```

The test suite runs without ffmpeg or model weights: the structural half of every
check is unit-testable on its own.

## License

MIT
