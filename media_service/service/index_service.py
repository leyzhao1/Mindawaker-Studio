from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from media_service.model.schemas import MediaAnnotation
from media_service.utils.io import read_annotation, scan_annotation_files


class IndexService:
    def __init__(self) -> None:
        self._cache: dict[str, list[MediaAnnotation]] = {}

    def build_index(self, annotation_root: Path) -> Dict[str, Any]:
        annotation_files = scan_annotation_files(annotation_root)
        documents: List[MediaAnnotation] = []
        invalid_files: List[Dict[str, str]] = []
        for path in annotation_files:
            try:
                annotation = read_annotation(path)
                documents.append(annotation)
            except Exception as exc:
                invalid_files.append({"path": str(path), "error": str(exc)})
        self._cache[str(annotation_root.resolve())] = documents
        return {
            "success": True,
            "annotation_root": str(annotation_root.resolve()),
            "count": len(documents),
            "image_count": sum(1 for item in documents if item.media_type == "image"),
            "video_count": sum(1 for item in documents if item.media_type == "video"),
            "invalid_files": invalid_files,
        }

    def get_index(self, annotation_root: Path) -> List[MediaAnnotation]:
        key = str(annotation_root.resolve())
        if key not in self._cache:
            self.build_index(annotation_root)
        return self._cache.get(key, [])

    def stats(self, annotation_root: Path) -> Dict[str, Any]:
        docs = self.get_index(annotation_root)
        return {
            "success": True,
            "annotation_root": str(annotation_root.resolve()),
            "count": len(docs),
            "image_count": sum(1 for item in docs if item.media_type == "image"),
            "video_count": sum(1 for item in docs if item.media_type == "video"),
        }
