# The pipeline

```
media ──transcribe──► segments.json ──build──► .srt ──burn──► video with subtitles
                            │                    ▲
                            │                    │
                            └──template──► .txt ─┘   (your translation)
```

Each stage is a separate command on purpose. Transcription is the slow, expensive
step — several minutes of CPU for a few minutes of video. Editing a translation or
restyling a burn should never cost another decode, and with this split it doesn't.

## The segment file

`segments.json` is the contract between stages:

```json
{
  "source": "C:/media/video.mp4",
  "duration": 250.63,
  "model": "large-v3",
  "language": "ar",
  "segments": [
    { "id": 1, "start": 5.87, "end": 21.73, "text": "…" },
    { "id": 2, "start": 21.73, "end": 27.69, "text": "…" }
  ]
}
```

Timestamps are established once, here. Every later stage reads them and none of them
invents its own. That single rule is what gives you:

- **Frame-accurate parity between languages.** Turkish and English subtitle tracks cut
  at exactly the same moments, because they are the same timestamps with different
  text.
- **Cheap edits.** Fix a word in the translation, re-run `build`, done.
- **A place to correct the transcript.** If verification turns up a mishearing, edit
  `text` in the segment file and rebuild everything downstream.

## Translation files

A translation is a flat list of `[id] text` lines:

```
[1] Modern inşaatın kalbinde düz cam en hayati malzemelerden biridir.
[2] First Glass düz cam fabrikası, günde 600 ton kapasitesiyle
```

`build` cross-checks the ids against the segment file and **refuses to write anything**
if they do not match exactly — missing, unknown, duplicated or empty. This is
deliberate. A single skipped line would shift every later cue onto the wrong shot,
and that is much harder to notice than an error at build time.

Generate the skeleton with `subforge template`, optionally prefilled with the source
text to translate against:

```bash
subforge template video.ar.segments.json -o video.tr.txt --with-source
```

## From segments to cues

Segments are speech units; cues are what fits on screen. One long segment becomes
several cues.

`split_block` divides an over-long segment, apportioning its duration by character
count and preferring sentence then clause boundaries. When there is no punctuation to
use, candidate positions are scored so the cut avoids two specific mistakes:

- separating a number from its unit — `…ve 400 | metre uzunluğunda…`
- stranding a conjunction at the end of a block — `…depolama alanı ve |`

That is why 49 segments can become 62 Turkish cues but only 53 Arabic ones: the same
timings, different text lengths.

## Re-rendering at a different resolution

Subtitles are resolution-independent. If a higher-resolution master turns up later,
nothing needs transcribing again — only the burn is repeated, with the font scaled in
proportion:

```bash
subforge burn master-1080p.mp4 video.tr.srt out.mp4 --font-size 50
```
