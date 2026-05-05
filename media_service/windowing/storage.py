from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from media_service.windowing.schema import VideoWindowIndex


WINDOW_INDEX_DIR_NAME = "window_indices"
WINDOW_MANIFEST_NAME = "manifest.json"


class WindowIndexStorage:
    def resolve_index_dir(self, output_root: Path) -> Path:
        return (output_root / WINDOW_INDEX_DIR_NAME).resolve()

    def resolve_manifest_path(self, output_root: Path) -> Path:
        return self.resolve_index_dir(output_root) / WINDOW_MANIFEST_NAME

    def build_index_file_name(self, source_path: str) -> str:
        digest = hashlib.sha1(source_path.encode("utf-8")).hexdigest()
        return f"{digest}.json"

    def save_index(self, output_root: Path, index: VideoWindowIndex) -> Path:
        index_dir = self.resolve_index_dir(output_root)
        index_dir.mkdir(parents=True, exist_ok=True)
        file_name = self.build_index_file_name(index.source_path)
        index_path = index_dir / file_name
        with index_path.open("w", encoding="utf-8") as f:
            json.dump(index.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
        self.update_manifest(output_root, index.source_path, str(index_path.resolve()))
        return index_path.resolve()

    def load_index(self, path: Path) -> VideoWindowIndex:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return VideoWindowIndex(**data)

    def list_indices(self, output_root: Path) -> List[Path]:
        index_dir = self.resolve_index_dir(output_root)
        if index_dir.exists():
            files = [path for path in index_dir.glob("*.json") if path.name != WINDOW_MANIFEST_NAME and path.is_file()]
            files.sort()
            return files
        files = [path for path in output_root.rglob("*.json") if path.is_file() and path.name != WINDOW_MANIFEST_NAME]
        files.sort()
        return files

    def read_manifest(self, output_root: Path) -> Dict[str, str]:
        manifest_path = self.resolve_manifest_path(output_root)
        if not manifest_path.exists():
            return {}
        with manifest_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return {}
        return {str(k): str(v) for k, v in payload.items()}

    def update_manifest(self, output_root: Path, source_path: str, index_path: str) -> None:
        manifest_path = self.resolve_manifest_path(output_root)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = self.read_manifest(output_root)
        manifest[str(source_path)] = str(index_path)
        with manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
