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

## Cleaning up audio

Security-camera and phone recordings arrive at 8 kHz with hum, hiss and a voice buried
under door slams. `enhance` pulls the track out of each video and writes it beside the
video twice: once copied untouched, and once cleaned for a purpose you choose.

```bash
cuewright enhance video/                          # every file under the folder
cuewright enhance clip.mp4 --profile listen --tempo 0.8 --format flac
```

```
video/clip.mp4  [aac 8000 Hz 1 ch]
  raw      -> video/clip.audio.m4a
  clean    -> video/clip.clean.wav
  level mean -38.2 dB, peak 0.0 dB  ->  mean -27.6 dB, peak -0.3 dB  (14s)
skip  video/other.mp4  (no audio track)

1 file(s) enhanced, 1 without an audio track
```

There are two profiles, because a model and a person need different things:

- **`transcribe`** (default, writes `.clean`) keeps the full band for Whisper: a steep
  200 Hz high-pass, FFT noise reduction that tracks a drifting noise floor, gentle
  compression and RMS-targeted normalisation.
- **`listen`** (writes `.listen`) is for a human ear on far-field, low-bitrate audio.
  It keeps only the 250-3400 Hz speech band, removes noise with non-local means,
  squashes door slams and footsteps down to voice level with a hard compressor, adds a
  presence lift and normalises loudness. `--tempo 0.8` slows it with the pitch kept,
  which gives the ear more time per syllable; the result no longer lines up with the
  video.

The listen profile exists because of a real case. Ceiling-camera recordings at 8 kHz
and 15 kbps contained voices that people could hear but no model could decode:
voice-activity detection dropped them and Whisper returned only stock phrases.
Squashing the bursts that drown the voice made the speech stand out for listeners
even though the words stayed out of the model's reach.

Every stage is tunable; `cuewright enhance --help` lists which flags belong to which
profile, and a flag given to the wrong profile is refused rather than ignored.

| Flag | Profile | Default | What it does |
| --- | --- | --- | --- |
| `--highpass` | both | 200 / 250 | Hz below which rumble is cut; `0` disables |
| `--rate` | both | 16000 | output sample rate |
| `--denoise` | transcribe | 18 | dB of noise reduction; `0` disables |
| `--noise-floor` | transcribe | -45 | dB; initial noise-floor estimate, tracked from there |
| `--max-gain` | transcribe | 26 | dB; cap on how far quiet passages are raised |
| `--target-rms` | transcribe | 0.2 | loudness quiet passages are raised towards |
| `--lowpass` | listen | 3400 | Hz above which hiss is cut; `0` disables |
| `--tempo` | listen | 1 | playback speed 0.5-2.0, pitch preserved |

Files without an audio track are listed and skipped; the command fails only when none
of its inputs had one.

## Looking at the audio

When the tools disagree with your ears, look. `spectrogram` renders the audio track as
a picture: voices show up as stacked horizontal harmonics, door slams and footsteps as
vertical bursts.

```bash
cuewright spectrogram clip.mp4 --start 72 --duration 16
# clip.72s-88s.spectrogram.png
```

The frequency axis stops at 4 kHz by default, which covers telephone-band and camera
audio; raise it with `--max-hz` for full-band recordings.

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
| `enhance` | Extract the audio track and clean it up for transcription or listening |
| `spectrogram` | Render the audio as a time-frequency picture |
| `transcribe` | Speech to timestamped segments and an SRT |
| `template` | Translation skeleton (`[id] text` per segment) |
| `build` | Segments plus a translation to SRT or VTT |
| `export` | Segments to SRT or VTT in the source language |
| `burn` | Render subtitles into the picture |
| `verify` | Find dropped speech, implausible segments and likely hallucinations |
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
