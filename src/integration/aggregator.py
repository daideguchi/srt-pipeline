from __future__ import annotations

from collections import defaultdict, Counter
from typing import Dict, Iterable, List, Tuple

import unicodedata

from src.types import Transcript, Segment, Word


def _norm(s: str) -> str:
    # Normalize for Japanese: NFKC, strip spaces
    s = unicodedata.normalize("NFKC", s)
    return s.replace(" ", "").replace("\u3000", "").strip()


def _iter_all_words(transcripts: List[Transcript]) -> Iterable[Word]:
    for t in transcripts:
        for seg in t.segments:
            for w in seg.words:
                if w.text:
                    yield w


def integrate_transcripts(transcripts: List[Transcript], bucket_ms: int = 200) -> Transcript:
    """Integrate multiple word-level transcripts via time-bucketing and voting.

    - Build buckets by time window; for each bucket, pick the best word candidate.
    - Confidence-weighted majority voting across engines.
    """
    if not transcripts:
        return Transcript(segments=[], source="integrated")

    # Collect all words and time range
    words = [w for w in _iter_all_words(transcripts)]
    if not words:
        # Fall back to concatenating segments text if no word timestamps
        text = "".join([seg.text for t in transcripts for seg in t.segments])
        return Transcript(segments=[Segment(0.0, 0.0, text=text, words=[])], source="integrated")

    start = min(w.start for w in words)
    end = max(w.end for w in words)
    bucket = bucket_ms / 1000.0

    # Build buckets: index -> list of word candidates
    buckets: Dict[int, List[Word]] = defaultdict(list)
    for w in words:
        i = int((w.start - start) // bucket)
        buckets[i].append(w)

    # Resolve buckets to a single word choice
    resolved: List[Word] = []
    for i in sorted(buckets.keys()):
        cands = buckets[i]
        # group by normalized text
        groups: Dict[str, List[Word]] = defaultdict(list)
        for w in cands:
            groups[_norm(w.text)].append(w)
        # pick by count, then average confidence
        best_key = None
        best_score = (-1.0, -1.0)
        for k, arr in groups.items():
            count = len(arr)
            avg_conf = sum(w.confidence for w in arr) / max(len(arr), 1)
            score = (count, avg_conf)
            if score > best_score:
                best_key = k
                best_score = score
        chosen_group = groups[best_key] if best_key is not None else cands
        # determine time span by min start / max end of chosen group
        w_start = min(w.start for w in chosen_group)
        w_end = max(w.end for w in chosen_group)
        # prefer the instance with max confidence for metadata
        best_inst = max(chosen_group, key=lambda w: w.confidence)
        resolved.append(Word(text=best_inst.text, start=w_start, end=w_end, confidence=best_inst.confidence, source="integrated"))

    # Merge adjacent identical tokens
    merged: List[Word] = []
    for w in resolved:
        if merged and _norm(merged[-1].text) == _norm(w.text) and (w.start - merged[-1].end) <= bucket / 2:
            merged[-1].end = max(merged[-1].end, w.end)
            merged[-1].confidence = max(merged[-1].confidence, w.confidence)
        else:
            merged.append(w)

    # Create single segment from merged words
    if merged:
        text = "".join([w.text for w in merged])
        seg = Segment(start=merged[0].start, end=merged[-1].end, text=text, words=merged)
        return Transcript(segments=[seg], source="integrated")
    else:
        return Transcript(segments=[], source="integrated")

