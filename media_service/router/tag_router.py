from __future__ import annotations

import logging
import mimetypes
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from media_service.config.settings import resolve_media_library_root, resolve_output_dir
from media_service.model.schemas import DirectoryListRequest, FileUploadRequest, TagFileRequest, TagScanRequest
from media_service.service.tagging_service import TaggingService
from media_service.utils.io import build_output_json_path, is_supported_file, scan_media_files, write_json

router = APIRouter()
service = TaggingService()
logger = logging.getLogger(__name__)


@router.post("/scan")
def scan_and_tag(request: TagScanRequest) -> dict:
    input_dir = resolve_media_library_root(request.input_dir)
    output_dir = resolve_output_dir(request.output_dir)
    logger.info("HTTP /tag/scan input=%s output=%s overwrite=%s recursive=%s", input_dir, output_dir, request.overwrite, request.recursive)
    return service.process_directory(
        input_dir=input_dir,
        output_dir=output_dir,
        overwrite=request.overwrite,
        recursive=request.recursive,
    )


@router.post("/file")
def tag_file(request: TagFileRequest) -> dict:
    media_path = Path(request.file_path).resolve()
    input_root = resolve_media_library_root(request.input_root)
    output_dir = resolve_output_dir(request.output_dir)
    output_path = build_output_json_path(media_path, input_root, output_dir)
    logger.info("HTTP /tag/file file=%s input_root=%s output=%s overwrite=%s", media_path, input_root, output_path, request.overwrite)

    if output_path.exists() and not request.overwrite:
        return {
            "success": True,
            "skipped": True,
            "output": str(output_path),
        }

    annotation = service.process_file(
        media_path=media_path,
        input_root=input_root,
    )
    write_json(output_path, annotation.model_dump(mode="json"))
    return {
        "success": True,
        "output": str(output_path),
        "annotation": annotation.model_dump(mode="json"),
    }


@router.post("/list")
def list_directory(request: DirectoryListRequest) -> dict:
    """列出目录中的媒体文件"""
    directory = Path(request.directory).resolve()
    if not directory.exists():
        return {
            "success": False,
            "error": f"目录不存在: {directory}",
            "files": []
        }

    if not directory.is_dir():
        return {
            "success": False,
            "error": f"路径不是目录: {directory}",
            "files": []
        }

    try:
        media_files = scan_media_files(directory, recursive=request.recursive)
        files_info = []

        for file_path in media_files:
            file_type = "image" if file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else "video"
            try:
                file_size = file_path.stat().st_size
            except OSError:
                file_size = 0

            files_info.append({
                "path": str(file_path),
                "name": file_path.name,
                "type": file_type,
                "size": file_size,
                "relative_path": str(file_path.relative_to(directory)) if file_path.is_relative_to(directory) else file_path.name
            })

        return {
            "success": True,
            "directory": str(directory),
            "total_files": len(files_info),
            "files": files_info
        }

    except Exception as e:
        logger.exception("列出目录失败: %s", directory)
        return {
            "success": False,
            "error": f"列出目录失败: {str(e)}",
            "files": []
        }


@router.get("/media")
def get_media_file(path: str = Query(..., description="媒体文件绝对路径")) -> FileResponse:
    media_path = Path(path).resolve()

    if not media_path.exists() or not media_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {media_path}")

    if not is_supported_file(media_path):
        raise HTTPException(status_code=400, detail=f"不支持的媒体文件: {media_path.suffix.lower()}")

    mime_type, _ = mimetypes.guess_type(str(media_path))
    return FileResponse(path=str(media_path), media_type=mime_type or "application/octet-stream")


@router.post("/upload")
async def upload_file(
    directory: str,
    overwrite: bool = True,
    file: UploadFile = File(...)
) -> dict:
    """上传文件到指定目录"""
    target_dir = Path(directory).resolve()

    if not target_dir.exists():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"目录不存在: {target_dir}"}
        )

    if not target_dir.is_dir():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"路径不是目录: {target_dir}"}
        )

    # 检查文件类型
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".mkv"}:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"不支持的文件类型: {file_ext}"}
        )

    target_path = target_dir / file.filename

    # 检查文件是否已存在
    if target_path.exists() and not overwrite:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"文件已存在: {file.filename}"}
        )

    try:
        # 保存上传的文件
        with target_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 获取文件信息
        file_type = "image" if file_ext in {".jpg", ".jpeg", ".png", ".webp"} else "video"
        file_size = target_path.stat().st_size

        return {
            "success": True,
            "message": f"文件上传成功: {file.filename}",
            "file_info": {
                "path": str(target_path),
                "name": file.filename,
                "type": file_type,
                "size": file_size
            }
        }

    except Exception as e:
        logger.exception("文件上传失败: %s", file.filename)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"文件上传失败: {str(e)}"}
        )
