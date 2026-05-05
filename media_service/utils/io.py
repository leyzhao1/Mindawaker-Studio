from __future__ import annotations

import json
from pathlib import Path
from typing import List

from media_service.model.schemas import MediaAnnotation

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}


def is_supported_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def is_video_file(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def scan_media_files(input_dir: Path, recursive: bool = True) -> List[Path]:
    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    files = [path for path in iterator if is_supported_file(path)]
    files.sort()
    return files


def scan_annotation_files(annotation_root: Path) -> List[Path]:
    files = [path for path in annotation_root.rglob("*.json") if path.is_file()]
    files.sort()
    return files


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_output_json_path(source_path: Path, input_dir: Path, output_dir: Path) -> Path:
    relative_path = source_path.relative_to(input_dir)
    target_path = output_dir / relative_path
    return target_path.with_name(f"{target_path.name}.json")


def safe_relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def write_json(path: Path, data: dict) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_annotation(path: Path) -> MediaAnnotation:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return MediaAnnotation(**data)
