from __future__ import annotations

import os
import contextlib
import wave
from typing import List, Optional, Tuple

from src.engines.base import BaseEngine
from src.types import Transcript, Segment, Word


class GoogleSpeechEngine(BaseEngine):
    name = "google-stt"

    def __init__(self, sample_rate_hz: int | None = None):
        self._sample_rate = sample_rate_hz

    def is_available(self) -> bool:
        try:
            import google.cloud.speech  # noqa: F401
            return True
        except Exception:
            return False

    # --- helpers ---
    def _map_language(self, language: str | None) -> str:
        if not language:
            return "ja-JP"
        lang = language.strip()
        if lang.lower() in {"ja", "jp", "japanese"}:
            return "ja-JP"
        # Pass through other codes (e.g., en-US)
        return lang

    def _infer_encoding_and_rate(self, path: str) -> Tuple[Optional[str], Optional[int]]:
        # Best effort: use file extension, and peek into WAV headers if possible
        _, ext = os.path.splitext(path.lower())
        ext = ext.lstrip('.')
        encoding = None
        rate = None

        if ext == 'wav':
            try:
                with contextlib.closing(wave.open(path, 'rb')) as wf:
                    sampwidth = wf.getsampwidth()
                    rate = wf.getframerate()
                    comptype = wf.getcomptype()
                    if comptype == 'NONE' and sampwidth in (2, 1):
                        # Treat PCM 16-bit or 8-bit as LINEAR16
                        encoding = 'LINEAR16'
            except Exception:
                pass
        elif ext == 'flac':
            encoding = 'FLAC'
        elif ext == 'mp3':
            encoding = 'MP3'
        elif ext in ('ogg', 'opus'):
            encoding = 'OGG_OPUS'
        elif ext in ('webm',):
            encoding = 'WEBM_OPUS'

        return encoding, rate

    def _estimate_duration_sec(self, path: str) -> Optional[float]:
        # Try WAV first
        try:
            _, ext = os.path.splitext(path.lower())
            if ext == '.wav':
                with contextlib.closing(wave.open(path, 'rb')) as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    if rate:
                        return frames / float(rate)
        except Exception:
            pass

        # Try mutagen if available (covers mp3, flac, etc.)
        try:
            from mutagen import File as MutagenFile  # type: ignore
            mf = MutagenFile(path)
            if mf is not None and getattr(mf, 'info', None) is not None:
                length = getattr(mf.info, 'length', None)
                if isinstance(length, (int, float)):
                    return float(length)
        except Exception:
            pass

        # Fallback heuristic by file size (rough estimate): assume 128kbps
        try:
            size = os.path.getsize(path)
            # duration seconds = bits / 128kbps
            return (size * 8) / 128_000.0
        except Exception:
            return None

    def _build_config(self, language_code: str, speech_mod) -> object:
        # Build RecognitionConfig with our best-guess encoding and sample rate
        # We'll set encoding and sample rate in transcribe() after we know the file
        return speech_mod.RecognitionConfig(
            language_code=language_code,
            enable_word_time_offsets=True,
            model="default",
        )

    def _make_client(self):
        try:
            from google.cloud import speech
            from google.auth.exceptions import DefaultCredentialsError
        except Exception as ex:
            raise RuntimeError(f"google-cloud-speech not available: {ex}")

        # Try instantiate client to surface credential issues early
        try:
            client = speech.SpeechClient()
        except Exception as ex:  # DefaultCredentialsError or transport errors
            # Helpful guidance
            cred_hint = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if not cred_hint:
                raise RuntimeError(
                    "Google credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS to your service account JSON file."
                ) from ex
            if cred_hint and not os.path.isfile(cred_hint):
                raise RuntimeError(
                    f"Google credentials file not found: {cred_hint}"
                ) from ex
            raise RuntimeError(f"Failed to initialize Google Speech client: {ex}") from ex

        return client, speech

    def transcribe(self, audio_path: str, language: str = "ja") -> Transcript:
        # Validate path or URI
        is_gcs_uri = isinstance(audio_path, str) and audio_path.startswith("gs://")
        if not is_gcs_uri:
            if not os.path.isfile(audio_path):
                raise FileNotFoundError(f"audio not found: {audio_path}")

        client, speech = self._make_client()

        # Language mapping (ensure ja -> ja-JP)
        language_code = self._map_language(language)

        # Build base config
        config = self._build_config(language_code, speech)

        # Attempt to refine encoding/sample rate for local files
        if not is_gcs_uri:
            enc_name, rate = self._infer_encoding_and_rate(audio_path)
            if enc_name:
                try:
                    config.encoding = getattr(speech.RecognitionConfig.AudioEncoding, enc_name)
                except Exception:
                    # Fallback: leave unspecified
                    pass
            if self._sample_rate or rate:
                config.sample_rate_hertz = int(self._sample_rate or rate)

        # Prepare audio reference
        if is_gcs_uri:
            audio = speech.RecognitionAudio(uri=audio_path)
        else:
            with open(audio_path, 'rb') as f:
                content = f.read()
            audio = speech.RecognitionAudio(content=content)

        # Choose sync vs long-running based on estimated duration
        dur = None if is_gcs_uri else self._estimate_duration_sec(audio_path)
        # Use synchronous for short clips (<= 55s), otherwise long-running
        use_long_running = (dur is None) or (dur > 55.0)

        try:
            if use_long_running:
                operation = client.long_running_recognize(config=config, audio=audio)
                response = operation.result(timeout=3600)
            else:
                response = client.recognize(config=config, audio=audio)
        except Exception as ex:
            raise RuntimeError(f"Google STT request failed: {ex}")

        # Convert response to our Transcript types, segment per result
        segments: List[Segment] = []
        try:
            for result in getattr(response, 'results', []) or []:
                if not getattr(result, 'alternatives', None):
                    continue
                alt = result.alternatives[0]
                s_words: List[Word] = []
                for w in getattr(alt, 'words', []) or []:
                    w_text = getattr(w, 'word', '') or ''
                    w_start = float(getattr(w, 'start_time', 0.0).total_seconds() if getattr(w, 'start_time', None) else 0.0)
                    w_end = float(getattr(w, 'end_time', 0.0).total_seconds() if getattr(w, 'end_time', None) else w_start)
                    # Word-level confidence may not be populated; fall back to alternative confidence
                    w_conf = 0.0
                    try:
                        w_conf = float(getattr(w, 'confidence', 0.0) or 0.0)
                    except Exception:
                        w_conf = 0.0
                    if not w_conf:
                        try:
                            w_conf = float(getattr(alt, 'confidence', 0.0) or 0.0)
                        except Exception:
                            w_conf = 0.0
                    s_words.append(Word(text=w_text, start=w_start, end=w_end, confidence=w_conf, source=self.name))

                seg_text = getattr(alt, 'transcript', '') or ''
                if not seg_text and s_words:
                    seg_text = "".join(w.text for w in s_words)
                s_start = s_words[0].start if s_words else 0.0
                s_end = s_words[-1].end if s_words else 0.0
                segments.append(Segment(start=s_start, end=s_end, text=seg_text, words=s_words))
        except Exception as ex:
            raise RuntimeError(f"Failed to parse Google STT response: {ex}")

        # Fallback: if API returned no word details, synthesize per-character timing within each result if possible
        if segments and not any(seg.words for seg in segments):
            # Without timestamps, we cannot time words accurately; keep as-is
            pass

        return Transcript(segments=segments, source=self.name)
