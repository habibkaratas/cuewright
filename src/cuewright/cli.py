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
from .burn import BurnStyle, burn
from .check import check_srt
from .compare import compare
from .ffmpeg import FFmpegNotFound
from .segments import SegmentFile, TranslationError, load_translation
from .srt import Cue, format_timestamp, to_vtt, write_srt
from .transcribe import TranscribeOptions, transcribe
from .verify import verify


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
    blocks = write_srt(result.segments, srt_path)
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
    if out.suffix.lower() == ".vtt":
        blocks = to_vtt(cues, out)
    else:
        blocks = write_srt(cues, out)
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
    blocks = to_vtt(cues, out) if out.suffix.lower() == ".vtt" else write_srt(cues, out)
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
        report = check_srt(path)
        status = "OK    " if report.ok else "FAILED"
        print(f"{status} {report.path}")
        print(
            f"       {report.blocks} blocks | longest line {report.max_line} "
            f"| longest block {report.max_block} "
            f"| shortest cue {report.min_duration:.2f}s"
        )
        if report.wide_lines:
            print("       note: some lines exceed the 42-character guideline")
        for problem in report.problems[:10]:
            print(f"       - {problem}")
        failures += 0 if report.ok else 1
    print(f"\n{failures} file(s) with problems")
    return 1 if failures else 0


# --------------------------------------------------------------------------- #


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
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("export", help="segments -> SRT/VTT in the source language")
    p.add_argument("segments")
    p.add_argument("output")
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

    p = sub.add_parser("verify", help="find dropped speech and odd segments")
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
    p.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FFmpegNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    except (FileNotFoundError, RuntimeError, TranslationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
