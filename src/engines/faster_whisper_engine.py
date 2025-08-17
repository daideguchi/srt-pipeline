from __future__ import annotations

from typing import List

from src.engines.base import BaseEngine
from src.types import Transcript, Segment, Word


class FasterWhisperEngine(BaseEngine):
    name = "faster-whisper"

    def __init__(self, model_size: str = "medium", device: str | None = None, compute_type: str | None = None):
        self._model_size = model_size
        self._device = device or "auto"
        self._compute_type = compute_type or "default"
        self._model = None

    def is_available(self) -> bool:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            return True
        except Exception:
            return False

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except Exception as ex:
            raise RuntimeError(f"faster-whisper not available: {ex}")
        try:
            self._model = WhisperModel(self._model_size, device=self._device, compute_type=self._compute_type)
        except Exception as ex:
            raise RuntimeError(f"failed to load faster-whisper model '{self._model_size}': {ex}")

    def transcribe(self, audio_path: str, language: str = "ja") -> Transcript:
        # Basic validation
        try:
            import os
            if not os.path.isfile(audio_path):
                raise FileNotFoundError(f"audio not found: {audio_path}")
        except Exception:
            # If os import fails for some reason, proceed and let downstream raise
            pass

        self._ensure_model()
        try:
            segments, _info = self._model.transcribe(
                audio_path,
                language=language,
                vad_filter=True,
                word_timestamps=True,
            )
        except Exception as ex:
            raise RuntimeError(f"faster-whisper transcription failed: {ex}")

        segs: List[Segment] = []
        for seg in segments:
            s_start = float(getattr(seg, "start", 0.0) or 0.0)
            s_end = float(getattr(seg, "end", 0.0) or 0.0)
            s_text = getattr(seg, "text", "") or ""
            words: List[Word] = []
            raw_words = getattr(seg, "words", []) or []
            for w in raw_words:
                w_start = float(getattr(w, "start", s_start) or s_start)
                w_end = float(getattr(w, "end", s_end) or s_end)
                w_text = getattr(w, "word", "") or getattr(w, "text", "") or ""
                w_conf = float(getattr(w, "probability", 0.0) or getattr(w, "confidence", 0.0) or 0.0)
                words.append(Word(text=w_text, start=w_start, end=w_end, confidence=w_conf, source=self.name))

            # Fallback: synthesize per-character words if none provided
            if not words and s_text:
                dur = max(s_end - s_start, 0.0)
                n = max(len(s_text), 1)
                step = (dur / n) if n > 0 else 0.0
                t = s_start
                for ch in s_text:
                    words.append(Word(text=ch, start=t, end=min(t + step, s_end) if step else s_end, confidence=0.0, source=self.name))
                    t += step

            if not s_text and words:
                s_text = "".join(w.text for w in words)

            segs.append(Segment(start=s_start, end=s_end, text=s_text, words=words))

        return Transcript(segments=segs, source=self.name)
