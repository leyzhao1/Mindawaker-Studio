from __future__ import annotations

from pathlib import Path

from media_service.windowing.schema import VideoWindowAnnotation, VideoWindowIndex, WindowBuildConfig, WindowFeatures
from media_service.windowing.storage import WindowIndexStorage


def _build_index(source_path: Path) -> VideoWindowIndex:
    return VideoWindowIndex(
        source_path=str(source_path),
        relative_path="videos/sample.mp4",
        file_name="sample.mp4",
        duration_sec=12.0,
        fps=25.0,
        width=1280,
        height=720,
        build_config=WindowBuildConfig(window_sizes_sec=[2.0, 5.0]),
        windows=[
            VideoWindowAnnotation(
                window_id="w1",
                source_path=str(source_path),
                relative_path="videos/sample.mp4",
                level=2.0,
                window_size_sec=2.0,
                stride_sec=1.0,
                start_sec=0.0,
                end_sec=2.0,
                duration_sec=2.0,
                sample_count=2,
                sample_fps=1.0,
                features=WindowFeatures(readability_score=80.0),
            )
        ],
    )


def test_save_load_and_manifest(tmp_path):
    storage = WindowIndexStorage()
    output_root = tmp_path / "scan_out"
    source_path = tmp_path / "videos" / "sample.mp4"

    index = _build_index(source_path)
    saved_path = storage.save_index(output_root, index)

    assert saved_path.exists()
    manifest = storage.read_manifest(output_root)
    assert str(source_path) in manifest
    assert manifest[str(source_path)] == str(saved_path)

    listed = storage.list_indices(output_root)
    assert saved_path in listed

    loaded = storage.load_index(saved_path)
    assert loaded.source_path == str(source_path)
    assert loaded.windows[0].window_id == "w1"
