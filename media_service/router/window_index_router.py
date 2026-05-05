from __future__ import annotations

from fastapi import APIRouter

from media_service.config.settings import resolve_media_library_root, resolve_output_dir
from media_service.model.schemas import WindowBuildRequest, WindowBuildFileRequest
from media_service.service.window_index_service import WindowIndexService
from media_service.windowing.schema import WindowBuildConfig

router = APIRouter()
service = WindowIndexService()


@router.post("/scan")
def build_window_index(request: WindowBuildRequest) -> dict:
    input_dir = resolve_media_library_root(request.input_dir)
    output_dir = resolve_output_dir(request.output_dir)
    config = WindowBuildConfig(
        window_sizes_sec=request.window_sizes_sec,
        stride_ratio=request.stride_ratio,
        sample_fps=request.sample_fps,
        max_frames_per_window=request.max_frames_per_window,
        min_window_coverage_ratio=request.min_window_coverage_ratio,
    )
    return service.build_window_index(
        input_dir=input_dir,
        output_dir=output_dir,
        overwrite=request.overwrite,
        recursive=request.recursive,
        config=config,
        enable_semantic_caption=request.enable_semantic_caption,
    )


@router.post("/file")
def build_window_index_for_file(request: WindowBuildFileRequest) -> dict:
    input_root = resolve_media_library_root(request.input_root)
    output_dir = resolve_output_dir(request.output_dir)
    config = WindowBuildConfig(
        window_sizes_sec=request.window_sizes_sec,
        stride_ratio=request.stride_ratio,
        sample_fps=request.sample_fps,
        max_frames_per_window=request.max_frames_per_window,
        min_window_coverage_ratio=request.min_window_coverage_ratio,
    )
    return service.build_window_index_for_file(
        file_path=request.file_path,
        input_root=input_root,
        output_dir=output_dir,
        config=config,
        enable_semantic_caption=request.enable_semantic_caption,
    )
