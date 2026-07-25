# Verification

Machine transcription fails quietly. A dropped sentence or a misheard word reads as
perfectly ordinary text; nothing about the output announces that it is wrong. Watching
the whole video with the transcript in hand is the only complete check, and nobody
does that for every file.

These tools do not replace that. What they do is **narrow down where to look** — turning
"somewhere in twenty minutes of audio" into three timestamps.

Transcription goes wrong in two distinct ways, and each needs a different check.

## 1. Dropped speech — `subforge verify`

Voice-activity detection is what stops Whisper hallucinating over silence, but it
sometimes classifies quiet speech as silence and removes it. The transcript then has a
hole, with no indication anything is missing.

`verify` finds every stretch the segments do not cover and measures its audio level
with ffmpeg's `volumedetect`. A gap that is genuinely silent is fine. A gap carrying
speech-level audio is a candidate for dropped narration.

```bash
subforge verify video.ar.segments.json video.mp4
```

```
49 segments | speech 242s / 251s (96.5%)

coverage gaps (2)
  reference speech level: -17.8 dB
     0.00s -    5.87s ( 5.87s) | mean -22.3 dB, peak -7.2 dB | before segment 1  <-- speech-level audio, check this
   247.76s -  250.63s ( 2.87s) | mean -32.0 dB, peak -19.2 dB | end of media
```

The reference level is measured from the first segment, so the comparison adapts to
how loud the source actually is. Music and room tone raise a gap's level too — the
flag means "listen to this", not "this is missing".

It also reports per-segment anomalies computed from the data alone:

| Kind | Meaning |
| --- | --- |
| `repeat` | Identical to the previous segment — a hallucination loop |
| `fast` | Over 25 characters/second — timing is probably too tight |
| `slow` | Under 3 characters/second across a long segment — text may be missing |
| `long` | Over 15 seconds — should be split into more cues |

## 2. Misheard words — `subforge compare`

Decode the same audio twice with different settings, then diff the results. Where the
two passes agree, the transcript is dependable. Where they diverge, the model was
unsure — and that is precisely the shortlist worth listening to.

The usual second pass disables voice-activity filtering, since that changes what the
decoder sees without changing the model:

```bash
subforge transcribe video.mp4 --language ar --no-vad --tag check
subforge compare video.ar.segments.json video.check.segments.json
```

```
pass A:   49 segments, 411 words
pass B:   47 segments, 411 words
word-level agreement: 99.76%

  [replace] … توفر رمال … المحلية عالية الجودة …
      A: السلك
      B: السيليكا
```

One word in 411 — and it was a real error. `السلك` ("the wire") is meaningless in a
passage about glassmaking; `السيليكا` ("silica") is correct, and matches the same word
elsewhere in the transcript. Found without anyone listening to the audio.

Comparison also reports segments that pass B found where pass A has no coverage at
all, which catches dropped speech from the other direction.

Arabic orthographic variants (`أ إ آ` → `ا`, `ى` → `ي`, `ة` → `ه`) and diacritics are
folded before comparison, so spelling noise does not masquerade as disagreement.

### What this cannot catch

Both passes usually run the same model. A mistake the model makes *consistently* —
the same mishearing every time — appears in both and survives the comparison intact.

**This check finds uncertainty, not truth.** High agreement means the model was
confident, not that it was right. Proper nouns, brand names and numbers stay the
highest-risk items and deserve a human ear regardless of the score. In the example
above, both passes rendered "First Glass" as *First Class* and agreed with each other
perfectly while doing so.

To get a genuinely independent opinion you need a different model — run the second
pass with `--model medium` against a `large-v3` first pass, and expect more noise in
the diff in exchange for real independence.

## 3. Structural validity — `subforge check`

The transcript can be perfect and the file still broken. `check` validates the SRT
itself: sequential numbering, timings that run forwards, cues that do not overlap,
at most two lines per block, and block widths that fit the frame.

```bash
subforge check video.tr.srt video.en.srt
```

```
OK     video.tr.srt
       62 blocks | longest line 43 | longest block 82 | shortest cue 2.00s
       note: some lines exceed the 42-character guideline
```

All three commands exit non-zero when they find something, so they drop into CI or a
pre-publish script without extra glue.
