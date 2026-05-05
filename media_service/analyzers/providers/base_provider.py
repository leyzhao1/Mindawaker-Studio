from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from media_service.model.schemas import ContentTag


class BaseContentProvider(ABC):
    @abstractmethod
    def analyze_image(self, path: Path) -> ContentTag:
        raise NotImplementedError

    @abstractmethod
    def analyze_video(self, path: Path, frame_count: int = 6) -> ContentTag:
        raise NotImplementedError

    @abstractmethod
    def summarize_frames(self, frame_results: Iterable[ContentTag]) -> ContentTag:
        raise NotImplementedError
