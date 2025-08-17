from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from src.types import Transcript, Segment, Word
from src.integration.aggregator import integrate_transcripts
from src.engines.base import BaseEngine
from src.engines.faster_whisper_engine import FasterWhisperEngine
from src.engines.whisper_engine import WhisperEngine
from src.engines.google_engine import GoogleSpeechEngine


def fmt_ts_srt(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fmt_ts_vtt(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    # WebVTT supports hours optional, but we keep it consistent
    return f"{h:02d}:{m:02d}:{s:06.3f}"


JP_PUNCT = set("。．！!？?、，, ・…‥：:；;―ー〜～」』】〉》］）」』】〉》］】)》>」}\n")


def words_to_segments(words: List[Word], max_chars: int = 18) -> List[Segment]:
    if not words:
        return []
    segs: List[Segment] = []
    buf: List[Word] = []
    for w in words:
        if not w.text:
            continue
        if not buf:
            buf.append(w)
            continue
        text_len = sum(len(x.text) for x in buf)
        should_break = False
        if (text_len >= max_chars) or (buf and (buf[-1].text in JP_PUNCT)):
            should_break = True
        if should_break:
            segs.append(_flush_words(buf))
            buf = [w]
        else:
            buf.append(w)
    if buf:
        segs.append(_flush_words(buf))
    return segs


def _flush_words(ws: List[Word]) -> Segment:
    start = ws[0].start
    end = ws[-1].end
    text = "".join(w.text for w in ws)
    return Segment(start=start, end=end, text=text, words=list(ws))


def transcript_to_srt(transcript: Transcript) -> str:
    # Prefer word-driven segmentation if available
    if transcript.segments and transcript.segments[0].words:
        words: List[Word] = []
        for seg in transcript.segments:
            words.extend(seg.words)
        segs = words_to_segments(words)
    else:
        segs = transcript.segments
    lines = []
    for i, seg in enumerate(segs, start=1):
        lines.append(str(i))
        lines.append(f"{fmt_ts_srt(seg.start)} --> {fmt_ts_srt(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def transcript_to_vtt(transcript: Transcript) -> str:
    if transcript.segments and transcript.segments[0].words:
        words: List[Word] = []
        for seg in transcript.segments:
            words.extend(seg.words)
        segs = words_to_segments(words)
    else:
        segs = transcript.segments
    lines = ["WEBVTT", ""]
    for seg in segs:
        lines.append(f"{fmt_ts_vtt(seg.start)} --> {fmt_ts_vtt(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def discover_engines(args) -> List[BaseEngine]:
    engines: List[BaseEngine] = []
    if not args.no_faster:
        engines.append(FasterWhisperEngine(model_size=args.model, device=args.device, compute_type=args.compute_type))
    if not args.no_whisper:
        engines.append(WhisperEngine(model_size=args.model))
    if args.google:
        engines.append(GoogleSpeechEngine())
    # Filter by availability
    ready: List[BaseEngine] = []
    for e in engines:
        try:
            if e.is_available():
                ready.append(e)
        except Exception:
            # Ignore broken environments
            continue
    return ready


def run(audio_path: str, out_prefix: str, args) -> int:
    engines = discover_engines(args)
    if not engines:
        print("No STT engines available. Install faster-whisper, stable-ts, or whisper.", file=sys.stderr)
        return 2

    transcripts: List[Transcript] = []
    for e in engines:
        try:
            print(f"[engine] {e.name} starting...")
            t = e.transcribe(audio_path, language=args.language)
            print(f"[engine] {e.name} done: {sum(len(s.words) for s in t.segments)} words, {len(t.segments)} segments")
            transcripts.append(t)
            if args.first_only:
                break
        except Exception as ex:
            print(f"[engine] {e.name} failed: {ex}", file=sys.stderr)

    if not transcripts:
        print("All engines failed.", file=sys.stderr)
        return 3

    if len(transcripts) == 1:
        integrated = transcripts[0]
    else:
        integrated = integrate_transcripts(transcripts)

    os.makedirs(os.path.dirname(out_prefix), exist_ok=True)
    srt_path = out_prefix + ".srt"
    vtt_path = out_prefix + ".vtt"
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(transcript_to_srt(integrated))
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(transcript_to_vtt(integrated))
    print(f"Wrote {srt_path} and {vtt_path}")
    return 0


def parse_args(argv: Optional[List[str]] = None):
    p = argparse.ArgumentParser(description="Generate JP subtitles from audio with multiple STT engines.")
    p.add_argument("--audio", required=True, help="Path to input audio file (wav/mp3/etc)")
    p.add_argument("--out", default="out/output", help="Output prefix without extension (default: out/output)")
    p.add_argument("--language", default="ja", help="Language code (default: ja)")
    p.add_argument("--model", default="small", help="Whisper model size (small, medium, large, etc)")
    p.add_argument("--device", default="auto", help="Device for faster-whisper (auto/cpu/cuda)")
    p.add_argument("--compute-type", default="default", help="Compute type for faster-whisper (e.g., float16)")
    p.add_argument("--no-faster", action="store_true", help="Disable faster-whisper engine")
    p.add_argument("--no-whisper", action="store_true", help="Disable whisper/stable-ts engine")
    p.add_argument("--google", action="store_true", help="Enable Google Cloud STT engine")
    p.add_argument("--first-only", action="store_true", help="Stop after first successful engine")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    return run(args.audio, args.out, args)


if __name__ == "__main__":
    raise SystemExit(main())

