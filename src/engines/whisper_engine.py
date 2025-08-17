from __future__ import annotations

from typing import List

from src.engines.base import BaseEngine
from src.types import Transcript, Segment, Word


class WhisperEngine(BaseEngine):
    name = "whisper/stable-ts"

    def __init__(self, model_size: str = "medium"):
        self._model_size = model_size
        self._impl = None
        self._impl_type = None  # "stable-ts" | "stable-whisper" | "whisper"

    def is_available(self) -> bool:
        # Prefer stable-ts/stable-whisper (both import as stable_whisper), then openai-whisper
        try:
            import stable_whisper  # noqa: F401
            self._impl_type = "stable-whisper"
            return True
        except Exception:
            pass
        try:
            import whisper  # noqa: F401
            self._impl_type = "whisper"
            return True
        except Exception:
            return False

    def _load_model(self):
        if self._impl is not None:
            return
        if self._impl_type in ("stable-whisper", "stable-ts"):
            import stable_whisper
            self._impl = stable_whisper.load_model(self._model_size)
        elif self._impl_type == "whisper":
            import whisper
            self._impl = whisper.load_model(self._model_size)
        else:
            raise RuntimeError("No whisper implementation available")

    def transcribe(self, audio_path: str, language: str = "ja") -> Transcript:
        self._load_model()
        segs: List[Segment] = []

        if self._impl_type in ("stable-whisper", "stable-ts"):
            result = self._impl.transcribe(
                audio_path,
                language=language,
                vad=True,
                word_timestamps=True,
            )

            # stable-ts/stable-whisper may return an object with .segments or a dict
            if hasattr(result, "segments"):
                raw_segments = getattr(result, "segments") or []
                for s in raw_segments:
                    # s can be an object with attributes
                    s_start = float(getattr(s, "start", 0.0) or 0.0)
                    s_end = float(getattr(s, "end", 0.0) or 0.0)
                    s_text = getattr(s, "text", "") or ""
                    raw_words = getattr(s, "words", []) or []
                    words: List[Word] = []
                    for w in raw_words:
                        words.append(
                            Word(
                                text=getattr(w, "word", "") or getattr(w, "text", ""),
                                start=float(getattr(w, "start", s_start) or s_start),
                                end=float(getattr(w, "end", s_end) or s_end),
                                confidence=float(getattr(w, "probability", 0.0) or getattr(w, "confidence", 0.0) or 0.0),
                                source=self.name,
                            )
                        )
                    if not s_text and words:
                        s_text = "".join(w.text for w in words)
                    segs.append(Segment(start=s_start, end=s_end, text=s_text, words=words))
            else:
                # assume dict-like structure
                seg_list = (result or {}).get("segments", [])
                for s in seg_list:
                    s_start = float(s.get("start", 0.0))
                    s_end = float(s.get("end", 0.0))
                    s_text = s.get("text", "") or ""
                    words: List[Word] = []
                    for w in (s.get("words", []) or []):
                        words.append(
                            Word(
                                text=w.get("word") or w.get("text", ""),
                                start=float(w.get("start", s_start)),
                                end=float(w.get("end", s_end)),
                                confidence=float(w.get("probability", 0.0) or w.get("confidence", 0.0) or 0.0),
                                source=self.name,
                            )
                        )
                    if not s_text and words:
                        s_text = "".join(w.text for w in words)
                    segs.append(Segment(start=s_start, end=s_end, text=s_text, words=words))
        else:
            # openai-whisper does not provide word timestamps natively; approximate by distributing segment time
            result = self._impl.transcribe(audio_path, language=language)
            seg_list = (result or {}).get("segments", [])
            for s in seg_list:
                start = float(s.get("start", 0.0))
                end = float(s.get("end", start))
                text = s.get("text", "") or ""
                words: List[Word] = []
                if end > start and text:
                    # Split by characters to preserve JP; timing evenly spread
                    n = max(len(text), 1)
                    dur = (end - start) / n
                    t = start
                    for ch in text:
                        words.append(Word(text=ch, start=t, end=t + dur, confidence=0.0, source=self.name))
                        t += dur
                segs.append(Segment(start=start, end=end, text=text, words=words))

        return Transcript(segments=segs, source=self.name)
