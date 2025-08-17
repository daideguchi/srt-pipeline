"""
Script/Subtitles Checker for Japanese content.

Functions:
- load_srt(path): Parse SRT into segments with timing and normalized text.
- load_script(path): Load and clean original script text (JP-aware normalization).
- compare_content(srt_text, script_text): Compute similarity and coverage metrics.
- analyze_segments(segments, script_text=None): Timing/segmentation quality analysis.
- generate_report(...): Orchestrate end-to-end comparison and produce a report.

This module focuses on Japanese text handling (full-width characters, punctuation,
and common transcription artifacts) without external dependencies.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional, Tuple
from difflib import SequenceMatcher


# -----------------------------
# Data structures and constants
# -----------------------------


@dataclass
class SRTSegment:
    index: int
    start: float  # seconds
    end: float  # seconds
    duration: float  # seconds
    text: str
    text_norm: str


# Timing and quality heuristics (tuned for JP subtitles)
MIN_DURATION = 1.0  # s: too short to read comfortably
MAX_DURATION = 7.0  # s: too long to keep on screen
TARGET_CPS = 4.0  # chars/sec recommended target (JP)
WARN_CPS = 6.0  # chars/sec warning threshold (high reading speed)
MAX_CHARS_PER_LINE = 13  # JP broadcast guideline (approx.)

# Punctuation considered good boundaries for line/segment ends
JA_END_PUNCT = "。｡！？!?…♪」』】》〉〕≫≫」』"
JA_PAUSE_PUNCT = "、，,・：:；;―ー…"


# -----------------------------
# Utility functions
# -----------------------------


def _parse_srt_timestamp(ts: str) -> float:
    """Parse SRT timestamp 'HH:MM:SS,mmm' into seconds (float)."""
    # Robust to variations like '.' as millisecond separator
    ts = ts.strip()
    ts = ts.replace(".", ",")
    hhmmss, ms = ts.split(",")
    hh, mm, ss = hhmmss.split(":")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def _strip_srt_tags(text: str) -> str:
    """Remove common SRT inline tags like <i>...</i> and HTML-like artifacts."""
    # Remove <i>, <b>, <font ...>, </...>
    text = re.sub(r"</?[^>]+>", "", text)
    # Remove speaker labels like "[Music]", "(笑)", "♪"
    text = re.sub(r"\[(?:[^\]]+)\]", "", text)
    text = re.sub(r"\((?:[^\)]+)\)", "", text)
    text = text.replace("♪", "")
    return text


def normalize_ja_text(text: str, *, keep_quotes: bool = True) -> str:
    """Normalize Japanese text for comparison.

    - NFKC normalization to unify widths
    - Remove SRT tags and most bracketed stage directions
    - Lowercase ASCII
    - Collapse whitespace and newlines
    - Keep Japanese quotes 「」『』 by default
    - Preserve sentence punctuation, but unify some variants
    """
    if not text:
        return ""

    text = _strip_srt_tags(text)
    text = unicodedata.normalize("NFKC", text)

    # Optionally protect JP quotes content from being stripped
    placeholders: List[Tuple[str, str]] = []
    if keep_quotes:
        def _protect(m: re.Match) -> str:
            placeholder = f"§Q{len(placeholders)}§"
            placeholders.append((placeholder, m.group(0)))
            return placeholder

        text = re.sub(r"[「『][^」』]*[」』]", _protect, text)

    # Remove bracketed stage directions ((), [], {}, 【】, 《》, 〈〉, 『』 already protected)
    text = re.sub(r"[\(\[\{（【《〈][^\)\]\}）】》〉]*[\)\]\}）】》〉]", " ", text)

    # Restore protected quotes
    if keep_quotes and placeholders:
        for ph, original in placeholders:
            text = text.replace(ph, original)

    # Normalize punctuation spaces around
    text = re.sub(r"\s+", " ", text).strip()

    # Lowercase ASCII only (JP unaffected)
    text = ''.join(ch.lower() if ord(ch) < 128 else ch for ch in text)

    return text


def _char_ngrams(s: str, n: int = 2) -> List[str]:
    s = s.replace(" ", "")
    return [s[i : i + n] for i in range(max(0, len(s) - n + 1))]


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein distance (DP). O(len(a)*len(b)) memory-optimized."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Ensure a is the shorter
    if len(a) > len(b):
        a, b = b, a
    previous = list(range(len(a) + 1))
    for i, cb in enumerate(b, 1):
        current = [i]
        for j, ca in enumerate(a, 1):
            ins = current[j - 1] + 1
            dele = previous[j] + 1
            sub = previous[j - 1] + (ca != cb)
            current.append(min(ins, dele, sub))
        previous = current
    return previous[-1]


def _matching_coverage(a: str, b: str) -> Tuple[int, int]:
    """Return total matching characters between a and b using SequenceMatcher blocks.
    Returns (match_len, a_covered_len). Since blocks reflect LCS-like matching, the
    sum of block sizes equals total matched characters. a_covered_len equals match_len.
    """
    sm = SequenceMatcher(None, a, b)
    blocks = sm.get_matching_blocks()
    match_len = sum(b.size for b in blocks)
    return match_len, match_len


# -----------------------------
# Core API
# -----------------------------


def load_srt(path: str) -> List[SRTSegment]:
    """Load an SRT file and return a list of SRTSegment with normalized text.

    Each segment contains:
    - index: sequence number
    - start, end, duration: seconds
    - text: original multi-line text
    - text_norm: normalized text for comparison
    """
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Normalize newlines and strip BOM if present
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = content.lstrip("\ufeff")

    # Split on blank lines between entries
    raw_blocks = re.split(r"\n\s*\n", content)
    segments: List[SRTSegment] = []

    for block in raw_blocks:
        if not block.strip():
            continue
        lines = block.strip().split("\n")
        # Expect at least 3 lines: index, timing, text
        if len(lines) < 2:
            continue

        # First line: index (if not, attempt to parse anyway)
        idx_line = lines[0].strip()
        try:
            index = int(idx_line)
            time_line_idx = 1
        except ValueError:
            # Some SRTs omit numeric index
            index = len(segments) + 1
            time_line_idx = 0

        time_line = lines[time_line_idx].strip()
        m = re.match(r"(\d\d:\d\d:\d\d[\.,]\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d[\.,]\d\d\d)", time_line)
        if not m:
            # Skip malformed blocks
            continue
        start = _parse_srt_timestamp(m.group(1))
        end = _parse_srt_timestamp(m.group(2))
        duration = max(0.0, end - start)

        text_lines = lines[time_line_idx + 1 :]
        text = "\n".join(text_lines).strip()
        text_norm = normalize_ja_text(text)

        segments.append(SRTSegment(index=index, start=start, end=end, duration=duration, text=text, text_norm=text_norm))

    # Ensure chronological order
    segments.sort(key=lambda s: (s.start, s.index))
    return segments


def load_script(path: str) -> str:
    """Load and clean the original script text (Japanese-aware normalization)."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    cleaned = normalize_ja_text(raw)
    return cleaned


def compare_content(srt_text: str, script_text: str) -> Dict[str, float]:
    """Compute similarity metrics between concatenated SRT text and script text.

    Returns dict with:
    - ratio: difflib SequenceMatcher ratio (0..1)
    - levenshtein: absolute Levenshtein distance
    - levenshtein_norm: normalized by max length (0..1; lower is better)
    - bigrams_jaccard: Jaccard similarity over character bigrams (0..1)
    - coverage_script: fraction of script chars covered by matches (0..1)
    - coverage_srt: fraction of srt chars covered by matches (0..1)
    - lcs_len: total matched characters (proxy for LCS length)
    - script_len, srt_len: lengths used
    """
    a = script_text or ""
    b = srt_text or ""
    sm = SequenceMatcher(None, a, b)
    ratio = sm.ratio()

    lev = _levenshtein(a, b)
    max_len = max(len(a), len(b), 1)
    lev_norm = lev / max_len

    a_bi = set(_char_ngrams(a, 2))
    b_bi = set(_char_ngrams(b, 2))
    inter = len(a_bi & b_bi)
    union = max(1, len(a_bi | b_bi))
    jacc = inter / union

    match_len, _ = _matching_coverage(a, b)
    coverage_script = match_len / max(1, len(a))
    coverage_srt = match_len / max(1, len(b))

    return {
        "ratio": ratio,
        "levenshtein": float(lev),
        "levenshtein_norm": lev_norm,
        "bigrams_jaccard": jacc,
        "coverage_script": coverage_script,
        "coverage_srt": coverage_srt,
        "lcs_len": float(match_len),
        "script_len": float(len(a)),
        "srt_len": float(len(b)),
    }


def _best_match_position(haystack: str, needle: str) -> Tuple[int, int, int, float]:
    """Return best matching position of 'needle' in 'haystack' via SequenceMatcher.
    Returns (start, end, match_len, match_ratio) where match_ratio is
    match_len / max(1, len(needle)).
    """
    if not needle:
        return (0, 0, 0, 0.0)
    sm = SequenceMatcher(None, haystack, needle)
    m = sm.find_longest_match(0, len(haystack), 0, len(needle))
    start, size = m.a, m.size
    return (start, start + size, size, size / max(1, len(needle)))


def analyze_segments(segments: List[SRTSegment], script_text: Optional[str] = None) -> Dict:
    """Analyze timing, segmentation, and content alignment per segment.

    Returns a dict with aggregate stats and per-segment diagnostics.
    """
    diagnostics = []
    total_chars = 0
    total_duration = 0.0

    overlaps = 0
    gaps = 0
    total_gap = 0.0
    max_gap = 0.0

    prev_end = None

    # For coverage mapping
    coverage_spans: List[Tuple[int, int]] = []

    for seg in segments:
        chars = len(seg.text_norm.replace(" ", ""))
        total_chars += chars
        total_duration += max(0.0, seg.duration)
        cps = chars / seg.duration if seg.duration > 0 else float("inf")

        # Boundary heuristics
        lines = seg.text.split("\n") if seg.text else [""]
        max_line_len = max((len(line) for line in lines), default=0)
        ends_with_punct = seg.text.strip().endswith(tuple(JA_END_PUNCT)) if seg.text.strip() else False
        starts_with_punct = seg.text.strip().startswith(tuple(JA_PAUSE_PUNCT + JA_END_PUNCT)) if seg.text.strip() else False

        timing_flags: List[str] = []
        if seg.duration < MIN_DURATION:
            timing_flags.append("too_short")
        if seg.duration > MAX_DURATION:
            timing_flags.append("too_long")
        if cps > WARN_CPS:
            timing_flags.append("high_cps")
        if max_line_len > MAX_CHARS_PER_LINE:
            timing_flags.append("line_overflow")
        if not ends_with_punct:
            timing_flags.append("no_end_punct")
        if starts_with_punct:
            timing_flags.append("starts_with_punct")

        match_info = None
        if script_text:
            s, e, size, ratio = _best_match_position(script_text, seg.text_norm)
            match_info = {
                "script_start": s,
                "script_end": e,
                "match_len": size,
                "match_ratio": ratio,
            }
            if size > 0:
                coverage_spans.append((s, e))

        diagnostics.append(
            {
                "index": seg.index,
                "start": seg.start,
                "end": seg.end,
                "duration": seg.duration,
                "text": seg.text,
                "text_norm": seg.text_norm,
                "chars": chars,
                "cps": cps,
                "max_line_len": max_line_len,
                "timing_flags": timing_flags,
                "boundary": {
                    "ends_with_punct": ends_with_punct,
                    "starts_with_punct": starts_with_punct,
                },
                "alignment": match_info,
            }
        )

        if prev_end is not None:
            if seg.start < prev_end:
                overlaps += 1
            else:
                gap = seg.start - prev_end
                if gap > 0:
                    gaps += 1
                    total_gap += gap
                    if gap > max_gap:
                        max_gap = gap
        prev_end = seg.end

    avg_cps = total_chars / total_duration if total_duration > 0 else 0.0
    avg_gap = total_gap / gaps if gaps > 0 else 0.0

    # Merge coverage spans and compute uncovered script regions
    missing_regions: List[Tuple[int, int]] = []
    if script_text and coverage_spans:
        coverage_spans.sort()
        merged: List[Tuple[int, int]] = []
        cs, ce = coverage_spans[0]
        for s, e in coverage_spans[1:]:
            if s <= ce:
                ce = max(ce, e)
            else:
                merged.append((cs, ce))
                cs, ce = s, e
        merged.append((cs, ce))

        # Invert to find gaps
        last = 0
        for s, e in merged:
            if s > last:
                missing_regions.append((last, s))
            last = e
        if last < len(script_text):
            missing_regions.append((last, len(script_text)))

        # Filter very small gaps
        missing_regions = [(s, e) for s, e in missing_regions if (e - s) >= 10]

    aggregate = {
        "segments": diagnostics,
        "stats": {
            "count": len(segments),
            "total_duration": total_duration,
            "total_chars": total_chars,
            "avg_cps": avg_cps,
            "overlaps": overlaps,
            "gaps": gaps,
            "avg_gap": avg_gap,
            "max_gap": max_gap,
        },
        "missing_regions": missing_regions,
    }

    return aggregate


def _recommendations(analysis: Dict, content_metrics: Dict, script_text: Optional[str]) -> List[str]:
    """Generate actionable recommendations based on analysis and metrics."""
    recs: List[str] = []

    # Global content similarity
    ratio = content_metrics.get("ratio", 0.0)
    cov = content_metrics.get("coverage_script", 0.0)
    if ratio < 0.8 or cov < 0.8:
        recs.append("台本と字幕の整合性が低めです。原文と照合して誤聴・誤字を修正してください。")

    # High CPS segments
    high_cps = [s for s in analysis["segments"] if s["cps"] > WARN_CPS]
    if high_cps:
        recs.append(
            f"読書速度が高すぎる字幕が{len(high_cps)}件あります（>{WARN_CPS:.0f} cps）。短縮・分割、または表示時間の延長を検討してください。"
        )

    # Too short/long durations
    too_short = [s for s in analysis["segments"] if "too_short" in s["timing_flags"]]
    too_long = [s for s in analysis["segments"] if "too_long" in s["timing_flags"]]
    if too_short:
        recs.append(f"表示時間が短すぎる字幕が{len(too_short)}件あります（<{MIN_DURATION:.1f}s）。結合や台詞の簡略化を検討。")
    if too_long:
        recs.append(f"表示時間が長すぎる字幕が{len(too_long)}件あります（>{MAX_DURATION:.1f}s）。自然な切れ目で分割してください。")

    # Line overflow
    overflow = [s for s in analysis["segments"] if "line_overflow" in s["timing_flags"]]
    if overflow:
        recs.append(
            f"1行の文字数超過（>{MAX_CHARS_PER_LINE}字）が{len(overflow)}件あります。改行や省略で調整してください。"
        )

    # Boundary punctuation
    bad_end = [s for s in analysis["segments"] if "no_end_punct" in s["timing_flags"]]
    if bad_end:
        recs.append("文末が句読点で終わらない字幕があります。文の切れ目で区切ると可読性が上がります。")

    # Overlaps/gaps
    if analysis["stats"]["overlaps"] > 0:
        recs.append("字幕同士の時間重なりがあります。タイムラインを調整してください。")
    if analysis["stats"]["gaps"] > 0 and analysis["stats"]["avg_gap"] > 0.5:
        recs.append("字幕間の空白が長い箇所があります。不要な間延びを抑えるとテンポが改善します。")

    # Missing script regions
    if script_text and analysis.get("missing_regions"):
        recs.append("台本の未カバー部分があります。重要な台詞が抜けていないか確認してください。")

    # General JP-specific tips
    recs.append(
        "日本語字幕は1–2行、1行13–15字程度、読書速度は4cps前後が目安です。読点（、）や句点（。）、助詞で自然に改行・分割してください。"
    )

    return recs


def generate_report(
    srt_path: Optional[str] = None,
    script_path: Optional[str] = None,
    *,
    segments: Optional[List[SRTSegment]] = None,
    script_text: Optional[str] = None,
) -> Dict:
    """Generate a comprehensive comparison report.

    You can pass file paths (srt_path, script_path) or preloaded data (segments, script_text).
    Returns a dict with keys: 'report' (human-readable), 'metrics', 'analysis'.
    """
    if segments is None:
        if not srt_path:
            raise ValueError("srt_path or segments must be provided")
        segments = load_srt(srt_path)
    if script_text is None:
        if not script_path:
            raise ValueError("script_path or script_text must be provided")
        script_text = load_script(script_path)

    # Concatenate SRT normalized text for global comparison
    srt_all_text = "".join(seg.text_norm + "。" for seg in segments)  # add separators to avoid run-on

    metrics = compare_content(srt_all_text, script_text)
    analysis = analyze_segments(segments, script_text)
    recs = _recommendations(analysis, metrics, script_text)

    # Identify low-alignment segments
    low_align = []
    for s in analysis["segments"]:
        align = s.get("alignment") or {}
        if align.get("match_ratio", 1.0) < 0.6:
            low_align.append(s)

    # Prepare top missing regions with context
    missing_snippets: List[str] = []
    for s, e in analysis.get("missing_regions", [])[:5]:
        left = max(0, s - 10)
        right = min(len(script_text), e + 10)
        snippet = script_text[left:right]
        missing_snippets.append(snippet)

    # Compose human-readable report (concise but detailed)
    lines: List[str] = []
    lines.append("=== 字幕 vs 台本 比較レポート ===")
    lines.append("")
    lines.append("[全体メトリクス]")
    lines.append(f"- 類似度(ratio): {metrics['ratio']:.3f}")
    lines.append(f"- レーベンシュタイン距離: {int(metrics['levenshtein'])} (正規化 {metrics['levenshtein_norm']:.3f})")
    lines.append(f"- 2-gramジャッカード: {metrics['bigrams_jaccard']:.3f}")
    lines.append(f"- 台本カバレッジ: {metrics['coverage_script']:.3f}  / 字幕側: {metrics['coverage_srt']:.3f}")
    lines.append("")
    lines.append("[タイミング・セグメント品質]")
    lines.append(
        f"- セグメント数: {analysis['stats']['count']} / 総時間: {analysis['stats']['total_duration']:.1f}s / 平均CPS: {analysis['stats']['avg_cps']:.2f}"
    )
    lines.append(
        f"- 重なり: {analysis['stats']['overlaps']} / 空白数: {analysis['stats']['gaps']} (平均 {analysis['stats']['avg_gap']:.2f}s, 最大 {analysis['stats']['max_gap']:.2f}s)"
    )

    # Summaries of issues
    def _count(flag: str) -> int:
        return sum(1 for s in analysis["segments"] if flag in s["timing_flags"])

    lines.append(
        f"- 高CPS(>{WARN_CPS:.0f}): {_count('high_cps')} / 短すぎ: {_count('too_short')} / 長すぎ: {_count('too_long')} / 行超過: {_count('line_overflow')}"
    )
    lines.append(f"- 文末句読点なし: {_count('no_end_punct')}")

    if low_align:
        lines.append("")
        lines.append("[低アラインメントの字幕例 (上位5件)]")
        for s in low_align[:5]:
            mr = s["alignment"]["match_ratio"] if s.get("alignment") else 0.0
            lines.append(
                f"  #{s['index']} {s['start']:.2f}-{s['end']:.2f}s | match {mr:.2f} | '{s['text'].replace('\n', ' / ')}'"
            )

    if missing_snippets:
        lines.append("")
        lines.append("[未カバー台本の抜粋]")
        for i, sn in enumerate(missing_snippets, 1):
            lines.append(f"  ({i}) …{sn}…")

    if recs:
        lines.append("")
        lines.append("[改善提案]")
        for r in recs:
            lines.append(f"- {r}")

    report_text = "\n".join(lines)

    return {"report": report_text, "metrics": metrics, "analysis": analysis}


__all__ = [
    "SRTSegment",
    "load_srt",
    "load_script",
    "compare_content",
    "analyze_segments",
    "generate_report",
]

