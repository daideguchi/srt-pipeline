from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Word:
    text: str
    start: float  # seconds
    end: float    # seconds
    confidence: float = 0.0
    source: str = ""


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)


@dataclass
class Transcript:
    segments: List[Segment]
    source: str

