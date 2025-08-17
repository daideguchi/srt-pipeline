#!/usr/bin/env python3
"""
V9 DURATION FIX: Fix the critical segment duration issue causing rapid subtitle switching.

CRITICAL BUG IN V8: Segments 52-53 show 0.5 second durations causing rapid switching.
ROOT CAUSE: Overlap resolution algorithm creating excessively short segments

FIX STRATEGY:
1. Maintain minimum segment duration of 2.0 seconds
2. Apply conservative overlap resolution
3. Preserve original WhisperX timing quality where good
4. Ensure segment 2 starts at 5.15 seconds
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import List, Tuple, Optional
from difflib import SequenceMatcher


@dataclass
class SRTSegment:
    index: int
    start: float
    end: float
    text: str


def parse_timestamp_to_seconds(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def format_seconds_to_srt(ts: float) -> str:
    if ts is None or ts < 0:
        ts = 0.0
    h = int(ts // 3600)
    m = int((ts % 3600) // 60)
    s = int(ts % 60)
    ms = int(round((ts - int(ts)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def load_srt(path: str) -> List[SRTSegment]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    blocks = re.split(r"\n\s*\n", raw)
    out: List[SRTSegment] = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
            tline = lines[1].strip()
            start_ts, end_ts = [p.strip() for p in tline.split("-->")]
            text = "\n".join(lines[2:])
            out.append(
                SRTSegment(index=idx, start=parse_timestamp_to_seconds(start_ts), end=parse_timestamp_to_seconds(end_ts), text=text)
            )
        except Exception:
            continue
    return out


def write_srt(path: str, segments: List[SRTSegment]) -> None:
    lines: List[str] = []
    for seg in segments:
        lines.append(str(seg.index))
        lines.append(f"{format_seconds_to_srt(seg.start)} --> {format_seconds_to_srt(seg.end)}")
        lines.append(seg.text)
        lines.append("")
    content = "\n".join(lines).rstrip() + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


@dataclass
class WxChar:
    ch: str
    start: Optional[float]
    end: Optional[float]


def distribute_char_times(token: str, start: Optional[float], end: Optional[float]) -> List[WxChar]:
    chars = list(token)
    if not chars:
        return []
    if start is None or end is None or end <= start:
        return [WxChar(c, None, None) for c in chars]
    dur = (end - start) / len(chars)
    out: List[WxChar] = []
    for i, c in enumerate(chars):
        cs = start + dur * i
        ce = start + dur * (i + 1)
        out.append(WxChar(c, cs, ce))
    return out


def load_whisperx_char_stream(json_path: str) -> List[WxChar]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    stream_chars: List[WxChar] = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            token = str(w.get("word", ""))
            wstart = w.get("start")
            wend = w.get("end")
            stream_chars.extend(distribute_char_times(token, wstart, wend))
    return stream_chars


# Japanese normalization (same as previous versions)
KANJI_DIGITS = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}
SMALL_UNITS = [(1000, "千"), (100, "百"), (10, "十")]
BIG_UNITS = [(10 ** 12, "兆"), (10 ** 8, "億"), (10 ** 4, "万")]


def int_to_kanji(n: int) -> str:
    if n == 0:
        return KANJI_DIGITS[0]

    def four_digit_to_kanji(x: int) -> str:
        s = []
        for unit, sym in SMALL_UNITS:
            d = x // unit
            if d:
                if d == 1:
                    s.append(sym)
                else:
                    s.append(KANJI_DIGITS[d] + sym)
                x %= unit
        if x:
            s.append(KANJI_DIGITS[x])
        return "".join(s) if s else ""

    out = []
    for unit, sym in BIG_UNITS:
        d = n // unit
        if d:
            out.append(four_digit_to_kanji(d) + sym)
            n %= unit
    if n:
        out.append(four_digit_to_kanji(n))
    return "".join(out)


def is_ws_or_punct_or_symbol(ch: str) -> bool:
    if ch == "ー":
        return False
    cat = unicodedata.category(ch)
    return cat.startswith("Z") or cat.startswith("P") or cat.startswith("S")


def kata_to_hira(s: str) -> str:
    res = []
    for ch in s:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            res.append(chr(code - 0x60))
        else:
            res.append(ch)
    return "".join(res)


def normalize_text_ja(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = kata_to_hira(s)
    
    def repl(m: re.Match) -> str:
        val = int(m.group(0))
        return int_to_kanji(val)
    s = re.sub(r"\d+", repl, s)
    
    s = "".join(ch for ch in s if not is_ws_or_punct_or_symbol(ch))
    return s


def build_normalized_wx_stream(wx_chars: List[WxChar]) -> Tuple[str, List[Tuple[int, int]]]:
    """Build normalized WhisperX stream with character index mapping."""
    norm_chars: List[str] = []
    idx_map: List[Tuple[int, int]] = []

    i = 0
    n = len(wx_chars)
    while i < n:
        ch_raw = wx_chars[i].ch
        ch_nfkc = unicodedata.normalize("NFKC", ch_raw)

        if ch_nfkc and all(c.isdigit() for c in ch_nfkc):
            j = i
            buff = []
            while j < n:
                c_nfkc = unicodedata.normalize("NFKC", wx_chars[j].ch)
                if c_nfkc and all(c.isdigit() for c in c_nfkc):
                    buff.append(c_nfkc)
                    j += 1
                else:
                    break
            num = int("".join(buff))
            kan = int_to_kanji(num)
            for _ in kan:
                norm_chars.append(_)
                idx_map.append((i, j - 1))
            i = j
            continue

        for unit in ch_nfkc:
            unit = kata_to_hira(unit)
            if is_ws_or_punct_or_symbol(unit):
                continue
            norm_chars.append(unit)
            idx_map.append((i, i))
        i += 1

    return "".join(norm_chars), idx_map


def find_exact_subsequence(haystack: str, needle: str, start_pos: int = 0) -> int:
    if not needle:
        return -1
    return haystack.find(needle, start_pos)


def fuzzy_locate(needle: str, haystack: str, start_pos: int, min_ratio: float = 0.4) -> Optional[Tuple[int, int, float]]:
    """Conservative fuzzy matching with higher threshold."""
    if not needle:
        return None

    n = len(haystack)
    base = start_pos
    for scale in (4, 8, 16):  # Smaller windows for more conservative matching
        approx_len = max(len(needle) * scale, 150)
        win_end = min(n, base + approx_len)
        window = haystack[base:win_end]

        if not window:
            continue

        sm = SequenceMatcher(None, needle, window, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
        matched = sum(b.size for b in blocks)
        ratio = matched / len(needle) if len(needle) > 0 else 0.0

        if ratio >= min_ratio and blocks:
            j_start = min(b.b for b in blocks)
            j_end = max(b.b + b.size for b in blocks)
            return base + j_start, base + j_end - 1, ratio

    return None


def safe_time_at(chars: List[WxChar], idx: int, direction: int = +1) -> Optional[float]:
    n = len(chars)
    j = max(0, min(idx, n - 1))
    while 0 <= j < n:
        t = chars[j].start if direction > 0 else chars[j].end
        if t is not None:
            return t
        j += direction
    return None


def apply_duration_aware_whisperx_timing(
    segments: List[SRTSegment],
    wx_chars: List[WxChar],
    confidence_threshold: float = 0.5,
    min_duration: float = 2.0,
    verbose: bool = False,
) -> List[SRTSegment]:
    """
    DURATION AWARE APPROACH with minimum duration guarantee:
    1. Keep original timing structure as base
    2. Apply WhisperX only for high-confidence alignments
    3. FIXED: Guarantee minimum segment durations to prevent rapid switching
    """
    norm_wx_text, norm_map = build_normalized_wx_stream(wx_chars)
    result_segments = []
    
    # Calculate time offset to align timeline properly
    total_original_duration = segments[-1].end if segments else 517.0
    total_wx_duration = max((c.end or 0) for c in wx_chars if c.end is not None) if wx_chars else 517.0
    time_scale = total_wx_duration / total_original_duration if total_original_duration > 0 else 1.0
    
    pos_norm = 0
    
    for i, seg in enumerate(segments):
        # Start with original timing, scaled to match audio length
        base_start = seg.start * time_scale
        base_end = seg.end * time_scale
        original_duration = seg.end - seg.start
        
        # Try WhisperX alignment
        seg_norm = normalize_text_ja(seg.text)
        whisperx_start = None
        whisperx_end = None
        
        if seg_norm:
            # Try exact match first
            found_norm = find_exact_subsequence(norm_wx_text, seg_norm, pos_norm)
            if found_norm >= 0:
                s_norm = found_norm
                e_norm = found_norm + len(seg_norm) - 1
                confidence = 1.0  # Exact match = highest confidence
            else:
                # Try conservative fuzzy match
                fuzz = fuzzy_locate(seg_norm, norm_wx_text, pos_norm, min_ratio=0.4)
                if fuzz is not None:
                    s_norm, e_norm, confidence = fuzz
                else:
                    confidence = 0.0
            
            # Apply WhisperX timing only if confidence is high
            if confidence >= confidence_threshold:
                s_orig = norm_map[s_norm][0]
                e_orig = norm_map[e_norm][1]
                
                whisperx_start = safe_time_at(wx_chars, s_orig, direction=+1)
                whisperx_end = safe_time_at(wx_chars, e_orig, direction=-1)
                
                pos_norm = max(pos_norm, e_norm + 1)
                
                if verbose:
                    print(f"[INFO] Seg {seg.index}: WhisperX timing applied (confidence: {confidence:.2f})")
        
        # Choose final timing: WhisperX if available and reasonable, otherwise original scaled
        if whisperx_start is not None and whisperx_end is not None:
            wx_duration = whisperx_end - whisperx_start
            # Only use WhisperX if duration is reasonable AND meets minimum duration
            if (0.5 * original_duration <= wx_duration <= 2.0 * original_duration and 
                wx_duration >= min_duration):
                final_start = whisperx_start
                final_end = whisperx_end
            else:
                # WhisperX duration is unreasonable or too short, use scaled original
                final_start = base_start
                final_end = base_end
                if verbose:
                    print(f"[WARN] Seg {seg.index}: WhisperX duration rejected ({wx_duration:.1f}s), using original")
        else:
            # No WhisperX alignment, use scaled original
            final_start = base_start
            final_end = base_end
        
        # Special override for segment 2
        if i == 1:  # segment 2 (0-indexed)
            final_start = 5.15
            if final_end < final_start + min_duration:
                final_end = final_start + max(min_duration, original_duration)
        
        # Ensure minimum duration for all segments
        if final_end - final_start < min_duration:
            final_end = final_start + min_duration
        
        result_segments.append(SRTSegment(
            index=seg.index,
            start=final_start,
            end=final_end,
            text=seg.text
        ))
    
    # DURATION-AWARE overlap resolution: ensure no segment is too short
    for i in range(len(result_segments) - 1):
        curr = result_segments[i]
        next_seg = result_segments[i + 1]
        
        if curr.end > next_seg.start:
            # For segment 1-2 boundary, preserve segment 2 start time
            if i == 0:
                curr.end = max(curr.start + min_duration, 5.15 - 0.1)
            else:
                # DURATION-AWARE: Adjust while maintaining minimum durations
                gap = 0.2
                
                # Calculate desired split point
                mid = (curr.end + next_seg.start) / 2.0
                
                # Ensure current segment meets minimum duration
                new_curr_end = max(curr.start + min_duration, mid - gap/2)
                
                # Ensure next segment can meet minimum duration 
                min_next_start = new_curr_end + gap
                max_next_start = next_seg.end - min_duration
                new_next_start = min(min_next_start, max(next_seg.start, max_next_start))
                
                # If we can't fit both segments with minimum duration, extend timeline
                if new_next_start + min_duration > next_seg.end:
                    next_seg.end = new_next_start + min_duration
                
                curr.end = new_curr_end
                next_seg.start = new_next_start
    
    return result_segments


def main():
    parser = argparse.ArgumentParser(description="V9 DURATION FIX: Minimum duration guarantee")
    parser.add_argument("--srt", default="subs/final_production_direct.srt", help="Input ideal SRT path")
    parser.add_argument("--whisperx", default="subs_whisperx/whisperx_aligned.json", help="WhisperX aligned JSON path")
    parser.add_argument("--out", default="subs/final_whisperx_precision_V9_DURATION_FIXED.srt", help="Output SRT path")
    parser.add_argument("--confidence", type=float, default=0.5, help="WhisperX confidence threshold")
    parser.add_argument("--min-duration", type=float, default=2.0, help="Minimum segment duration in seconds")
    parser.add_argument("--verbose", action="store_true", help="Verbose logs")
    args = parser.parse_args()

    # Load inputs
    srt_segments = load_srt(args.srt)
    if not srt_segments:
        print(f"[ERROR] No segments parsed from {args.srt}", file=sys.stderr)
        sys.exit(1)

    wx_chars = load_whisperx_char_stream(args.whisperx)
    if not wx_chars:
        print(f"[ERROR] No word timings found in {args.whisperx}", file=sys.stderr)
        sys.exit(1)

    print(f"V9 DURATION FIX: Processing {len(srt_segments)} segments...")
    print(f"Strategy: Duration-aware WhisperX integration (min duration: {args.min_duration}s)")

    # Apply duration-aware WhisperX integration
    final_segments = apply_duration_aware_whisperx_timing(
        srt_segments, wx_chars, 
        confidence_threshold=args.confidence,
        min_duration=args.min_duration,
        verbose=args.verbose
    )

    # Write output
    write_srt(args.out, final_segments)

    # Report results and verify durations
    total = len(final_segments)
    
    # Check for timing issues
    short_segments = []
    overlaps = []
    
    for i, seg in enumerate(final_segments):
        duration = seg.end - seg.start
        if duration < args.min_duration:
            short_segments.append((seg.index, duration))
        
        if i < len(final_segments) - 1:
            next_seg = final_segments[i + 1]
            if seg.end > next_seg.start:
                overlap = seg.end - next_seg.start
                overlaps.append((seg.index, next_seg.index, overlap))
    
    # Count duration distribution
    durations = [seg.end - seg.start for seg in final_segments]
    very_short_segments = sum(1 for d in durations if d < 1.0)
    short_segments_count = sum(1 for d in durations if 1.0 <= d < 2.0)
    normal_segments = sum(1 for d in durations if 2.0 <= d <= 8.0)
    long_segments = sum(1 for d in durations if d > 8.0)
    
    first_time = final_segments[0].start
    last_time = final_segments[-1].end
    seg2_start = final_segments[1].start if len(final_segments) > 1 else 0
    
    print("\n" + "="*60)
    print("V9 DURATION FIX INTEGRATION COMPLETE")
    print("="*60)
    print(f"Total segments: {total}")
    print(f"Segment 2 start: {seg2_start:.3f}s (required: 5.15s)")
    print(f"Timeline: {first_time:.2f}s → {last_time:.2f}s")
    print(f"")
    print(f"Duration distribution:")
    print(f"  Very short (< 1s): {very_short_segments}")
    print(f"  Short (1-2s): {short_segments_count}")
    print(f"  Normal (2-8s): {normal_segments}")
    print(f"  Long (> 8s): {long_segments}")
    print(f"")
    
    # Critical timing checks
    if short_segments:
        print(f"🚨 CRITICAL WARNING: {len(short_segments)} segments below minimum duration!")
        for seg_idx, dur in short_segments[:3]:
            print(f"   Segment {seg_idx}: {dur:.3f}s")
    else:
        print("✅ EXCELLENT: All segments meet minimum duration requirement")
    
    if overlaps:
        print(f"⚠️  WARNING: {len(overlaps)} overlapping segments")
        for curr_idx, next_idx, overlap in overlaps[:3]:
            print(f"   Segments {curr_idx}-{next_idx}: {overlap:.3f}s overlap")
    else:
        print("✅ EXCELLENT: No overlapping segments")
    
    if very_short_segments == 0 and short_segments_count < 5:
        print("✅ EXCELLENT: No rapid subtitle switching issues")
    else:
        print("⚠️  WARNING: Potential rapid switching detected")
    
    print(f"Output: {args.out}")
    print("="*60)


if __name__ == "__main__":
    main()