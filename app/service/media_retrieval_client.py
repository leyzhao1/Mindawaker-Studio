from __future__ import annotations

from typing import Any, Dict

import httpx


class MediaRetrievalClient:
    def __init__(self, base_url: str, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> Dict[str, Any]:
        return self._get("/health")

    def index_stats(self, annotation_root: str) -> Dict[str, Any]:
        return self._get("/index/stats", params={"annotation_root": annotation_root})

    def build_index(self, annotation_root: str) -> Dict[str, Any]:
        return self._post("/index/build", json={"annotation_root": annotation_root})

    def batch_search(
        self,
        texts: str | list[str],
        annotation_root: str,
        top_k_per_line: int = 3,
        prefer_media_type: str = "video",
        strategy: str = "sequential_coherence",
        search_mode: str = "window_level",
        ranking_strategy: str = "cascade_sequence_v1",
        window_annotation_root: str | None = None,
        window_level_preferred: bool = True,
        coarse_top_n: int = 50,
        fine_top_k: int = 10,
        durations: list[float] | None = None,
    ) -> Dict[str, Any]:
        return self._post(
            "/retrieve/batch",
            json={
                "texts": texts,
                "durations": durations,
                "annotation_root": annotation_root,
                "top_k_per_line": top_k_per_line,
                "prefer_media_type": prefer_media_type,
                "strategy": strategy,
                "search_mode": search_mode,
                "ranking_strategy": ranking_strategy,
                "window_annotation_root": window_annotation_root or annotation_root,
                "window_level_preferred": window_level_preferred,
                "coarse_top_n": coarse_top_n,
                "fine_top_k": fine_top_k,
            },
        )

    def _get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get(path, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"media_service GET {path} timed out after {self.timeout}s") from exc

    def _post(self, path: str, json: Dict[str, Any]) -> Dict[str, Any]:
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.post(path, json=json)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"media_service POST {path} timed out after {self.timeout}s") from exc
