# Languages

There is no single number for "languages supported", because the three stages
support different things. Being precise about which is which saves you from
discovering the gap in a finished file.

## Transcription — 100 languages

Whatever the Whisper model handles. Pass `--language` or let it autodetect:

```
af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr
gl gu ha haw he hi hr ht hu hy id is it ja jw ka kk km kn ko la lb ln lo lt lv
mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl ps pt ro ru sa sd si sk sl sn
so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz vi yi yo yue zh
```

Accuracy varies enormously across this list — a well-resourced language like
Spanish and a low-resourced one like Sindhi are not comparable, whatever the
shared label says. `cuewright verify` and `cuewright compare` exist precisely
because you should not take a transcript on trust.

`--task translate` renders speech directly into **English only**; it is a
Whisper feature, not a general translator.

## Translation — unlimited

cuewright does not translate. `template` gives you a file, `build` puts the
result back on the original timestamps. Any language you can type works,
including ones Whisper cannot transcribe.

## Subtitle formatting — tuned per language, with sensible fallbacks

This is the stage where language actually changes behaviour, and where the
support is uneven. Three things vary.

### Line width

42 characters per line assumes half-width glyphs. CJK and Korean text is
full-width, so the budget drops to **20**:

| Languages | Characters per line |
| --- | --- |
| `zh` `yue` `ja` `ko` `th` `lo` `my` `km` `bo` | 20 |
| everything else | 42 |

### Word breaking

Chinese, Japanese, Cantonese, Thai, Lao, Burmese, Khmer and Tibetan are written
without spaces between words. Wrapping them on whitespace produces one
unbreakable line that overflows the frame. Those scripts are wrapped **per
character**, preferring to break immediately after punctuation
(`。！？、；：，` and closing brackets) so a clause is not severed mid-phrase.

Before and after, on a Japanese sentence:

```
83 characters, one line, no break possible
現代の建設産業の中心において、板ガラスは最も重要かつ不可欠な材料の一つです。単なる構造材で…

3 cues, punctuation-aware
現代の建設産業の中心において、
板ガラスは最も重要かつ不可欠な材料の一つです。
```

### Function words

When a segment has to be split and there is no punctuation to split on,
cuewright avoids cutting after a conjunction or preposition — a block ending in
"and" or "ve" reads badly. That list is per-language:

**`tr` `en` `ar` `de` `fr` `es` `ru`** have curated lists.

Any other language falls back to the union of all of them, which is a blunt
instrument but still better than stranding a conjunction. Cuts that would
separate a number from its unit (`400 | metre`) are avoided in **every**
language, since that rule needs no vocabulary.

### Adding a language

Add an entry to `FUNCTION_WORDS` in [`src/cuewright/srt.py`](../src/cuewright/srt.py):

```python
FUNCTION_WORDS = {
    ...
    "it": frozenset("e o il la di a da in con per che ma".split()),
}
```

If the language is written without spaces, add its code to `NO_SPACE_LANGS`; if
its glyphs are full-width, add it to `WIDE_LANGS`. A test in
[`tests/test_languages.py`](../tests/test_languages.py) covering the new
language is welcome — the existing ones show the shape.

## Telling cuewright which language you mean

`transcribe` and `export` know the language from the segment file. `build`
cannot: the target language of a translation is by definition not the source
language, so pass it:

```bash
cuewright build video.segments.json video.ja.txt video.ja.srt --lang ja
cuewright check video.ja.srt --lang ja
```

Omitting `--lang` is not fatal. The script is guessed from the text itself,
which reliably distinguishes wide/space-less scripts from the rest. What
guessing cannot do is pick the right function-word list, so an explicit
`--lang` still gives better splits for the seven curated languages.
