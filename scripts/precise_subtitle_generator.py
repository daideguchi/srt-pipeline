#!/usr/bin/env python3
"""
Precise Japanese subtitle generator with strict length and real timing.

Key improvements in this version:
- Uses actual word timestamps from Whisper (faster-whisper preferred)
- Aligns reference script to recognized words to respect speech timing
- Maps reference chunks to audio using alignment, not naive time division
- Strict visual layout: 36 chars/line, max 2 lines (72 total)
- Sensible display time normalization (target 2–5s when possible)
"""

import argparse
import json
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
import numpy as np

"""
Runtime deps strategy:
- Prefer faster-whisper for word timestamps
- Fallback to whisper result with segment-level timing; synthesize per-char timings
- Avoid hard failure if whisper libs are missing; user can provide prior SRT
"""
_HAVE_FASTER = False
_HAVE_WHISPER = False
try:
    from faster_whisper import WhisperModel  # type: ignore
    _HAVE_FASTER = True
except Exception:
    pass
try:
    import whisper  # type: ignore
    _HAVE_WHISPER = True
except Exception:
    pass

# Internal types used elsewhere in this repo
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src.types import Word as WWord, Segment as WSegment  # lightweight reuse
from src.alignment.smart_segmentation import (
    align_with_script as _align_with_script,
    balanced_alignment as _balanced_alignment,
)


def setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )


@dataclass
class SubtitleSegment:
    text: str
    start: float
    end: float


def load_reference_script(path: str) -> str:
    """Load reference script and clean it for processing"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Remove empty lines and normalize
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    full_text = " ".join(lines)
    
    # Normalize Unicode and remove extra spaces
    full_text = unicodedata.normalize('NFKC', full_text)
    full_text = re.sub(r'\s+', '', full_text)  # Remove all spaces for Japanese
    
    return full_text


def split_text_strictly(text: str, max_chars: int = 72) -> List[str]:
    """
    Split text into strict character limits while respecting Japanese punctuation.
    Each chunk must be <= max_chars and break at natural points.
    """
    # Japanese sentence endings that make good break points
    major_breaks = "。！？"
    minor_breaks = "、：；"
    
    chunks = []
    current_chunk = ""
    
    i = 0
    while i < len(text):
        char = text[i]
        
        # Check if adding this character would exceed limit
        if len(current_chunk + char) > max_chars:
            # We need to break here
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = char
            else:
                # Single character exceeds limit (shouldn't happen with reasonable text)
                chunks.append(char)
        else:
            current_chunk += char
            
            # Check for natural break points
            if char in major_breaks:
                # Major sentence ending - always break here if chunk is reasonable length
                if len(current_chunk) >= 20:  # Minimum reasonable subtitle length
                    chunks.append(current_chunk)
                    current_chunk = ""
            elif char in minor_breaks and len(current_chunk) >= 40:
                # Minor break point - break if chunk is getting long
                chunks.append(current_chunk)
                current_chunk = ""
        
        i += 1
    
    # Add remaining text
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def format_subtitle_lines(text: str, max_line_chars: int = 36) -> str:
    """
    Format text into 1-2 lines with max characters per line.
    """
    if len(text) <= max_line_chars:
        return text
    
    # Find the best break point near the middle
    ideal_break = len(text) // 2
    search_range = min(10, len(text) // 4)  # Search within reasonable range
    
    best_break = ideal_break
    best_score = float('inf')
    
    # Look for good break points around the ideal position
    for pos in range(max(0, ideal_break - search_range), 
                     min(len(text), ideal_break + search_range + 1)):
        if pos >= len(text):
            continue
            
        char = text[pos]
        line1_len = pos
        line2_len = len(text) - pos
        
        # Score this position (lower is better)
        score = 0
        
        # Penalty for lines that are too long
        if line1_len > max_line_chars:
            score += (line1_len - max_line_chars) * 10
        if line2_len > max_line_chars:
            score += (line2_len - max_line_chars) * 10
        
        # Bonus for breaking at punctuation
        if char in "、。！？：；":
            score -= 5
        
        # Penalty for uneven lines
        score += abs(line1_len - line2_len) * 0.1
        
        if score < best_score:
            best_score = score
            best_break = pos
    
    # Create two lines
    line1 = text[:best_break]
    line2 = text[best_break:]
    
    # Trim if still too long
    if len(line1) > max_line_chars:
        line1 = line1[:max_line_chars]
    if len(line2) > max_line_chars:
        line2 = line2[:max_line_chars]
    
    # Remove leading punctuation from second line
    line2 = re.sub(r'^[、。！？：；\s]+', '', line2)
    
    if line2:
        return line1 + "\n" + line2
    else:
        return line1

def transcribe_with_word_timestamps(
    audio_path: str,
    model_name: str = "medium",
    language: str = "ja",
    device: Optional[str] = None,
) -> List[WWord]:
    """
    Transcribe audio and return a flat list of Words with real timestamps.

    Priority:
    - faster-whisper (robust word_timestamps)
    - openai-whisper (segment-level; synthesize per-char timing)
    """
    words: List[WWord] = []
    if _HAVE_FASTER:
        logging.info(f"Using faster-whisper model: {model_name}")
        # Set device
        compute_type = "int8" if (os.environ.get("FW_INT8") == "1") else "float16"
        try:
            model = WhisperModel(model_name, device=device or "auto", compute_type=compute_type)
            segments, info = model.transcribe(
                audio_path,
                language=language,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 200},
                word_timestamps=True,
                temperature=0.0,
            )
            count_seg = 0
            for seg in segments:
                count_seg += 1
                for w in (seg.words or []):
                    if w.word.strip() == "":
                        continue
                    words.append(WWord(text=w.word, start=float(w.start), end=float(w.end), confidence=float(getattr(w, "probability", 0.0)), source="faster-whisper"))
            logging.info(f"Transcription complete (faster-whisper): {count_seg} segments, {len(words)} words")
            return words
        except Exception as e:
            logging.warning(f"faster-whisper failed, falling back to openai-whisper: {e}")

    if _HAVE_WHISPER:
        logging.info(f"Using openai-whisper model: {model_name}")
        try:
            model = whisper.load_model(model_name)
            result = model.transcribe(
                audio_path,
                language=language,
                verbose=False,
                temperature=0.0,
            )
            # If per-word exists (e.g., timestamped forks), use it
            segments = result.get("segments", [])
            tmp_words: List[WWord] = []
            for seg in segments:
                seg_start = float(seg.get("start", 0.0))
                seg_end = float(seg.get("end", seg_start))
                if "words" in seg and isinstance(seg["words"], list) and seg["words"]:
                    for w in seg["words"]:
                        wt = str(w.get("word", w.get("text", "")))
                        ws = float(w.get("start", seg_start))
                        we = float(w.get("end", seg_end))
                        tmp_words.append(WWord(text=wt, start=ws, end=we, confidence=float(w.get("probability", 0.0)), source="openai-whisper-words"))
                else:
                    # Synthesize per-character timing within the segment
                    t = str(seg.get("text", ""))
                    t = t.strip()
                    if not t:
                        continue
                    dur = max(1e-6, seg_end - seg_start)
                    n = len(t)
                    step = dur / max(1, n)
                    cur = seg_start
                    for ch in t:
                        nxt = min(seg_end, cur + step)
                        tmp_words.append(WWord(text=ch, start=cur, end=nxt, confidence=0.0, source="openai-whisper-synth"))
                        cur = nxt
            logging.info(f"Transcription complete (openai-whisper): {len(segments)} segments, {len(tmp_words)} words")
            return tmp_words
        except Exception as e:
            logging.error(f"openai-whisper failed: {e}\nPlease install a Whisper backend or provide a prior SRT to bootstrap timing.")
            return words

    logging.error("No Whisper backend available. Install faster-whisper or openai-whisper.")
    return words


def words_to_initial_segments(words: List[WWord]) -> List[WSegment]:
    """Wrap the entire word stream into a single segment to feed alignment.

    Alignment utilities flatten words anyway, so one segment suffices.
    """
    if not words:
        return []
    return [WSegment(start=words[0].start, end=words[-1].end, text="", words=list(words))]


def _norm_text(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").replace(" ", "").replace("\u3000", "").replace("\n", "").replace("\r", "")


def _segment_text(seg: WSegment) -> str:
    if seg.text:
        return seg.text
    if seg.words:
        return "".join(w.text for w in seg.words)
    return ""


def _split_segment_by_char_cap(seg: WSegment, max_total_chars: int = 72) -> List[WSegment]:
    """Split a segment so each piece has <= max_total_chars (visible chars).

    Works on word list and honors punctuation as preferred cut points.
    """
    text = _norm_text(_segment_text(seg))
    if len(text) <= max_total_chars:
        return [seg]
    # iterate through words, accumulate until cap, prefer cuts at JP punctuation
    JA_END_PUNCT = set("。｡！？!?…♪」』】》〉〕≫")
    JA_PAUSE_PUNCT = set("、，,・：:；;―ー…")
    groups: List[List[WWord]] = []
    cur: List[WWord] = []
    cur_len = 0
    def visible_len(t: str) -> int:
        return len(_norm_text(t))
    for w in (seg.words or []):
        wt = w.text
        wlen = visible_len(wt)
        if cur and cur_len + wlen > max_total_chars:
            # If current word is punctuation and small, allow include when possible
            if wt in JA_END_PUNCT or wt in JA_PAUSE_PUNCT:
                # still too long; cut before punctuation
                groups.append(cur)
                cur = [w]
                cur_len = wlen
            else:
                # cut here
                groups.append(cur)
                cur = [w]
                cur_len = wlen
        else:
            cur.append(w)
            cur_len += wlen
            # soft cut at sentence-ending punct if approaching cap
            if (wt in JA_END_PUNCT) and cur_len >= max_total_chars * 0.8:
                groups.append(cur)
                cur = []
                cur_len = 0
    if cur:
        groups.append(cur)
    out: List[WSegment] = []
    for g in groups:
        if not g:
            continue
        out.append(WSegment(start=g[0].start, end=g[-1].end, text="".join(x.text for x in g), words=list(g)))
    return out


def _adjust_display_windows(segments: List[WSegment], min_duration: float = 2.0, max_duration: float = 5.0) -> List[WSegment]:
    """Adjust only display window (start/end) to target duration, without changing word times."""
    if not segments:
        return []
    segs = [WSegment(start=s.start, end=s.end, text=_segment_text(s), words=list(s.words)) for s in segments]
    n = len(segs)
    for i, s in enumerate(segs):
        cur_dur = max(0.0, s.end - s.start)
        target = min(max(cur_dur, min_duration), max_duration)
        if abs(target - cur_dur) < 1e-3:
            continue
        prev_end = segs[i - 1].end if i > 0 else None
        next_start = segs[i + 1].start if i < n - 1 else None
        # allowable expansion without overlap; keep a tiny gap
        gap = 0.05
        before_slack = (s.start - (prev_end + gap)) if prev_end is not None else float('inf')
        after_slack = ((next_start - gap) - s.end) if next_start is not None else float('inf')
        extend = target - cur_dur
        if extend <= 0:
            # do not shrink aggressively; keep as is
            continue
        # Prefer extending after, then before
        add_after = min(extend, max(0.0, after_slack))
        s.end += add_after
        remain = extend - add_after
        if remain > 1e-6 and before_slack > 0:
            add_before = min(remain, max(0.0, before_slack))
            s.start -= add_before
    return segs


def create_precise_subtitles(
    reference_text: str,
    words: List[WWord],
    use_balanced_alignment: bool = True,
    min_duration: float = 2.0,
    max_duration: float = 5.0,
) -> List[SubtitleSegment]:
    """Create precisely timed and sized subtitle segments using real word timings."""

    if not words:
        raise ValueError("No word timestamps available to align.")

    # Initial single segment from all words
    init_segments = words_to_initial_segments(words)

    # Align to script boundaries using recognized text <-> script mapping
    if use_balanced_alignment:
        aligned: List[WSegment] = _balanced_alignment(init_segments, reference_text)
    else:
        aligned = _align_with_script(init_segments, reference_text)

    # Enforce 72-char cap per subtitle by splitting long aligned segments
    capped: List[WSegment] = []
    for s in aligned:
        capped.extend(_split_segment_by_char_cap(s, max_total_chars=72))

    # Normalize display windows towards 2–5s without altering word timings
    adjusted = _adjust_display_windows(capped, min_duration=min_duration, max_duration=max_duration)

    # Final formatting: 36 chars/line, 2 lines max
    precise: List[SubtitleSegment] = []
    for s in adjusted:
        raw_text = _segment_text(s)
        formatted = format_subtitle_lines(_norm_text(raw_text), max_line_chars=36)
        precise.append(SubtitleSegment(text=formatted, start=s.start, end=s.end))

    return precise


def format_timestamp_srt(seconds: float) -> str:
    """Format timestamp for SRT format"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    """Format timestamp for VTT format"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def export_srt(segments: List[SubtitleSegment], output_path: str) -> None:
    """Export subtitles as SRT format"""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{format_timestamp_srt(segment.start)} --> {format_timestamp_srt(segment.end)}\n")
            f.write(f"{segment.text}\n\n")
    
    logging.info(f"Exported {len(segments)} subtitle entries to {output_path}")


def export_vtt(segments: List[SubtitleSegment], output_path: str) -> None:
    """Export subtitles as VTT format"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for segment in segments:
            f.write(f"{format_timestamp_vtt(segment.start)} --> {format_timestamp_vtt(segment.end)}\n")
            f.write(f"{segment.text}\n\n")
    
    logging.info(f"Exported VTT subtitle file to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate precisely sized Japanese subtitles"
    )
    parser.add_argument("audio_path", help="Path to audio file")
    parser.add_argument("script_path", help="Path to reference script file")
    parser.add_argument("--output-dir", "-o", default="subs", help="Output directory")
    parser.add_argument("--model", "-m", default="medium", 
                       choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
                       help="Whisper model size")
    parser.add_argument("--language", "-l", default="ja", help="Audio language")
    parser.add_argument("--verbose", "-v", action="count", default=0, help="Increase verbosity")
    parser.add_argument("--prefix", "-p", default="precise", help="Output file prefix")
    parser.add_argument("--simple-align", action="store_true", help="Use simple strict script alignment (not balanced)")
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    # Validate inputs
    if not os.path.exists(args.audio_path):
        logging.error(f"Audio file not found: {args.audio_path}")
        return 1
    
    if not os.path.exists(args.script_path):
        logging.error(f"Script file not found: {args.script_path}")
        return 1
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    try:
        # Step 1: Load reference script
        logging.info("Loading reference script...")
        reference_text = load_reference_script(args.script_path)
        logging.info(f"Loaded script with {len(reference_text)} characters")
        
        # Step 2: Transcribe audio and get word timestamps
        logging.info("Transcribing audio for word-level timings...")
        words = transcribe_with_word_timestamps(
            args.audio_path, model_name=args.model, language=args.language
        )

        # Step 3: Create precise subtitles
        logging.info("Creating precisely sized subtitles...")
        segments = create_precise_subtitles(
            reference_text,
            words,
            use_balanced_alignment=(not args.simple_align),
            min_duration=2.0,
            max_duration=5.0,
        )
        
        logging.info(f"Generated {len(segments)} precise subtitle segments")
        
        # Validate segment lengths
        for i, segment in enumerate(segments):
            lines = segment.text.split('\n')
            for line in lines:
                if len(line) > 36:
                    logging.warning(f"Segment {i+1} line too long: {len(line)} chars: '{line[:50]}...'")
        
        # Step 4: Export files
        srt_path = os.path.join(args.output_dir, f"{args.prefix}.srt")
        vtt_path = os.path.join(args.output_dir, f"{args.prefix}.vtt")
        
        export_srt(segments, srt_path)
        export_vtt(segments, vtt_path)
        
        # Export metadata
        metadata = {
            "audio_file": args.audio_path,
            "script_file": args.script_path,
            "model": args.model,
            "language": args.language,
            "segments": len(segments),
            "max_chars_per_line": 36,
            "max_lines": 2,
            "output_files": [srt_path, vtt_path]
        }
        
        metadata_path = os.path.join(args.output_dir, f"{args.prefix}_metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logging.info(f"✅ Success! Generated precise subtitles:")
        logging.info(f"  📄 SRT: {srt_path}")
        logging.info(f"  📄 VTT: {vtt_path}")
        logging.info(f"  📊 Metadata: {metadata_path}")
        logging.info(f"  📏 Format: Max 36 chars/line, 2 lines max, {len(segments)} segments")
        
        return 0
        
    except Exception as e:
        logging.error(f"❌ Error during processing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
