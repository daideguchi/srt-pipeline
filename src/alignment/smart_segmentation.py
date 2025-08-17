from __future__ import annotations

import unicodedata
from dataclasses import replace
from difflib import SequenceMatcher
from typing import List, Tuple, Optional

from src.types import Segment, Word


# -----------------------------
# JP-aware constants and helpers
# -----------------------------

JA_END_PUNCT = set("。｡！？!?…♪」』】》〉〕≫")
JA_PAUSE_PUNCT = set("、，,・：:；;―ー…")
MAX_CHARS_PER_LINE = 13  # guideline for JP readability
MIN_DURATION = 1.5  # increased for better readability
MAX_DURATION = 8.0  # slightly increased to allow longer natural segments
TARGET_CPS_MIN = 4.0
TARGET_CPS_MAX = 7.0  # slightly relaxed to preserve content accuracy
MIN_GAP = 0.05  # reduced to allow more extension


def _norm(s: str) -> str:
    # NFKC and remove spaces/newlines for robust alignment
    s = unicodedata.normalize("NFKC", s or "")
    return s.replace(" ", "").replace("\u3000", "").replace("\n", "").replace("\r", "")


def _chars_len(s: str) -> int:
    return len(_norm(s))


def _segment_text(seg: Segment) -> str:
    if seg.text:
        return seg.text
    if seg.words:
        return "".join(w.text for w in seg.words)
    return ""


def _rebuild_text(ws: List[Word]) -> str:
    return "".join(w.text for w in ws)


def _cps(seg: Segment) -> float:
    dur = max(seg.end - seg.start, 0.000001)
    return _chars_len(_segment_text(seg)) / dur


def _ensure_linebreaks(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> str:
    """Insert line breaks at natural JP punctuation to keep lines readable."""
    t = text.strip()
    if not t:
        return t

    res: List[str] = []
    cur = t
    while _chars_len(cur) > max_chars:
        # Find last good break within first max_chars
        limit = max_chars
        slice_chars = 0
        pos = 0
        last_break = -1
        # iterate by characters to find breakpoints (punctuation or quotes)
        while pos < len(cur) and slice_chars < limit:
            ch = cur[pos]
            if ch in JA_END_PUNCT or ch in JA_PAUSE_PUNCT or ch in {"」", "』"}:
                last_break = pos + 1
            # count visible chars (ignore spaces)
            if ch not in {" ", "\u3000"}:
                slice_chars += 1
            pos += 1
        if last_break <= 0:
            # fallback: break at current pos
            last_break = pos
        res.append(cur[: last_break].strip())
        cur = cur[last_break :].lstrip()
    if cur:
        res.append(cur)
    return "\n".join(res)


def _flatten_words(segments: List[Segment]) -> List[Word]:
    words: List[Word] = []
    for seg in segments:
        if seg.words:
            words.extend(seg.words)
        elif seg.text:
            # synthesize per-char words using segment timing distribution
            start = seg.start
            end = seg.end
            text = seg.text
            n = max(len(text), 1)
            step = (end - start) / n if end > start and n > 0 else 0.0
            t = start
            for ch in text:
                w_end = min(end, t + step) if step else end
                words.append(Word(text=ch, start=t, end=w_end, confidence=0.0, source="synthetic"))
                t = w_end
    return words


def _map_rec_to_script(script_text: str, words: List[Word]) -> Tuple[List[int], List[Tuple[int, int]]]:
    """Return mapping from recognized char index -> script char index, and per-word spans.

    - Recognized string is join of words' text, NFKC, no spaces.
    - script_text also normalized similarly.
    """
    script_norm = _norm(script_text)
    rec_norm_parts: List[str] = []
    word_spans: List[Tuple[int, int]] = []
    rec_pos = 0
    for w in words:
        nw = _norm(w.text)
        rec_norm_parts.append(nw)
        word_spans.append((rec_pos, rec_pos + len(nw)))
        rec_pos += len(nw)
    rec_norm = "".join(rec_norm_parts)

    # Build char mapping using longest match blocks
    sm = SequenceMatcher(None, rec_norm, script_norm)
    blocks = sm.get_matching_blocks()
    rec_to_script = [-1] * len(rec_norm)
    for b in blocks:
        a, bpos, size = b.a, b.b, b.size
        for k in range(size):
            rec_to_script[a + k] = bpos + k
    return rec_to_script, word_spans


def _break_indices_from_script(script_text: str, rec_to_script: List[int]) -> List[int]:
    """Collect recognized-string indices where script has sentence-ending punctuation."""
    script_norm = _norm(script_text)
    # indices just after an end punct in script
    boundary_script_positions = [i + 1 for i, ch in enumerate(script_norm) if ch in JA_END_PUNCT]

    rec_breaks: List[int] = []
    if not rec_to_script:
        return rec_breaks
    # For each script boundary, find farthest rec index mapping to it (rightmost)
    for sp in boundary_script_positions:
        best = -1
        for ri, si in enumerate(rec_to_script):
            if si == sp - 1:
                best = max(best, ri + 1)
        if best >= 0:
            rec_breaks.append(best)
    # Ensure sorted and unique
    rec_breaks = sorted(set(rec_breaks))
    return rec_breaks


def _group_words_by_breaks(words: List[Word], word_spans: List[Tuple[int, int]], rec_breaks: List[int]) -> List[List[Word]]:
    """Group words into chunks by nearest recognized-char breaks."""
    groups: List[List[Word]] = []
    cur: List[Word] = []
    b_idx = 0
    cur_break = rec_breaks[b_idx] if b_idx < len(rec_breaks) else None
    for w, span in zip(words, word_spans):
        if cur_break is None:
            cur.append(w)
            continue
        # word lies entirely before the break
        if span[1] <= cur_break:
            cur.append(w)
            continue
        # word crosses or lies after the break -> close current before this word
        if cur:
            groups.append(cur)
            cur = []
        # Advance break indices until this word ends before current break
        while cur_break is not None and span[0] >= cur_break:
            b_idx += 1
            cur_break = rec_breaks[b_idx] if b_idx < len(rec_breaks) else None
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def _words_to_segment(ws: List[Word]) -> Segment:
    if not ws:
        return Segment(start=0.0, end=0.0, text="", words=[])
    start = ws[0].start
    end = ws[-1].end
    text = _ensure_linebreaks(_rebuild_text(ws))
    return Segment(start=start, end=end, text=text, words=list(ws))


def align_with_script(srt_segments: List[Segment], script_text: str) -> List[Segment]:
    """Forced-align segmentation to the original script's sentence boundaries.

    - Build recognized string from word sequence and align to script via SequenceMatcher.
    - Use script sentence-ending punctuation to decide segment boundaries.
    - Reconstruct segments from original word timing, preserving word-level info.
    """
    words = _flatten_words(srt_segments)
    if not words:
        return list(srt_segments)

    rec_to_script, word_spans = _map_rec_to_script(script_text, words)
    rec_breaks = _break_indices_from_script(script_text, rec_to_script)
    # Always include end-of-stream as a break
    if word_spans:
        total_len = word_spans[-1][1]
        if total_len not in rec_breaks:
            rec_breaks.append(total_len)
    groups = _group_words_by_breaks(words, word_spans, rec_breaks)
    segments = [_words_to_segment(g) for g in groups if g]
    # Clean up: merge extremely small trailing segments produced by alignment noise
    segments = merge_short_segments(segments)
    return segments


def fix_boundaries(segments: List[Segment]) -> List[Segment]:
    """Ensure segments end at natural punctuation, borrowing words across boundaries when safe."""
    if not segments:
        return []
    segs = [replace(s, words=list(s.words), text=_segment_text(s)) for s in segments]
    out: List[Segment] = []
    i = 0
    while i < len(segs):
        s = segs[i]
        text = _segment_text(s)
        # If already ends with end punct, keep
        if text.strip().endswith(tuple(JA_END_PUNCT)) or i == len(segs) - 1:
            out.append(_words_to_segment(s.words or []))
            i += 1
            continue
        # Try to pull words from following segment until reaching punctuation, limited to small time extension
        j = i + 1
        pulled: List[Word] = []
        while j < len(segs) and not (_rebuild_text(pulled) and _rebuild_text(pulled).strip().endswith(tuple(JA_END_PUNCT))):
            next_seg = segs[j]
            for w in next_seg.words:
                pulled.append(w)
                if w.text and w.text.strip() in JA_END_PUNCT:
                    break
            # stop after first punct obtained
            if pulled and pulled[-1].text.strip() in JA_END_PUNCT:
                break
            j += 1
            # Do not cross too many segments
            if (j - i) > 2:
                break
        if pulled and pulled[-1].text.strip() in JA_END_PUNCT:
            # Extend current with pulled words up to punctuation
            new_words = list(s.words) + pulled
            out.append(_words_to_segment(new_words))
            # Trim the consumed words from following segments
            remaining = pulled[-1]
            # Build remainder words list
            rem_words: List[Word] = []
            consumed = 0
            k = i + 1
            done = False
            for k in range(i + 1, j + 1):
                for w in segs[k].words:
                    if not done:
                        consumed += 1
                    if w is remaining:
                        done = True
                        continue
                    if done:
                        rem_words.append(w)
            # Replace first next segment with remainder; drop fully consumed ones
            if rem_words:
                segs[i + 1] = _words_to_segment(rem_words)
                # Drop segments between i+2 and j inclusive
                del segs[i + 2 : j + 1]
            else:
                # Remove fully consumed segments
                del segs[i + 1 : j + 1]
            i += 1
        else:
            out.append(_words_to_segment(s.words or []))
            i += 1
    return out


def merge_short_segments(segments: List[Segment]) -> List[Segment]:
    """Merge too-short segments with neighbors to improve readability and CPS stability."""
    if not segments:
        return []
    out: List[Segment] = []
    i = 0
    while i < len(segments):
        cur = segments[i]
        dur = max(cur.end - cur.start, 0.0)
        if dur >= MIN_DURATION or i == len(segments) - 1:
            out.append(_words_to_segment(cur.words or []))
            i += 1
            continue
        # Try merge with next
        nxt = segments[i + 1]
        merged_words = (cur.words or []) + (nxt.words or [])
        merged = _words_to_segment(merged_words)
        if _cps(merged) <= TARGET_CPS_MAX + 0.5:  # less aggressive merging to preserve accuracy
            out.append(merged)
            i += 2
        else:
            out.append(_words_to_segment(cur.words or []))
            i += 1
    return out


def split_long_segments(segments: List[Segment]) -> List[Segment]:
    """Split long or dense segments at natural breaks (句読点)."""
    result: List[Segment] = []
    for s in segments:
        need_split = (s.end - s.start) > MAX_DURATION or _cps(s) > TARGET_CPS_MAX + 1.0  # more tolerant threshold
        if not need_split or not s.words:
            result.append(_words_to_segment(s.words or []))
            continue
        # Identify split points by punctuation in text
        words = s.words
        cuts: List[int] = []  # word indices after which to cut
        for idx, w in enumerate(words):
            if w.text.strip() in JA_END_PUNCT or w.text.strip() in JA_PAUSE_PUNCT:
                if idx + 1 < len(words):
                    cuts.append(idx + 1)
        if not cuts:
            # fallback: split roughly in half
            cuts = [len(words) // 2]
        last = 0
        for c in cuts:
            chunk = words[last:c]
            if chunk:
                result.append(_words_to_segment(chunk))
            last = c
        if last < len(words):
            result.append(_words_to_segment(words[last:]))
    return result


def _extend_display_times(segments: List[Segment]) -> List[Segment]:
    """Adjust segment start/end within available gaps to bring CPS into 4-6 range.

    Does not alter word timings; only display window (segment.start/end).
    """
    if not segments:
        return []
    segs = [replace(s, words=list(s.words)) for s in segments]
    n = len(segs)
    for i, s in enumerate(segs):
        chars = _chars_len(_segment_text(s))
        if chars == 0:
            continue
        desired_min = max(chars / TARGET_CPS_MAX, MIN_DURATION)
        desired_max = min(chars / TARGET_CPS_MIN, MAX_DURATION)
        cur_dur = max(s.end - s.start, 0.0)
        target_dur = min(max(cur_dur, desired_min), desired_max)
        if target_dur <= cur_dur + 1e-6:
            # no extension needed or possible shrinking (we avoid shrinking)
            continue
        # Available slack before and after
        prev_end = segs[i - 1].end if i > 0 else None
        next_start = segs[i + 1].start if i < n - 1 else None
        slack_before = float('inf') if prev_end is None else max(0.0, (s.start - prev_end) - MIN_GAP)
        slack_after = float('inf') if next_start is None else max(0.0, (next_start - s.end) - MIN_GAP)
        need = target_dur - cur_dur
        # Prefer extending after, then before
        extend_after = min(need, slack_after)
        s.end += extend_after
        need -= extend_after
        if need > 1e-6 and slack_before > 0:
            extend_before = min(need, slack_before)
            s.start -= extend_before
    return segs


def optimize_cps(segments: List[Segment]) -> List[Segment]:
    """Optimize CPS by merging, splitting, and extending display time to target 4–7 cps."""
    if not segments:
        return []
    # Apply optimizations more conservatively to preserve content accuracy
    segs = merge_short_segments(segments)
    segs = split_long_segments(segs)
    segs = _extend_display_times(segs)
    # Normalize text line breaks for readability
    cleaned: List[Segment] = []
    for s in segs:
        ws = s.words or []
        text = _ensure_linebreaks(_rebuild_text(ws))
        cleaned.append(Segment(start=s.start, end=s.end, text=text, words=ws))
    return cleaned


def balanced_alignment(srt_segments: List[Segment], script_text: str) -> List[Segment]:
    """Balanced alignment that prioritizes content accuracy while improving readability.
    
    Uses script alignment more selectively to avoid over-segmentation and content loss.
    """
    words = _flatten_words(srt_segments)
    if not words:
        return list(srt_segments)

    # First, try conservative optimization of existing segments
    optimized_original = optimize_cps(srt_segments)
    
    # Check if original segmentation is already reasonable
    original_coverage = _calculate_coverage(optimized_original, script_text)
    original_avg_cps = sum(_cps(s) for s in optimized_original) / len(optimized_original) if optimized_original else 0
    
    # If original is already decent (>75% coverage and reasonable CPS), use lighter alignment
    if original_coverage > 0.75 and original_avg_cps < 7.5:
        # Apply only boundary fixes and minimal adjustments
        adjusted = fix_boundaries(optimized_original)
        return optimize_cps(adjusted)
    
    # Otherwise, apply full script alignment
    rec_to_script, word_spans = _map_rec_to_script(script_text, words)
    rec_breaks = _break_indices_from_script(script_text, rec_to_script)
    
    # Use fewer break points to avoid over-segmentation
    if len(rec_breaks) > len(srt_segments) * 1.5:
        # Keep only the strongest breaks (at major punctuation)
        rec_breaks = rec_breaks[::2]  # Take every other break
    
    if word_spans:
        total_len = word_spans[-1][1]
        if total_len not in rec_breaks:
            rec_breaks.append(total_len)
            
    groups = _group_words_by_breaks(words, word_spans, rec_breaks)
    segments = [_words_to_segment(g) for g in groups if g]
    
    # Apply conservative optimization
    segments = merge_short_segments(segments)
    return segments


def _calculate_coverage(segments: List[Segment], script_text: str) -> float:
    """Calculate how much of the script is covered by segments."""
    if not script_text or not segments:
        return 0.0
    
    script_norm = _norm(script_text)
    srt_text = "".join(s.text or "" for s in segments)
    srt_norm = _norm(srt_text)
    
    from difflib import SequenceMatcher
    sm = SequenceMatcher(None, script_norm, srt_norm)
    blocks = sm.get_matching_blocks()
    match_len = sum(b.size for b in blocks)
    return match_len / max(1, len(script_norm))


__all__ = [
    "align_with_script",
    "balanced_alignment",
    "optimize_cps",
    "fix_boundaries",
    "merge_short_segments",
    "split_long_segments",
]

