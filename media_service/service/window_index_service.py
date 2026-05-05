from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from media_service.utils.io import is_video_file, scan_media_files
from media_service.windowing.extractor import WindowExtractor
from media_service.windowing.schema import WindowBuildConfig
from media_service.windowing.storage import WindowIndexStorage

logger = logging.getLogger(__name__)


class WindowIndexService:
    def __init__(self) -> None:
        self.extractor = WindowExtractor()
        self.storage = WindowIndexStorage()

    def build_window_index(
        self,
        input_dir: str | Path,
        output_dir: str | Path,
        overwrite: bool = True,
        recursive: bool = True,
        config: WindowBuildConfig | None = None,
        enable_semantic_caption: bool = False,
    ) -> Dict[str, Any]:
        input_root = Path(input_dir).resolve()
        output_root = Path(output_dir).resolve()
        effective_config = config or WindowBuildConfig(
            window_sizes_sec=[2.0, 5.0, 10.0],
            stride_ratio=0.5,
            sample_fps=1.0,
            max_frames_per_window=8,
        )

        media_files = scan_media_files(input_root, recursive=recursive)
        video_files = [path for path in media_files if is_video_file(path)]
        outputs: List[str] = []
        errors: List[Dict[str, str]] = []
        processed = 0
        skipped = 0
        total_windows = 0

        manifest = self.storage.read_manifest(output_root)

        for video_path in video_files:
            source_key = str(video_path.resolve())
            if not overwrite and source_key in manifest:
                existing_path = Path(manifest[source_key])
                if existing_path.exists():
                    skipped += 1
                    outputs.append(str(existing_path))
                    continue
            try:
                index = self.extractor.extract_video_windows(
                    video_path=video_path,
                    input_root=input_root,
                    config=effective_config,
                    enable_semantic_caption=enable_semantic_caption,
                )
                out_path = self.storage.save_index(output_root, index)
                outputs.append(str(out_path))
                processed += 1
                total_windows += len(index.windows)
            except Exception as exc:
                logger.exception("build window index failed for %s", video_path)
                errors.append({"source_path": str(video_path), "error": str(exc)})

        return {
            "success": True,
            "input_dir": str(input_root),
            "output_dir": str(output_root),
            "scanned": len(video_files),
            "processed": processed,
            "skipped": skipped,
            "failed": len(errors),
            "total_windows": total_windows,
            "errors": errors,
            "outputs": outputs,
            "manifest": str(self.storage.resolve_manifest_path(output_root)),
        }

    def build_window_index_for_file(
        self,
        file_path: str | Path,
        input_root: str | Path,
        output_dir: str | Path,
        config: WindowBuildConfig | None = None,
        enable_semantic_caption: bool = False,
    ) -> Dict[str, Any]:
        source_path = Path(file_path).resolve()
        resolved_input_root = Path(input_root).resolve()
        output_root = Path(output_dir).resolve()
        if not source_path.exists():
            return {"success": False, "error": f"file not found: {source_path}"}
        if not is_video_file(source_path):
            return {"success": False, "error": f"unsupported media type: {source_path}"}
        effective_config = config or WindowBuildConfig(
            window_sizes_sec=[2.0, 5.0, 10.0],
            stride_ratio=0.5,
            sample_fps=1.0,
            max_frames_per_window=8,
        )
        index = self.extractor.extract_video_windows(
            video_path=source_path,
            input_root=resolved_input_root,
            config=effective_config,
            enable_semantic_caption=enable_semantic_caption,
        )
        out_path = self.storage.save_index(output_root, index)
        return {
            "success": True,
            "source_path": str(source_path),
            "output": str(out_path),
            "window_count": len(index.windows),
            "manifest": str(self.storage.resolve_manifest_path(output_root)),
        }
