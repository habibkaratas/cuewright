# Translating

`subforge` does not translate for you. It gives you a file to translate and checks
that what comes back still lines up with the video. Use a human translator, a machine
service, or an LLM — the workflow is the same.

```bash
subforge template video.ar.segments.json -o video.tr.txt --with-source
# translate the text in video.tr.txt, keeping every [id] marker
subforge build video.ar.segments.json video.tr.txt video.tr.srt
```

## Rules that matter

**Keep the id markers.** Every line must stay `[n] text`. `build` rejects the file if
any id is missing, unknown, duplicated or empty rather than producing subtitles that
are quietly out of sync.

**One line per segment.** Do not merge two segments into one line or split one across
two — the ids are how text finds its timestamp. If a sentence spans several segments,
translate it as a sentence and distribute the result across those lines, which is
usually what the source did anyway.

**Watch the length.** A cue is on screen for a fixed time, decided by the video. Text
much longer than the source will be split into more cues than the shot can carry, and
the viewer runs out of time to read. Around **17 characters per second** of segment
duration is comfortable; a 3-second segment wants roughly 50 characters.

Turkish is agglutinative and habitually runs longer than Arabic or English, so this
constraint bites in practice. Prefer the tighter phrasing:

| Longer | Tighter |
| --- | --- |
| aynı zamanda kendine yeterliliğin güçlenmesine katkı sağlar | kendine yeterliliği artırır |
| ithalat faturasının düşürülmesi ve ulusal ürünün güçlendirilmesi | ithalat faturasını düşürmek |

**Numbers are the highest-risk content.** Speech recognition and translation both
mangle them, and a wrong figure in a corporate or technical video is the most visible
possible error. Check every one against the source audio: quantities, areas, capacities,
percentages, dates, job counts.

## Checking your work

```bash
subforge check video.tr.srt
```

Look at `longest block`. If it exceeds 84 characters the splitter could not find a
good cut point, which usually means a very long clause with no punctuation — add a
comma or rephrase.

Reviewing timing is easiest against the source-language file, since both share the
same timestamps:

```bash
subforge export video.ar.segments.json video.ar.srt
```

## Fixing a transcription error

If verification turns up a mishearing, correct it at the source — edit `text` in
`segments.json` — and rebuild. Do not patch the SRT directly: the next `build` would
overwrite it, and any other language track would still carry the error.
