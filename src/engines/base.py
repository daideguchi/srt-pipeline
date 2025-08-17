from __future__ import annotations

import abc
from typing import List

from src.types import Transcript


class BaseEngine(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def is_available(self) -> bool:
        ...

    @abc.abstractmethod
    def transcribe(self, audio_path: str, language: str = "ja") -> Transcript:
        ...

