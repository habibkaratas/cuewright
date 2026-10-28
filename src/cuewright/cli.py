"""Command-line interface.

Every stage is a separate subcommand on purpose. Transcription is the slow,
expensive step; keeping it apart means editing a translation or restyling the
burn never costs another decode.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .audio import (
    ENHANCED_CODECS,
    AudioLevel,
    audio_level,
    enhance_audio,
    extract_audio,
    probe_audio,
    raw_container_for,
)
from .burn import BurnStyle, burn
from .check import check_srt
from .compare import compare
from .ffmpeg import FFmpegNotFound
from .media_scan import collect_media, mirrored_folder
from .profiles import PROFILES, ListenProfile, Profile, ProfileError, TranscribeProfile
from .segments import SegmentFile, TranslationError, load_translation
from .spectrogram import SpectrogramOptions, render_spectrogram
from .srt import Cue, format_timestamp, to_vtt, write_srt
from .transcribe import TranscribeOptions, transcribe
from .verify import verify

RAW_TAG = "audio"
OUTPUT_TAGS = (RAW_TAG, *(profile.tag for profile in PROFILES.values()))


def _stem(path: Path) -> str:
    return path.stem


# --------------------------------------------------------------------------- #
# transcribe
# --------------------------------------------------------------------------- #


def cmd_transcribe(args: argparse.Namespace) -> int:
    media = Path(args.media)
    out_dir = Path(args.out_dir) if args.out_dir else media.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _stem(media)

    options = TranscribeOptions(
        model=args.model,
        language=args.language,
        task=args.task,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        cpu_threads=args.threads,
        vad=not args.no_vad,
    )

    print(f"loading model {options.model} ({options.device}/{options.compute_type})", flush=True)
    started = time.monotonic()

    def progress(fraction: float, segment) -> None:
        elapsed = time.monotonic() - started
        speed = segment.end / elapsed if elapsed > 0 else 0.0
        print(
            f"  {fraction * 100:5.1f}%  {format_timestamp(segment.start)}  "
            f"{speed:.2f}x  {segment.text[:58]}",
            flush=True,
        )

    result = transcribe(media, options, progress=progress)

    tag = args.tag or (result.language or "src")
    srt_path = out_dir / f"{stem}.{tag}.srt"
    json_path = out_dir / f"{stem}.{tag}.segments.json"
    blocks = write_srt(result.segments, srt_path, lang=result.language)
    result.save(json_path)

    minutes = (time.monotonic() - started) / 60
    print(f"\n{len(result.segments)} segments ({blocks} cues) in {minutes:.1f} min")
    print(f"  {srt_path}")
    print(f"  {json_path}")
    return 0


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #


def cmd_build(args: argparse.Namespace) -> int:
    segments = SegmentFile.load(args.segments)
    try:
        translations = load_translation(args.translation, (s.id for s in segments.segments))
    except TranslationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    cues = [Cue(s.start, s.end, translations[s.id]) for s in segments.segments]
    out = Path(args.output)
    # The target language, not the segment file's: formatting follows the
    # language being written, and a translation is by definition a different one.
    lang = args.lang
    if out.suffix.lower() == ".vtt":
        blocks = to_vtt(cues, out, lang=lang)
    else:
        blocks = write_srt(cues, out, lang=lang)
    print(f"{len(cues)} segments -> {blocks} cues -> {out}")
    return 0


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #


def cmd_export(args: argparse.Namespace) -> int:
    """Write the source-language subtitles straight from a segment file."""
    segments = SegmentFile.load(args.segments)
    cues = [Cue(s.start, s.end, s.text) for s in segments.segments]
    out = Path(args.output)
    lang = args.lang or segments.language or None
    blocks = (
        to_vtt(cues, out, lang=lang)
        if out.suffix.lower() == ".vtt"
        else write_srt(cues, out, lang=lang)
    )
    print(f"{blocks} cues -> {out}")
    return 0


# --------------------------------------------------------------------------- #
# template
# --------------------------------------------------------------------------- #


def cmd_template(args: argparse.Namespace) -> int:
    """Emit a translation skeleton: one '[id] text' line per segment."""
    segments = SegmentFile.load(args.segments)
    lines = [f"[{s.id}] {s.text if args.with_source else ''}" for s in segments.segments]
    body = "\n".join(lines) + "\n"
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
        print(f"{len(lines)} lines -> {args.output}")
    else:
        sys.stdout.write(body)
    return 0


# --------------------------------------------------------------------------- #
# burn
# --------------------------------------------------------------------------- #


def cmd_burn(args: argparse.Namespace) -> int:
    style = BurnStyle(
        font=args.font, font_size=args.font_size, margin_v=args.margin, outline=args.outline
    )
    out = burn(
        args.video, args.subtitles, args.output, style=style, crf=args.crf, preset=args.preset
    )
    size = out.stat().st_size / 1024 / 1024
    print(f"\n{out} ({size:.1f} MB)")
    return 0


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #


def cmd_verify(args: argparse.Namespace) -> int:
    segments = SegmentFile.load(args.segments)
    report = verify(segments, args.media)

    print(
        f"{len(segments.segments)} segments | speech {report.speech_seconds:.0f}s "
        f"/ {report.total_seconds:.0f}s ({report.coverage * 100:.1f}%)"
    )

    print(f"\ncoverage gaps ({len(report.gaps)})")
    if report.reference_db is not None:
        print(f"  reference speech level: {report.reference_db:.1f} dB")
    for gap in report.gaps:
        where = f"before segment {gap.next_id}" if gap.next_id else "end of media"
        level = (
            f"mean {gap.mean_db:.1f} dB, peak {gap.peak_db:.1f} dB"
            if gap.mean_db is not None
            else "not measured"
        )
        flag = "  <-- speech-level audio, check this" if gap.suspicious else ""
        print(
            f"  {gap.start:7.2f}s - {gap.end:7.2f}s ({gap.duration:5.2f}s) "
            f"| {level} | {where}{flag}"
        )

    print(f"\nanomalies ({len(report.anomalies)})")
    for anomaly in report.anomalies:
        print(f"  segment {anomaly.segment_id}: [{anomaly.kind}] {anomaly.detail}")

    suspicious = report.suspicious_gaps
    print(f"\n{len(suspicious)} suspicious gap(s), {len(report.anomalies)} anomaly(ies)")
    for gap in suspicious:
        print(f"  listen at {format_timestamp(gap.start)} - {format_timestamp(gap.end)}")
    return 0 if report.ok else 1


# --------------------------------------------------------------------------- #
# compare
# --------------------------------------------------------------------------- #


def cmd_compare(args: argparse.Namespace) -> int:
    a, b = SegmentFile.load(args.pass_a), SegmentFile.load(args.pass_b)
    report = compare(a, b)

    print(f"pass A: {len(a.segments):>4} segments, {report.a_words} words")
    print(f"pass B: {len(b.segments):>4} segments, {report.b_words} words")
    print(f"word-level agreement: {report.similarity * 100:.2f}%")

    for div in report.divergences:
        print(f"\n  [{div.kind}] {div.context}")
        print(f"      A: {div.a_text}")
        print(f"      B: {div.b_text}")
    if not report.divergences:
        print("\nthe two passes agree word for word")

    if report.only_in_b:
        print(
            f"\nwarning: {len(report.only_in_b)} segment(s) found only in pass B "
            f"— pass A may have dropped them:"
        )
        for seg in report.only_in_b:
            print(f"  {seg.start:7.2f}s - {seg.end:7.2f}s | {seg.text}")
    else:
        print("\npass B found no speech that pass A missed")
    return 0 if report.agrees else 1


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #


def cmd_check(args: argparse.Namespace) -> int:
    failures = 0
    for path in args.subtitles:
        report = check_srt(path, lang=args.lang)
        status = "OK    " if report.ok else "FAILED"
        print(f"{status} {report.path}")
        print(
            f"       {report.blocks} blocks | longest line {report.max_line} "
            f"| longest block {report.max_block} "
            f"| shortest cue {report.min_duration:.2f}s"
        )
        if report.wide_lines:
            print(
                f"       note: some lines exceed the {report.line_limit}-character "
                f"guideline for this script"
            )
        for problem in report.problems[:10]:
            print(f"       - {problem}")
        failures += 0 if report.ok else 1
    print(f"\n{failures} file(s) with problems")
    return 1 if failures else 0


# --------------------------------------------------------------------------- #


def is_enhance_output(path: Path) -> bool:
    return path.stem.endswith(tuple(f".{tag}" for tag in OUTPUT_TAGS))


def output_paths(
    media: Path, folder: Path, fmt: str, raw_suffix: str, tag: str
) -> tuple[Path, Path]:
    raw = folder / f"{media.stem}.{RAW_TAG}{raw_suffix}"
    enhanced = folder / f"{media.stem}.{tag}.{fmt}"
    return raw, enhanced


PROFILE_FLAGS = {
    "highpass": "highpass_hz",
    "rate": "sample_rate",
    "denoise": "noise_reduction_db",
    "noise_floor": "noise_floor_db",
    "max_gain": "max_gain_db",
    "target_rms": "target_rms",
    "lowpass": "lowpass_hz",
    "tempo": "tempo",
}


def build_profile(args: argparse.Namespace) -> Profile:
    profile_type = PROFILES[args.profile]
    accepted = profile_type.__dataclass_fields__
    overrides: dict[str, float] = {}
    rejected: list[str] = []
    for flag, field_name in PROFILE_FLAGS.items():
        value = getattr(args, flag)
        if value is None:
            continue
        if field_name not in accepted:
            rejected.append("--" + flag.replace("_", "-"))
            continue
        overrides[field_name] = value
    if rejected:
        raise ProfileError(
            f"{', '.join(rejected)} cannot be used with the {args.profile!r} profile; "
            "see 'cuewright enhance --help'"
        )
    return profile_type(**overrides)


def _describe_level(level: AudioLevel) -> str:
    if level.mean_db is None or level.peak_db is None:
        return "not measured"
    return f"mean {level.mean_db:.1f} dB, peak {level.peak_db:.1f} dB"


def _enhance_one(media: Path, outputs: tuple[Path, Path], profile: Profile, keep_raw: bool) -> None:
    raw_path, enhanced_path = outputs
    started = time.monotonic()
    if keep_raw:
        extract_audio(media, raw_path)
        print(f"  raw      -> {raw_path}", flush=True)
    enhance_audio(media, enhanced_path, profile)
    print(f"  {profile.tag:8s} -> {enhanced_path}", flush=True)
    before, after = audio_level(media), audio_level(enhanced_path)
    elapsed = time.monotonic() - started
    print(f"  level {_describe_level(before)}  ->  {_describe_level(after)}  ({elapsed:.0f}s)")


def cmd_enhance(args: argparse.Namespace) -> int:
    profile = build_profile(args)
    out_dir = Path(args.out_dir) if args.out_dir else None
    enhanced = 0
    silent = 0
    for root, media in collect_media(args.media, exclude=is_enhance_output):
        stream = probe_audio(media)
        if stream is None:
            silent += 1
            print(f"skip  {media}  (no audio track)", flush=True)
            continue
        print(f"{media}  [{stream.codec} {stream.sample_rate} Hz {stream.channels} ch]", flush=True)
        folder = mirrored_folder(media, root, out_dir)
        outputs = output_paths(media, folder, args.format, raw_container_for(stream), profile.tag)
        _enhance_one(media, outputs, profile, keep_raw=not args.clean_only)
        enhanced += 1
    print(f"\n{enhanced} file(s) enhanced, {silent} without an audio track")
    if not enhanced:
        print("error: none of the inputs carries an audio track", file=sys.stderr)
        return 1
    return 0


def cmd_spectrogram(args: argparse.Namespace) -> int:
    options = SpectrogramOptions(
        start=args.start,
        duration=args.duration,
        max_hz=args.max_hz,
        width=args.width,
        height=args.height,
        log_scale=not args.linear,
    )
    print(render_spectrogram(args.media, args.output, options))
    return 0


ENHANCE_DESCRIPTION = """\
Extract the first audio track of each input and write, next to it (or under
--out-dir, mirroring the scanned folders):

  <name>.audio.<codec>       the track copied untouched
  <name>.clean.<format>      --profile transcribe (default): for Whisper
  <name>.listen.<format>     --profile listen: for human ears

transcribe  high-pass, FFT noise reduction with noise tracking, gentle
            compression, RMS-targeted normalisation. Keeps the full band,
            so it suits a second transcription pass.
listen      speech band only (high-pass + low-pass), non-local-means
            denoising, hard compression that squashes door slams and
            footsteps down to voice level, presence boost, EBU R128
            loudness. Built for far-field, low-bitrate recordings where
            a person can still pick out words the model cannot.

Directories are scanned recursively. Files with no audio track are listed
and skipped; the command fails only when none of the inputs has one.
Earlier outputs (.audio, .clean, .listen) are never fed back in."""


def add_enhance_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "enhance",
        help="extract the audio track and clean it up for transcription or listening",
        description=ENHANCE_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("media", nargs="+", help="media files or directories (scanned recursively)")
    p.add_argument(
        "--profile",
        default="transcribe",
        choices=sorted(PROFILES),
        help="what the enhanced track is for (default: %(default)s)",
    )
    p.add_argument("--out-dir", default=None, help="defaults to each media file's own folder")
    p.add_argument(
        "--format",
        default="wav",
        choices=sorted(ENHANCED_CODECS),
        help="container for the enhanced track: wav (16-bit PCM), flac (lossless) or "
        "m4a (AAC, smallest) (default: %(default)s)",
    )
    p.add_argument("--clean-only", action="store_true", help="skip the untouched copy of the track")
    transcribe, listen = TranscribeProfile(), ListenProfile()

    shared = p.add_argument_group("both profiles")
    shared.add_argument(
        "--highpass",
        type=int,
        default=None,
        help=f"Hz; rumble below this is cut, 0 disables "
        f"(default: transcribe {transcribe.highpass_hz}, listen {listen.highpass_hz})",
    )
    shared.add_argument(
        "--rate",
        type=int,
        default=None,
        help=f"output sample rate (default: {transcribe.sample_rate})",
    )

    group = p.add_argument_group("transcribe profile only")
    group.add_argument(
        "--denoise",
        type=float,
        default=None,
        help=f"dB of noise reduction, 0 disables (default: {transcribe.noise_reduction_db:g})",
    )
    group.add_argument(
        "--noise-floor",
        type=float,
        default=None,
        help=f"dB; starting estimate of the noise floor, tracked from there "
        f"(default: {transcribe.noise_floor_db:g})",
    )
    group.add_argument(
        "--max-gain",
        type=float,
        default=None,
        help=f"dB; cap on how far quiet passages are raised (default: {transcribe.max_gain_db:g})",
    )
    group.add_argument(
        "--target-rms",
        type=float,
        default=None,
        help=f"0-1; loudness quiet passages are raised towards "
        f"(default: {transcribe.target_rms:g})",
    )

    group = p.add_argument_group("listen profile only")
    group.add_argument(
        "--lowpass",
        type=int,
        default=None,
        help=f"Hz; hiss above this is cut, 0 disables (default: {listen.lowpass_hz})",
    )
    group.add_argument(
        "--tempo",
        type=float,
        default=None,
        help="playback speed 0.5-2.0, pitch preserved; 0.8 gives the ear more time per "
        "syllable, but anything other than 1 no longer lines up with the video (default: 1)",
    )
    p.set_defaults(func=cmd_enhance)


def add_spectrogram_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "spectrogram",
        help="render the audio as a time-frequency picture",
        description="Render a PNG spectrogram of the first audio track. Voices show up as "
        "stacked horizontal harmonics, door slams and footsteps as vertical bursts, so it "
        "reveals speech that voice-activity detection and transcription miss. Without -o "
        "the picture is written next to the media as "
        "<name>[.<start>s-<end>].spectrogram.png.",
    )
    p.add_argument("media", help="any media file with an audio track")
    p.add_argument("-o", "--output", default=None, help="PNG path")
    defaults = SpectrogramOptions()
    p.add_argument("--start", type=float, default=None, help="seconds into the media")
    p.add_argument("--duration", type=float, default=None, help="seconds to render")
    p.add_argument(
        "--max-hz",
        type=int,
        default=defaults.max_hz,
        help="top of the frequency axis; 4000 covers telephone-band and camera audio "
        "(default: %(default)s)",
    )
    p.add_argument(
        "--width", type=int, default=defaults.width, help="pixels (default: %(default)s)"
    )
    p.add_argument(
        "--height", type=int, default=defaults.height, help="pixels (default: %(default)s)"
    )
    p.add_argument("--linear", action="store_true", help="linear amplitude scale instead of log")
    p.set_defaults(func=cmd_spectrogram)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cuewright",
        description="Transcribe speech, translate it, and produce verified subtitles.",
    )
    parser.add_argument("--version", action="version", version=f"cuewright {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("transcribe", help="speech -> timestamped segments + SRT")
    p.add_argument("media")
    p.add_argument("--model", default="large-v3")
    p.add_argument("--language", default=None, help="ISO code; omit to autodetect")
    p.add_argument(
        "--task",
        default="transcribe",
        choices=["transcribe", "translate"],
        help="'translate' renders English directly",
    )
    p.add_argument("--device", default="cpu")
    p.add_argument("--compute-type", default="int8")
    p.add_argument("--beam-size", type=int, default=5)
    p.add_argument("--threads", type=int, default=0)
    p.add_argument(
        "--no-vad",
        action="store_true",
        help="disable voice-activity filtering (use for a cross-check pass)",
    )
    p.add_argument("--tag", default=None, help="output suffix (default: detected language)")
    p.add_argument("--out-dir", default=None)
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("template", help="emit a translation skeleton")
    p.add_argument("segments")
    p.add_argument("-o", "--output", default=None)
    p.add_argument(
        "--with-source", action="store_true", help="prefill each line with the source text"
    )
    p.set_defaults(func=cmd_template)

    p = sub.add_parser("build", help="translation + segments -> SRT/VTT")
    p.add_argument("segments")
    p.add_argument("translation")
    p.add_argument("output")
    p.add_argument(
        "--lang",
        default=None,
        help="target language code (e.g. tr, ja). Tunes line width, word "
        "breaking and which function words may end a block. Guessed from the "
        "text when omitted.",
    )
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("export", help="segments -> SRT/VTT in the source language")
    p.add_argument("segments")
    p.add_argument("output")
    p.add_argument(
        "--lang", default=None, help="override the segment file's language for formatting"
    )
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("burn", help="render subtitles into the picture")
    p.add_argument("video")
    p.add_argument("subtitles")
    p.add_argument("output")
    p.add_argument("--font", default="Arial")
    p.add_argument("--font-size", type=int, default=22)
    p.add_argument("--margin", type=int, default=28)
    p.add_argument("--outline", type=int, default=2)
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--preset", default="medium")
    p.set_defaults(func=cmd_burn)

    p = sub.add_parser(
        "verify",
        help="find dropped speech, odd segments and likely hallucinations",
        description="Report coverage gaps, measured against the media's audio level when "
        "it is given, and per-segment anomalies: repeat, fast, slow, long, boilerplate "
        "(stock phrases Whisper invents over noise) and no-speech (segments the model "
        "itself rated as probably not speech). Exits 1 when anything needs a listen.",
    )
    p.add_argument("segments")
    p.add_argument(
        "media", nargs="?", default=None, help="source media; enables audio-level measurement"
    )
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("compare", help="cross-check two transcription passes")
    p.add_argument("pass_a")
    p.add_argument("pass_b")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("check", help="validate SRT structure")
    p.add_argument("subtitles", nargs="+")
    p.add_argument(
        "--lang",
        default=None,
        help="language code, so widths are judged against the right script "
        "(CJK lines hold about half as many characters)",
    )
    p.set_defaults(func=cmd_check)

    add_enhance_parser(sub)
    add_spectrogram_parser(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FFmpegNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    except (FileNotFoundError, RuntimeError, TranslationError, ProfileError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
