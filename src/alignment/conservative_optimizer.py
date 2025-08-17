#!/usr/bin/env python3
"""
Conservative subtitle optimizer - preserves content accuracy while improving readability.

Strategy:
1. Keep original segmentation intact
2. Optimize only timing (extend display time) 
3. Improve line breaks within segments
4. Minimal segment merging only where absolutely safe
"""

from __future__ import annotations

import unicodedata
from dataclasses import replace
from typing import List, Tuple

from src.types import Segment, Word


# Constants
JA_END_PUNCT = set("。｡！？!?…♪」』】》〉〕≫")
JA_PAUSE_PUNCT = set("、，,・：:；;―ー…")
MAX_CHARS_PER_LINE = 15  # slightly more lenient for natural text
MIN_DURATION = 1.0
MAX_DURATION = 8.0
TARGET_CPS_MIN = 4.0
TARGET_CPS_MAX = 6.5  # conservative target
MIN_GAP = 0.05


def _norm(s: str) -> str:
    """Normalize text for consistent processing."""
    s = unicodedata.normalize("NFKC", s or "")
    return s.replace(" ", "").replace("\u3000", "").replace("\n", "").replace("\r", "")


def _chars_len(s: str) -> int:
    """Count visible characters."""
    return len(_norm(s))


def _segment_text(seg: Segment) -> str:
    """Get text from segment."""
    if seg.text:
        return seg.text
    if seg.words:
        return "".join(w.text for w in seg.words)
    return ""


def _cps(seg: Segment) -> float:
    """Calculate characters per second."""
    dur = max(seg.end - seg.start, 0.000001)
    return _chars_len(_segment_text(seg)) / dur


def _ensure_linebreaks(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> str:
    """Insert natural line breaks at Japanese punctuation."""
    t = text.strip()
    if not t:
        return t

    # If text is short enough, return as-is
    if _chars_len(t) <= max_chars:
        return t
    
    # Find natural break point
    lines = []
    current = t
    
    while _chars_len(current) > max_chars:
        # Look for punctuation break within reasonable range
        best_break = -1
        char_count = 0
        
        for i, char in enumerate(current):
            if char not in {" ", "\u3000"}:
                char_count += 1
                
            # Found a good break point
            if char in JA_END_PUNCT or char in JA_PAUSE_PUNCT:
                if char_count <= max_chars:
                    best_break = i + 1
                elif best_break == -1:  # No good break found yet, take this as fallback
                    best_break = i + 1
                    break
        
        if best_break == -1:
            # No punctuation found, break at character limit
            char_count = 0
            for i, char in enumerate(current):
                if char not in {" ", "\u3000"}:
                    char_count += 1
                if char_count >= max_chars:
                    best_break = i + 1
                    break
        
        if best_break <= 0:
            best_break = len(current) // 2  # Emergency fallback
            
        lines.append(current[:best_break].strip())
        current = current[best_break:].strip()
    
    if current:
        lines.append(current)
    
    return "\n".join(lines)


def _extend_display_time(segments: List[Segment]) -> List[Segment]:
    """Extend display time to improve CPS without changing content."""
    if not segments:
        return []
        
    result = []
    n = len(segments)
    
    for i, seg in enumerate(segments):
        chars = _chars_len(_segment_text(seg))
        if chars == 0:
            result.append(seg)
            continue
            
        current_cps = _cps(seg)
        
        # Only extend if CPS is too high
        if current_cps <= TARGET_CPS_MAX:
            result.append(seg)
            continue
            
        # Calculate ideal duration
        ideal_duration = chars / TARGET_CPS_MAX
        current_duration = seg.end - seg.start
        
        if ideal_duration <= current_duration:
            result.append(seg)
            continue
            
        # Check available space
        prev_end = segments[i-1].end if i > 0 else 0.0
        next_start = segments[i+1].start if i < n-1 else float('inf')
        
        # Calculate maximum possible extension
        max_start = prev_end + MIN_GAP if i > 0 else seg.start
        max_end = next_start - MIN_GAP if i < n-1 else seg.start + ideal_duration
        
        # Extend within available space
        new_duration = min(ideal_duration, max_end - max_start)
        new_duration = min(new_duration, MAX_DURATION)
        
        if new_duration > current_duration:
            # Center the extension
            extension = new_duration - current_duration
            extend_before = min(extension / 2, seg.start - max_start)
            extend_after = extension - extend_before
            
            new_start = max(max_start, seg.start - extend_before)
            new_end = min(max_end, seg.end + extend_after)
            
            extended_seg = replace(seg, start=new_start, end=new_end)
            result.append(extended_seg)
        else:
            result.append(seg)
    
    return result


def _safe_merge_segments(segments: List[Segment]) -> List[Segment]:
    """Safely merge only very short segments with neighbors."""
    if not segments:
        return []
        
    result = []
    i = 0
    
    while i < len(segments):
        current = segments[i]
        current_duration = current.end - current.start
        
        # Only merge if segment is extremely short
        if current_duration < 0.8 and i < len(segments) - 1:
            next_seg = segments[i + 1]
            
            # Check if merging makes sense
            merged_text = _segment_text(current) + _segment_text(next_seg)
            merged_chars = _chars_len(merged_text)
            merged_duration = next_seg.end - current.start
            merged_cps = merged_chars / max(merged_duration, 0.001)
            
            # Only merge if result is not too dense
            if merged_cps <= TARGET_CPS_MAX + 1.0 and merged_duration <= MAX_DURATION:
                merged_seg = Segment(
                    start=current.start,
                    end=next_seg.end,
                    text=_ensure_linebreaks(merged_text),
                    words=(current.words or []) + (next_seg.words or [])
                )
                result.append(merged_seg)
                i += 2  # Skip the next segment
                continue
        
        # Apply line break optimization to current segment
        optimized_text = _ensure_linebreaks(_segment_text(current))
        optimized_seg = replace(current, text=optimized_text)
        result.append(optimized_seg)
        i += 1
    
    return result


def conservative_optimize(segments: List[Segment]) -> List[Segment]:
    """Conservative optimization focusing on timing and formatting improvements."""
    if not segments:
        return []
    
    # Step 1: Safe merging of extremely short segments
    merged = _safe_merge_segments(segments)
    
    # Step 2: Extend display time to improve CPS
    extended = _extend_display_time(merged)
    
    # Step 3: Final formatting pass
    formatted = []
    for seg in extended:
        text = _ensure_linebreaks(_segment_text(seg))
        formatted_seg = replace(seg, text=text)
        formatted.append(formatted_seg)
    
    return formatted


def analyze_optimization_impact(original: List[Segment], optimized: List[Segment]) -> dict:
    """Analyze the impact of optimization."""
    def _segment_stats(segments):
        if not segments:
            return {"count": 0, "avg_cps": 0, "high_cps_count": 0, "short_count": 0}
        
        cps_values = [_cps(s) for s in segments]
        avg_cps = sum(cps_values) / len(cps_values)
        high_cps_count = sum(1 for cps in cps_values if cps > TARGET_CPS_MAX)
        short_count = sum(1 for s in segments if (s.end - s.start) < MIN_DURATION)
        
        return {
            "count": len(segments),
            "avg_cps": avg_cps,
            "high_cps_count": high_cps_count,
            "short_count": short_count
        }
    
    orig_stats = _segment_stats(original)
    opt_stats = _segment_stats(optimized)
    
    return {
        "original": orig_stats,
        "optimized": opt_stats,
        "improvements": {
            "segment_change": opt_stats["count"] - orig_stats["count"],
            "cps_improvement": orig_stats["avg_cps"] - opt_stats["avg_cps"],
            "high_cps_reduction": orig_stats["high_cps_count"] - opt_stats["high_cps_count"],
            "short_reduction": orig_stats["short_count"] - opt_stats["short_count"]
        }
    }