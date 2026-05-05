import time, os, ffmpeg
import asyncio
import logging
from time import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from app.storyboard.schema import ensure_storyboard, StoryboardValidationError
from app.storyboard.renderer import emit_python_script

# 从环境变量读取 HF 缓存路径，使用默认值
def setup_hf_env():
    """设置 HuggingFace 环境变量"""
    # 默认缓存路径 (项目根目录下的 cache 文件夹)
    default_cache = Path(__file__).parent.parent.parent / "cache" / "huggingface"
    default_cache.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
    os.environ.setdefault("HF_HOME", str(default_cache))
    os.environ.setdefault("HF_HUB_CACHE", str(default_cache))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(default_cache))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(default_cache))


setup_hf_env()
import json
import re
from pathlib import Path
from uuid import uuid4
from typing import Dict, Any, Callable, List, Optional, Tuple

from app.service.dependencies import (
    get_text_service,
    get_audio_service,
    get_image_service,
    get_subtitle_service,
)
from app.service.story_pipeline import run_story_pipeline
from app.service.math_pipeline import run_math_pipeline
from app.service.animate_math_layers import _run_manim_render
from app.service.media_retrieval_client import MediaRetrievalClient
from app.service.video_retrieval_pipeline import retrieve_background_assets
from app.langchain_pipeline.text_generation_chain import LangChainTextGenerator
from app.model.story_visual_schema import StoryVisualSession, ShotRenderPrompt, ShotRenderRequest
from app.utils.config_loader import get_default_language, get_template_path
from app.utils.language_utils import resolve_language
import torch

import subprocess
import shlex


class Project:
    id: str  # project_id
    name: str
    target: str  # "text" | "audio" | "image" | "video" | "custom"
    # status: str           # "draft" | "in_progress" | "completed"
    config: dict  # 选用的模型、风格等
    created_at: time
    updated_at: time


textGenerationService = get_text_service()
imageGenerationService = get_image_service()
audioGenerationService = get_audio_service()
sub = get_subtitle_service()
# storyPromptPipeline = get_story_prompt_pipeline()
targets = ["text", "audio", "image", "video", "video_retrieval", "custom"]
all_status = [
    "draft",
    "in_text_progress",
    "in_building_characters",
    "in_building_scenes",
    "in_audio_progress",
    "in_image_progress",
    "in_video_progress",
    "in_video_rebuild",
    "in_video_concat",
    "completed",
    "error",
    "block",
]


TASKS = {}  # 简单用内存字典保存进度，生产可换为 Redis 等
SETTINGS = {}
PROGRESS_CALLBACKS = {}  # project_id -> progress callback function
logger = logging.getLogger(__name__)


def register_progress_callback(project_id: str, callback):
    """注册进度回调函数，当 update_progress 被调用时触发"""
    PROGRESS_CALLBACKS[project_id] = callback


def unregister_progress_callback(project_id: str):
    """注销进度回调函数"""
    PROGRESS_CALLBACKS.pop(project_id, None)


def update_progress(project_id: str, percent: int, stage: str):
    print("percent:", percent, ", stage:", stage)
    TASKS[project_id]["percent"] = percent
    TASKS[project_id]["stage"] = stage
    pipeline_status = TASKS[project_id].get("status", "")

    # 调用进度回调（如果已注册）
    if project_id in PROGRESS_CALLBACKS:
        try:
            PROGRESS_CALLBACKS[project_id](
                {
                    "project_id": project_id,
                    "progress": percent,
                    "percent": percent,
                    "stage": stage,
                    "message": stage,
                    "pipeline_status": pipeline_status,
                }
            )
        except Exception as e:
            print(f"进度回调调用失败: {e}")


def emit_progress_status(project_id: str, status: str, stage: Optional[str] = None, percent: Optional[int] = None):
    set_progress_status(project_id=project_id, status=status)
    payload = {
        "project_id": project_id,
        "pipeline_status": TASKS[project_id].get("status", ""),
        "progress": TASKS[project_id].get("percent", 0),
        "percent": TASKS[project_id].get("percent", 0),
        "stage": TASKS[project_id].get("stage", ""),
        "message": TASKS[project_id].get("stage", ""),
    }
    if percent is not None:
        TASKS[project_id]["percent"] = percent
        payload["progress"] = percent
        payload["percent"] = percent
    if stage is not None:
        TASKS[project_id]["stage"] = stage
        payload["stage"] = stage
        payload["message"] = stage

    if project_id in PROGRESS_CALLBACKS:
        try:
            PROGRESS_CALLBACKS[project_id](payload)
        except Exception as e:
            print(f"状态回调调用失败: {e}")




def set_progress_data(project_id: str, key: str, data: Any):
    TASKS[project_id][key] = data


def set_progress_data_with_index(project_id: str, key: str, index: int, data: Any):
    # if index < len(TASKS[project_id][key]):
    TASKS[project_id][key][index] = data


def get_progress_data(project_id: str, key: str):
    return TASKS[project_id].get(key)


def get_progress_data_len(project_id: str, key: str):
    return len(TASKS[project_id].get(key))


def get_progress_data_with_index(project_id: str, key: str, index: int):
    if index < len(TASKS[project_id][key]):
        return TASKS[project_id][key][index]


def set_progress_status(project_id: str, status: str):
    if status not in all_status:
        status = "unknown status"
    TASKS[project_id]["status"] = status


def get_progress_status(project_id: str):
    return TASKS[project_id].get("status")


def update_audio_task_config(project_id: str, config: dict, index: int):
    TASKS[project_id]["audios_configs"][index] = config


def update_image_task_config(project_id: str, config: dict, index: int):
    TASKS[project_id]["images_configs"][index] = config


def update_text_task_config(project_id: str, config: dict):
    TASKS[project_id]["text_config"] = config


class PipelineManager:
    REDRAW_HISTORY_LIMIT = 4

    def __init__(self, base_dir: str = "app/assets/projects"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.projects: Dict[str, Dict[str, Any]] = {}  # 也可以只存 meta，把详细的放文件里

    def _normalize_config_for_save(self, config: Any):
        if config is None:
            return None
        if isinstance(config, dict):
            return config
        if hasattr(config, "model_dump"):
            return config.model_dump()
        if hasattr(config, "dict"):
            return config.dict()
        return config

    def _get_project_language(self, project_id: str, text: str = "", requested_language: Optional[str] = None) -> str:
        project = self.projects.get(project_id, {})
        config = project.get("config") or {}
        default_language = get_default_language()
        if isinstance(config, dict):
            configured_language = config.get("language") or config.get("default_language")
        else:
            configured_language = getattr(config, "language", None) or getattr(config, "default_language", None)
        return resolve_language(text=text, requested_language=requested_language or configured_language, default_language=default_language)

    def _get_config_value(self, config: Any, key: str, default: Any = ""):
        if isinstance(config, dict):
            value = config.get(key, default)
        else:
            value = getattr(config, key, default)
        return default if value is None else value

    def _get_project_config_value(self, project_id: str, key: str, default: Any = ""):
        config = self.projects.get(project_id, {}).get("config") or {}
        return self._get_config_value(config, key, default)

    def _resolve_overlay_axis_expr(self, project_id: str, *, axis: str) -> str:
        base_expr = "(W-w)/2" if axis == "x" else "(H-h)/2"
        direct_key = f"math_overlay_{axis}"
        offset_key = f"math_overlay_offset_{axis}"

        direct_expr = self._get_project_config_value(project_id, direct_key, "")
        if isinstance(direct_expr, str) and direct_expr.strip():
            return direct_expr.strip()

        offset = self._to_float(self._get_project_config_value(project_id, offset_key, 0.0), 0.0)
        if abs(offset) < 1e-6:
            return base_expr
        return f"{base_expr}{offset:+.3f}"

    def _math_overlay_position_exprs(self, project_id: str) -> tuple[str, str]:
        return (
            self._resolve_overlay_axis_expr(project_id, axis="x"),
            self._resolve_overlay_axis_expr(project_id, axis="y"),
        )

    def _project_meta_path(self, project_id: str) -> Path:
        return self.base_dir / project_id / "meta.json"

    def _project_dir(self, project_id: str) -> Path:
        return self.base_dir / project_id

    def _artifacts_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "artifacts"

    def _artifact_section_dir(self, project_id: str, section: str) -> Path:
        return self._prepare_output_dir(self._artifacts_dir(project_id) / section)

    def _to_serializable(self, value: Any):
        if isinstance(value, dict):
            return {str(k): self._to_serializable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_serializable(v) for v in value]
        if hasattr(value, "model_dump"):
            return self._to_serializable(value.model_dump())
        if hasattr(value, "dict"):
            return self._to_serializable(value.dict())
        return value

    def _register_artifact(self, project_id: str, section: str, key: str, value: Any):
        task_data = TASKS.setdefault(project_id, {})
        artifacts = task_data.setdefault("artifacts", {})
        section_map = artifacts.setdefault(section, {})
        section_map[key] = value

    def _write_artifact_text(self, project_id: str, section: str, filename: str, content: str, key: Optional[str] = None) -> str:
        directory = self._artifact_section_dir(project_id, section)
        path = directory / filename
        path.write_text(content or "", encoding="utf-8")
        relative_path = str(path.relative_to(self._project_dir(project_id))).replace("\\", "/")
        self._register_artifact(project_id, section, key or filename, relative_path)
        return relative_path

    def _write_artifact_json(self, project_id: str, section: str, filename: str, data: Any, key: Optional[str] = None) -> str:
        directory = self._artifact_section_dir(project_id, section)
        path = directory / filename
        serializable = self._to_serializable(data)
        path.write_text(json.dumps(serializable, indent=4, ensure_ascii=False), encoding="utf-8")
        relative_path = str(path.relative_to(self._project_dir(project_id))).replace("\\", "/")
        self._register_artifact(project_id, section, key or filename, relative_path)
        return relative_path

    def _index_math_scripts(self, project_id: str, math_dir: Path):
        scripts = [str(path.relative_to(self._project_dir(project_id))).replace("\\", "/") for path in sorted(math_dir.glob("*_manim.py"))]
        self._register_artifact(project_id, "math", "script_files", scripts)
        self._register_artifact(project_id, "math", "animation_dir", str(math_dir.relative_to(self._project_dir(project_id))).replace("\\", "/"))
        return scripts

    def _persist_story_artifacts(self, project_id: str, story_result: Dict[str, Any]):
        self._write_artifact_json(project_id, "story", "characters.json", story_result.get("characters", []), key="characters_json")
        self._write_artifact_json(project_id, "story", "character_specs.json", story_result.get("character_specs", []), key="character_specs_json")
        self._write_artifact_json(project_id, "story", "items.json", story_result.get("items", {}), key="items_json")
        self._write_artifact_json(project_id, "story", "scenes.json", story_result.get("scenes", []), key="scenes_json")
        self._write_artifact_json(project_id, "story", "world_scenes.json", story_result.get("world_scenes", []), key="world_scenes_json")
        self._write_artifact_json(project_id, "story", "scene_to_world_scene.json", story_result.get("scene_to_world_scene", {}), key="scene_to_world_scene_json")
        self._write_artifact_json(project_id, "story", "shots.json", story_result.get("shots", []), key="shots_json")
        self._write_artifact_json(project_id, "story", "segments.json", story_result.get("segments", []), key="segments_json")
        self._write_artifact_json(project_id, "story", "anchor_store.json", story_result.get("anchor_store", {}), key="anchor_store_json")
        self._register_artifact(project_id, "story", "scene_count", story_result.get("scene_count", 0))
        self._register_artifact(project_id, "story", "world_scene_count", story_result.get("world_scene_count", 0))
        self._register_artifact(project_id, "story", "shot_count", story_result.get("shot_count", 0))

    def _build_story_visual_session(
        self,
        project_id: str,
        story_result: Dict[str, Any],
        character_result: Dict[str, Any],
        scene_result: Dict[str, Any],
    ) -> StoryVisualSession:
        character_bindings = {
            item.get("source_character_id"): item.get("mw_character_id")
            for item in character_result.get("characters", [])
            if item.get("source_character_id") and item.get("mw_character_id")
        }
        scene_bindings = {}
        for item in scene_result.get("scenes", []):
            world_scene_id = item.get("world_scene_id") or item.get("source_scene_id") or item.get("scene_id")
            mw_scene_instance_id = item.get("mw_scene_instance_id") or item.get("scene_instance_id") or item.get("mw_scene_id")
            if world_scene_id and mw_scene_instance_id:
                scene_bindings[world_scene_id] = mw_scene_instance_id
        return StoryVisualSession(
            project_id=project_id,
            style_id="default",
            character_bindings=character_bindings,
            scene_bindings=scene_bindings,
            raw_character_mappings=character_result.get("characters", []),
            raw_scene_mappings=scene_result.get("scenes", []),
        )

    def _persist_story_visual_session(self, project_id: str, session: StoryVisualSession):
        set_progress_data(project_id=project_id, key="story_visual_session", data=session.model_dump())
        self._write_artifact_json(
            project_id,
            "story",
            "story_visual_session.json",
            session,
            key="story_visual_session_json",
        )
        return session

    def _load_story_visual_session(self, project_id: str) -> Optional[StoryVisualSession]:
        session_data = get_progress_data(project_id=project_id, key="story_visual_session")
        if session_data:
            return StoryVisualSession(**session_data)
        artifacts = (TASKS.get(project_id, {}) or {}).get("artifacts", {}).get("story", {})
        session_rel = artifacts.get("story_visual_session_json")
        if not session_rel:
            return None
        session_path = self._project_dir(project_id) / session_rel
        if not session_path.exists():
            return None
        return StoryVisualSession(**json.loads(session_path.read_text(encoding="utf-8")))

    def _prepare_story_world(self, project_id: str, image_model_name: str, image_api_key: str, story_result: Dict[str, Any]):
        character_specs = story_result.get("character_specs", [])
        scene_specs = story_result.get("world_scenes", [])
        if not character_specs and not scene_specs:
            return {"success": True, "characters": {}, "scenes": {}}

        if not imageGenerationService.ensure_engine(image_model_name=image_model_name, image_api_key=image_api_key):
            return {"success": False, "error": "创建 mw 图像引擎失败"}
        if not imageGenerationService.supports_story_world_preparation():
            return {"success": True, "characters": {}, "scenes": {}}

        set_progress_status(project_id=project_id, status="in_building_characters")
        update_progress(project_id=project_id, percent=55, stage="正在构建故事角色")
        character_result = imageGenerationService.build_characters(character_specs)
        if not character_result.get("success"):
            return {"success": False, "error": "mw 构建角色失败", "detail": character_result}

        character_mapping = {
            item.get("source_character_id"): item.get("mw_character_id")
            for item in character_result.get("characters", [])
            if item.get("source_character_id") and item.get("mw_character_id")
        }

        enriched_scene_specs = []
        for scene_spec in scene_specs:
            scene_copy = dict(scene_spec)
            object_bindings = {}
            for character_id in scene_copy.get("characters_in_scene", []):
                if character_id in character_mapping:
                    object_bindings[character_id] = character_mapping[character_id]
            scene_copy["character_bindings"] = object_bindings
            enriched_scene_specs.append(scene_copy)

        set_progress_status(project_id=project_id, status="in_building_scenes")
        update_progress(project_id=project_id, percent=65, stage="正在构建固定场景")
        scene_result = imageGenerationService.build_scenes(enriched_scene_specs, character_mapping)
        if not scene_result.get("success"):
            return {"success": False, "error": "mw 构建场景失败", "detail": scene_result}

        set_progress_data(project_id=project_id, key="story_character_mappings", data=character_result.get("characters", []))
        set_progress_data(project_id=project_id, key="story_scene_mappings", data=scene_result.get("scenes", []))
        self._write_artifact_json(project_id, "story", "mw_character_mappings.json", character_result.get("characters", []), key="mw_character_mappings_json")
        self._write_artifact_json(project_id, "story", "mw_scene_mappings.json", scene_result.get("scenes", []), key="mw_scene_mappings_json")
        self._register_artifact(project_id, "story", "mw_character_count", len(character_result.get("characters", [])))
        self._register_artifact(project_id, "story", "mw_scene_count", len(scene_result.get("scenes", [])))
        session = self._build_story_visual_session(project_id, story_result, character_result, scene_result)
        self._persist_story_visual_session(project_id, session)
        return {"success": True, "characters": character_result, "scenes": scene_result, "story_visual_session": session.model_dump()}

    def _restore_story_world_if_needed(self, project_id: str, image_model_name: str, image_api_key: str):
        session = self._load_story_visual_session(project_id)
        if session is not None:
            set_progress_data(project_id=project_id, key="story_character_mappings", data=session.raw_character_mappings)
            set_progress_data(project_id=project_id, key="story_scene_mappings", data=session.raw_scene_mappings)
            set_progress_data(project_id=project_id, key="story_visual_session", data=session.model_dump())
            return True

        artifacts = (TASKS.get(project_id, {}) or {}).get("artifacts", {}).get("story", {})
        if get_progress_data(project_id=project_id, key="story_character_mappings") and get_progress_data(project_id=project_id, key="story_scene_mappings"):
            return True
        character_specs_rel = artifacts.get("character_specs_json")
        world_scenes_rel = artifacts.get("world_scenes_json")
        if not character_specs_rel and not world_scenes_rel:
            return True
        base_dir = self._project_dir(project_id)
        story_result = {
            "character_specs": json.loads((base_dir / character_specs_rel).read_text(encoding="utf-8")) if character_specs_rel else [],
            "world_scenes": json.loads((base_dir / world_scenes_rel).read_text(encoding="utf-8")) if world_scenes_rel else [],
        }
        result = self._prepare_story_world(project_id, image_model_name, image_api_key, story_result)
        if not result.get("success"):
            raise ValueError(result.get("error") or "恢复 story world 失败")
        return True

    def _build_shot_render_request(
        self,
        project_id: str,
        segment: Dict[str, Any],
        size: str,
        n: int,
    ) -> ShotRenderRequest:
        session = self._load_story_visual_session(project_id)
        return ShotRenderRequest(
            story_session=session,
            scene_ref=segment.get("world_scene_id") or segment.get("scene_id", ""),
            character_refs=segment.get("focus_characters", []),
            shot_id=segment.get("shot_id") or f"shot_{segment.get('shot_idx', 0)}",
            shot={
                "scene_id": segment.get("scene_id", ""),
                "shot_idx": segment.get("shot_idx", 0),
                "text": segment.get("text", ""),
            },
            prompt=ShotRenderPrompt(positive=segment.get("image_prompt", ""), negative=""),
            size=size,
            n=n,
        )

    def render_story_shot(
        self,
        project_id: str,
        segment: Dict[str, Any],
        model_name: str,
        api_key: str,
        size: str,
        n: int,
    ):
        shot_id = segment.get("shot_id") or f"shot_{segment.get('shot_idx', 0)}"
        scene_ref = segment.get("world_scene_id") or segment.get("scene_id", "")
        print(f"[PipelineManager.render_story_shot] start project_id={project_id} shot_id={shot_id} scene_ref={scene_ref}")
        if not imageGenerationService.ensure_engine(image_model_name=model_name, image_api_key=api_key):
            return self._image_result(False, error="创建 mw 图像引擎失败")
        if not imageGenerationService.supports_shot_render():
            print(f"[PipelineManager.render_story_shot] engine lacks shot render, fallback to gen_image shot_id={shot_id}")
            return self.gen_image(
                project_id=project_id,
                text=segment.get("image_prompt", ""),
                model_name=model_name,
                api_key=api_key,
                n=n,
                size=size,
            )
        request = self._build_shot_render_request(project_id, segment, size, n)
        response = imageGenerationService.render_shot(request)
        if not response.success:
            print(f"[PipelineManager.render_story_shot] failed shot_id={shot_id} error={response.error}")
            return self._image_result(False, error=response.error)
        print(f"[PipelineManager.render_story_shot] success shot_id={shot_id} image_paths={response.image_paths}")
        return self._image_result(True, image_paths=response.image_paths)

    def _story_result(self, success: bool, error: Optional[str] = None, **kwargs):
        result = {"success": success, "error": error}
        result.update(kwargs)
        return result

    def _persist_math_artifacts(self, project_id: str, math_result: Dict[str, Any]):
        self._write_artifact_json(project_id, "math", "scenes.json", math_result.get("scenes", []), key="scenes_json")
        self._write_artifact_json(project_id, "math", "segments.json", math_result.get("segments", []), key="segments_json")
        self._register_artifact(project_id, "math", "animation_files", math_result.get("math_animations", []))
        self._register_artifact(project_id, "math", "lines", math_result.get("lines", []))
        math_dir = self._math_animations_dir(project_id)
        self._index_math_scripts(project_id, math_dir)

    def _text_result(self, success: bool, error: Optional[str] = None, content: str = "", prompts: Optional[List[str]] = None):
        return {
            "success": success,
            "error": error,
            "content": content or "",
            "prompts": prompts or [],
        }

    def _audio_result(self, success: bool, error: Optional[str] = None, audio_path: str = "", duration: float = 0):
        return {
            "success": success,
            "error": error,
            "audio_path": audio_path or "",
            "duration": duration or 0,
        }

    def _image_result(self, success: bool, error: Optional[str] = None, image_paths: Optional[List[str]] = None):
        return {
            "success": success,
            "error": error,
            "image_paths": image_paths or [],
        }

    def _audio_sequence_result(
        self,
        success: bool,
        error: Optional[str] = None,
        audios: Optional[List[str]] = None,
        durations: Optional[List[float]] = None,
        cancelled: bool = False,
    ):
        return {
            "success": success,
            "error": error,
            "audios": audios or [],
            "durations": durations or [],
            "cancelled": cancelled,
        }

    def _image_sequence_result(
        self,
        success: bool,
        error: Optional[str] = None,
        images: Optional[List[str]] = None,
        cancelled: bool = False,
    ):
        return {
            "success": success,
            "error": error,
            "images": images or [],
            "cancelled": cancelled,
        }

    def _video_result(
        self,
        success: bool,
        error: Optional[str] = None,
        video_path: str = "",
        cancelled: bool = False,
        **kwargs,
    ):
        result = {
            "success": success,
            "error": error,
            "video_path": video_path or "",
            "cancelled": cancelled,
        }
        result.update(kwargs)
        return result

    def _set_project_error(self, project_id: str, error: str):
        task_data = TASKS.setdefault(project_id, {})
        task_data["error"] = error
        set_progress_data(project_id=project_id, key="errors", data=error)
        if task_data.get("status") != "completed":
            set_progress_status(project_id=project_id, status="error")

    def _persist_project_failure(self, project_id: str, error: str):
        self._set_project_error(project_id, error)
        try:
            self.save_project(project_id)
        except Exception as save_error:
            print(f"[persist_project_failure] save_project failed for {project_id}: {save_error}")

    def _build_partial_video_payload(self, project_id: str):
        task_data = TASKS.get(project_id, {})
        payload = {
            "text": task_data.get("text", ""),
            "lines": task_data.get("lines", []),
            "prompts": task_data.get("prompts", []),
            "images": task_data.get("images", []),
            "audios": task_data.get("audios", []),
            "durations": task_data.get("durations", []),
            "images_configs": task_data.get("images_configs", []),
            "audios_configs": task_data.get("audios_configs", []),
            "clips": task_data.get("clips", []),
            "video_segments": task_data.get("video_segments", []),
            "background_assets": task_data.get("background_assets", []),
            "retrieval_items": task_data.get("retrieval_items", []),
            "missing_head_keywords": task_data.get("missing_head_keywords", []),
            "shot_texts": task_data.get("shot_texts", []),
            "retrieval_texts": task_data.get("retrieval_texts", []),
            "scene_segment_files": task_data.get("scene_segment_files", []),
            "math_scripts": task_data.get("math_scripts", []),
            "math_script_files": task_data.get("math_script_files", []),
        }
        if "math_animations" in task_data:
            payload["math_animations"] = task_data.get("math_animations", [])
        if "math_animations_dir" in task_data:
            payload["math_animations_dir"] = task_data.get("math_animations_dir", "")
        return payload

    def _cancelled_video_result(self, project_id: str):
        return self._video_result(False, error="任务已取消", cancelled=True, **self._build_partial_video_payload(project_id))

    def _failed_video_result(self, project_id: str, error: str):
        self._set_project_error(project_id, error)
        return self._video_result(False, error=error, **self._build_partial_video_payload(project_id))

    def _video_result_with_assets(self, success: bool, project_id: str, video_path: str = "", error: Optional[str] = None):
        return self._video_result(success, error=error, video_path=video_path, **self._build_partial_video_payload(project_id))

    def _math_animations_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "math_animations"

    def _video_segments_root_dir(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "video_segments"

    def _video_segments_mode_dir(self, project_id: str, mode: str) -> Path:
        return self._video_segments_root_dir(project_id) / mode

    def _prepare_output_dir(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _prepare_fresh_output_dir(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        for child in directory.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink()
            elif child.is_dir():
                import shutil

                shutil.rmtree(child, ignore_errors=True)
        return directory

    def _set_video_artifact_metadata(
        self,
        project_id: str,
        *,
        mode: str,
        segments_dir: Path,
        segment_paths: List[str],
        math_animations: Optional[List[str]] = None,
        math_animations_dir: Optional[Path] = None,
    ):
        task_data = TASKS.setdefault(project_id, {})
        task_data["video_segments_mode"] = mode
        task_data["video_segments_dir"] = str(segments_dir).replace("\\", "/")
        task_data["video_segments"] = [str(path).replace("\\", "/") for path in segment_paths]

        mode_key = f"{mode}_video_segments"
        mode_dir_key = f"{mode}_video_segments_dir"
        task_data[mode_key] = task_data["video_segments"]
        task_data[mode_dir_key] = task_data["video_segments_dir"]

        if math_animations is not None:
            task_data["math_animations"] = [str(path).replace("\\", "/") for path in math_animations]
        if math_animations_dir is not None:
            task_data["math_animations_dir"] = str(math_animations_dir).replace("\\", "/")

        self._sync_clips_from_assets(project_id)

    def _supports_clip_rebuild(self, project_id: str) -> bool:
        config = self.projects.get(project_id, {}).get("config") or {}
        style = config.get("style", "") if isinstance(config, dict) else getattr(config, "style", "")
        return "math" not in style

    def _sync_clips_from_assets(self, project_id: str):
        task_data = TASKS.setdefault(project_id, {})
        images = task_data.get("images") or []
        audios = task_data.get("audios") or []
        durations = task_data.get("durations") or []
        segments = task_data.get("video_segments") or []
        prompts = task_data.get("prompts") or []
        lines = task_data.get("lines") or []
        math_scripts = task_data.get("math_scripts") or []
        math_script_files = task_data.get("math_script_files") or []
        math_animations = task_data.get("math_animations") or []
        background_assets = task_data.get("background_assets") or []
        existing = task_data.get("clips") or []
        total = max(len(images), len(audios), len(durations), len(segments), len(lines), len(math_script_files), len(background_assets))
        clips = []
        for index in range(total):
            previous = existing[index] if index < len(existing) and isinstance(existing[index], dict) else {}
            asset = background_assets[index] if index < len(background_assets) and isinstance(background_assets[index], dict) else {}
            source_path = asset.get("source_path", previous.get("source_path", ""))
            media_type = self._normalize_media_type(str(asset.get("media_type", previous.get("media_type", ""))))
            image_path = images[index] if index < len(images) else previous.get("image_path", "")
            if not image_path and media_type == "image":
                image_path = source_path
            clips.append({
                "index": index,
                "clip_path": segments[index] if index < len(segments) else previous.get("clip_path", ""),
                "image_path": image_path,
                "audio_path": audios[index] if index < len(audios) else previous.get("audio_path", ""),
                "duration": durations[index] if index < len(durations) else previous.get("duration", 0),
                "prompt": prompts[index] if index < len(prompts) else previous.get("prompt", ""),
                "text": lines[index] if index < len(lines) else previous.get("text", asset.get("text", "")),
                "dirty": bool(previous.get("dirty", False)),
                "script": math_scripts[index] if index < len(math_scripts) else previous.get("script", ""),
                "script_file": math_script_files[index] if index < len(math_script_files) else previous.get("script_file", ""),
                "math_animation_path": math_animations[index] if index < len(math_animations) else previous.get("math_animation_path", ""),
                "source_path": source_path,
                "media_type": media_type,
                "annotation_path": asset.get("annotation_path", previous.get("annotation_path", "")),
                "start_sec": asset.get("start_sec", previous.get("start_sec")),
                "end_sec": asset.get("end_sec", previous.get("end_sec")),
                "score": asset.get("score", previous.get("score", 0.0)),
            })
        task_data["clips"] = clips
        return clips

    def _mark_clips_dirty(self, project_id: str, indices: List[int]):
        clips = self._sync_clips_from_assets(project_id)
        for index in indices:
            if 0 <= index < len(clips):
                clips[index]["dirty"] = True
        return clips

    def _dirty_clip_indices(self, project_id: str) -> List[int]:
        clips = self._sync_clips_from_assets(project_id)
        return [clip.get("index", idx) for idx, clip in enumerate(clips) if clip.get("dirty")]

    def _run_ffmpeg_with_timeout(self, ffmpeg_cmd, timeout=120):
        """
        运行ffmpeg命令并添加超时控制
        Args:
            ffmpeg_cmd: ffmpeg命令对象（ffmpeg.Stream对象）
            timeout: 超时时间（秒）
        Returns:
            无，成功执行
        Raises:
            ffmpeg.Error: ffmpeg执行错误
            subprocess.TimeoutExpired: 命令执行超时
        """
        timeout_sec = max(float(timeout or 120), 1.0)
        try:
            # 编译ffmpeg命令获取命令行参数
            cmd = ffmpeg_cmd.compile()
            cmd_args = [str(part) for part in cmd]
            cmd_text = shlex.join(cmd_args)
            started_at = time()
            logger.info("[ffmpeg] start timeout=%ss cmd=%s", timeout_sec, cmd_text)

            # 使用subprocess.run执行命令，设置超时
            result = subprocess.run(
                cmd_args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_sec,
            )
            elapsed = time() - started_at
            logger.info("[ffmpeg] done returncode=%s elapsed=%.2fs cmd=%s", result.returncode, elapsed, cmd_text)

            # 检查返回码
            if result.returncode != 0:
                stderr_text = (result.stderr or b"").decode("utf-8", errors="ignore")
                logger.error("[ffmpeg] failed returncode=%s elapsed=%.2fs stderr=%s", result.returncode, elapsed, stderr_text)
                raise ffmpeg.Error(cmd_text, result.stdout, result.stderr)

        except subprocess.TimeoutExpired as exc:
            elapsed = time() - started_at
            stderr_raw = exc.stderr or b""
            stderr_text = stderr_raw.decode("utf-8", errors="ignore") if isinstance(stderr_raw, (bytes, bytearray)) else str(stderr_raw)
            logger.error(
                "[ffmpeg] timeout elapsed=%.2fs timeout=%ss cmd=%s stderr=%s",
                elapsed,
                timeout_sec,
                cmd_text,
                (stderr_text or "")[:2000],
            )
            # 重新抛出超时异常，但包装成ffmpeg.Error以保持兼容性
            raise ffmpeg.Error(
                cmd_text,
                b"",
                f"Command timeout after {timeout_sec} seconds".encode(),
            )
        except Exception:
            raise


    def _normalize_media_type(self, media_type: str) -> str:
        value = (media_type or "").lower().strip()
        if value in {"image", "video", "color"}:
            return value
        if value in {"img", "photo", "picture"}:
            return "image"
        if value in {"clip", "movie"}:
            return "video"
        return "unknown"

    def _is_math_style(self, style: str) -> bool:
        return "math" in (style or "").lower()

    def _extract_json_block(self, content: str) -> str:
        raw = (content or "").strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            if len(parts) >= 2:
                candidate = parts[1]
                if candidate.startswith("json"):
                    candidate = candidate[len("json"):]
                raw = candidate.strip()
        if raw.startswith("{") and raw.endswith("}"):
            return raw
        first = raw.find("{")
        last = raw.rfind("}")
        if first != -1 and last != -1 and last > first:
            return raw[first:last + 1]
        return raw

    def _strip_inline_formula_markers(self, text: Any) -> str:
        raw = str(text or "")
        if not raw:
            return ""

        cleaned = re.sub(
            r"\$([^$]+)\$|\\\((.*?)\\\)",
            lambda m: (m.group(1) or m.group(2) or "").strip(),
            raw,
        )
        cleaned = cleaned.replace("$", "")
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        return cleaned.strip()

    _VALID_LAYOUT_MODES = {"stack_with_footer", "two_col", "card_row", "summary_stack", "plot_with_side_annotation"}

    _LAYOUT_MODE_ALIASES = {
        "stack": "stack_with_footer",
        "stack_layout": "stack_with_footer",
        "vertical_stack": "stack_with_footer",
        "vertical": "stack_with_footer",
        "two_column": "two_col",
        "two_columns": "two_col",
        "two-col": "two_col",
        "side_by_side": "two_col",
        "horizontal": "card_row",
        "card": "card_row",
        "card_layout": "card_row",
        "summary": "summary_stack",
        "summary_layout": "summary_stack",
        "plot_with_side": "plot_with_side_annotation",
        "plot_side": "plot_with_side_annotation",
        "plot": "plot_with_side_annotation",
    }

    def _normalize_layout_mode(self, value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in self._VALID_LAYOUT_MODES:
            return raw
        alias = self._LAYOUT_MODE_ALIASES.get(raw)
        return alias if alias else "stack_with_footer"

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    def _write_math_retrieval_scene_script(self, project_id: str, index: int, script: str) -> str:
        scripts_dir = self._prepare_output_dir(self._project_dir(project_id) / "math_retrieval_scripts")
        script_filename = f"math_retrieval_{index:04d}.py"
        script_path = scripts_dir / script_filename
        script_path.write_text(script or "", encoding="utf-8")
        relative_path = str(script_path.relative_to(self._project_dir(project_id))).replace("\\", "/")
        self._register_artifact(project_id, "math_retrieval", f"script_{index:04d}", relative_path)
        return relative_path

    def _render_math_retrieval_scene_script(self, project_id: str, index: int, script_relative_path: str) -> str:
        script_path = self._project_dir(project_id) / script_relative_path
        output_dir = self._prepare_output_dir(self._project_dir(project_id) / "math_retrieval_segments")
        output_path = output_dir / f"math_retrieval_{index:04d}.mov"
        normalized = self._render_manim_script_with_retry(script_path, output_path)
        self._register_artifact(project_id, "math_retrieval", f"segment_{index:04d}", normalized)
        return normalized

    def _normalize_generated_manim_script(self, script: Any) -> str:
        content = str(script or "").strip()
        if not content:
            return ""
        if content.startswith("```"):
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1]
                if content.startswith("python"):
                    content = content[len("python"):]
                content = content.strip()
        if "from manim import" not in content and "import manim" not in content:
            content = "from manim import *\n\n" + content
        return content

    def _render_manim_script_with_retry(
        self,
        script_path: Path,
        output_path: Path,
        resolution: Tuple[int, int] = (1920, 1080),
        fps: int = 30,
        max_attempts: int = 2,
    ) -> str:
        source_script = script_path.read_text(encoding="utf-8") if script_path.exists() else ""
        normalized_script = self._normalize_generated_manim_script(source_script)
        if not normalized_script:
            raise ValueError(f"manim 脚本为空: {script_path}")
        script_path.write_text(normalized_script, encoding="utf-8")

        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                rendered = asyncio.run(_run_manim_render(script_path, output_path, resolution, fps))
                return str(rendered).replace("\\", "/")
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[math_retrieval] manim render failed attempt=%s/%s script=%s error=%s",
                    attempt,
                    max_attempts,
                    script_path,
                    exc,
                )

        raise RuntimeError(f"manim 渲染失败: {script_path}: {last_error}")

    def _render_story_style_clip(
        self,
        image_path: str,
        audio_path: str,
        duration: float,
        clip_path: Path,
        fps: int = 30,
    ) -> str:
        if duration <= 0:
            duration = 5.0
        if not self._is_valid_media_file(image_path):
            raise FileNotFoundError(f"图片素材缺失: {image_path}")
        if not self._is_valid_media_file(audio_path):
            raise FileNotFoundError(f"音频素材缺失: {audio_path}")

        video_stream = (
            ffmpeg
            .input(image_path, loop=1, framerate=fps)
            .video
            .filter("scale", 1280, 720)
            .filter("fps", fps=fps)
            .filter("trim", duration=duration)
            .filter("setpts", "PTS-STARTPTS")
        )
        audio_stream = ffmpeg.input(audio_path).audio.filter("atrim", duration=duration).filter("asetpts", "PTS-STARTPTS")
        ffmpeg_cmd = ffmpeg.output(
            video_stream,
            audio_stream,
            str(clip_path),
            vcodec="libx264",
            preset="ultrafast",
            pix_fmt="yuv420p",
            acodec="aac",
            r=fps,
            t=duration,
            shortest=None,
        ).overwrite_output()
        clip_timeout = max(45, int(duration * 12))
        self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=clip_timeout)
        return str(clip_path).replace("\\", "/")

    def _build_black_color_asset(
        self,
        *,
        index: int,
        text: str,
        audio_path: str,
        audio_duration: float,
    ) -> Dict[str, Any]:
        return {
            "index": index,
            "text": text,
            "source_path": "",
            "media_type": "color",
            "color": "#000000",
            "annotation_path": "",
            "score": 0.0,
            "start_sec": None,
            "end_sec": None,
            "audio_path": audio_path,
            "audio_duration": audio_duration,
            "retrieval_result": {},
        }

    def _build_math_retrieval_query_units(
        self,
        *,
        line_items: List[Dict[str, Any]],
        durations: List[float],
    ) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        for line_index, item in enumerate(line_items):
            scene_index = self._to_int(item.get("scene_index"), line_index)
            line_text = self._strip_inline_formula_markers(item.get("line") or item.get("shot_text") or "")
            line_text = line_text.strip()
            scene_duration = self._to_float(
                durations[line_index] if line_index < len(durations) else item.get("estimated_duration"),
                self._to_float(item.get("estimated_duration"), 0.0),
            )
            if scene_duration <= 0:
                scene_duration = 5.0

            raw_chunks = [chunk for chunk in (item.get("narration_chunks") or []) if isinstance(chunk, dict)]
            chunk_units: List[Dict[str, Any]] = []
            for chunk_index, chunk in enumerate(raw_chunks):
                chunk_text = self._strip_inline_formula_markers(chunk.get("text") or "")
                if not chunk_text:
                    continue
                start = self._to_float(chunk.get("start"), 0.0)
                end = self._to_float(chunk.get("end"), start)
                duration = end - start
                if duration <= 0:
                    duration = 0.0
                chunk_id = str(chunk.get("chunk_id") or "").strip() or f"scene_{scene_index:02d}_chunk_{chunk_index:02d}"
                chunk_units.append(
                    {
                        "query_index": len(units) + len(chunk_units),
                        "scene_index": scene_index,
                        "line_index": line_index,
                        "chunk_index": chunk_index,
                        "chunk_id": chunk_id,
                        "text": chunk_text,
                        "duration": duration,
                        "start": start,
                        "end": end,
                    }
                )

            if not chunk_units:
                fallback_text = line_text
                if not fallback_text:
                    continue
                units.append(
                    {
                        "query_index": len(units),
                        "scene_index": scene_index,
                        "line_index": line_index,
                        "chunk_index": 0,
                        "chunk_id": f"scene_{scene_index:02d}_chunk_00",
                        "text": fallback_text,
                        "duration": scene_duration,
                        "start": 0.0,
                        "end": scene_duration,
                    }
                )
                continue

            missing_indices = [idx for idx, unit in enumerate(chunk_units) if self._to_float(unit.get("duration"), 0.0) <= 0]
            if missing_indices:
                total_chars = sum(max(len(str(unit.get("text") or "").strip()), 1) for unit in chunk_units)
                if total_chars <= 0:
                    total_chars = len(chunk_units)
                for idx in missing_indices:
                    text_len = max(len(str(chunk_units[idx].get("text") or "").strip()), 1)
                    chunk_units[idx]["duration"] = scene_duration * (text_len / total_chars)

            total_duration = sum(max(self._to_float(unit.get("duration"), 0.0), 0.0) for unit in chunk_units)
            if total_duration <= 0:
                default_duration = scene_duration / max(len(chunk_units), 1)
                for unit in chunk_units:
                    unit["duration"] = default_duration
            else:
                scale = scene_duration / total_duration
                for unit in chunk_units:
                    unit["duration"] = max(self._to_float(unit.get("duration"), 0.0), 0.0) * scale

            cursor = 0.0
            for unit in chunk_units:
                normalized_duration = max(self._to_float(unit.get("duration"), 0.0), 0.0)
                unit["start"] = cursor
                unit["end"] = cursor + normalized_duration
                cursor = unit["end"]
                unit["query_index"] = len(units)
                units.append(unit)

        return units

    def _build_math_retrieval_assets(
        self,
        *,
        lines: List[str],
        retrieval_result: Dict[str, Any],
        audio_files: List[str],
        durations: List[float],
        query_units: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        chunk_assets = retrieval_result.get("background_assets") or []
        chunk_missing_indices = set(retrieval_result.get("empty_result_indices") or [])
        chunk_missing_head = retrieval_result.get("missing_head_keywords") or []

        chunk_assets_by_index: Dict[int, Dict[str, Any]] = {}
        for idx, asset in enumerate(chunk_assets):
            if not isinstance(asset, dict):
                continue
            asset_index = self._to_int(asset.get("index"), idx)
            chunk_assets_by_index[asset_index] = asset

        chunk_missing_by_index: Dict[int, Dict[str, Any]] = {}
        for item in chunk_missing_head:
            if not isinstance(item, dict):
                continue
            item_index = self._to_int(item.get("index"), -1)
            if item_index < 0:
                continue
            chunk_missing_by_index[item_index] = item

        units_by_line: Dict[int, List[Dict[str, Any]]] = {}
        for unit in query_units:
            if not isinstance(unit, dict):
                continue
            line_index = self._to_int(unit.get("line_index"), -1)
            if line_index < 0:
                continue
            units_by_line.setdefault(line_index, []).append(unit)

        completed_assets: List[Dict[str, Any]] = []
        scene_missing: List[Dict[str, Any]] = []
        normalized_missing_indices: set[int] = set()

        for index, line in enumerate(lines):
            audio_path = audio_files[index] if index < len(audio_files) else ""
            audio_duration = self._to_float(durations[index], 0.0) if index < len(durations) else 0.0
            line_units = units_by_line.get(index, [])

            selected_asset: Dict[str, Any] | None = None
            selected_score = float("-inf")
            selected_query_text = ""
            missing_keywords: set[str] = set()
            has_missing_chunk = False

            for unit in line_units:
                query_index = self._to_int(unit.get("query_index"), -1)
                if query_index < 0:
                    continue

                if query_index in chunk_missing_indices:
                    has_missing_chunk = True
                missing_item = chunk_missing_by_index.get(query_index)
                if isinstance(missing_item, dict):
                    for keyword in missing_item.get("head_keywords") or []:
                        token = str(keyword).strip()
                        if token:
                            missing_keywords.add(token)

                candidate = chunk_assets_by_index.get(query_index)
                if not isinstance(candidate, dict):
                    continue

                candidate_score = self._to_float(candidate.get("score"), 0.0)
                if candidate_score > selected_score:
                    selected_score = candidate_score
                    selected_asset = candidate
                    selected_query_text = str(unit.get("text") or candidate.get("text") or "").strip()

            if selected_asset:
                item = dict(selected_asset)
                item["index"] = index
                item["text"] = line
                item["query_text"] = selected_query_text or str(item.get("text") or "").strip()
                item["audio_path"] = audio_path
                item["audio_duration"] = audio_duration
                item["media_type"] = self._normalize_media_type(str(item.get("media_type", "")))
                if item["media_type"] == "unknown":
                    item["media_type"] = "color"
                    item["color"] = "#000000"
                    item["source_path"] = ""
                completed_assets.append(item)
            else:
                normalized_missing_indices.add(index)
                completed_assets.append(
                    self._build_black_color_asset(
                        index=index,
                        text=line,
                        audio_path=audio_path,
                        audio_duration=audio_duration,
                    )
                )

            if has_missing_chunk or (index in normalized_missing_indices):
                normalized_missing_indices.add(index)
                scene_missing.append(
                    {
                        "index": index,
                        "text": line,
                        "head_keywords": sorted(missing_keywords),
                    }
                )

        if not scene_missing and normalized_missing_indices:
            scene_missing = [{"index": idx, "text": lines[idx], "head_keywords": []} for idx in sorted(normalized_missing_indices)]

        existing_scene_indices = {self._to_int(item.get("index"), -1) for item in scene_missing if isinstance(item, dict)}
        for idx in sorted(normalized_missing_indices):
            if idx not in existing_scene_indices:
                scene_missing.append({"index": idx, "text": lines[idx], "head_keywords": []})

        retrieval_result["success"] = True
        retrieval_result["chunk_background_assets"] = chunk_assets
        retrieval_result["chunk_empty_result_indices"] = sorted(idx for idx in chunk_missing_indices if idx >= 0)
        retrieval_result["chunk_missing_head_keywords"] = chunk_missing_head
        retrieval_result["background_assets"] = completed_assets
        retrieval_result["empty_result_indices"] = sorted(normalized_missing_indices)
        retrieval_result["missing_head_keywords"] = scene_missing
        return retrieval_result
    def _normalize_storyboard_for_validation(
        self,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        scenes = data.get("scenes") if isinstance(data.get("scenes"), list) else []
        normalized_scenes: List[Dict[str, Any]] = []

        for scene_index, raw_scene in enumerate(scenes):
            if not isinstance(raw_scene, dict):
                continue

            normalized_scene = self._normalize_storyboard_scene_item(raw_scene, scene_index)

            scene_payload: Dict[str, Any] = {
                "scene_id": normalized_scene.get("scene_id") or f"scene_{scene_index + 1:02d}",
                "scene_type": normalized_scene.get("scene_type") or "content",
                "layout_mode": self._normalize_layout_mode(normalized_scene.get("layout_mode")),
                "clear_policy": normalized_scene.get("clear_policy") or "clear_all",
                "nodes": normalized_scene.get("nodes") or [],
                "asset_requirements": normalized_scene.get("asset_requirements") or [],
                "narration_chunks": normalized_scene.get("narration_chunks") or [],
            }

            header_text = str(normalized_scene.get("header_text") or "").strip()
            if header_text:
                scene_payload["header"] = {"text": header_text}

            narration_text = str(normalized_scene.get("narration_text") or "").strip()
            if narration_text:
                scene_payload["narration"] = {"text": narration_text}

            hold_after = self._to_float(normalized_scene.get("hold_after"), 0.0)
            duration_hint = self._to_float(normalized_scene.get("estimated_duration"), 0.0)
            timing_payload: Dict[str, Any] = {}
            if hold_after > 0:
                timing_payload["hold_after"] = hold_after
            if duration_hint > 0:
                timing_payload["duration_hint"] = duration_hint
            if timing_payload:
                scene_payload["timing"] = timing_payload

            transitions = normalized_scene.get("transitions")
            if isinstance(transitions, dict) and transitions:
                scene_payload["transitions"] = transitions

            normalized_scenes.append(scene_payload)

        normalized_data = {
            "version": str(data.get("version") or "mw_storyboard_v1"),
            "video_id": str(data.get("video_id") or "math_retrieval_story").strip() or "math_retrieval_story",
            "lang": str(data.get("lang") or "en"),
            "theme": str(data.get("theme") or ""),
            "metadata": data.get("metadata") or {
                "title": str(data.get("theme") or "Math Retrieval"),
                "subject": "math_story",
                "target_audience": "general",
                "aspect_ratio": "16:9",
            },
            "global_style": data.get("global_style") or {},
            "scenes": normalized_scenes,
        }
        return normalized_data

    def _load_math_retrieval_structure(self, theme: str, model_name: str, api_key: str) -> Dict[str, Any]:
        configured_template_raw = str(get_template_path("math", "en") or "").strip()
        configured_template_path: Optional[Path] = None
        if configured_template_raw:
            configured_template_path = Path(configured_template_raw)
            if not configured_template_path.is_absolute():
                configured_template_path = Path(__file__).resolve().parents[2] / configured_template_path

        default_template_path = Path(__file__).resolve().parents[1] / "assets" / "templates" / "math_en.j2"
        template_path = default_template_path
        if configured_template_path and configured_template_path.is_file():
            template_path = configured_template_path
        if not template_path.is_file():
            raise FileNotFoundError(
                f"math template not found, expected one of: configured={configured_template_path}, default={default_template_path}"
            )

        template_text = template_path.read_text(encoding="utf-8")
        prompt = (
            template_text
            .replace("{THEME}", theme)
            .replace("{{THEME}}", theme)
            .replace("{{ THEME }}", theme)
        )
        generator = LangChainTextGenerator()
        generator.select_model(model_name, api_key)
        try:
            response = generator._invoke_model(prompt)
            raw_content = response["content"] if isinstance(response, dict) else getattr(response, "content", "")
            json_text = self._extract_json_block(raw_content or "")
            if not json_text.strip():
                raise ValueError("math retrieval template output is empty, cannot extract json")

            data = json.loads(json_text)
            if not isinstance(data, dict):
                raise ValueError("math retrieval output is not json object")
            scenes = data.get("scenes")
            if not isinstance(scenes, list) or not scenes:
                raise ValueError("math retrieval storyboard schema invalid: scenes missing or empty")

            try:
                normalized_for_validation = self._normalize_storyboard_for_validation(data)
                ensure_storyboard(normalized_for_validation)
            except StoryboardValidationError as exc:
                detail_lines = []
                for detail in (exc.details or []):
                    loc = detail.get("loc", "")
                    msg = detail.get("msg", "")
                    typ = detail.get("type", "")
                    detail_lines.append(f"loc={loc} type={typ} msg={msg}")
                detail_text = " | ".join(detail_lines[:8])
                if detail_text:
                    raise ValueError(
                        f"math retrieval storyboard schema validation failed: {exc}; details: {detail_text}"
                    ) from exc
                raise ValueError(f"math retrieval storyboard schema validation failed: {exc}") from exc
            return data
        except json.JSONDecodeError as exc:
            raise ValueError(f"math retrieval json parse failed: {exc}") from exc
        finally:
            generator.unload_model()


    def _polish_retrieval_queries(
        self,
        *,
        project_id: str,
        lines: List[str],
        model_name: str,
        api_key: str,
        media_prompt_style: str,
        media_model_name: str = "",
        language: str = "",
        cancel_event=None,
    ) -> List[str]:
        if not lines:
            return []
        textGenerationService.use_model(model_name=model_name, api_key=api_key)
        try:
            full_text = "\n".join(lines)
            polished: List[str] = []
            for idx, line in enumerate(lines):
                if cancel_event and cancel_event.is_set():
                    return []
                line_text = str(line or "").strip()
                if not line_text:
                    polished.append("")
                    continue
                try:
                    polished_prompt = textGenerationService.polish_media_prompts(
                        text=line_text,
                        language=self._get_project_language(project_id, text=line_text, requested_language=language),
                        media_model_name=media_model_name,
                        media_prompt_style=media_prompt_style,
                        texts=full_text,
                    )
                    polished.append(str(polished_prompt or "").strip() or line_text)
                except Exception as exc:
                    logger.warning("polish retrieval prompt failed index=%s: %s", idx, exc)
                    polished.append(line_text)
                update_progress(
                    project_id=project_id,
                    percent=35 + int(20 * (idx + 1) / max(len(lines), 1)),
                    stage=f"正在打磨检索提示词 {idx + 1}/{len(lines)}",
                )
            return polished
        finally:
            textGenerationService.release_model()



    def _collect_leaf_node_dicts(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        leaves: List[Dict[str, Any]] = []

        def _walk(items: List[Dict[str, Any]]):
            for item in items:
                if not isinstance(item, dict):
                    continue
                children = item.get("children") if isinstance(item.get("children"), list) else []
                if children:
                    _walk(children)
                    continue
                leaves.append(item)

        _walk(nodes)
        return leaves

    def _resolve_scene_node_timing(
        self,
        *,
        nodes: List[Dict[str, Any]],
        narration_chunks: List[Dict[str, Any]],
        scene_duration: float,
    ) -> None:
        leaves = self._collect_leaf_node_dicts(nodes)
        if not leaves:
            return

        duration = self._to_float(scene_duration, 0.0)
        if duration <= 0:
            duration = 5.0

        normalized_chunks: List[Dict[str, Any]] = []
        for idx, chunk in enumerate(narration_chunks):
            if not isinstance(chunk, dict):
                continue
            start = max(self._to_float(chunk.get("start"), 0.0), 0.0)
            end = self._to_float(chunk.get("end"), start)
            if end <= start:
                continue
            end = min(end, duration)
            if end <= start:
                continue
            chunk_id = str(chunk.get("chunk_id") or "").strip() or f"chunk_{idx:02d}"
            normalized_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "start": start,
                    "end": end,
                    "duration": end - start,
                }
            )

        if not normalized_chunks:
            normalized_chunks.append({"chunk_id": "chunk_00", "start": 0.0, "end": duration, "duration": duration})

        chunk_by_id = {chunk["chunk_id"]: chunk for chunk in normalized_chunks}

        used_intervals: List[Tuple[float, float]] = []

        def _fit_start_end(start_v: float, end_v: float) -> Tuple[float, float]:
            start = max(start_v, 0.0)
            end = min(max(end_v, start + 0.05), duration)
            if end <= start:
                end = min(duration, start + 0.05)
            for prev_start, prev_end in used_intervals:
                if start < prev_end and end > prev_start:
                    shift = prev_end - start
                    start += shift
                    end += shift
            if end > duration:
                excess = end - duration
                start = max(0.0, start - excess)
                end = duration
            if end <= start:
                end = min(duration, start + 0.05)
            return start, end

        leaf_count = len(leaves)
        fallback_step = duration / max(leaf_count, 1)

        for leaf_idx, leaf in enumerate(leaves):
            timing = leaf.get("timing") if isinstance(leaf.get("timing"), dict) else {}
            align_chunk_id = str(timing.get("align_chunk_id") or "").strip()
            offset_s = self._to_float(timing.get("offset_s"), 0.0)
            start_s_raw = timing.get("start_s")
            end_s_raw = timing.get("end_s")

            target_chunk = chunk_by_id.get(align_chunk_id)
            if target_chunk is None:
                target_chunk = normalized_chunks[min(leaf_idx, len(normalized_chunks) - 1)]

            chunk_start = self._to_float(target_chunk.get("start"), 0.0)
            chunk_end = self._to_float(target_chunk.get("end"), chunk_start)
            chunk_duration = max(chunk_end - chunk_start, 0.05)

            has_explicit_start = start_s_raw is not None
            has_explicit_end = end_s_raw is not None

            if has_explicit_start:
                start_s = self._to_float(start_s_raw, chunk_start)
            else:
                start_s = chunk_start + offset_s

            if has_explicit_end:
                end_s = self._to_float(end_s_raw, start_s + 0.2)
            else:
                suggested = start_s + max(chunk_duration * 0.85, fallback_step * 0.8, 0.2)
                end_s = min(suggested, chunk_end)
                if end_s <= start_s:
                    end_s = start_s + max(min(chunk_duration * 0.8, 0.6), 0.2)

            if not has_explicit_start and start_s < chunk_start:
                start_s = chunk_start
            if not has_explicit_end and end_s > chunk_end:
                end_s = chunk_end

            start_s, end_s = _fit_start_end(start_s, end_s)
            used_intervals.append((start_s, end_s))
            leaf["timing"] = {
                "start_s": round(start_s, 4),
                "end_s": round(end_s, 4),
                "align_chunk_id": target_chunk.get("chunk_id"),
                "offset_s": round(offset_s, 4),
            }

    def _scale_scene_node_timing(self, *, nodes: List[Dict[str, Any]], scale: float, scene_duration: float) -> None:
        if scale <= 0:
            return
        duration = max(self._to_float(scene_duration, 0.0), 0.05)
        for leaf in self._collect_leaf_node_dicts(nodes):
            timing = leaf.get("timing") if isinstance(leaf.get("timing"), dict) else None
            if not timing:
                continue
            start = self._to_float(timing.get("start_s"), 0.0) * scale
            end = self._to_float(timing.get("end_s"), start + 0.05) * scale
            start = max(0.0, min(start, duration))
            end = max(start + 0.05, min(end, duration))
            timing["start_s"] = round(start, 4)
            timing["end_s"] = round(end, 4)

    def _normalize_storyboard_scene_item(
        self,
        raw_scene: Dict[str, Any],
        scene_index: int,
    ) -> Dict[str, Any]:
        scene = dict(raw_scene or {})

        def _pick_text(value: Any) -> str:
            if isinstance(value, dict):
                return str(value.get("text") or "").strip()
            return str(value or "").strip()

        def _truncate_text(value: Any, max_chars: int = 160) -> str:
            text = str(value or "").strip()
            if len(text) <= max_chars:
                return text
            prefix = text[:max_chars]
            cut_points = [prefix.rfind(". "), prefix.rfind("。"), prefix.rfind("!"), prefix.rfind("?")]
            cut = max(cut_points)
            if cut >= int(max_chars * 0.5):
                return prefix[: cut + 1].strip()
            return prefix.rstrip() + "..."

        def _normalize_comparison_box_items(value: Any) -> List[Dict[str, Any]]:
            raw_items = value if isinstance(value, list) else ([] if value is None else [value])
            normalized: List[Dict[str, Any]] = []
            for item in raw_items:
                if len(normalized) >= 3:
                    break
                if isinstance(item, dict):
                    title = str(item.get("title") or item.get("label") or "").strip()
                    body = str(
                        item.get("body")
                        or item.get("description")
                        or item.get("desc")
                        or item.get("text")
                        or ""
                    ).strip()
                    cleaned = {"title": title, "body": body}
                    for key in ("color", "width", "box_width", "box_height", "title_size", "body_size"):
                        if key in item:
                            cleaned[key] = item.get(key)
                    normalized.append(cleaned)
                    continue

                raw = str(item or "").strip()
                if not raw:
                    continue
                if ":" in raw:
                    left, right = raw.split(":", 1)
                    normalized.append({"title": left.strip(), "body": right.strip()})
                else:
                    normalized.append({"title": raw, "body": ""})
            return normalized

        def _normalize_node_timing(value: Any) -> Optional[Dict[str, Any]]:
            if not isinstance(value, dict):
                return None
            start_raw = value.get("start_s", value.get("start"))
            end_raw = value.get("end_s", value.get("end"))
            align_chunk_id = str(value.get("align_chunk_id") or value.get("chunk_id") or "").strip()
            offset_raw = value.get("offset_s")

            normalized: Dict[str, Any] = {}
            if start_raw is not None:
                normalized["start_s"] = max(self._to_float(start_raw, 0.0), 0.0)
            if end_raw is not None:
                normalized["end_s"] = max(self._to_float(end_raw, 0.0), 0.0)
            if align_chunk_id:
                normalized["align_chunk_id"] = align_chunk_id
            if offset_raw is not None:
                normalized["offset_s"] = self._to_float(offset_raw, 0.0)

            if "start_s" in normalized and "end_s" in normalized and normalized["end_s"] <= normalized["start_s"]:
                normalized["end_s"] = normalized["start_s"] + 0.2

            return normalized or None

        allowed_roles = {"primary", "secondary", "note", "remark", "overlay", "caption"}
        allowed_layout_hints = {"vertical", "horizontal", "overlay", "anchor_relative", "auto_grid"}
        allowed_node_types = {
            "title_card",
            "transition_note",
            "formula_focus",
            "axes_curve",
            "number_sequence",
            "comparison_boxes",
            "summary_block",
            "text_label",
            "rich_text_label",
            "relation_map",
            "stat_bar_grid",
            "process_flow",
            "pipeline_chain",
            "terminal_output",
            "space_bridge",
            "group",
            "timeline",
            "state_machine",
            "layer_stack",
            "table_grid",
            "code_panel",
            "callout_panel",
            "concept_map",
            "before_after_panel",
            "memory_grid",
            "address_space",
            "stack_frame_trace",
            "cpu_state",
            "instruction_cycle",
            "array_cells",
            "linked_list",
            "tree_diagram",
        }
        allowed_plot_presets = {"logistic_basic", "exp2", "linear", "unit_circle"}
        node_type_aliases = {
            "flow_chain": "pipeline_chain",
            "process_chain": "pipeline_chain",
            "pipeline_flow": "pipeline_chain",
            "terminal_panel": "terminal_output",
            "console_output": "terminal_output",
            "syscall_bridge": "space_bridge",
            "kernel_user_bridge": "space_bridge",
        }

        def _normalize_role(role_value: Any) -> str:
            raw = str(role_value or "").strip().lower()
            if not raw:
                return "primary"
            role_alias = {
                "left": "secondary",
                "right": "secondary",
                "main": "primary",
                "main_plot": "primary",
                "annotation": "note",
            }
            mapped = role_alias.get(raw, raw)
            return mapped if mapped in allowed_roles else "primary"

        def _normalize_layout_hint(layout_hint_value: Any) -> Optional[str]:
            raw = str(layout_hint_value or "").strip()
            if not raw:
                return None
            return raw if raw in allowed_layout_hints else None

        def _sanitize_node(node_obj: Dict[str, Any], scene_has_header: bool) -> Dict[str, Any]:
            node_type = str(node_obj.get("type") or "text_label").strip()
            node_type = node_type_aliases.get(node_type, node_type)
            if node_type not in allowed_node_types:
                node_type = "text_label"

            raw_params = node_obj.get("params") if isinstance(node_obj.get("params"), dict) else {}
            params = dict(raw_params)

            if scene_has_header:
                params.pop("header_text", None)

            if node_type == "axes_curve":
                preset_name = str(params.get("preset_name") or "").strip()
                if preset_name and not params.get("preset"):
                    params["preset"] = preset_name
                params.pop("preset_name", None)

                plot_kind = str(params.get("plot_kind") or "expression").strip().lower()
                if plot_kind not in {"expression", "preset"}:
                    plot_kind = "expression"
                params["plot_kind"] = plot_kind

                if plot_kind == "preset":
                    preset = str(params.get("preset") or "").strip()
                    if preset not in allowed_plot_presets:
                        note_text = str(params.get("note") or "").lower()
                        formula_text = str(params.get("formula_tex") or "").lower()
                        x_label_text = str(params.get("x_label_text") or "").lower()
                        y_label_text = str(params.get("y_label_text") or "").lower()
                        should_use_unit_circle = any(
                            token in (note_text + " " + formula_text)
                            for token in ("unit circle", "e^{i", "e^i", "theta", "\\theta", "pi", "\\pi")
                        ) or (
                            "real" in x_label_text and "imag" in y_label_text
                        )
                        params["preset"] = "unit_circle" if should_use_unit_circle else "exp2"
                    params.pop("expression", None)

            if node_type == "formula_focus":
                latex = params.get("latex")
                formula_tex = params.get("formula_tex")
                if latex and not formula_tex:
                    params["formula_tex"] = latex
                params.pop("latex", None)
                params.pop("highlight_parts", None)

            if node_type == "summary_block":
                points = params.get("points")
                summary_lines = params.get("summary_lines")
                if isinstance(points, list) and not isinstance(summary_lines, list):
                    params["summary_lines"] = [str(x) for x in points if str(x).strip()]
                params.pop("points", None)
                title = str(params.pop("title", "") or "").strip()
                if title and not params.get("footer_text"):
                    params["footer_text"] = title

            if node_type == "comparison_boxes":
                params["items"] = _normalize_comparison_box_items(params.get("items"))

            if "note" in params:
                params["note"] = _truncate_text(params.get("note"), max_chars=140)
            if "remark" in params:
                params["remark"] = _truncate_text(params.get("remark"), max_chars=140)

            sanitized_children: List[Dict[str, Any]] = []
            raw_children = node_obj.get("children") if isinstance(node_obj.get("children"), list) else []
            for child in raw_children:
                if not isinstance(child, dict):
                    continue
                sanitized_children.append(_sanitize_node(child, scene_has_header=scene_has_header))

            cleaned_node: Dict[str, Any] = {
                "key": str(node_obj.get("key") or "").strip() or f"scene_{scene_index}_node_{len(sanitized_children)}",
                "type": node_type,
                "role": _normalize_role(node_obj.get("role")),
                "params": params,
            }
            layout_hint = _normalize_layout_hint(node_obj.get("layout_hint"))
            if layout_hint:
                cleaned_node["layout_hint"] = layout_hint
            node_timing = _normalize_node_timing(node_obj.get("timing"))
            if node_timing:
                cleaned_node["timing"] = node_timing
            if sanitized_children:
                cleaned_node["children"] = sanitized_children
            return cleaned_node

        scene_id = str(scene.get("scene_id") or f"scene_{scene_index + 1:02d}").strip()
        scene_type = str(scene.get("scene_type") or "content").strip() or "content"
        layout_mode = self._normalize_layout_mode(scene.get("layout_mode"))
        clear_policy = str(scene.get("clear_policy") or "clear_all").strip() or "clear_all"

        header_text = _pick_text(scene.get("header"))
        narration_text = _pick_text(scene.get("narration"))
        narration_text_plain = self._strip_inline_formula_markers(narration_text)

        timing = scene.get("timing") if isinstance(scene.get("timing"), dict) else {}
        duration_hint = self._to_float(timing.get("duration_hint"), 0.0)
        hold_after = self._to_float(timing.get("hold_after"), 0.0)
        if hold_after <= 0:
            hold_after = 2.5

        raw_nodes = scene.get("nodes") if isinstance(scene.get("nodes"), list) else []
        scene_duration = duration_hint if duration_hint > 0 else max(hold_after, 5.0)
        sanitized_nodes: List[Dict[str, Any]] = []
        for node in raw_nodes:
            if not isinstance(node, dict):
                continue
            sanitized_nodes.append(_sanitize_node(node, scene_has_header=bool(header_text)))

        def _count_leaf_nodes(node_list: List[Dict[str, Any]]) -> int:
            count = 0
            for item in node_list:
                children = item.get("children") if isinstance(item.get("children"), list) else []
                if children:
                    count += _count_leaf_nodes(children)
                else:
                    count += 1
            return count

        minimum_leaf_nodes = 2
        existing_leaf_nodes = _count_leaf_nodes(sanitized_nodes)
        if existing_leaf_nodes < minimum_leaf_nodes:
            fallback_text = _truncate_text(narration_text_plain or header_text or "Key takeaway", max_chars=120)
            needed = minimum_leaf_nodes - existing_leaf_nodes
            for idx in range(needed):
                sanitized_nodes.append(
                    {
                        "key": f"scene_{scene_index}_auto_note_{idx}",
                        "type": "text_label",
                        "role": "note",
                        "params": {
                            "text": fallback_text,
                        },
                        "timing": {
                            "start_s": 0.0,
                            "end_s": max(scene_duration * 0.55, 0.6),
                        },
                    }
                )

        # line = narration_text_plain or header_text
        # if header_text and narration_text_plain:
        #     line = f"{header_text}：{narration_text_plain}"
        line = narration_text_plain

        # shot_text_parts = [header_text, narration_text_plain]
        shot_text_parts = [narration_text_plain]
        for node in sanitized_nodes:
            params = node.get("params") if isinstance(node.get("params"), dict) else {}
            if node.get("type") == "formula_focus":
                formula_text = str(params.get("formula_tex") or "").strip()
                if formula_text:
                    shot_text_parts.append(formula_text)
            elif node.get("type") == "summary_block":
                for x in params.get("summary_lines") or []:
                    text = str(x or "").strip()
                    if text:
                        shot_text_parts.append(text)
            elif node.get("type") == "comparison_boxes":
                for box in params.get("items") or []:
                    if not isinstance(box, dict):
                        continue
                    title = str(box.get("title") or "").strip()
                    body = str(box.get("body") or "").strip()
                    if title:
                        shot_text_parts.append(title)
                    if body:
                        shot_text_parts.append(body)

        shot_text = " ".join(x for x in shot_text_parts if x).strip() or line

        raw_chunks = scene.get("narration_chunks") if isinstance(scene.get("narration_chunks"), list) else []
        narration_chunks: List[Dict[str, Any]] = []
        for chunk_index, chunk in enumerate(raw_chunks):
            if not isinstance(chunk, dict):
                continue
            text = self._strip_inline_formula_markers(chunk.get("text") or "")
            if not text:
                continue
            start = max(self._to_float(chunk.get("start"), 0.0), 0.0)
            end = self._to_float(chunk.get("end"), start)
            if end <= start:
                continue
            chunk_id = str(chunk.get("chunk_id") or "").strip() or f"chunk_{chunk_index:02d}"
            narration_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": text,
                    "start": start,
                    "end": end,
                }
            )

        if not narration_chunks:
            fallback_text = narration_text_plain or line
            if fallback_text:
                narration_chunks.append(
                    {
                        "chunk_id": "chunk_00",
                        "text": fallback_text,
                        "start": 0.0,
                        "end": scene_duration,
                    }
                )

        if narration_chunks:
            raw_durations = []
            for chunk in narration_chunks:
                d = self._to_float(chunk.get("end"), 0.0) - self._to_float(chunk.get("start"), 0.0)
                raw_durations.append(max(d, 0.0))
            if sum(raw_durations) <= 0:
                total_chars = sum(max(len(str(chunk.get("text") or "").strip()), 1) for chunk in narration_chunks)
                raw_durations = [scene_duration * (max(len(str(chunk.get("text") or "").strip()), 1) / max(total_chars, 1)) for chunk in narration_chunks]
            scale = scene_duration / max(sum(raw_durations), 1e-6)
            cursor = 0.0
            for idx, chunk in enumerate(narration_chunks):
                duration = max(raw_durations[idx] * scale, 0.0)
                chunk["start"] = round(cursor, 4)
                chunk["end"] = round(cursor + duration, 4)
                cursor += duration

        self._resolve_scene_node_timing(
            nodes=sanitized_nodes,
            narration_chunks=narration_chunks,
            scene_duration=scene_duration,
        )

        normalized_scene = {
            "scene_index": scene_index,
            "scene_id": scene_id,
            "scene_type": scene_type,
            "layout_mode": layout_mode,
            "clear_policy": clear_policy,
            "header_text": header_text,
            "narration_text": narration_text,
            "line": line,
            "shot_text": shot_text,
            "estimated_duration": scene_duration,
            "hold_after": hold_after,
            "narration_chunks": narration_chunks,
            "nodes": sanitized_nodes,
            "transitions": scene.get("transitions") if isinstance(scene.get("transitions"), dict) else None,
            "asset_requirements": scene.get("asset_requirements") if isinstance(scene.get("asset_requirements"), list) else [],
            "raw_scene": scene,
        }
        return normalized_scene


    def _compile_storyboard_scene_script(
        self,
        *,
        normalized_scene: Dict[str, Any],
        storyboard_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        storyboard_data = storyboard_data or {}

        scene_payload: Dict[str, Any] = {
            "scene_id": str(normalized_scene.get("scene_id") or "scene_01"),
            "scene_type": str(normalized_scene.get("scene_type") or "content"),
            "layout_mode": self._normalize_layout_mode(normalized_scene.get("layout_mode")),
            "clear_policy": str(normalized_scene.get("clear_policy") or "clear_all"),
            "nodes": normalized_scene.get("nodes") or [],
            "asset_requirements": normalized_scene.get("asset_requirements") or [],
            "narration_chunks": normalized_scene.get("narration_chunks") or [],
        }

        header_text = str(normalized_scene.get("header_text") or "").strip()
        if header_text:
            scene_payload["header"] = {"text": header_text}

        narration_text = str(normalized_scene.get("narration_text") or "").strip()
        if narration_text:
            scene_payload["narration"] = {"text": narration_text}

        scene_timing: Dict[str, Any] = {}
        duration_hint = self._to_float(normalized_scene.get("estimated_duration"), 0.0)
        hold_after = self._to_float(normalized_scene.get("hold_after"), 0.0)
        if duration_hint > 0:
            scene_timing["duration_hint"] = duration_hint
        if hold_after > 0:
            scene_timing["hold_after"] = hold_after
        if scene_timing:
            scene_payload["timing"] = scene_timing

        transitions = normalized_scene.get("transitions")
        if isinstance(transitions, dict) and transitions:
            scene_payload["transitions"] = transitions

        storyboard_payload: Dict[str, Any] = {
            "version": str(storyboard_data.get("version") or "mw_storyboard_v1"),
            "video_id": str(storyboard_data.get("video_id") or "math_retrieval_story").strip() or "math_retrieval_story",
            "lang": str(storyboard_data.get("lang") or "en"),
            "theme": str(storyboard_data.get("theme") or ""),
            "metadata": storyboard_data.get("metadata")
            or {
                "title": str(storyboard_data.get("theme") or "Math Retrieval"),
                "subject": "math_story",
                "target_audience": "general",
                "aspect_ratio": "16:9",
            },
            "global_style": storyboard_data.get("global_style") or {},
            "scenes": [scene_payload],
        }

        return emit_python_script(storyboard_payload)

    def _build_math_retrieval_line_items(
        self,
        scenes: List[Dict[str, Any]],
        storyboard_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        storyboard_data = storyboard_data or {}

        for scene_index, raw_scene in enumerate(scenes or []):
            if not isinstance(raw_scene, dict):
                continue

            normalized_scene = self._normalize_storyboard_scene_item(raw_scene, scene_index)
            line = str(normalized_scene.get("line") or "").strip()
            shot_text = str(normalized_scene.get("shot_text") or "").strip()

            if not line and not shot_text:
                continue

            item_type = "scene"
            if normalized_scene.get("scene_type") == "transition" and not normalized_scene.get("nodes"):
                item_type = "line"

            scene_script = ""
            if item_type == "scene":
                try:
                    scene_script = self._compile_storyboard_scene_script(
                        storyboard_data=storyboard_data,
                        normalized_scene=normalized_scene,
                    )
                except Exception as exc:
                    raise ValueError(
                        f"compile storyboard scene failed at index={scene_index}, "
                        f"scene_id={normalized_scene.get('scene_id')}: {exc}"
                    ) from exc

            items.append(
                {
                    "type": item_type,
                    "scene_index": normalized_scene.get("scene_index", scene_index),
                    "scene_id": normalized_scene.get("scene_id", ""),
                    "scene_type": normalized_scene.get("scene_type", "content"),
                    "layout_mode": self._normalize_layout_mode(normalized_scene.get("layout_mode")),
                    "header": normalized_scene.get("header_text", ""),
                    "line": line,
                    "shot_text": shot_text or line,
                    "estimated_duration": self._to_float(normalized_scene.get("estimated_duration"), 5.0) or 5.0,
                    "narration_chunks": normalized_scene.get("narration_chunks") or [],
                    "scene_script": scene_script,
                    "asset_requirements": normalized_scene.get("asset_requirements") or [],
                    "normalized_scene": normalized_scene,
                }
            )

        return items

    def _build_resolved_storyboard_data(
        self,
        *,
        storyboard_data: Dict[str, Any],
        line_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        resolved_scenes: List[Dict[str, Any]] = []
        for idx, item in enumerate(line_items):
            normalized_scene = item.get("normalized_scene") if isinstance(item.get("normalized_scene"), dict) else {}
            scene_payload: Dict[str, Any] = {
                "scene_id": str(normalized_scene.get("scene_id") or f"scene_{idx + 1:02d}"),
                "scene_type": str(normalized_scene.get("scene_type") or "content"),
                "layout_mode": self._normalize_layout_mode(normalized_scene.get("layout_mode")),
                "clear_policy": str(normalized_scene.get("clear_policy") or "clear_all"),
                "nodes": normalized_scene.get("nodes") or [],
                "asset_requirements": normalized_scene.get("asset_requirements") or [],
                "narration_chunks": normalized_scene.get("narration_chunks") or [],
            }

            header_text = str(normalized_scene.get("header_text") or "").strip()
            if header_text:
                scene_payload["header"] = {"text": header_text}

            narration_text = str(normalized_scene.get("narration_text") or "").strip()
            if narration_text:
                scene_payload["narration"] = {"text": narration_text}

            transitions = normalized_scene.get("transitions")
            if isinstance(transitions, dict) and transitions:
                scene_payload["transitions"] = transitions

            duration_hint = self._to_float(normalized_scene.get("estimated_duration"), 0.0)
            hold_after = self._to_float(normalized_scene.get("hold_after"), 0.0)
            timing_payload: Dict[str, Any] = {}
            if duration_hint > 0:
                timing_payload["duration_hint"] = round(duration_hint, 4)
            if hold_after > 0:
                timing_payload["hold_after"] = round(hold_after, 4)
            if timing_payload:
                scene_payload["timing"] = timing_payload

            resolved_scenes.append(scene_payload)

        return {
            "version": str(storyboard_data.get("version") or "mw_storyboard_v1"),
            "video_id": str(storyboard_data.get("video_id") or "math_retrieval_story").strip() or "math_retrieval_story",
            "lang": str(storyboard_data.get("lang") or "en"),
            "theme": str(storyboard_data.get("theme") or ""),
            "metadata": storyboard_data.get("metadata")
            or {
                "title": str(storyboard_data.get("theme") or "Math Retrieval"),
                "subject": "math_story",
                "target_audience": "general",
                "aspect_ratio": "16:9",
            },
            "global_style": storyboard_data.get("global_style") or {},
            "scenes": resolved_scenes,
        }
    def _prepare_math_retrieval_project(
        self,
        project_id: str,
        *,
        text_model_name: str,
        text_api_key: str,
        audio_model_name: str,
        audio_api_key: str,
        voice: str,
        theme: str,
        with_media_prompts: bool = True,
        media_prompt_style: str = "retrieval_default",
        media_model_name: str = "",
        language: str = "",
        cancel_event=None,
    ) -> Dict[str, Any]:
        task_data = TASKS.setdefault(project_id, {})
        math_data = self._load_math_retrieval_structure(theme, text_model_name, text_api_key)
        scenes = math_data.get("scenes") or []
        line_items = self._build_math_retrieval_line_items(scenes, storyboard_data=math_data)
        if not line_items:
            return {"success": False, "error": "math 高级结构未生成有效讲解行"}

        lines = [item.get("line", "") for item in line_items]
        shot_texts = [item.get("shot_text", "") for item in line_items]
        retrieval_query_units = self._build_math_retrieval_query_units(line_items=line_items, durations=[])
        retrieval_texts = [str(unit.get("text") or "").strip() for unit in retrieval_query_units if str(unit.get("text") or "").strip()]
        retrieval_prompt_texts = list(retrieval_texts)
        full_text = "\n".join(lines)
        if with_media_prompts:
            polished = self._polish_retrieval_queries(
                project_id=project_id,
                lines=retrieval_texts,
                model_name=text_model_name,
                api_key=text_api_key,
                media_prompt_style=media_prompt_style or self._get_project_config_value(project_id, "media_prompt_style", "retrieval_default"),
                media_model_name=media_model_name or self._get_project_config_value(project_id, "image_model_name", ""),
                language=language,
                cancel_event=cancel_event,
            )
            if cancel_event and cancel_event.is_set():
                return {"success": False, "cancelled": True}
            if polished:
                retrieval_prompt_texts = polished

        for idx, unit in enumerate(retrieval_query_units):
            if idx < len(retrieval_prompt_texts):
                unit["text"] = str(retrieval_prompt_texts[idx] or "").strip() or str(unit.get("text") or "").strip()
        retrieval_texts = [str(unit.get("text") or "").strip() for unit in retrieval_query_units if str(unit.get("text") or "").strip()]

        set_progress_data(project_id=project_id, key="text", data=full_text)
        set_progress_data(project_id=project_id, key="lines", data=lines)
        set_progress_data(project_id=project_id, key="prompts", data=retrieval_texts)
        set_progress_data(project_id=project_id, key="shot_texts", data=shot_texts)
        set_progress_data(project_id=project_id, key="retrieval_texts", data=retrieval_texts)
        resolved_structure = self._build_resolved_storyboard_data(storyboard_data=math_data, line_items=line_items)
        set_progress_data(project_id=project_id, key="math_retrieval_structure", data=resolved_structure)

        self._write_artifact_text(project_id, "math_retrieval", "generated_text.txt", full_text, key="generated_text")
        self._write_artifact_json(project_id, "math_retrieval", "structure.json", math_data, key="structure_json")
        self._write_artifact_json(project_id, "math_retrieval", "structure_resolved.json", resolved_structure, key="structure_resolved_json")

        audio_result = self._gen_audios(
            project_id=project_id,
            lines=lines,
            model_name=audio_model_name,
            api_key=audio_api_key,
            voice=voice,
            cancel_event=cancel_event,
        )
        if audio_result.get("cancelled"):
            return {"success": False, "cancelled": True}
        if not audio_result.get("success"):
            return {"success": False, "error": audio_result.get("error") or "音频生成失败"}

        audio_files = audio_result.get("audios") or []
        durations = audio_result.get("durations") or []
        for line_index, item in enumerate(line_items):
            normalized_scene = item.get("normalized_scene") if isinstance(item.get("normalized_scene"), dict) else None
            if normalized_scene is None:
                continue
            audio_duration = self._to_float(durations[line_index] if line_index < len(durations) else item.get("estimated_duration"), 0.0)
            estimated_duration = self._to_float(item.get("estimated_duration"), 0.0)
            if estimated_duration <= 0 or audio_duration <= 0:
                continue

            scale = audio_duration / estimated_duration
            normalized_scene["estimated_duration"] = audio_duration

            hold_after = self._to_float(normalized_scene.get("hold_after"), 0.0)
            if hold_after > 0:
                normalized_scene["hold_after"] = round(hold_after * scale, 4)
                if line_index < len(durations):
                    durations[line_index] = round(durations[line_index] + normalized_scene["hold_after"], 4)

            chunks = normalized_scene.get("narration_chunks") if isinstance(normalized_scene.get("narration_chunks"), list) else []
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                start = self._to_float(chunk.get("start"), 0.0) * scale
                end = self._to_float(chunk.get("end"), start) * scale
                chunk["start"] = round(max(start, 0.0), 4)
                chunk["end"] = round(max(end, chunk["start"]), 4)

            nodes = normalized_scene.get("nodes") if isinstance(normalized_scene.get("nodes"), list) else []
            self._scale_scene_node_timing(nodes=nodes, scale=scale, scene_duration=audio_duration)

        resolved_structure = self._build_resolved_storyboard_data(storyboard_data=math_data, line_items=line_items)
        set_progress_data(project_id=project_id, key="math_retrieval_structure", data=resolved_structure)
        self._write_artifact_json(project_id, "math_retrieval", "structure_resolved.json", resolved_structure, key="structure_resolved_json")

        retrieval_query_units = self._build_math_retrieval_query_units(line_items=line_items, durations=durations)
        for idx, unit in enumerate(retrieval_query_units):
            if idx < len(retrieval_prompt_texts):
                unit["text"] = str(retrieval_prompt_texts[idx] or "").strip() or str(unit.get("text") or "").strip()
        retrieval_texts = [str(unit.get("text") or "").strip() for unit in retrieval_query_units if str(unit.get("text") or "").strip()]
        retrieval_query_durations = [self._to_float(unit.get("duration"), 0.0) for unit in retrieval_query_units]
        if len(retrieval_query_durations) < len(retrieval_texts):
            retrieval_query_durations.extend([5.0] * (len(retrieval_texts) - len(retrieval_query_durations)))
        elif len(retrieval_query_durations) > len(retrieval_texts):
            retrieval_query_durations = retrieval_query_durations[: len(retrieval_texts)]
        set_progress_data(project_id=project_id, key="audios", data=audio_files)
        set_progress_data(project_id=project_id, key="durations", data=durations)
        set_progress_data(project_id=project_id, key="retrieval_chunk_units", data=retrieval_query_units)
        set_progress_data(project_id=project_id, key="retrieval_chunk_durations", data=retrieval_query_durations)

        scene_segment_files: List[str] = []
        line_foreground_layers: List[str] = []
        scene_script_files: List[str] = []
        scene_scripts: List[str] = []
        for line_index, item in enumerate(line_items):
            if cancel_event and cancel_event.is_set():
                return {"success": False, "cancelled": True}
            if item.get("type") != "scene":
                line_foreground_layers.append("")
                continue

            scene_script = ""
            normalized_scene = item.get("normalized_scene") if isinstance(item.get("normalized_scene"), dict) else None
            if normalized_scene is not None:
                try:
                    scene_script = self._compile_storyboard_scene_script(
                        storyboard_data=math_data,
                        normalized_scene=normalized_scene,
                    )
                except Exception as exc:
                    return {
                        "success": False,
                        "error": f"math structure scene {item.get('scene_index', line_index)} recompile failed: {exc}",
                    }
            if not scene_script:
                scene_script = str(item.get("scene_script") or "").strip()
            if scene_script.startswith("```"):
                parts = scene_script.split("```")
                if len(parts) >= 2:
                    scene_script = parts[1]
                    if scene_script.startswith("python"):
                        scene_script = scene_script[len("python"):].lstrip()
            scene_script = self._normalize_generated_manim_script(scene_script)
            if not scene_script:
                return {
                    "success": False,
                    "error": f"math structure scene {item.get('scene_index', line_index)} script is empty",
                }

            target_duration = self._to_float(
                durations[line_index] if line_index < len(durations) else item.get("estimated_duration"),
                self._to_float(item.get("estimated_duration"), 0.0),
            )
            if target_duration > 0 and "fade_out_all(" in scene_script:
                scene_script = re.sub(
                    r"fade_out_all\(\s*self\s*,\s*run_time\s*=\s*[^\)]*\)",
                    "fade_out_all(self, run_time=max(0.6, min(1.0, target_duration * 0.12)))",
                    scene_script,
                )
                scene_script = re.sub(
                    r"(def\s+construct\(self\):\n)",
                    r"\1        target_duration = " + f"{target_duration:.3f}" + "\n",
                    scene_script,
                    count=1,
                )

            script_rel = self._write_math_retrieval_scene_script(project_id, len(scene_segment_files), scene_script)

            rendered = self._render_math_retrieval_scene_script(project_id, len(scene_segment_files), script_rel)
            scene_scripts.append(scene_script)
            scene_script_files.append(script_rel)
            scene_segment_files.append(rendered)
            line_foreground_layers.append(rendered)

        set_progress_data(project_id=project_id, key="math_scripts", data=scene_scripts)
        set_progress_data(project_id=project_id, key="math_script_files", data=scene_script_files)
        set_progress_data(project_id=project_id, key="scene_segment_files", data=scene_segment_files)
        set_progress_data(project_id=project_id, key="math_animations", data=line_foreground_layers)
        set_progress_data(project_id=project_id, key="math_animations_dir", data=str(self._project_dir(project_id) / "math_retrieval_segments").replace("\\", "/"))

        task_data["scene_segment_files"] = scene_segment_files
        task_data["shot_texts"] = shot_texts
        task_data["retrieval_texts"] = retrieval_texts
        task_data["retrieval_chunk_units"] = retrieval_query_units
        task_data["retrieval_chunk_durations"] = retrieval_query_durations

        return {
            "success": True,
            "text": full_text,
            "lines": lines,
            "shot_texts": shot_texts,
            "retrieval_texts": retrieval_texts,
            "retrieval_query_units": retrieval_query_units,
            "retrieval_query_durations": retrieval_query_durations,
            "audio_files": audio_files,
            "durations": durations,
            "scene_segment_files": scene_segment_files,
            "line_foreground_layers": line_foreground_layers,
            "line_items": line_items,
            "math_structure": resolved_structure,
        }

    def _render_retrieval_video_clip(
        self,
        source_path: str,
        audio_path: str,
        duration: float,
        clip_path: Path,
        fps: int = 30,
        start_sec: Optional[float] = None,
        end_sec: Optional[float] = None,
    ):
        if duration <= 0:
            duration = 5.0

        clip_start = 0.0
        clip_end: Optional[float] = None
        try:
            if start_sec is not None:
                clip_start = max(float(start_sec), 0.0)
        except (TypeError, ValueError):
            clip_start = 0.0
        try:
            if end_sec is not None:
                parsed_end = float(end_sec)
                if parsed_end > clip_start:
                    clip_end = parsed_end
        except (TypeError, ValueError):
            clip_end = None

        input_options: Dict[str, Any] = {}
        if clip_start > 0:
            input_options["ss"] = clip_start
        if clip_end is None:
            input_options["stream_loop"] = -1

        video_input = ffmpeg.input(source_path, **input_options)
        audio_input = ffmpeg.input(audio_path)
        render_started_at = time()
        logger.info(
            "[retrieval] render_clip_start media_type=video duration=%.2f start=%.3f end=%s source=%s audio=%s output=%s",
            duration,
            clip_start,
            f"{clip_end:.3f}" if clip_end is not None else "",
            self._short_media_path(source_path),
            self._short_media_path(audio_path),
            self._short_media_path(str(clip_path)),
        )
        try:
            window_len = (clip_end - clip_start) if clip_end is not None else 0.0
            window_len = max(window_len, 0.01) if clip_end is not None else 0.0
            speed_factor = 1.0
            if window_len > 0 and window_len < duration:
                speed_factor = max(window_len / duration, 0.01)

            video_stream = video_input.video.filter("scale", 1280, 720)
            if clip_end is not None:
                video_stream = video_stream.filter("trim", start=0, duration=window_len).filter("setpts", "PTS-STARTPTS")
            if speed_factor < 0.999:
                video_stream = video_stream.filter("setpts", f"PTS/{speed_factor}")
            video_stream = (
                video_stream
                .filter("fps", fps=fps)
                .filter("trim", duration=duration)
                .filter("setpts", "PTS-STARTPTS")
            )
            logger.info("[retrieval] render_clip_speed window_len=%.2f duration=%.2f speed_factor=%.4f", window_len, duration, speed_factor)

            ffmpeg_cmd = ffmpeg.output(
                video_stream,
                audio_input.audio.filter("atrim", duration=duration).filter("asetpts", "PTS-STARTPTS"),
                str(clip_path),
                vcodec="libx264",
                preset="ultrafast",
                pix_fmt="yuv420p",
                r=fps,
                acodec="aac",
                t=duration,
                shortest=None,
            ).overwrite_output()
            logger.info("[retrieval] render_clip_profile profile=low_cpu scale=1280x720 preset=ultrafast fps=%s", fps)
            clip_timeout = max(60, int(duration * 20))
            logger.info("[retrieval] render_clip_timeout timeout=%ss", clip_timeout)
            self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=clip_timeout)
            logger.info(
                "[retrieval] render_clip_done media_type=video elapsed=%.2fs output=%s",
                time() - render_started_at,
                self._short_media_path(str(clip_path)),
            )
        except ffmpeg.Error as e:
            stderr = e.stderr.decode("utf-8", errors="ignore") if getattr(e, "stderr", None) else ""
            logger.error(
                "检索视频素材渲染失败 source=%s audio=%s start=%.3f end=%s clip=%s elapsed=%.2fs stderr=%s",
                source_path,
                audio_path,
                clip_start,
                f"{clip_end:.3f}" if clip_end is not None else "",
                clip_path,
                time() - render_started_at,
                stderr,
            )
            raise
        return str(clip_path).replace("\\", "/")

    def _short_media_path(self, value: str) -> str:
        if not value:
            return ""
        normalized = value.replace("\\", "/")
        return normalized if len(normalized) <= 160 else f"...{normalized[-160:]}"

    def _log_retrieval_clip_start(self, project_id: str, index: int, total: int, clip: Dict[str, Any], clip_path: Path):
        logger.info(
            "[retrieval] project=%s clip=%s/%s media_type=%s duration=%.2f source=%s audio=%s output=%s",
            project_id,
            index + 1,
            total,
            clip.get("media_type", ""),
            float(clip.get("duration") or 0) or 0.0,
            self._short_media_path(str(clip.get("source_path") or clip.get("image_path") or "")),
            self._short_media_path(str(clip.get("audio_path") or "")),
            self._short_media_path(str(clip_path)),
        )

    def _log_retrieval_clip_done(self, project_id: str, index: int, total: int, rendered_path: str):
        logger.info(
            "[retrieval] project=%s clip=%s/%s done output=%s",
            project_id,
            index + 1,
            total,
            self._short_media_path(rendered_path),
        )

    def _log_retrieval_concat_start(self, project_id: str, total: int, output_path: str):
        logger.info(
            "[retrieval] project=%s concat_start clips=%s output=%s",
            project_id,
            total,
            self._short_media_path(output_path),
        )

    def _log_retrieval_finalize_done(self, project_id: str, final_video_path: str):
        logger.info(
            "[retrieval] project=%s finalize_done output=%s",
            project_id,
            self._short_media_path(final_video_path),
        )

    def _render_color_background_clip(
        self,
        *,
        color: str,
        audio_path: str,
        duration: float,
        clip_path: Path,
        fps: int = 30,
    ) -> str:
        if duration <= 0:
            duration = 5.0
        ff_color = (color or "#000000").strip() or "#000000"
        video_stream = ffmpeg.input(
            f"color=c={ff_color}:s=1280x720:r={fps}:d={duration}",	            f="lavfi",
        ).video
        audio_stream = ffmpeg.input(audio_path).audio.filter("atrim", duration=duration).filter("asetpts", "PTS-STARTPTS")
        ffmpeg_cmd = ffmpeg.output(
            video_stream,
            audio_stream,
            str(clip_path),
            vcodec="libx264",
            preset="ultrafast",
            pix_fmt="yuv420p",
            acodec="aac",
            r=fps,
            t=duration,
            shortest=None,
        ).overwrite_output()
        clip_timeout = max(45, int(duration * 12))
        self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=clip_timeout)
        return str(clip_path).replace("\\", "/")
    
    def _render_retrieval_asset_clip(self, clip: Dict[str, Any], clip_path: Path):
        source_path = clip.get("source_path") or clip.get("image_path", "")
        media_type = self._normalize_media_type(str(clip.get("media_type") or ""))
        audio_path = clip.get("audio_path", "")
        duration = float(clip.get("duration") or 0)
        if duration <= 0:
            duration = 5.0
        if not self._is_valid_media_file(audio_path):
            raise FileNotFoundError(f"检索片段缺少有效音频文件: {audio_path}")
        try:
            if media_type == "image":
                if not self._is_valid_media_file(source_path):
                    raise FileNotFoundError(f"检索素材缺少有效文件: {source_path}")
                return self._render_story_style_clip(source_path, audio_path, duration, clip_path)
            if media_type == "video":
                if not self._is_valid_media_file(source_path):
                    raise FileNotFoundError(f"检索素材缺少有效文件: {source_path}")
                start_sec = clip.get("start_sec")
                end_sec = clip.get("end_sec")
                return self._render_retrieval_video_clip(
                    source_path,
                    audio_path,
                    duration,
                    clip_path,
                    start_sec=start_sec,
                    end_sec=end_sec,
                )
            if media_type == "color":
                color_value = str(clip.get("color") or "#000000")
                return self._render_color_background_clip(
                    color=color_value,
                    audio_path=audio_path,
                    duration=duration,
                    clip_path=clip_path,
                )
        except ffmpeg.Error as e:
            stderr = e.stderr.decode("utf-8", errors="ignore") if getattr(e, "stderr", None) else ""
            logger.error("检索素材片段渲染失败 media_type=%s source=%s audio=%s clip=%s stderr=%s", media_type, source_path, audio_path, clip_path, stderr)
            raise
        raise ValueError(f"不支持的检索素材类型: {media_type or 'unknown'}")


    def _build_retrieval_video(self, project_id: str, lines: list, background_assets: list, audio_files: list, durations: list):
        if not background_assets:
            raise ValueError("检索素材为空，无法生成视频")
        pdir = self.base_dir / project_id
        task_data = TASKS.setdefault(project_id, {})
        output_path = os.path.join(pdir, f"final_{int(time())}.mp4")
        segments_dir = self._prepare_fresh_output_dir(self._video_segments_mode_dir(project_id, "retrieval"))
        clips = []
        segment_paths = []
        image_paths = []

        emit_progress_status(project_id, "in_video_progress", "正在生成检索视频片段", 78)
        total = len(background_assets)
        logger.info("[retrieval] project=%s render_start total=%s", project_id, total)
        for index, asset in enumerate(background_assets):
            clip = {
                "index": asset.get("index", index),
                "clip_path": "",
                "image_path": asset.get("source_path", "") if asset.get("media_type") == "image" else "",
                "audio_path": audio_files[index] if index < len(audio_files) else asset.get("audio_path", ""),
                "duration": durations[index] if index < len(durations) else asset.get("audio_duration", 0),
                "prompt": "",
                "text": asset.get("text", lines[index] if index < len(lines) else ""),
                "dirty": False,
                "script": "",
                "script_file": "",
                "math_animation_path": "",
                "source_path": asset.get("source_path", ""),
                "media_type": asset.get("media_type", ""),
                "annotation_path": asset.get("annotation_path", ""),
                "start_sec": asset.get("start_sec"),
                "end_sec": asset.get("end_sec"),
                "score": asset.get("score", 0.0),
            }
            clip_path = segments_dir / f"clip_{index:04d}.mp4"
            self._log_retrieval_clip_start(project_id, index, total, clip, clip_path)
            rendered_path = self._render_retrieval_asset_clip(clip, clip_path)
            self._log_retrieval_clip_done(project_id, index, total, rendered_path)
            clip["clip_path"] = rendered_path
            clips.append(clip)
            segment_paths.append(rendered_path)
            image_paths.append(clip["image_path"])
            update_progress(project_id, 78 + int(10 * (index + 1) / max(total, 1)), f"正在生成第{index + 1}/{total}个检索视频段")

        self._log_retrieval_concat_start(project_id, len(segment_paths), output_path)

        for index, asset in enumerate(background_assets):
            if index < len(clips):
                asset["clip_path"] = clips[index].get("clip_path", "")
        task_data["images"] = image_paths
        task_data["clips"] = clips
        self._set_video_artifact_metadata(
            project_id,
            mode="retrieval",
            segments_dir=segments_dir,
            segment_paths=segment_paths,
        )
        self._concat_video_segments(project_id, segments_dir, segment_paths, output_path)
        final_video_path = self._finalize_video_output(project_id, lines, durations, output_path)
        self._log_retrieval_finalize_done(project_id, final_video_path)
        set_progress_status(project_id=project_id, status="completed")
        return final_video_path

    def _build_retrieval_math_video(
        self,
        project_id: str,
        lines: list,
        background_assets: list,
        audio_files: list,
        durations: list,
        line_foreground_layers: list,
    ):
        if not background_assets:
            raise ValueError("检索素材为空，无法生成 math retrieval 视频")

        pdir = self.base_dir / project_id
        task_data = TASKS.setdefault(project_id, {})
        output_path = os.path.join(pdir, f"final_{int(time())}.mp4")
        segments_dir = self._prepare_fresh_output_dir(self._video_segments_mode_dir(project_id, "retrieval_math"))

        clips = []
        segment_paths = []
        image_paths = []

        emit_progress_status(project_id, "in_video_progress", "正在生成数学检索视频片段", 78)

        total = len(background_assets)
        logger.info("[retrieval_math] project=%s render_start total=%s", project_id, total)

        for index, asset in enumerate(background_assets):
            duration = durations[index] if index < len(durations) else asset.get("audio_duration", 0)
            audio_path = audio_files[index] if index < len(audio_files) else asset.get("audio_path", "")
            foreground_path = line_foreground_layers[index] if index < len(line_foreground_layers) else ""

            clip = {
                "index": asset.get("index", index),
                "clip_path": "",
                "image_path": asset.get("source_path", "") if asset.get("media_type") == "image" else "",
                "audio_path": audio_path,
                "duration": duration,
                "prompt": "",
                "text": asset.get("text", lines[index] if index < len(lines) else ""),
                "dirty": False,
                "script": "",
                "script_file": "",
                "math_animation_path": foreground_path,
                "source_path": asset.get("source_path", ""),
                "media_type": asset.get("media_type", ""),
                "annotation_path": asset.get("annotation_path", ""),
                "start_sec": asset.get("start_sec"),
                "end_sec": asset.get("end_sec"),
                "score": asset.get("score", 0.0),
            }

            bg_clip_path = segments_dir / f"bg_{index:04d}.mp4"
            final_clip_path = segments_dir / f"clip_{index:04d}.mp4"

            logger.info(
                "[retrieval_math] project=%s clip=%s/%s bg_start media_type=%s source=%s audio=%s fg=%s",
                project_id,
                index + 1,
                total,
                clip.get("media_type"),
                self._short_media_path(clip.get("source_path", "")),
                self._short_media_path(audio_path),
                self._short_media_path(foreground_path),
            )

            # 先生成背景 + 音频 clip
            rendered_bg = self._render_retrieval_asset_clip(clip, bg_clip_path)

            # 再决定是否叠前景数学动画
            if foreground_path and self._is_valid_media_file(foreground_path):
                self._create_math_video_retrieval(
                    project_id=project_id,
                    image_files=[rendered_bg],
                    audio_files=[audio_path],
                    text_layers=[],
                    math_layers=[foreground_path],
                    durations=[float(duration or 0)],
                    video_path=str(final_clip_path),
                    concat_final=False,
                )
                rendered_path = str(final_clip_path).replace("\\", "/")
            else:
                rendered_path = str(rendered_bg).replace("\\", "/")

            logger.info(
                "[retrieval_math] project=%s clip=%s/%s done output=%s",
                project_id,
                index + 1,
                total,
                self._short_media_path(rendered_path),
            )

            clip["clip_path"] = rendered_path
            clips.append(clip)
            segment_paths.append(rendered_path)
            image_paths.append(clip.get("image_path", ""))

        emit_progress_status(project_id, "in_video_concat", "正在拼接数学检索视频", 92)
        logger.info("[retrieval_math] project=%s concat_start clips=%s output=%s", project_id, len(segment_paths), output_path)

        self._concat_video_segments(project_id, segments_dir, segment_paths, output_path)

        self._set_video_artifact_metadata(
            project_id,
            mode="retrieval_math",
            segments_dir=segments_dir,
            segment_paths=segment_paths,
            math_animations=line_foreground_layers,
            math_animations_dir=self._project_dir(project_id) / "math_retrieval_segments",
        )

        task_data["clips"] = clips
        task_data["images"] = image_paths
        task_data["video_path"] = output_path
        task_data["video_segments"] = segment_paths
        task_data["video_segments_dir"] = str(segments_dir).replace("\\", "/")
        task_data["video_segments_mode"] = "retrieval_math"

        logger.info("[retrieval_math] project=%s finalize_done output=%s", project_id, self._short_media_path(output_path))
        return output_path
    def _rebuild_dirty_clips(self, project_id: str):
        if not self._supports_clip_rebuild(project_id):
            raise ValueError("当前项目暂不支持片段级重建")
        task_data = TASKS.setdefault(project_id, {})
        clips = self._sync_clips_from_assets(project_id)
        dirty_indices = self._dirty_clip_indices(project_id)
        if not dirty_indices:
            return clips

        segments_dir_path = task_data.get("video_segments_dir")
        if not segments_dir_path:
            raise ValueError("视频片段目录缺失，无法重建视频段")
        segments_dir = self._prepare_output_dir(Path(segments_dir_path))
        segments = task_data.get("video_segments") or []

        emit_progress_status(project_id, "in_video_rebuild", "正在重建视频段", 75)
        for order, index in enumerate(dirty_indices, start=1):
            clip = clips[index]
            clip_path = segments_dir / f"clip_{index:04d}.mp4"
            rendered_path = self._render_retrieval_asset_clip(clip, clip_path) if clip.get("media_type") in {"image", "video", "color"} else self._render_story_style_clip(
                clip.get("image_path", ""),
                clip.get("audio_path", ""),
                float(clip.get("duration") or 0) or 5.0,
                clip_path,
            )
            clip["clip_path"] = rendered_path
            clip["dirty"] = False
            while len(segments) <= index:
                segments.append("")
            segments[index] = clip["clip_path"]
            update_progress(project_id, 75 + int(10 * order / max(len(dirty_indices), 1)), f"正在重建第{order}/{len(dirty_indices)}个视频段")

        task_data["video_segments"] = segments
        task_data["clips"] = clips
        emit_progress_status(project_id, "in_video_concat", "视频段已更新，待拼接整片", 90)
        self.save_project(project_id)
        return clips

    def _concat_existing_clips(self, project_id: str):
        task_data = TASKS.setdefault(project_id, {})
        clips = self._sync_clips_from_assets(project_id)
        dirty_indices = self._dirty_clip_indices(project_id)
        if dirty_indices:
            raise ValueError("仍有待重建的视频段，请先执行重建视频段")
        lines = task_data.get("lines") or []
        durations = task_data.get("durations") or []
        return self._compose_existing_video_segments(project_id, lines, durations)

    async def async_rebuild_dirty_clips(
        self,
        project_id: str,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        register_progress_callback(project_id, progress_cb)
        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            self._ensure_project_loaded(project_id)
            clips = await asyncio.to_thread(self._rebuild_dirty_clips, project_id)
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            snapshot = self.get_project_snapshot(project_id)
            return {
                "status": "completed",
                "project_id": project_id,
                "snapshot": snapshot,
                "clips": clips,
                **self._build_partial_video_payload(project_id),
            }
        except asyncio.CancelledError:
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            self._persist_project_failure(project_id, str(e))
            return {"status": "error", "project_id": project_id, "error": str(e), "snapshot": self.get_project_snapshot(project_id), **self._build_partial_video_payload(project_id)}
        finally:
            unregister_progress_callback(project_id)

    async def async_concat_video_clips(
        self,
        project_id: str,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        register_progress_callback(project_id, progress_cb)
        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            self._ensure_project_loaded(project_id)
            video_path = await asyncio.to_thread(self._concat_existing_clips, project_id)
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}
            snapshot = self.get_project_snapshot(project_id)
            return {
                "status": "completed",
                "project_id": project_id,
                "video_path": video_path,
                "snapshot": snapshot,
                **self._build_partial_video_payload(project_id),
            }
        except asyncio.CancelledError:
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            self._persist_project_failure(project_id, str(e))
            return {"status": "error", "project_id": project_id, "error": str(e), "snapshot": self.get_project_snapshot(project_id), **self._build_partial_video_payload(project_id)}
        finally:
            unregister_progress_callback(project_id)

    def _is_valid_media_file(self, file_path: Optional[str]) -> bool:
        if not file_path or not isinstance(file_path, str):
            return False
        normalized = file_path.strip()
        if not normalized or normalized in {".", ".."}:
            return False
        return os.path.isfile(normalized)

    def _ensure_audio_configs(
        self,
        project_id: str,
        lines: list,
        model_name: str,
        api_key: str,
        voice: str,
        language: Optional[str] = None,
        start_index: int = 0,
    ) -> List[Dict[str, Any]]:
        existing = get_progress_data(project_id=project_id, key="audios_configs") or []
        configs: List[Dict[str, Any]] = []
        for idx, line in enumerate(lines):
            line_text = self._strip_inline_formula_markers(line or "")
            if idx < len(existing) and idx < start_index and existing[idx]:
                config = existing[idx]
                if hasattr(config, "model_dump"):
                    config = config.model_dump()
                elif hasattr(config, "dict"):
                    config = config.dict()
                else:
                    config = dict(config)
                config = dict(config)
                if line_text:
                    config["text"] = line_text
            else:
                config = {
                    "audio_model_name": model_name,
                    "audio_api_key": api_key,
                    "voice": voice,
                    "text": line_text,
                    "language": self._get_project_language(project_id, text=line_text, requested_language=language),
                }
            configs.append(config)
        set_progress_data(project_id=project_id, key="audios_configs", data=configs)
        return configs

    def _concat_video_segments(self, project_id: str, segments_dir: Path, clip_paths: List[str], output_path: str):
        print(f"拼接 {len(clip_paths)} 个片段...")
        emit_progress_status(
            project_id=project_id,
            status="in_video_concat",
            percent=90,
            stage="视频片段已生成，正在拼接整片",
        )

        if len(clip_paths) == 1:
            import shutil

            shutil.copy2(clip_paths[0], output_path)
            return output_path

        concat_list = segments_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in clip_paths:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        try:
            ffmpeg_cmd = ffmpeg.input(str(concat_list), format="concat", safe=0).output(
                output_path,
                vcodec="libx264",
                acodec="aac",
                preset="ultrafast",
                pix_fmt="yuv420p",
                r=30,
                shortest=None,
                loglevel="error",
            )
            self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=60)
            print(f"🎬 完整视频合成完成：{output_path}")
        except ffmpeg.Error as e:
            stderr = getattr(e, "stderr", None)
            stderr_text = stderr.decode(errors="replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr or e)
            print(f"视频拼接时出错：{stderr_text}")
            raise

        return output_path

    def _finalize_video_output(self, project_id: str, lines: list, durations: list, video_path: str, with_subtitles: bool = True):
        pdir = self.base_dir / project_id
        if not with_subtitles:
            update_progress(project_id=project_id, percent=100, stage="已完成视频制作！")
            set_progress_data(project_id=project_id, key="video_path", data=video_path)
            print("无字幕视频总工程完毕")
            return video_path

        print("视频生成完成，正在生成字幕……")

        subtitle_segments = [
            {"text": line, "duration": dur} for line, dur in zip(lines, durations) if len(line) >= 2
        ]
        subtitle_path = sub.generate_srt(segments=subtitle_segments, output_dir=pdir)

        print("字幕生成完成，正在组装视频……")
        update_progress(project_id=project_id, percent=95, stage="字幕已生成，正在组装视频！")
        video_path_with_subtitle = video_path.replace(".mp4", ".with_subtitle.mp4")

        final_with_subtitle = sub.burn_subtitles(
            video_path, subtitle_path, video_path_with_subtitle
        )
        final_video_path = final_with_subtitle or video_path_with_subtitle or video_path
        update_progress(project_id=project_id, percent=100, stage="已完成视频制作！")
        set_progress_data(project_id=project_id, key="video_path", data=final_video_path)
        print("带字幕视频总工程完毕")
        return final_video_path

    def _compose_video_by_style(
        self,
        project_id: str,
        style: str,
        lines: list,
        image_files: list,
        audio_files: list,
        durations: list,
        math_animations: Optional[list] = None,
    ):
        pdir = self.base_dir / project_id
        video_path = os.path.join(pdir, f"final_{int(time())}.mp4")
        set_progress_status(project_id=project_id, status="in_video_progress")

        if "story" in style:
            self._create_mixed_video(
                project_id=project_id,
                image_files=image_files,
                audio_files=audio_files,
                math_layers=math_animations or [],
                durations=durations,
                video_path=video_path,
            )
        else:
            self._create_video(project_id, image_files, audio_files, durations, video_path)

        final_video_path = self._finalize_video_output(
            project_id,
            lines,
            durations,
            video_path,
            with_subtitles=True,
        )
        return final_video_path

    def _compose_existing_video_segments(self, project_id: str, lines: list, durations: list):
        video_segments = get_progress_data(project_id=project_id, key="video_segments") or []
        segments_dir_path = get_progress_data(project_id=project_id, key="video_segments_dir")
        if not video_segments or not segments_dir_path:
            raise ValueError("video segments are missing for concat stage")
        pdir = self.base_dir / project_id
        video_path = os.path.join(pdir, f"final_{int(time())}.mp4")
        self._concat_video_segments(
            project_id=project_id,
            segments_dir=Path(segments_dir_path),
            clip_paths=video_segments,
            output_path=video_path,
        )
        style = str(self._get_project_config_value(project_id, "style", "") or "")
        final_video_path = self._finalize_video_output(
            project_id,
            lines,
            durations,
            video_path,
            with_subtitles=True,
        )
        set_progress_status(project_id=project_id, status="completed")
        return final_video_path

    def _resume_video_output(self, project_id: str, style: str, lines: list, image_files: list, audio_files: list, durations: list):
        if get_progress_status(project_id=project_id) == "in_video_concat":
            return self._compose_existing_video_segments(project_id, lines, durations)
        math_animations = get_progress_data(project_id=project_id, key="math_animations") or []
        return self._compose_video_by_style(
            project_id=project_id,
            style=style,
            lines=lines,
            image_files=image_files,
            audio_files=audio_files,
            durations=durations,
            math_animations=math_animations,
        )

    def _build_audio_configs_from_project(self, project_id: str, lines: list):
        config = self.projects[project_id]["config"]
        return self._ensure_audio_configs(
            project_id=project_id,
            lines=lines,
            model_name=config["audio_model_name"],
            api_key=config["audio_api_key"],
            voice=config["voice"],
        )

    def _build_audio_configs_for_values(self, project_id: str, lines: list, model_name: str, api_key: str, voice: str, start_index: int = 0):
        return self._ensure_audio_configs(project_id, lines, model_name, api_key, voice, start_index)

    def _ensure_video_pipeline_status(self, project_id: str):
        if get_progress_status(project_id=project_id) not in {"in_video_progress", "in_video_concat", "completed"}:
            set_progress_status(project_id=project_id, status="in_video_progress")

    def _normalize_existing_video_stage(self, project_id: str):
        current_status = get_progress_status(project_id=project_id)
        if current_status == "completed" and get_progress_data(project_id=project_id, key="video_segments"):
            set_progress_status(project_id=project_id, status="in_video_concat")
        return get_progress_status(project_id=project_id)

    def _validate_video_resume_assets(self, lines: list, image_files: list, audio_files: list, durations: list):
        if not lines or not audio_files or not durations:
            raise ValueError("video rebuild assets are incomplete")
        if image_files is None:
            raise ValueError("video rebuild image assets are missing")
        return True

    def _prepare_video_concat_resume(self, project_id: str):
        if get_progress_status(project_id=project_id) == "in_video_concat":
            emit_progress_status(project_id, "in_video_concat", "继续视频拼接", 90)

    def _resume_video_segments_or_render(self, project_id: str, style: str, lines: list, image_files: list, audio_files: list, durations: list):
        if get_progress_status(project_id=project_id) == "in_video_concat":
            return self._compose_existing_video_segments(project_id, lines, durations)
        return self._compose_video_by_style(
            project_id,
            style,
            lines,
            image_files,
            audio_files,
            durations,
            get_progress_data(project_id=project_id, key="math_animations") or [],
        )

    def _finalize_video_task(self, project_id: str, video_path: str):
        set_progress_data(project_id=project_id, key="video_path", data=video_path)
        set_progress_status(project_id=project_id, status="completed")
        return video_path

    def _normalize_redraw_history(self, history: Any, kind: str) -> List[List[Dict[str, Any]]]:
        if not isinstance(history, list):
            return []

        normalized_history: List[List[Dict[str, Any]]] = []
        for entry in history:
            if not isinstance(entry, list):
                normalized_history.append([])
                continue

            normalized_candidates: List[Dict[str, Any]] = []
            for candidate in entry:
                if not isinstance(candidate, dict):
                    continue
                candidate_copy = dict(candidate)
                config = candidate_copy.get("config")
                candidate_copy["config"] = self._normalize_config_for_save(config) if isinstance(config, dict) else config
                if kind == "image" and candidate_copy.get("prompt") is None:
                    candidate_copy["prompt"] = candidate_copy.get("text", "")
                normalized_candidates.append(candidate_copy)
            normalized_history.append(normalized_candidates)
        return normalized_history

    def _ensure_history_container(self, project_id: str, key: str, expected_len: int) -> List[List[Dict[str, Any]]]:
        history = TASKS[project_id].setdefault(key, [])
        while len(history) < expected_len:
            history.append([])
        return history

    def _ensure_image_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        images = get_progress_data(project_id=project_id, key="images") or []
        image_configs = get_progress_data(project_id=project_id, key="images_configs") or []
        prompts = get_progress_data(project_id=project_id, key="prompts") or []
        history = self._ensure_history_container(project_id, "image_redraw_history", len(images))
        entry = history[index]
        if entry:
            return entry

        prompt = prompts[index] if index < len(prompts) else ""
        config = image_configs[index] if index < len(image_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "image_model_name": getattr(config, "image_model_name", ""),
                "image_api_key": getattr(config, "image_api_key", ""),
                "prompt": getattr(config, "prompt", prompt),
                "text": getattr(config, "text", prompt),
                "n": getattr(config, "n", 1),
                "size": getattr(config, "size", ""),
            }
        config = dict(config)
        config_prompt = config.get("prompt") or config.get("text") or prompt
        config["prompt"] = config_prompt
        config["text"] = config.get("text") or config_prompt
        config.setdefault("render_mode", "prompt")
        config.setdefault("story_segment", None)
        entry.append(
            {
                "image_path": images[index] if index < len(images) else "",
                "prompt": config_prompt,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _ensure_audio_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        audios = get_progress_data(project_id=project_id, key="audios") or []
        durations = get_progress_data(project_id=project_id, key="durations") or []
        audio_configs = get_progress_data(project_id=project_id, key="audios_configs") or []
        history = self._ensure_history_container(project_id, "audio_redraw_history", len(audios))
        entry = history[index]
        if entry:
            return entry

        config = audio_configs[index] if index < len(audio_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "audio_model_name": getattr(config, "audio_model_name", ""),
                "audio_api_key": getattr(config, "audio_api_key", ""),
                "text": getattr(config, "text", ""),
                "voice": getattr(config, "voice", ""),
            }
        config = dict(config)
        entry.append(
            {
                "audio_path": audios[index] if index < len(audios) else "",
                "duration": durations[index] if index < len(durations) else 0,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _append_redraw_history_candidate(self, project_id: str, kind: str, index: int, candidate: Dict[str, Any]):
        if kind == "image":
            entry = self._ensure_image_history_entry(project_id, index)
        else:
            entry = self._ensure_audio_history_entry(project_id, index)

        for item in entry:
            item["is_current"] = False
        entry.append(candidate)
        while len(entry) > self.REDRAW_HISTORY_LIMIT:
            del entry[1]

    def _build_project_snapshot(self, project_id: str) -> Dict[str, Any]:
        project = self.projects.get(project_id, {})
        task_data = TASKS.get(project_id, {})
        return {
            "project_id": project_id,
            "project_name": project.get("name", ""),
            "project_target": project.get("target", ""),
            "project_config": self._normalize_config_for_save(project.get("config")),
            "task_data": task_data,
            "status": task_data.get("status"),
            "stage": task_data.get("stage"),
            "progress": task_data.get("percent", 0),
            "updated_at": int(time()),
        }

    def create_project(self, name: str, target: str) -> str:
        if target not in targets:
            return None
        pid = str(uuid4())
        pdir = self.base_dir / pid
        pdir.mkdir(exist_ok=True)
        meta = {
            "project_id": pid,
            "name": name,
            "target": target,
            "config": None,
        }
        self.projects[pid] = meta
        TASKS[pid] = {}
        return pid

    def _normalize_redraw_history(self, history: Any, kind: str) -> List[List[Dict[str, Any]]]:
        if not isinstance(history, list):
            return []

        normalized_history: List[List[Dict[str, Any]]] = []
        for entry in history:
            if not isinstance(entry, list):
                normalized_history.append([])
                continue

            normalized_candidates: List[Dict[str, Any]] = []
            for candidate in entry:
                if not isinstance(candidate, dict):
                    continue
                candidate_copy = dict(candidate)
                config = candidate_copy.get("config")
                candidate_copy["config"] = self._normalize_config_for_save(config) if isinstance(config, dict) else config
                if kind == "image" and candidate_copy.get("prompt") is None:
                    candidate_copy["prompt"] = candidate_copy.get("text", "")
                normalized_candidates.append(candidate_copy)
            normalized_history.append(normalized_candidates)
        return normalized_history

    def _ensure_history_container(self, project_id: str, key: str, expected_len: int) -> List[List[Dict[str, Any]]]:
        history = TASKS[project_id].setdefault(key, [])
        while len(history) < expected_len:
            history.append([])
        return history

    def _ensure_image_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        images = get_progress_data(project_id=project_id, key="images") or []
        image_configs = get_progress_data(project_id=project_id, key="images_configs") or []
        prompts = get_progress_data(project_id=project_id, key="prompts") or []
        history = self._ensure_history_container(project_id, "image_redraw_history", len(images))
        entry = history[index]
        if entry:
            return entry

        prompt = prompts[index] if index < len(prompts) else ""
        config = image_configs[index] if index < len(image_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "image_model_name": getattr(config, "image_model_name", ""),
                "image_api_key": getattr(config, "image_api_key", ""),
                "prompt": getattr(config, "prompt", prompt),
                "text": getattr(config, "text", prompt),
                "n": getattr(config, "n", 1),
                "size": getattr(config, "size", ""),
            }
        config = dict(config)
        config_prompt = config.get("prompt") or config.get("text") or prompt
        config["prompt"] = config_prompt
        config["text"] = config.get("text") or config_prompt
        config.setdefault("render_mode", "prompt")
        config.setdefault("story_segment", None)
        entry.append(
            {
                "image_path": images[index] if index < len(images) else "",
                "prompt": config_prompt,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _ensure_audio_history_entry(self, project_id: str, index: int) -> List[Dict[str, Any]]:
        audios = get_progress_data(project_id=project_id, key="audios") or []
        durations = get_progress_data(project_id=project_id, key="durations") or []
        audio_configs = get_progress_data(project_id=project_id, key="audios_configs") or []
        history = self._ensure_history_container(project_id, "audio_redraw_history", len(audios))
        entry = history[index]
        if entry:
            return entry

        config = audio_configs[index] if index < len(audio_configs) else {}
        if config is None:
            config = {}
        if hasattr(config, "model_dump"):
            config = config.model_dump()
        elif hasattr(config, "dict"):
            config = config.dict()
        elif not isinstance(config, dict):
            config = {
                "audio_model_name": getattr(config, "audio_model_name", ""),
                "audio_api_key": getattr(config, "audio_api_key", ""),
                "text": getattr(config, "text", ""),
                "voice": getattr(config, "voice", ""),
            }
        config = dict(config)
        entry.append(
            {
                "audio_path": audios[index] if index < len(audios) else "",
                "duration": durations[index] if index < len(durations) else 0,
                "config": config,
                "created_at": int(time()),
                "is_current": True,
            }
        )
        return entry

    def _append_redraw_history_candidate(self, project_id: str, kind: str, index: int, candidate: Dict[str, Any]):
        if kind == "image":
            entry = self._ensure_image_history_entry(project_id, index)
        else:
            entry = self._ensure_audio_history_entry(project_id, index)

        for item in entry:
            item["is_current"] = False
        entry.append(candidate)
        while len(entry) > self.REDRAW_HISTORY_LIMIT:
            del entry[1]

    def apply_redraw_selection(
        self,
        project_id: str,
        image_selected_history: Optional[Dict[str, int]] = None,
        audio_selected_history: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        self._ensure_project_loaded(project_id)
        task_data = TASKS.setdefault(project_id, {})

        image_selected_history = image_selected_history or {}
        audio_selected_history = audio_selected_history or {}
        changed_indices = set()

        images = task_data.setdefault("images", [])
        image_configs = task_data.setdefault("images_configs", [])
        prompts = task_data.setdefault("prompts", [])
        image_history = self._ensure_history_container(project_id, "image_redraw_history", len(images))

        for index_str, history_index in image_selected_history.items():
            index = int(index_str)
            if index >= len(image_history):
                raise IndexError(f"image history index out of range: {index}")
            candidates = image_history[index]
            if history_index < 0 or history_index >= len(candidates):
                raise IndexError(f"selected image history item out of range: {index}:{history_index}")
            selected = dict(candidates[history_index])
            config = dict(selected.get("config") or {})
            prompt = selected.get("prompt") or config.get("prompt") or config.get("text") or ""
            config["prompt"] = prompt
            config["text"] = prompt
            images[index] = selected.get("image_path", "")
            prompts[index] = prompt
            image_configs[index] = config
            changed_indices.add(index)
            for idx, item in enumerate(candidates):
                item["is_current"] = idx == history_index

        audios = task_data.setdefault("audios", [])
        durations = task_data.setdefault("durations", [])
        audio_configs = task_data.setdefault("audios_configs", [])
        audio_history = self._ensure_history_container(project_id, "audio_redraw_history", len(audios))
        lines = task_data.setdefault("lines", [])

        for index_str, history_index in audio_selected_history.items():
            index = int(index_str)
            if index >= len(audio_history):
                raise IndexError(f"audio history index out of range: {index}")
            candidates = audio_history[index]
            if history_index < 0 or history_index >= len(candidates):
                raise IndexError(f"selected audio history item out of range: {index}:{history_index}")
            selected = dict(candidates[history_index])
            config = dict(selected.get("config") or {})
            if index < len(lines):
                config["text"] = lines[index]
            audios[index] = selected.get("audio_path", "")
            durations[index] = selected.get("duration", 0)
            audio_configs[index] = config
            changed_indices.add(index)
            for idx, item in enumerate(candidates):
                item["is_current"] = idx == history_index

        self._mark_clips_dirty(project_id, sorted(changed_indices))
        if changed_indices:
            emit_progress_status(project_id, "in_video_rebuild", "素材已更新，待重建视频段", 72)
        self.save_project(project_id)
        return self.get_project_snapshot(project_id)

        # data={"text":str,"prompts":list,"audios":list,"images":list,"vid"}
        meta = {
            "project_id": pid,
            "name": name,
            "target": target,
            "config": None,
            # "status": "draft"
            # "data"
        }
        # (pdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.projects[pid] = meta
        TASKS[pid] = {}
        return pid

    def save_project(self, project_id: str):
        print("save project id==", project_id)
        if project_id not in self.projects:
            raise KeyError(f"project not found: {project_id}")

        pdir = self.base_dir / project_id
        pdir.mkdir(parents=True, exist_ok=True)
        data = self._build_project_snapshot(project_id)
        print("保存时的task_data:", data.get("task_data"))

        with open(self._project_meta_path(project_id), "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, indent=4, ensure_ascii=False)

        print("text_config=====", get_progress_data(project_id=project_id, key="text_config"))
        print(f"project_info saved in {pdir}/meta.json")

    def list_projects(self) -> Dict[str, Any]:
        projects = []
        invalid_meta_projects = []
        for meta_path in sorted(self.base_dir.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                with open(meta_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                task_data = data.get("task_data") or {}
                projects.append(
                    {
                        "project_id": data.get("project_id") or meta_path.parent.name,
                        "name": data.get("project_name") or meta_path.parent.name,
                        "target": data.get("project_target"),
                        "status": task_data.get("status") or data.get("status") or "draft",
                        "stage": task_data.get("stage") or data.get("stage") or "",
                        "progress": task_data.get("percent", data.get("progress", 0)),
                        "updated_at": data.get("updated_at") or int(meta_path.stat().st_mtime),
                        "video_path": task_data.get("video_path"),
                    }
                )
            except Exception as e:
                invalid_meta_projects.append(meta_path.parent.name)
                print(f"list_projects skip invalid meta {meta_path}: {e}")
        warning = None
        if invalid_meta_projects:
            warning = {
                "invalid_meta_count": len(invalid_meta_projects),
                "invalid_meta_projects": invalid_meta_projects,
            }
        return {"projects": projects, "warning": warning}

    def get_project_snapshot(self, project_id: str) -> Dict[str, Any]:
        if project_id not in self.projects:
            self.load_project(project_id)
        return self._build_project_snapshot(project_id)

    def load_project(self, project_id: str):
        print("load porject id==", project_id)
        file_path = self._project_meta_path(project_id)

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            print("JSON data loaded successfully:")
            project_config = data.get("project_config")
            if isinstance(project_config, str):
                project_config = json.loads(project_config)

            self.projects[project_id] = {
                "project_id": data.get("project_id", project_id),
                "name": data.get("project_name", project_id),
                "target": data.get("project_target", "video"),
                "config": project_config,
            }

            task_data = data.get("task_data") or {}
            task_data.setdefault("status", data.get("status") or "draft")
            task_data.setdefault("stage", data.get("stage") or "")
            task_data.setdefault("percent", data.get("progress", 0))
            task_data["image_redraw_history"] = self._normalize_redraw_history(
                task_data.get("image_redraw_history"), "image"
            )
            task_data["audio_redraw_history"] = self._normalize_redraw_history(
                task_data.get("audio_redraw_history"), "audio"
            )
            TASKS[project_id] = task_data
            self._sync_clips_from_assets(project_id)
            print("task data:", task_data)
            print("text_config=====", get_progress_data(project_id=project_id, key="text_config"))

        except FileNotFoundError:
            print(f"Error: The file '{file_path}' was not found.")
            return None
        except json.JSONDecodeError:
            print(
                f"Error: Could not decode JSON from '{file_path}'. Check if the file contains valid JSON."
            )
            return None
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return None
        return self.get_project_snapshot(project_id)

    def update_config(self, project_id: str, config: dict):
        print(
            f"[update_config] project_id: {project_id}, config type: {type(config)}, config keys: {list(config.keys()) if isinstance(config, dict) else 'not dict'}"
        )
        print(f"[update_config] project exists: {project_id in self.projects}")
        if project_id in self.projects:
            print(
                f"[update_config] current project config before update: {self.projects[project_id].get('config')}"
            )
            if hasattr(config, "model_dump"):
                config = config.model_dump()
            elif hasattr(config, "dict"):
                config = config.dict()

            # 确保article字段是字符串类型（文章内容）
            if isinstance(config, dict) and "article" in config:
                article = config["article"]
                if article is not None:
                    # 确保article是字符串
                    if not isinstance(article, str):
                        print(
                            f"[update_config] WARNING: article is not string, type: {type(article)}, converting to string"
                        )
                        config["article"] = str(article)

                    article_str = config["article"]
                    print(
                        f"[update_config] article content: length={len(article_str)}, preview: {article_str[:100]}{'...' if len(article_str) > 100 else ''}"
                    )
                else:
                    print(f"[update_config] article is None")
            else:
                print(f"[update_config] article not in config or config not dict")

            self.projects[project_id]["config"] = config
            print(f"[update_config] config updated successfully")
        else:
            print(f"[update_config] ERROR: project {project_id} not found in projects")

    # def update_status(self, project_id: str,status:str):
    #     # 更新 meta.json，记录当前阶段、最新脚本路径等
    #     if status not in all_status:
    #         return
    #     self.projects[project_id]["status"]=status

    def gen_texts(
        self,
        project_id: str,
        with_media_prompts: bool = False,
        media_prompt_style: str = "",
        model_name: str = "",
        api_key: str = "",
        theme: str = "",
        style: str = "",
        language: str = "",
        rebuild: bool = False,
    ):
        if rebuild == False:
            config = self.projects[project_id]["config"]
            # 支持字典和对象两种 config 格式
            if isinstance(config, dict):
                if model_name == "":
                    model_name = config.get("text_model_name", "") or ""
                if api_key == "":
                    api_key = config.get("text_api_key", "") or ""
                if theme == "":
                    theme = config.get("theme", "") or ""
                if not style:
                    style = config.get("style", "") or ""
                if not language:
                    language = config.get("language", "") or ""
                if not media_prompt_style:
                    media_prompt_style = config.get("media_prompt_style", "") or ""
            else:
                # 假设 config 是有属性的对象
                if model_name == "":
                    model_name = config.text_model_name
                if api_key == "":
                    api_key = config.text_api_key
                if theme == "":
                    theme = config.theme
                if not style:
                    style = config.style or ""
                if not language:
                    language = getattr(config, "language", "") or ""
                if not media_prompt_style:
                    media_prompt_style = getattr(config, "media_prompt_style", "") or ""
        else:
            text_config = get_progress_data(project_id=project_id, key="text_config")
            # 同样支持字典和对象
            if isinstance(text_config, dict):
                model_name = text_config.get("text_model_name", "")
                api_key = text_config.get("text_api_key", "")
                theme = text_config.get("theme", "")
                style = text_config.get("style", "")
                language = text_config.get("language", "")
                media_prompt_style = text_config.get("media_prompt_style", "")
            else:
                model_name = text_config.text_model_name
                api_key = text_config.text_api_key
                theme = text_config.theme
                style = text_config.style
                language = getattr(text_config, "language", "")
                media_prompt_style = getattr(text_config, "media_prompt_style", "")

        print("设置当前状态=====“in_text_progress”")
        set_progress_status(project_id=project_id, status="in_text_progress")

        print(f"正在创建{model_name}文案生成模型")
        if False == textGenerationService.use_model(model_name=model_name, api_key=api_key):
            error = "创建模型失败，可能是不支持的模型名"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            print("文案模型生成出错，可能是不支持的文案模型")
            return self._text_result(False, error=error)

        print("正在生成文案……")
        language = self._get_project_language(project_id, text=theme, requested_language=language)
        text = textGenerationService.generate_text(theme=theme, style=style, language=language)
        #临时添加
        print("received text:=====>",text)
        ##小测试
        # text="健康时自己最大的财富，他决定了你的身心平衡.\n 请爱惜你自己，正如你爱惜阳光，空气，食物，生活"
        print("with_media_prompts====>",with_media_prompts)
        if self.projects[project_id]["target"] == "text" and not with_media_prompts:
            print("正在更新提示词生成状态和数据……")
            update_progress(project_id=project_id, percent=100, stage="文案已经生成")
        else:
            update_progress(project_id=project_id, percent=50, stage="文案已经生成")

        set_progress_data(project_id=project_id, key="text", data=text)
        self._write_artifact_text(
            project_id,
            "text",
            "generated_text.txt",
            text,
            key="generated_text",
        )
        set_progress_data(
            project_id=project_id,
            key="text_config",
            data={
                "text_model_name": model_name,
                "text_api_key": api_key,
                "theme": theme,
                "style": style,
                "language": language,
                "media_prompt_style": media_prompt_style,
            },
        )
        print("文案生成完成。")
        print("正在释放文案引擎")
        textGenerationService.release_model()
        prompts = []

        if with_media_prompts == True:
            prompts = self.gen_prompts(
                project_id=project_id,
                text=text,
                model_name=model_name,
                api_key=api_key,
                language=language,
                media_prompt_style=media_prompt_style,
            )

        print("正在更新提示词生成状态数据……")
        if self.projects[project_id]["target"] == "text":
            set_progress_status(project_id=project_id, status="completed")

        if self.projects[project_id]["target"] == "text":
            update_progress(project_id=project_id, percent=100, stage="文案和提示词生成完成")
        else:
            update_progress(project_id=project_id, percent=99, stage="文案和提示词生成完成")

        set_progress_data(project_id=project_id, key="prompts", data=prompts)

        return self._text_result(True, content=text, prompts=prompts)

    def gen_prompts(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
        language: str = "",
        media_model_name: str = "",
        media_prompt_style: str = "",
        start_index: int = 0,
    ):
        if model_name == "":
            model_name = self.projects[project_id]["config"].text_model_name
        if api_key == "":
            api_key = self.projects[project_id]["config"].text_api_key
        if text == "":
            text = self.projects[project_id]["config"].text

        print(f"正在创建 media prompt 模型{model_name}……")
        textGenerationService.use_model(model_name=model_name, api_key=api_key)

        print("正在根据文案生成 media prompt 集合……")
        prompts = []
        if start_index > 0:
            prompts = get_progress_data(project_id=project_id, key="prompts")
        lines = text.replace("\n\n", "\n").split("\n")
        for i, line in enumerate(lines):
            if line == "" or len(line) < 2 or i < start_index:
                continue
            # 3️ 打磨 media prompt
            polished_prompt = textGenerationService.polish_media_prompts(
                text=line,
                language=self._get_project_language(project_id, text=line, requested_language=language),
                media_model_name=media_model_name or self._get_project_config_value(project_id, "image_model_name", ""),
                media_prompt_style=media_prompt_style or self._get_project_config_value(project_id, "media_prompt_style", "image_default"),
                texts=text,
            )
            update_progress(
                project_id=project_id,
                percent=50 + 50 * i / len(lines),
                stage=f"生成第{i}/{len(lines)}个提示词",
            )
            prompts.append(polished_prompt)
            TASKS[project_id]["prompts"] = prompts
        print("提示词生成完成。")
        print("正在释放提示词引擎")
        textGenerationService.release_model()
        return prompts

    def gen_prompts_by_story_structure(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
    ):
        if model_name == "":
            model_name = self.projects[project_id]["config"].text_model_name
        if api_key == "":
            api_key = self.projects[project_id]["config"].text_api_key
        if text == "":
            text = self.projects[project_id]["config"].text
        prompts, texts = run_story_pipeline(story=text, model_name=model_name, api_key=api_key)

    def gen_audio(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
        voice: str = "",
        language: str = "",
        index: int = -1,
    ):
        pdir = self.base_dir / project_id

        if index == -1:
            if model_name == "":
                model_name = self.projects[project_id]["config"].audio_model_name
            if api_key == "":
                api_key = self.projects[project_id]["config"].audio_api_key
            if text == "":
                text = self.projects[project_id]["config"].text
            if voice == "":
                voice = self.projects[project_id]["config"].voice
        else:
            audio_config = {
                "audio_model_name": model_name,
                "audio_api_key": api_key,
                "text": text,
                "voice": voice,
                "language": language,
            }
            if not all(audio_config.values()):
                stored_audio_config = get_progress_data_with_index(
                    project_id=project_id, key="audios_configs", index=index
                )
                if hasattr(stored_audio_config, "model_dump"):
                    stored_audio_config = stored_audio_config.model_dump()
                elif hasattr(stored_audio_config, "dict"):
                    stored_audio_config = stored_audio_config.dict()
                elif not isinstance(stored_audio_config, dict):
                    stored_audio_config = {
                        "audio_model_name": getattr(stored_audio_config, "audio_model_name", ""),
                        "audio_api_key": getattr(stored_audio_config, "audio_api_key", ""),
                        "text": getattr(stored_audio_config, "text", ""),
                        "voice": getattr(stored_audio_config, "voice", ""),
                        "language": getattr(stored_audio_config, "language", ""),
                    }
                audio_config = {
                    "audio_model_name": audio_config.get("audio_model_name") or stored_audio_config.get("audio_model_name", ""),
                    "audio_api_key": audio_config.get("audio_api_key") or stored_audio_config.get("audio_api_key", ""),
                    "text": audio_config.get("text") or stored_audio_config.get("text", ""),
                    "voice": audio_config.get("voice") or stored_audio_config.get("voice", ""),
                    "language": audio_config.get("language") or stored_audio_config.get("language", ""),
                }
            model_name = audio_config.get("audio_model_name", "")
            api_key = audio_config.get("audio_api_key", "")
            text = audio_config.get("text", "")
            voice = audio_config.get("voice", "")
            language = audio_config.get("language", "")

        text = self._strip_inline_formula_markers(text)

        print("设置当前状态=====“in_audio_progress”")
        set_progress_status(project_id=project_id, status="in_audio_progress")

        if (
            self.projects[project_id]["target"] == "audio" or index != -1
        ):  # 考虑视频中音频序列重抽情况
            print("正在生成音频引擎……")
            if False == audioGenerationService.create_engine(
                audio_model_name=model_name, audio_api_key=api_key
            ):
                error = "创建音频引擎出错"
                set_progress_status(project_id=project_id, status="error")
                set_progress_data(project_id=project_id, key="errors", data=error)
                return self._audio_result(False, error=error)

        print("正在生成语音信息……")
        success, audio_path, duration = audioGenerationService.generate_audio(
            text, voice, output_dir=pdir, language=language
        )
        print("生成语音：", audio_path)

        if not success:
            error = "生成语音失败"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            if index != -1 or self.projects[project_id]["target"] == "audio":
                self._persist_project_failure(project_id, error)
            return self._audio_result(False, error=error)

        if self.projects[project_id]["target"] == "audio":
            print("正在更新音频生成状态和数据……")
            set_progress_data(project_id=project_id, key="text", data=text)

            set_progress_data(project_id=project_id, key="audios", data=[audio_path])
            set_progress_data(project_id=project_id, key="durations", data=[duration])

            set_progress_status(project_id=project_id, status="completed")

            audios_len = get_progress_data_len(project_id=project_id, key="audios")
            update_progress(
                project_id=project_id,
                percent=99,
                stage=f"已经生成第{audios_len+1}/{audios_len}个音频",
            )

            print("正在释放音频引擎……")
            audioGenerationService.release_engine()
        elif index != -1:
            print("正在缓存音频重抽历史……")
            source_lines = get_progress_data(project_id=project_id, key="lines") or []
            locked_text = source_lines[index] if 0 <= index < len(source_lines) else text
            locked_text = self._strip_inline_formula_markers(locked_text)
            candidate_config = {
                "audio_model_name": model_name,
                "audio_api_key": api_key,
                "text": locked_text,
                "voice": voice,
                "language": self._get_project_language(project_id, text=locked_text, requested_language=language),
            }
            self._append_redraw_history_candidate(
                project_id=project_id,
                kind="audio",
                index=index,
                candidate={
                    "audio_path": audio_path,
                    "duration": duration,
                    "config": candidate_config,
                    "created_at": int(time()),
                    "is_current": False,
                },
            )


        if index != -1:
            self.save_project(project_id)
        print("语音信息生成完成。")
        return self._audio_result(True, audio_path=audio_path, duration=duration)

    def gen_image(
        self,
        project_id: str,
        text: str = "",
        model_name: str = "",
        api_key: str = "",
        n: int = 0,
        size: str = "",
        language: str = "",
        index: int = -1,
    ):
        pdir = self.base_dir / project_id

        if index == -1:
            if model_name == "":
                model_name = self.projects[project_id]["config"].image_model_name
            if api_key == "":
                api_key = self.projects[project_id]["config"].image_api_key
            if text == "":
                text = self.projects[project_id]["config"].prompt
            if n == 0:
                n = self.projects[project_id]["config"].n
            if size == "":
                size = self.projects[project_id]["config"].size
        else:
            image_config = {
                "image_model_name": model_name,
                "image_api_key": api_key,
                "prompt": text,
                "text": text,
                "n": n,
                "size": size,
                "language": language,
                "render_mode": "",
                "story_segment": None,
            }
            stored_image_config = get_progress_data_with_index(
                project_id=project_id, key="images_configs", index=index
            )
            if hasattr(stored_image_config, "model_dump"):
                stored_image_config = stored_image_config.model_dump()
            elif hasattr(stored_image_config, "dict"):
                stored_image_config = stored_image_config.dict()
            elif not isinstance(stored_image_config, dict):
                stored_image_config = {
                    "image_model_name": getattr(stored_image_config, "image_model_name", ""),
                    "image_api_key": getattr(stored_image_config, "image_api_key", ""),
                    "prompt": getattr(stored_image_config, "prompt", getattr(stored_image_config, "text", "")),
                    "text": getattr(stored_image_config, "text", getattr(stored_image_config, "prompt", "")),
                    "n": getattr(stored_image_config, "n", 1),
                    "size": getattr(stored_image_config, "size", ""),
                    "language": getattr(stored_image_config, "language", ""),
                    "render_mode": getattr(stored_image_config, "render_mode", ""),
                    "story_segment": getattr(stored_image_config, "story_segment", None),
                }
            if stored_image_config is None:
                stored_image_config = {}
            image_config = {
                "image_model_name": image_config.get("image_model_name") or stored_image_config.get("image_model_name", ""),
                "image_api_key": image_config.get("image_api_key") or stored_image_config.get("image_api_key", ""),
                "prompt": image_config.get("prompt") or image_config.get("text") or stored_image_config.get("prompt") or stored_image_config.get("text", ""),
                "text": image_config.get("text") or image_config.get("prompt") or stored_image_config.get("text") or stored_image_config.get("prompt", ""),
                "n": image_config.get("n") or stored_image_config.get("n", 1),
                "size": image_config.get("size") or stored_image_config.get("size", ""),
                "language": image_config.get("language") or stored_image_config.get("language", ""),
                "render_mode": image_config.get("render_mode") or stored_image_config.get("render_mode", ""),
                "story_segment": image_config.get("story_segment") or stored_image_config.get("story_segment"),
            }
            print("image_config====", image_config)
            model_name = image_config.get("image_model_name", "")
            print(model_name)
            api_key = image_config.get("image_api_key", "")
            text = image_config.get("prompt") or image_config.get("text", "")
            n = image_config.get("n", 1)
            size = image_config.get("size", "")
            language = image_config.get("language", "")
            print(model_name, ",", api_key, ",", text, ",", n, ",", size)
            if image_config.get("render_mode") == "story_shot" and image_config.get("story_segment"):
                image_result = self.render_story_shot(
                    project_id=project_id,
                    segment=dict(image_config.get("story_segment") or {}),
                    model_name=model_name,
                    api_key=api_key,
                    size=size,
                    n=n,
                )
                if not image_result["success"]:
                    error = image_result.get("error") or "生成图像失败"
                    set_progress_status(project_id=project_id, status="error")
                    set_progress_data(project_id=project_id, key="errors", data=error)
                    if index != -1 or self.projects[project_id]["target"] == "image":
                        self._persist_project_failure(project_id, error)
                    return self._image_result(False, error=error)
                image_paths = image_result["image_paths"]
                if index != -1:
                    story_segment = dict(image_config.get("story_segment") or {})
                    prompt = story_segment.get("image_prompt") or story_segment.get("text", "")
                    candidate_config = dict(image_config)
                    self._append_redraw_history_candidate(
                        project_id=project_id,
                        kind="image",
                        index=index,
                        candidate={
                            "image_path": image_paths[0],
                            "prompt": prompt,
                            "config": candidate_config,
                            "created_at": int(time()),
                            "is_current": False,
                        },
                    )
                    images_len = get_progress_data_len(project_id=project_id, key="images")
                    update_progress(
                        project_id=project_id,
                        percent=99,
                        stage=f"已经生成第{images_len}/{images_len}个文案图像候选",
                    )
                    imageGenerationService.release_engine()
                    self.save_project(project_id)
                return self._image_result(True, image_paths=image_paths)

        print("设置当前状态======“in_image_progress”")
        set_progress_status(project_id=project_id, status="in_image_progress")

        if self.projects[project_id]["target"] == "image" or (index != -1):
            print(f"正在创建{model_name}图像引擎……")
            if False == imageGenerationService.create_engine(
                image_model_name=model_name, image_api_key=api_key
            ):
                error = "创建图像引擎出错"
                set_progress_status(project_id=project_id, status="error")
                set_progress_data(project_id=project_id, key="errors", data=error)
                return self._image_result(False, error=error)

        print("正在创建图像……")
        success, image_paths = imageGenerationService.generate(text, pdir, size=size, n=n)
        print("生成图像：", image_paths)

        if not success or not image_paths:
            error = "生成图像失败"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            if index != -1 or self.projects[project_id]["target"] == "image":
                self._persist_project_failure(project_id, error)
            return self._image_result(False, error=error)

        if self.projects[project_id]["target"] == "image":
            print("正在更新图像生成状态和数据……")
            set_progress_data(project_id=project_id, key="prompts", data=[text])
            set_progress_data(project_id=project_id, key="images", data=[image_paths[0]])
            set_progress_status(project_id=project_id, status="completed")
            print("正在释放图像引擎……")
            imageGenerationService.release_engine()
        elif index != -1:  # 在视频的图像序列中
            print("正在缓存图像重抽历史……")
            prompt = text
            candidate_config = {
                "image_model_name": model_name,
                "image_api_key": api_key,
                "prompt": prompt,
                "text": prompt,
                "n": n,
                "size": size,
                "language": self._get_project_language(project_id, text=prompt, requested_language=language),
                "render_mode": image_config.get("render_mode", "prompt") if index != -1 else "prompt",
                "story_segment": image_config.get("story_segment") if index != -1 else None,
            }
            self._append_redraw_history_candidate(
                project_id=project_id,
                kind="image",
                index=index,
                candidate={
                    "image_path": image_paths[0],
                    "prompt": prompt,
                    "config": candidate_config,
                    "created_at": int(time()),
                    "is_current": False,
                },
            )
            images_len = get_progress_data_len(project_id=project_id, key="images")
            update_progress(
                project_id=project_id,
                percent=99,
                stage=f"已经生成第{images_len}/{images_len}个文案图像候选",
            )
            print("正在释放图像引擎……")
            imageGenerationService.release_engine()

            self.save_project(project_id)

        return self._image_result(True, image_paths=image_paths)

        return self._image_result(True, image_paths=image_paths)

    def _gen_audios(
        self,
        project_id: str,
        lines: list,
        model_name: str,
        api_key: str,
        voice: str,
        language: str = "",
        start_index: int = 0,
        cancel_event=None,
    ):
        audio_files = []
        durations = []

        if start_index > 0:
            audio_files = get_progress_data(project_id=project_id, key="audios") or []
            durations = get_progress_data(project_id=project_id, key="durations") or []

        self._ensure_audio_configs(project_id, lines, model_name, api_key, voice, language, start_index)

        print(f"正在生成{model_name}音频引擎……")
        if False == audioGenerationService.create_engine(
            audio_model_name=model_name, audio_api_key=api_key
        ):
            error = "创建音频引擎出错"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            print("出错")
            return self._audio_sequence_result(False, error=error, audios=audio_files, durations=durations)
        for i, line in enumerate(lines):
            if cancel_event and cancel_event.is_set():
                print(f"音频生成被取消，已生成 {len(audio_files)} 个音频")
                audioGenerationService.release_engine()
                return self._audio_sequence_result(True, audios=audio_files, durations=durations, cancelled=True)

            line = self._strip_inline_formula_markers(line or "")
            if line == "" or len(line) < 2 or i < start_index:
                continue
            print(line)
            audio_result = self.gen_audio(
                project_id=project_id,
                text=line,
                model_name=model_name,
                api_key=api_key,
                voice=voice,
                language=self._get_project_language(project_id, text=line, requested_language=language),
            )
            if not audio_result["success"]:
                audioGenerationService.release_engine()
                return self._audio_sequence_result(
                    False,
                    error=audio_result.get("error"),
                    audios=audio_files,
                    durations=durations,
                )
            audio_files.append(audio_result["audio_path"])
            durations.append(audio_result["duration"])
            update_progress(
                project_id=project_id,
                percent=99 * i / len(lines),
                stage=f"已经生成第{i}/{len(lines)}个配音音频",
            )
            set_progress_data(project_id=project_id, key="audios", data=audio_files)
            set_progress_data(project_id=project_id, key="durations", data=durations)

        print("正在释放音频引擎……")
        audioGenerationService.release_engine()

        print("音频序列创建完成。")
        return self._audio_sequence_result(True, audios=audio_files, durations=durations)

    def _gen_images(
        self,
        project_id: str,
        lines: list,
        model_name: str = "",
        api_key: str = "",
        n: int = 1,
        size: str = "1024*1024",
        language: str = "",
        start_index: int = 0,
        is_prompts=True,
        cancel_event=None,
    ):
        image_files = []

        if start_index > 0:
            image_files = get_progress_data(project_id=project_id, key="images") or []

        if is_prompts == False:
            print("正在生成图像提示词引擎")
            textGenerationService.use_polish_model(
                model_name=model_name,
                api_key=api_key,
            )
        print(f"正在生成{model_name}图像引擎……")
        if False == imageGenerationService.create_engine(
            image_model_name=model_name, image_api_key=api_key
        ):
            error = "创建图像引擎出错"
            set_progress_status(project_id=project_id, status="error")
            set_progress_data(project_id=project_id, key="errors", data=error)
            return self._image_sequence_result(False, error=error, images=image_files)
        for i, line in enumerate(lines):
            if cancel_event and cancel_event.is_set():
                print(f"图像生成被取消，已生成 {len(image_files)} 张图像")
                imageGenerationService.release_engine()
                return self._image_sequence_result(True, images=image_files, cancelled=True)

            if i < start_index:
                continue
            if isinstance(line, str) and (line == "" or len(line) < 2):
                continue
            if isinstance(line, str) and (line == "use previous background" or line == "use first background"):
                if line == "use previous background" :
                    if i==0:
                        print("there is an error in parsing math segments")
                    image_files.append(image_files[i-1])
                else:
                    image_files.append(image_files[0])
                update_progress(
                    project_id=project_id,
                    percent=99 * i / len(lines),
                    stage=f"已经生成第{i}/{len(lines)}个文案图像",
                    )
                set_progress_data(project_id=project_id, key="images", data=image_files)
                continue

            set_progress_data(project_id=project_id, key="images", data=image_files)

            if isinstance(line, dict):
                segment = dict(line)
                if not segment.get("image_prompt"):
                    segment["image_prompt"] = segment.get("text", "")
                image_result = self.render_story_shot(
                    project_id=project_id,
                    segment=segment,
                    model_name=model_name,
                    api_key=api_key,
                    n=n,
                    size=size,
                )
            else:
                if is_prompts == False:
                    polished_prompt = textGenerationService.polish_media_prompts(
                        line,
                        language=self._get_project_language(project_id, text=line, requested_language=language),
                        media_model_name=model_name,
                        media_prompt_style=self._get_project_config_value(project_id, "media_prompt_style", "image_default"),
                        texts="\n".join(lines),
                    )
                else:
                    polished_prompt = line
                image_result = self.gen_image(
                    project_id=project_id,
                    text=polished_prompt,
                    model_name=model_name,
                    api_key=api_key,
                    n=n,
                    size=size,
                )
            if not image_result["success"]:
                imageGenerationService.release_engine()
                return self._image_sequence_result(
                    False,
                    error=image_result.get("error"),
                    images=image_files,
                )
            image_files.append(image_result["image_paths"][0])
            update_progress(
                project_id=project_id,
                percent=99 * i / len(lines),
                stage=f"已经生成第{i}/{len(lines)}个文案图像",
            )
            set_progress_data(project_id=project_id, key="images", data=image_files)
        print("正在释放图像引擎……")
        imageGenerationService.release_engine()
        return self._image_sequence_result(True, images=image_files)

    def _gen_video(
        self, project_id: str, lines: list, image_files: list, audio_files: list, durations: list
    ):
        return self._compose_video_by_style(
            project_id=project_id,
            style="",
            lines=lines,
            image_files=image_files,
            audio_files=audio_files,
            durations=durations,
            math_animations=[],
        )

    def gen_video(self, project_id: str, cancel_event=None):
        # 检查取消
        if cancel_event and cancel_event.is_set():
            print("视频生成任务被取消")
            return self._cancelled_video_result(project_id)
        # os.makedirs(output_dir, exist_ok=True)
        print("正在初始化视频参数……")
        print(f"[gen_video] project_id: {project_id}, projects keys: {list(self.projects.keys())}")
        config = self.projects[project_id]["config"]
        print(f"[gen_video] config type: {type(config)}, config: {config}")

        # 记录article字段详细信息
        def get_article_info(cfg):
            if isinstance(cfg, dict):
                article = cfg.get("article")
                if article is not None:
                    return f"length={len(article)}, preview: {article[:100]}{'...' if len(article) > 100 else ''}"
                else:
                    return "article is None"
            else:
                # 对象类型
                try:
                    article = getattr(cfg, "article", None)
                    if article is not None:
                        return f"length={len(article)}, preview: {article[:100]}{'...' if len(article) > 100 else ''}"
                    else:
                        return "article is None"
                except:
                    return "cannot get article from object"

        print(f"[gen_video] article info: {get_article_info(config)}")

        # 支持字典和对象两种 config 格式，若值为 None 则使用默认值
        def get_config_value(key, default=""):
            if isinstance(config, dict):
                val = config.get(key, default)
                return val if val is not None else default
            else:
                # 假设 config 是有属性的对象
                val = getattr(config, key, default)
                return val if val is not None else default

        text_model_name = get_config_value("text_model_name", "")
        text_api_key = get_config_value("text_api_key", "")
        audio_model_name = get_config_value("audio_model_name", "")
        audio_api_key = get_config_value("audio_api_key", "")
        image_model_name = get_config_value("image_model_name", "")
        image_api_key = get_config_value("image_api_key", "")
        voice = get_config_value("voice", "")
        n = get_config_value("n", 1)
        size = get_config_value("size", "1024x1024")
        style = get_config_value("style", "")
        if (style or "").strip().lower() == "math":
            return self._failed_video_result(project_id, "纯math教学模式已下线，请使用story模式")
        with_media_prompts = bool(get_config_value("with_media_prompts", True))
        media_prompt_style = get_config_value("media_prompt_style", "image_default")

        lines = []
        prompts = []
        image_files = []
        math_animations = []
        text_animations = []
        if ("story" not in style) and ("math" not in style):
            # 检查取消
            if cancel_event and cancel_event.is_set():
                print("视频生成任务被取消")
                return self._cancelled_video_result(project_id)
            text_result = self.gen_texts(
                project_id=project_id,
                with_media_prompts=with_media_prompts,
                media_prompt_style=media_prompt_style,
                model_name=text_model_name,
                api_key=text_api_key,
            )
            if not text_result["success"]:
                return self._failed_video_result(project_id, text_result.get("error") or "文案生成失败")
            text = text_result["content"]
            prompts = text_result["prompts"]
            lines = text.split("\n") if text else []
            audio_result = self._gen_audios(
                project_id=project_id,
                lines=lines,
                model_name=audio_model_name,
                api_key=audio_api_key,
                voice=voice,
                cancel_event=cancel_event,
            )
            if audio_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not audio_result["success"]:
                return self._failed_video_result(project_id, audio_result.get("error") or "音频生成失败")
            audio_files = audio_result["audios"]
            durations = audio_result["durations"]
            image_result = self._gen_images(
                project_id=project_id,
                lines=prompts,
                model_name=image_model_name,
                api_key=image_api_key,
                n=n,
                size=size,
                cancel_event=cancel_event,
            )
            if image_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not image_result["success"]:
                return self._failed_video_result(project_id, image_result.get("error") or "图像生成失败")
            image_files = image_result["images"]
        elif "story" in style:
            print("混合模式: story + math")
            # 混合模式：故事中嵌入数学标记
            article = get_config_value("article", "")
            if not article:
                text_result = self.gen_texts(
                    project_id=project_id,
                    with_media_prompts=with_media_prompts,
                    media_prompt_style=media_prompt_style,
                    model_name=text_model_name,
                    api_key=text_api_key,
                )
                if not text_result["success"]:
                    return self._failed_video_result(project_id, text_result.get("error") or "文案生成失败")
                article = text_result["content"]
                prompts = text_result["prompts"]

            # 调用story_pipeline处理数学标记，使用相同的模型处理数学
            math_output_dir = self._prepare_fresh_output_dir(self._math_animations_dir(project_id))
            story_result = run_story_pipeline(
                story=article,
                model_name=text_model_name,
                api_key=text_api_key,
                math_model_name=text_model_name,  # 使用相同的模型
                math_api_key=text_api_key,
                math_output_dir=math_output_dir,
            )
            self._persist_story_artifacts(project_id, story_result)
            story_world_result = self._prepare_story_world(
                project_id=project_id,
                image_model_name=image_model_name,
                image_api_key=image_api_key,
                story_result=story_result,
            )
            if not story_world_result.get("success"):
                return self._failed_video_result(
                    project_id,
                    story_world_result.get("error") or "故事世界构建失败",
                )
            self._index_math_scripts(project_id, math_output_dir)
            self._register_artifact(project_id, "math", "animation_files", story_result.get("math_animation_files", []))
            self._register_artifact(project_id, "math", "animation_dir", str(math_output_dir.relative_to(self._project_dir(project_id))).replace("\\", "/"))

            # 提取segments
            segments = story_result.get("segments", [])
            math_animation_files = story_result.get("math_animation_files", [])
            has_math = story_result.get("has_math", False)

            print(f"混合模式得到 {len(segments)} 个segments，其中包含数学: {has_math}")

            # 处理混合segments
            lines = []
            prompts = []
            durations = []
            audio_files = []
            image_files = []
            math_animations = []

            for seg in segments:
                seg_type = seg.get("type", "story")
                if seg_type == "story":
                    text = seg.get("text", "")
                    lines.append(text)
                    prompts.append(seg)
                    math_animations.append("")  # story segment 无数学动画
                elif seg_type == "math":
                    narration = seg.get("narration", "")
                    background_prompt = seg.get("background_prompt", "")
                    math_anim_path = seg.get("math_animation_path", "")
                    lines.append(narration)
                    prompts.append(
                        background_prompt
                        if background_prompt
                        else "abstract background, neutral colors"
                    )
                    math_animations.append(math_anim_path)
                else:
                    # 未知类型，跳过
                    continue

            # 生成音频（所有lines）
            # 检查取消
            if cancel_event and cancel_event.is_set():
                print("视频生成任务被取消")
                return self._cancelled_video_result(project_id)
            audio_result = self._gen_audios(
                project_id=project_id,
                lines=lines,
                model_name=audio_model_name,
                api_key=audio_api_key,
                voice=voice,
                cancel_event=cancel_event,
            )
            if audio_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not audio_result["success"]:
                return self._failed_video_result(project_id, audio_result.get("error") or "音频生成失败")
            audio_files = audio_result["audios"]
            durations = audio_result["durations"]

            if cancel_event and cancel_event.is_set():
                print("视频生成任务被取消")
                return self._cancelled_video_result(project_id)

            image_result = self._gen_images(
                project_id=project_id,
                lines=prompts,
                model_name=image_model_name,
                api_key=image_api_key,
                n=n,
                size=size,
                cancel_event=cancel_event,
            )
            if image_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not image_result["success"]:
                return self._failed_video_result(project_id, image_result.get("error") or "图像生成失败")
            image_files = image_result["images"]

            while len(image_files) < len(prompts):
                image_files.append("")

            set_progress_data(project_id=project_id, key="images", data=image_files)

            if len(image_files) > len(prompts):
                image_files = image_files[: len(prompts)]
                set_progress_data(project_id=project_id, key="images", data=image_files)

            if len(prompts) != len(image_files):
                raise ValueError("story 模式图像数量与 prompts 数量不一致")

            if len(math_animations) != len(image_files):
                raise ValueError("story 模式数学动画数量与图像数量不一致")

            if len(audio_files) != len(image_files) or len(durations) != len(image_files):
                raise ValueError("story 模式音频/时长/图像数量不一致")

            if len(lines) != len(image_files):
                raise ValueError("story 模式文案与图像数量不一致")

            set_progress_data(project_id=project_id, key="prompts", data=prompts)

            image_configs = [
                {
                    "image_model_name": image_model_name,
                    "image_api_key": image_api_key,
                    "prompt": prompt if isinstance(prompt, str) else prompt.get("image_prompt", prompt.get("media_prompt", "")),
                    "text": prompt if isinstance(prompt, str) else prompt.get("text", prompt.get("image_prompt", prompt.get("media_prompt", ""))),
                    "n": n,
                    "size": size,
                    "render_mode": "story_shot" if isinstance(prompt, dict) and prompt.get("type") == "story" else "prompt",
                    "story_segment": dict(prompt) if isinstance(prompt, dict) and prompt.get("type") == "story" else None,
                }
                for prompt in prompts
            ]
            set_progress_data(project_id=project_id, key="images_configs", data=image_configs)

            valid_image_count = sum(1 for path in image_files if path)
            update_progress(
                project_id=project_id,
                percent=99,
                stage=f"已经生成第{valid_image_count}/{len(prompts)}个文案图像",
            )

            assert len(lines) == len(prompts) == len(audio_files) == len(durations) == len(image_files) == len(math_animations)

            if has_math:
                non_empty_math = sum(1 for m in math_animations if m)
                assert non_empty_math == sum(1 for seg in segments if seg.get("type") == "math")

            set_progress_data(project_id=project_id, key="lines", data=lines)
            set_progress_data(project_id=project_id, key="audios", data=audio_files)
            set_progress_data(project_id=project_id, key="durations", data=durations)
            set_progress_data(project_id=project_id, key="math_animations", data=math_animations)
            set_progress_data(project_id=project_id, key="math_animations_dir", data=str(math_output_dir).replace("\\", "/"))


        # else:
        #     # 纯故事模式
        #     if  hasattr(config, 'article') and config.article:
        #         article = config.article
        #     else:
        #         article,prompts=self.gen_texts(project_id=project_id,with_image_prompts=True,model_name=text_model_name,api_key=text_api_key)
        #     story_result = run_story_pipeline(story=article,model_name=text_model_name,api_key=text_api_key)
        #     # 兼容旧版本：检查返回值类型
        #     if isinstance(story_result, dict) and "segments" in story_result:
        #         # 新版本：提取lines和prompts
        #         segments = story_result.get("segments", [])
        #         lines = [seg.get("text", "") for seg in segments if seg.get("type") == "story"]
        #         prompts = [seg.get("image_prompt", "") for seg in segments if seg.get("type") == "story"]
        #     else:
        #         # 旧版本：直接解包
        #         lines, prompts = story_result
        #     print("len of prompts:",len(prompts))
        #     print("len of tts texts:",len(lines))
        #     assert len(prompts)==len(lines)
        #     # 检查取消
        #     if cancel_event and cancel_event.is_set():
        #         print("视频生成任务被取消")
        #         return None
        #     audio_files,durations=self._gen_audios(project_id=project_id,lines=lines,model_name=audio_model_name,api_key=audio_api_key,voice=voice,cancel_event=cancel_event)
        #     image_files=self._gen_images(project_id=project_id,lines=prompts,model_name=image_model_name,api_key=image_api_key,n=n,size=size,cancel_event=cancel_event)

        # # 检查取消
        if cancel_event and cancel_event.is_set():
            print("视频生成任务被取消")
            return self._cancelled_video_result(project_id)
        final_video_path = self._compose_video_by_style(
            project_id=project_id,
            style=style,
            lines=lines,
            image_files=image_files,
            audio_files=audio_files,
            durations=durations,
            math_animations=math_animations,
        )
        self._finalize_video_task(project_id, final_video_path)
        return self._video_result(True, video_path=final_video_path, **self._build_partial_video_payload(project_id))

    def _ensure_project_loaded(self, project_id: str):
        if project_id not in self.projects:
            loaded = self.load_project(project_id)
            if not loaded:
                raise ValueError(f"project not found or failed to load: {project_id}")

    def rebuild_video(self, project_id: str):
        self._ensure_project_loaded(project_id)
        current_status = get_progress_status(project_id=project_id)
        print("start rebuild video,current status:", current_status)
        config = self.projects[project_id]["config"]
        image_model_name = config.get("image_model_name")
        if image_model_name is None:
            raise ValueError("image model name should not be None Type.")
        image_api_key = config.get("image_api_key")
        if image_api_key is None:
            raise ValueError("image api key should not be None Type.")

        if current_status in {"in_building_characters", "in_building_scenes"}:
            print("continue from story world preparation stage.")
            self._restore_story_world_if_needed(project_id, image_model_name, image_api_key)
            current_status = "in_image_progress"
            set_progress_status(project_id=project_id, status=current_status)

        cascade = False
        if current_status == "in_text_progress":
            text_config = get_progress_data(project_id=project_id, key="text_config")
            text_config = self.projects[project_id]["config"]
            if text_config is None:
                raise ValueError("text_config should not be NoneType.")
            text_model_name = text_config.get("text_model_name")
            if text_model_name is None:
                raise ValueError("text_model_name should not be NoneType.")
            text_api_key = text_config.get("text_api_key")
            if text_api_key is None:
                raise ValueError("text_api_key should not be NoneType.")
            style = text_config.get("style")
            if style is None:
                raise ValueError("text style should not be NoneType.")
            theme = text_config.get("theme")
            if theme is None:
                raise ValueError("text theme should not be NoneType.")
            text = get_progress_data(project_id=project_id, key="text")
            if text is None:
                print("在重构项目时，发现text并未生成/保存，重新生成文案")
                text_result = self.gen_texts(
                    project_id=project_id,
                    with_media_prompts=with_media_prompts,
                    media_prompt_style=media_prompt_style,
                    model_name=text_model_name,
                    api_key=text_api_key,
                    theme=theme,
                    style=style,
                )
                if not text_result["success"]:
                    raise ValueError(text_result.get("error") or "文案生成失败")
                text = text_result["content"]
            texts = text.replace("\n\n", "\n").split("\n")
            prompts = get_progress_data(project_id=project_id, key="prompts")
            if prompts is None:
                print("在重构项目时，发现prompts并未生成/保存，开始生成 media prompt")
                prompts = self.gen_prompts(
                    project_id=project_id,
                    text=text,
                    model_name=text_model_name,
                    api_key=text_api_key,
                    media_prompt_style=self._get_project_config_value(project_id, "media_prompt_style", "image_default"),
                )

            if len(prompts) != len(texts):
                print("在重构项目时，发现text的行数和prompts个数不一致，继续生成图像提示词")
                start_index = len(prompts)
                prompts = self.gen_prompts(
                    project_id=project_id,
                    text=text,
                    model_name=text_model_name,
                    api_key=text_api_key,
                    start_index=start_index,
                )

            cascade = True

        cascade2 = False
        if current_status == "in_audio_progress" or (cascade is True):
            text = get_progress_data(project_id=project_id, key="text")
            texts = text.replace("\n\n", "\n").split("\n")
            # texts=[audio_config["text"] for audio_config in audios_configs]
            audios = get_progress_data(project_id=project_id, key="audios")
            print("config====", self.projects[project_id]["config"])
            audio_model_name = self.projects[project_id]["config"]["audio_model_name"]
            if audio_model_name is None:
                raise ValueError("audio model name should not be None Type.")
            audio_api_key = self.projects[project_id]["config"]["audio_api_key"]
            if audio_api_key is None:
                raise ValueError("audio api key should not be None Type.")
            voice = self.projects[project_id]["config"]["voice"]
            if voice is None:
                raise ValueError("voice should not be None Type.")

            if audios is None or cascade is True:
                self._ensure_audio_configs(
                    project_id=project_id,
                    lines=texts,
                    model_name=audio_model_name,
                    api_key=audio_api_key,
                    voice=voice,
                )
                audios, durations = self._gen_audios(
                    project_id=project_id,
                    lines=texts,
                    model_name=audio_model_name,
                    api_key=audio_api_key,
                    voice=voice,
                )

            if len(audios) != len(texts):
                audios, durations = self._gen_audios(
                    project_id=project_id,
                    lines=texts,
                    model_name=audio_model_name,
                    api_key=audio_api_key,
                    voice=voice,
                    start_index=len(audios),
                )

            cascade2 = True

        if current_status == "in_image_progress" or (cascade is True):
            print("continue from in_image_progress.")
            prompts = get_progress_data(project_id=project_id, key="prompts")
            images = get_progress_data(project_id=project_id, key="images")

            image_model_name = self.projects[project_id]["config"]["image_model_name"]
            if image_model_name is None:
                raise ValueError("image model name should not be None Type.")
            image_api_key = self.projects[project_id]["config"]["image_api_key"]
            if image_api_key is None:
                raise ValueError("image api key should not be None Type.")
            n = self.projects[project_id]["config"]["n"]
            if n is None:
                raise ValueError("image number should not be None Type.")
            size = self.projects[project_id]["config"]["size"]
            if size is None:
                raise ValueError("image size should not be None Type.")

            if images is None or cascade is True:
                images_configs = [
                    {
                        "image_model_name": image_model_name,
                        "image_api_key": image_api_key,
                        "n": n,
                        "size": size,
                        "text": prompts[i] if isinstance(prompts[i], str) else prompts[i].get("text", prompts[i].get("image_prompt", "")),
                        "prompt": prompts[i] if isinstance(prompts[i], str) else prompts[i].get("image_prompt", ""),
                        "render_mode": "story_shot" if isinstance(prompts[i], dict) and prompts[i].get("type") == "story" else "prompt",
                        "story_segment": dict(prompts[i]) if isinstance(prompts[i], dict) and prompts[i].get("type") == "story" else None,
                    }
                    for i in range(len(prompts))
                ]
                set_progress_data(project_id=project_id, key="images_configs", data=images_configs)
                images = self._gen_images(
                    project_id=project_id,
                    lines=prompts,
                    model_name=image_model_name,
                    api_key=image_api_key,
                    n=n,
                    size=size,
                )

            if len(images) != len(prompts):
                images = self._gen_images(
                    project_id=project_id,
                    lines=prompts,
                    model_name=image_model_name,
                    api_key=image_api_key,
                    n=n,
                    size=size,
                    start_index=len(images),
                )

            cascade2 = True

        if current_status in {"in_video_progress", "in_video_concat"} or (cascade2 is True):
            print("continue from video output stage.")
            lines = get_progress_data(project_id=project_id, key="lines")
            print("lines====", lines)
            image_files = get_progress_data(project_id=project_id, key="images")
            print("images====", image_files)
            audio_files = get_progress_data(project_id=project_id, key="audios")
            print("audios====", audio_files)
            durations = get_progress_data(project_id=project_id, key="durations")
            print("durations====", durations)
            style = self.projects[project_id]["config"].get("style", "")
            self._validate_video_resume_assets(lines, image_files, audio_files, durations)
            self._prepare_video_concat_resume(project_id)
            video_path = self._resume_video_segments_or_render(
                project_id=project_id,
                style=style,
                lines=lines,
                image_files=image_files,
                audio_files=audio_files,
                durations=durations,
            )
            self._finalize_video_task(project_id, video_path)

        return get_progress_data(project_id=project_id, key="video_path")

    def _create_video(self, project_id, images, audios, durations, output_path, fps=30):
        """
        将多张图像与对应音频拼接为完整视频
        Args:
            images: list[str] 图片路径
            audios: list[str] 音频路径
            durations: list[float] 每段音频时长
            output_path: 最终视频输出路径
            fps: 帧率
        """

        assert len(images) == len(audios) == len(durations), "图片、音频、时长数量必须一致"

        segments_dir = self._prepare_fresh_output_dir(self._video_segments_mode_dir(project_id, "story"))
        temp_videos = []

        # 1️⃣ 为每个片段生成视频（图像+音频）
        for i, (img, audio, dur) in enumerate(zip(images, audios, durations)):
            clip_path = segments_dir / f"clip_{i:04d}.mp4"
            print(f"[CreateVideo] clip={i} image={img} audio={audio} duration={dur}")
            video_center = ffmpeg.input(img, loop=1, t=dur, framerate=fps)

            video_input = video_center
            audio_input = ffmpeg.input(audio)
            ffmpeg_cmd = ffmpeg.output(
                video_input,
                audio_input,
                str(clip_path),
                vcodec="libx264",
                pix_fmt="yuv420p",
                acodec="aac",
            ).overwrite_output()
            self._run_ffmpeg_with_timeout(ffmpeg_cmd, timeout=30)

            temp_videos.append(str(clip_path).replace("\\", "/"))
            print(f"✅ 片段 {i} 合成完成：{clip_path}")

        self._concat_video_segments(project_id, segments_dir, temp_videos, output_path)

        self._set_video_artifact_metadata(
            project_id,
            mode="story",
            segments_dir=segments_dir,
            segment_paths=temp_videos,
        )
        return output_path

    def _create_mixed_video(self, project_id, image_files, audio_files, math_layers, durations, video_path):
        """
        合成混合视频（故事背景 + 数学动画叠加）

        Args:
            image_files: 背景图像文件列表（可能为空字符串表示无背景）
            audio_files: 音频文件列表
            math_layers: 数学动画文件列表（可能为空字符串表示无动画）
            durations: 每个片段的时长（秒）
            video_path: 输出视频路径
        """
        print("合成混合视频（故事背景 + 数学动画）……")
        print(f"输出视频路径: {video_path}")
        print(f"背景图像数量: {len(image_files)}")
        print(f"音频文件数量: {len(audio_files)}")
        print(f"数学动画数量: {len([m for m in math_layers if m])}（非空）")
        print(f"时长列表数量: {len(durations)}")
        print(f"背景图像列表: {image_files}")
        print(f"音频文件列表: {audio_files}")
        print(f"数学动画列表: {math_layers}")
        print(f"时长列表: {durations}")

        RESOLUTION = (1920, 1080)
        FPS = 30

        # 验证并处理输入
        n = min(len(image_files), len(audio_files), len(math_layers), len(durations))
        if n == 0:
            print("错误：没有可用的数据")
            return

        print(f"使用 {n} 个片段进行合成")

        segments_dir = self._prepare_fresh_output_dir(self._video_segments_mode_dir(project_id, "mixed"))
        temp_clips = []

        try:
            for i in range(n):
                print(f"处理片段 {i + 1}/{n}")
                image_file = image_files[i]
                audio_file = audio_files[i]
                math_file = math_layers[i] if i < len(math_layers) else ""
                raw_duration = durations[i]
                print(
                    f"  片段原始数据 image={image_file}, audio={audio_file}, math={math_file}, duration={raw_duration}"
                )
                duration = float(raw_duration)

                print(
                    f"  文件存在性 image={self._is_valid_media_file(image_file)}, "
                    f"audio={self._is_valid_media_file(audio_file)}, "
                    f"math={self._is_valid_media_file(math_file)}"
                )

                if not self._is_valid_media_file(audio_file):
                    raise FileNotFoundError(f"片段 {i} 缺少有效音频文件: {audio_file}")

                if duration <= 0:
                    print(f"警告：片段 {i} 时长为 {duration}，使用默认时长 5 秒")
                    duration = 5.0

                # 片段输出文件
                clip_path = segments_dir / f"clip_{i:04d}.mp4"

                # 处理背景
                if self._is_valid_media_file(image_file):
                    # 使用图像作为背景
                    print(f"  使用背景图像: {image_file}")
                    background = ffmpeg.input(image_file, loop=1, t=duration, framerate=FPS)

                    if self._is_valid_media_file(math_file):
                        print(f"  叠加数学动画: {math_file}")
                        # 输入0: 背景图像，输入1: 数学动画
                        # 缩放数学动画到合适大小并居中
                        video = ffmpeg.filter(background, "setsar", "1").overlay(
                            ffmpeg.input(math_file)
                            .filter("scale", RESOLUTION[0], RESOLUTION[1])
                            .filter("setsar", "1"),
                            x="(W-w)/2",
                            y="(H-h)/2",
                        )
                    else:
                        # 只有背景图像，无数学动画
                        video = ffmpeg.filter(background, "setsar", "1")
                else:
                    # 无背景图像，使用褐色背景（fallback）
                    BROWN_COLOR = "0x8B4513"
                    print(f"  无背景图像，使用褐色背景")
                    bg_filter = f"color=c={BROWN_COLOR}:s={RESOLUTION[0]}x{RESOLUTION[1]}:r={FPS}:d={duration}"
                    background = ffmpeg.input(bg_filter, f="lavfi")

                    if self._is_valid_media_file(math_file):
                        print(f"  叠加数学动画: {math_file}")
                        video = ffmpeg.filter(background, "setsar", "1").overlay(
                            ffmpeg.input(math_file)
                            .filter("scale", RESOLUTION[0], RESOLUTION[1])
                            .filter("setsar", "1"),
                            x="(W-w)/2",
                            y="(H-h)/2",
                        )
                    else:
                        # 只有褐色背景
                        video = ffmpeg.filter(background, "setsar", "1")

                # 合成片段（视频 + 音频）
                print(f"  开始输出片段到: {clip_path}")
                try:
                    (
                        ffmpeg.output(
                            video,
                            ffmpeg.input(audio_file),
                            str(clip_path),
                            vcodec="libx264",
                            acodec="aac",
                            pix_fmt="yuv420p",
                            r=FPS,
                            t=duration,
                            shortest=None,
                        )
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True)
                    )
                except ffmpeg.Error as clip_error:
                    clip_stderr = getattr(clip_error, "stderr", None)
                    clip_stderr_text = clip_stderr.decode(errors="replace") if isinstance(clip_stderr, (bytes, bytearray)) else str(clip_stderr or clip_error)
                    print(f"  片段 {i} ffmpeg 输出失败: {clip_stderr_text}")
                    raise

                if not os.path.exists(clip_path):
                    raise FileNotFoundError(f"片段 {i} 输出文件不存在: {clip_path}")

                clip_size = os.path.getsize(clip_path)
                print(f"  片段输出完成: {clip_path}, size={clip_size}")
                temp_clips.append(str(clip_path).replace("\\", "/"))

            print(f"临时片段列表: {temp_clips}")
            self._concat_video_segments(project_id, segments_dir, temp_clips, video_path)

            if os.path.exists(video_path):
                print(f"混合视频输出存在: {video_path}, size={os.path.getsize(video_path)}")
            else:
                print(f"混合视频输出不存在: {video_path}")

            self._set_video_artifact_metadata(
                project_id,
                mode="mixed",
                segments_dir=segments_dir,
                segment_paths=temp_clips,
                math_animations=math_layers,
                math_animations_dir=self._math_animations_dir(project_id),
            )
            print(f"混合视频合成完成: {video_path}")

        except ffmpeg.Error as e:
            stderr = getattr(e, "stderr", None)
            stderr_text = stderr.decode(errors="replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr or e)
            print(f"FFmpeg 错误: {stderr_text}")
            raise
        except Exception as e:
            print(f"合成混合视频时出错: {e}")
            raise
        finally:
            pass

    def _create_math_video_retrieval(
        self, project_id, image_files, audio_files, text_layers, math_layers, durations, video_path, concat_final: bool = True
    ):
        """
        合成数学视频（褐色背景），对接 animate_math_layers 生成的动画

        Args:
            image_files: 忽略（不需要人物图像）
            audio_files: 音频文件列表
            text_layers: 忽略（不需要文字层）
            math_layers: animate_math_layers 生成的数学动画文件列表 (.mov)
            durations: 每个片段的时长（秒）
            video_path: 输出视频路径
        """
        print(f"数学动画文件数量: {len(math_layers)}")
        print(f"音频文件数量: {len(audio_files)}")
        print(f"时长列表数量: {len(durations)}")

        # 褐色背景颜色 (saddlebrown)
        BROWN_COLOR = "0x8B4513"
        RESOLUTION = (1920, 1080)
        FPS = 30

        # 验证并处理输入
        n = min(len(audio_files), len(math_layers), len(durations))
        if n == 0:
            print("错误：没有可用的音频、动画或时长数据")
            return

        print(f"使用 {n} 个片段进行合成")

        segments_dir = self._prepare_fresh_output_dir(self._video_segments_mode_dir(project_id, "math"))
        temp_clips = []

        try:
            for i in range(n):
                print(f"处理片段 {i + 1}/{n}")
                bg_file= image_files[i]
                audio_file = audio_files[i]
                math_file = math_layers[i] if i < len(math_layers) else ""
                duration = float(durations[i])

                if duration <= 0:
                    print(f"警告：片段 {i} 时长为 {duration}，使用默认时长 5 秒")
                    duration = 5.0

                # 片段输出文件
                clip_path = segments_dir / f"clip_{i:04d}.mp4"

                if self._is_valid_media_file(math_file):
                    print(f"  叠加数学动画: {math_file}")
                    # 输入0: 褐色背景，输入1: 数学动画
                    # 缩放数学动画到合适大小并居中
                    (
                       ffmpeg
                            .input(bg_file)  # ✅ 背景视频作为底层
                            .filter("scale", RESOLUTION[0], RESOLUTION[1])
                            .filter("setsar", "1")

                            # ✅ 叠加 math layer
                            .overlay(
                                ffmpeg.input(math_file)
                                .filter("scale", RESOLUTION[0], RESOLUTION[1])
                                .filter("setsar", "1"),
                                x="(W-w)/2",
                                y="(H-h)/2",
                            )

                            # ✅ 输出 + 音频
                            .output(
                                ffmpeg.input(audio_file),
                                str(clip_path),
                                vcodec="libx264",
                                acodec="aac",
                                pix_fmt="yuv420p",
                                r=FPS,
                                t=duration,
                                shortest=None,
                            )
                            .overwrite_output()
                            .run()

                    )
                else:
                    print(f"  无数学动画，仅褐色背景")
                    # 只有褐色背景和音频
                    (
                        ffmpeg.input(bg_filter, f="lavfi")
                        .output(
                            ffmpeg.input(audio_file),
                            str(clip_path),
                            vcodec="libx264",
                            acodec="aac",
                            pix_fmt="yuv420p",
                            r=FPS,
                            t=duration,
                            shortest=None,
                        )
                        .overwrite_output()
                        .run()
                    )

                temp_clips.append(str(clip_path).replace("\\", "/"))

            if concat_final:
                self._concat_video_segments(project_id, segments_dir, temp_clips, video_path)

                self._set_video_artifact_metadata(
                    project_id,
                    mode="math",
                    segments_dir=segments_dir,
                    segment_paths=temp_clips,
                    math_animations=math_layers,
                    math_animations_dir=self._math_animations_dir(project_id),
                )
                print(f"数学视频合成完成: {video_path}")
            elif temp_clips:
                final_dir = Path(video_path).parent
                final_dir.mkdir(parents=True, exist_ok=True)
                import shutil

                shutil.copy2(temp_clips[-1], video_path)


        except ffmpeg.Error as e:
            stderr = getattr(e, "stderr", None)
            stderr_text = stderr.decode(errors="replace") if isinstance(stderr, (bytes, bytearray)) else str(stderr or e)
            print(f"FFmpeg 错误: {stderr_text}")
            raise
        except Exception as e:
            print(f"合成数学视频时出错: {e}")
            raise
        finally:
            pass


    async def async_rebuild_video(
        self,
        project_id: str,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        register_progress_callback(project_id, progress_cb)

        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}

            self._ensure_project_loaded(project_id)
            rebuild_result = await asyncio.to_thread(self.gen_video, project_id, cancel_event)

            if cancel_event.is_set() or rebuild_result.get("cancelled"):
                return {"status": "cancelled", "project_id": project_id}
            if not rebuild_result["success"]:
                self._persist_project_failure(project_id, rebuild_result.get("error") or "视频重建失败")
                return {
                    "status": "error",
                    "project_id": project_id,
                    "error": rebuild_result.get("error") or "视频重建失败",
                    "snapshot": self.get_project_snapshot(project_id),
                    **self._build_partial_video_payload(project_id),
                }

            snapshot = self.get_project_snapshot(project_id)
            result = {
                "status": "completed",
                "project_id": project_id,
                "video_path": rebuild_result["video_path"],
                "snapshot": snapshot,
            }
            task_data = TASKS.get(project_id, {})
            if "text" in task_data:
                result["text"] = task_data["text"]
            if "lines" in task_data:
                result["lines"] = task_data["lines"]
            for key in ["images", "audios", "durations", "prompts", "images_configs", "audios_configs", "math_scripts", "math_script_files", "clips", "video_segments", "math_animations"]:
                if key in task_data:
                    result[key] = task_data[key]
            return result
        except asyncio.CancelledError:
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            try:
                self.save_project(project_id)
            except Exception as save_error:
                print(f"[async_rebuild_video] save_project failed after rebuild error: {save_error}")
            return {"status": "error", "project_id": project_id, "error": str(e)}
        finally:
            unregister_progress_callback(project_id)

    async def async_generate_video_retrieval(
        self,
        project_id: str,
        config: Dict,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        register_progress_callback(project_id, progress_cb)
        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}

            self.update_config(project_id, config)
            result = await asyncio.to_thread(self.gen_video_retrieval, project_id, cancel_event)
            if cancel_event.is_set() or result.get("cancelled"):
                return {"status": "cancelled", "project_id": project_id}
            if not result.get("success"):
                self._persist_project_failure(project_id, result.get("error") or "视频检索生成失败")
                return {
                    "status": "error",
                    "project_id": project_id,
                    "error": result.get("error") or "视频检索生成失败",
                    "snapshot": self.get_project_snapshot(project_id),
                    **self._build_partial_video_payload(project_id),
                }

            self.save_project(project_id)
            return {
                "status": "completed",
                "project_id": project_id,
                "video_path": result.get("video_path", ""),
                "snapshot": self.get_project_snapshot(project_id),
                **self._build_partial_video_payload(project_id),
            }
        except asyncio.CancelledError:
            try:
                self.save_project(project_id)
            except Exception:
                pass
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            task_data = TASKS.setdefault(project_id, {})
            task_data["error"] = str(e)
            if task_data.get("status") != "completed":
                task_data["status"] = "error"
            try:
                self.save_project(project_id)
            except Exception:
                pass
            return {
                "status": "error",
                "project_id": project_id,
                "error": str(e),
                "snapshot": self.get_project_snapshot(project_id),
                **self._build_partial_video_payload(project_id),
            }
        finally:
            unregister_progress_callback(project_id)

    def gen_video_retrieval(self, project_id: str, cancel_event=None):
        if cancel_event and cancel_event.is_set():
            return self._cancelled_video_result(project_id)

        config = self.projects[project_id]["config"]

        def get_config_value(key, default=""):
            if isinstance(config, dict):
                val = config.get(key, default)
                return val if val is not None else default
            val = getattr(config, key, default)
            return val if val is not None else default

        text_model_name = get_config_value("text_model_name", "")
        text_api_key = get_config_value("text_api_key", "")
        theme = get_config_value("theme", "")
        style = get_config_value("style", "")
        if (style or "").strip().lower() == "story":
            return self._failed_video_result(project_id, "video retrieval 不再支持 story 风格")
        audio_model_name = get_config_value("audio_model_name", "")
        audio_api_key = get_config_value("audio_api_key", "")
        voice = get_config_value("voice", "")
        annotation_root = get_config_value("annotation_root", "")
        media_service_base_url = get_config_value("media_service_base_url", "http://127.0.0.1:6000")
        media_service_timeout_sec = float(get_config_value("media_service_timeout_sec", 180.0) or 180.0)
        top_k_per_line = int(get_config_value("top_k_per_line", 3) or 3)
        prefer_media_type = get_config_value("prefer_media_type", "auto")
        search_mode = get_config_value("search_mode", "window_level")
        ranking_strategy = get_config_value("ranking_strategy", "cascade_sequence_v1")
        window_annotation_root = get_config_value("window_annotation_root", "/root/media_service_test_assets/window_scan_out")
        window_level_preferred = bool(get_config_value("window_level_preferred", True))
        coarse_top_n = int(get_config_value("coarse_top_n", 50) or 50)
        fine_top_k = int(get_config_value("fine_top_k", 10) or 10)
        media_prompt_style = get_config_value("media_prompt_style", "retrieval_default")
        with_media_prompts = bool(get_config_value("with_media_prompts", True))
        math_background_enabled = bool(get_config_value("math_background_enabled", True))

        is_math_mode = self._is_math_style(style)

        lines: List[str] = []
        retrieval_queries: List[str] = []
        retrieval_query_units: List[Dict[str, Any]] = []
        retrieval_query_durations: List[float] = []
        audio_files: List[str] = []
        durations: List[float] = []
        line_foreground_layers: List[str] = []

        update_progress(project_id, 5, "正在生成检索视频文案")
        if is_math_mode:
            prepare_result = self._prepare_math_retrieval_project(
                project_id=project_id,
                text_model_name=text_model_name,
                text_api_key=text_api_key,
                audio_model_name=audio_model_name,
                audio_api_key=audio_api_key,
                voice=voice,
                theme=theme,
                with_media_prompts=with_media_prompts,
                media_prompt_style=media_prompt_style,
                media_model_name=get_config_value("image_model_name", ""),
                language=get_config_value("language", ""),
                cancel_event=cancel_event,
            )
            if prepare_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not prepare_result.get("success"):
                return self._failed_video_result(project_id, prepare_result.get("error") or "math 检索准备失败")

            lines = prepare_result.get("lines") or []
            retrieval_queries = prepare_result.get("retrieval_texts") or prepare_result.get("shot_texts") or lines
            retrieval_query_units = prepare_result.get("retrieval_query_units") or []
            retrieval_query_durations = prepare_result.get("retrieval_query_durations") or []
            audio_files = prepare_result.get("audio_files") or []
            durations = prepare_result.get("durations") or []
            line_foreground_layers = prepare_result.get("line_foreground_layers") or []
        else:
            text_result = self.gen_texts(
                project_id=project_id,
                with_media_prompts=with_media_prompts,
                media_prompt_style=media_prompt_style,
                model_name=text_model_name,
                api_key=text_api_key,
                theme=theme,
                style=style,
            )
            if not text_result["success"]:
                return self._failed_video_result(project_id, text_result.get("error") or "文案生成失败")

            text = text_result["content"]
            lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
            retrieval_prompts = [prompt.strip() for prompt in (text_result.get("prompts") or []) if isinstance(prompt, str) and prompt.strip()]
            retrieval_queries = retrieval_prompts if with_media_prompts and retrieval_prompts else lines
            set_progress_data(project_id=project_id, key="lines", data=lines)
            set_progress_data(project_id=project_id, key="prompts", data=retrieval_queries)

            if cancel_event and cancel_event.is_set():
                return self._cancelled_video_result(project_id)

            update_progress(project_id, 35, "正在生成检索视频音频")
            audio_result = self._gen_audios(
                project_id=project_id,
                lines=lines,
                model_name=audio_model_name,
                api_key=audio_api_key,
                voice=voice,
                cancel_event=cancel_event,
            )
            if audio_result.get("cancelled"):
                return self._cancelled_video_result(project_id)
            if not audio_result["success"]:
                return self._failed_video_result(project_id, audio_result.get("error") or "音频生成失败")

            audio_files = audio_result["audios"]
            durations = audio_result["durations"]
            set_progress_data(project_id=project_id, key="audios", data=audio_files)
            set_progress_data(project_id=project_id, key="durations", data=durations)

        if cancel_event and cancel_event.is_set():
            return self._cancelled_video_result(project_id)

        if not math_background_enabled:
            update_progress(project_id, 65, "math 背景检索已禁用，使用纯色背景")
            background_assets = [
                self._build_black_color_asset(
                    index=index,
                    text=lines[index] if index < len(lines) else "",
                    audio_path=audio_files[index] if index < len(audio_files) else "",
                    audio_duration=self._to_float(durations[index], 0.0) if index < len(durations) else 0.0,
                )
                for index in range(len(lines))
            ]
            retrieval_result = {
                "success": True,
                "background_assets": background_assets,
                "items": [],
                "empty_result_indices": [],
                "missing_head_keywords": [],
            }
        else:
            update_progress(project_id, 65, "正在调用 media_service 检索素材")
            client = MediaRetrievalClient(base_url=media_service_base_url, timeout=media_service_timeout_sec)
            retrieval_request_durations = durations
            if is_math_mode:
                if not retrieval_query_units:
                    fallback_units = [
                        {
                            "query_index": idx,
                            "scene_index": idx,
                            "line_index": idx,
                            "chunk_index": 0,
                            "text": str(text or "").strip(),
                            "duration": self._to_float(durations[idx], 5.0) if idx < len(durations) else 5.0,
                            "start": 0.0,
                            "end": self._to_float(durations[idx], 5.0) if idx < len(durations) else 5.0,
                        }
                        for idx, text in enumerate(lines)
                        if str(text or "").strip()
                    ]
                    retrieval_query_units = fallback_units
                    retrieval_queries = [str(unit.get("text") or "").strip() for unit in retrieval_query_units]
                    retrieval_query_durations = [self._to_float(unit.get("duration"), 0.0) for unit in retrieval_query_units]
                if not retrieval_query_durations or len(retrieval_query_durations) != len(retrieval_queries):
                    retrieval_query_durations = [self._to_float(unit.get("duration"), 0.0) for unit in retrieval_query_units]
                    if len(retrieval_query_durations) < len(retrieval_queries):
                        retrieval_query_durations.extend([5.0] * (len(retrieval_queries) - len(retrieval_query_durations)))
                    else:
                        retrieval_query_durations = retrieval_query_durations[: len(retrieval_queries)]
                if len(retrieval_queries) != len(retrieval_query_durations):
                    min_len = min(len(retrieval_queries), len(retrieval_query_durations))
                    retrieval_queries = retrieval_queries[:min_len]
                    retrieval_query_durations = retrieval_query_durations[:min_len]
                    retrieval_query_units = retrieval_query_units[:min_len]
                retrieval_request_durations = retrieval_query_durations
                set_progress_data(project_id=project_id, key="retrieval_chunk_units", data=retrieval_query_units)
                set_progress_data(project_id=project_id, key="retrieval_chunk_durations", data=retrieval_query_durations)

            if len(retrieval_request_durations) != len(retrieval_queries):
                print(
                    f"[math_retrieval] query/duration mismatch: queries={len(retrieval_queries)} durations={len(retrieval_request_durations)}"
                )

            retrieval_result = retrieve_background_assets(
                client=client,
                text=retrieval_queries,
                annotation_root=annotation_root,
                audio_paths=audio_files,
                audio_durations=retrieval_request_durations,
                top_k_per_line=top_k_per_line,
                prefer_media_type=prefer_media_type,
                search_mode=search_mode,
                ranking_strategy=ranking_strategy,
                window_annotation_root=window_annotation_root or None,
                window_level_preferred=window_level_preferred,
                coarse_top_n=coarse_top_n,
                fine_top_k=fine_top_k,
            )

            if is_math_mode:
                retrieval_result = self._build_math_retrieval_assets(
                    lines=lines,
                    retrieval_result=retrieval_result,
                    audio_files=audio_files,
                    durations=durations,
                    query_units=retrieval_query_units,
                )
            elif not retrieval_result.get("success"):
                retrieval_error = retrieval_result.get("error") or "素材检索失败"
                empty_result_indices = retrieval_result.get("empty_result_indices") or []
                missing_head_keywords = retrieval_result.get("missing_head_keywords") or []
                if empty_result_indices:
                    retrieval_error = f"素材检索失败：第{', '.join(str(i) for i in empty_result_indices)}条文案未检索到素材"
                set_progress_data(project_id=project_id, key="missing_head_keywords", data=missing_head_keywords)
                return self._failed_video_result(project_id, retrieval_error)

        set_progress_data(project_id=project_id, key="retrieval_items", data=retrieval_result.get("items", []))
        missing_head_keywords = retrieval_result.get("missing_head_keywords") or []
        set_progress_data(project_id=project_id, key="missing_head_keywords", data=missing_head_keywords)
        background_assets = retrieval_result.get("background_assets", [])
        set_progress_data(project_id=project_id, key="background_assets", data=background_assets)

        if cancel_event and cancel_event.is_set():
            return self._cancelled_video_result(project_id)

        if is_math_mode:
            final_video_path = self._build_retrieval_math_video(
                project_id=project_id,
                lines=lines,
                background_assets=background_assets,
                audio_files=audio_files,
                durations=durations,
                line_foreground_layers=line_foreground_layers,
            )
        else:
            final_video_path = self._build_retrieval_video(
                project_id=project_id,
                lines=lines,
                background_assets=background_assets,
                audio_files=audio_files,
                durations=durations,
            )

        update_progress(project_id, 100, "视频检索结果已生成")
        return self._video_result_with_assets(True, project_id, video_path=final_video_path)

    async def async_generate_video(
        self,
        project_id: str,
        config: Dict,
        cancel_event: asyncio.Event,
        progress_cb: Callable[[Dict], None],
    ):
        """
        可取消的异步视频生成（替代原 video_job 功能）

        Args:
            project_id: 项目ID
            config: 配置字典
            cancel_event: 取消事件，用于检查是否应该停止
            progress_cb: 进度回调函数

        Returns:
            Dict: 包含视频路径等信息
        """
        # 注册进度回调
        register_progress_callback(project_id, progress_cb)
        print(
            f"[async_generate_video] project_id: {project_id}, config type: {type(config)}, config keys: {list(config.keys()) if isinstance(config, dict) else 'not dict'}"
        )

        # 记录article字段详细信息
        if isinstance(config, dict):
            article = config.get("article")
            if article is not None:
                if isinstance(article, str):
                    print(
                        f"[async_generate_video] article content: length={len(article)}, preview: {article[:100]}{'...' if len(article) > 100 else ''}"
                    )
                else:
                    print(
                        f"[async_generate_video] WARNING: article is not string, type: {type(article)}, value: {article}"
                    )
            else:
                print(f"[async_generate_video] article is None")
        else:
            print(f"[async_generate_video] config is not dict, cannot check article directly")

        try:
            if cancel_event.is_set():
                return {"status": "cancelled", "project_id": project_id}

            self.update_config(project_id, config)
            video_result = await self._async_gen_video_with_cancel(project_id, config, cancel_event)

            if cancel_event.is_set() or video_result.get("cancelled"):
                return {"status": "cancelled", "project_id": project_id}
            if not video_result["success"]:
                self._persist_project_failure(project_id, video_result.get("error") or "视频生成失败")
                return {
                    "status": "error",
                    "project_id": project_id,
                    "error": video_result.get("error") or "视频生成失败",
                    "snapshot": self.get_project_snapshot(project_id),
                    **self._build_partial_video_payload(project_id),
                }

            self.save_project(project_id)

            result = {
                "status": "completed",
                "project_id": project_id,
                "video_path": video_result["video_path"],
                "snapshot": self.get_project_snapshot(project_id),
            }

            task_data = TASKS.get(project_id, {})
            if "text" in task_data:
                result["text"] = task_data["text"]
            if "lines" in task_data:
                result["lines"] = task_data["lines"]
            for key in ["images", "audios", "durations", "prompts", "images_configs", "audios_configs", "math_scripts", "math_script_files", "clips", "video_segments", "math_animations"]:
                if key in task_data:
                    result[key] = task_data[key]

            return result

        except asyncio.CancelledError:
            try:
                self.save_project(project_id)
            except Exception as save_error:
                print(f"[async_generate_video] save_project failed after cancel: {save_error}")
            return {"status": "cancelled", "project_id": project_id}
        except Exception as e:
            task_data = TASKS.setdefault(project_id, {})
            task_data["error"] = str(e)
            if task_data.get("status") != "completed":
                task_data["status"] = "error"
            try:
                self.save_project(project_id)
            except Exception as save_error:
                print(f"[async_generate_video] save_project failed after error: {save_error}")
            return {
                "status": "error",
                "project_id": project_id,
                "error": str(e),
                "snapshot": self.get_project_snapshot(project_id),
            }
        finally:
            unregister_progress_callback(project_id)

    async def _async_gen_video_with_cancel(
        self, project_id: str, config: Dict, cancel_event: asyncio.Event
    ):
        """
        支持取消的视频生成包装器 - 直接调用 gen_video 方法
        """

        # 定期检查取消事件
        async def check_cancel():
            if cancel_event.is_set():
                raise asyncio.CancelledError(f"任务被取消: {project_id}")

        # 检查取消
        await check_cancel()
        update_progress(project_id, 0, "正在生成视频...")

        try:
            # 调用同步的 gen_video 方法，传入 cancel_event 参数
            # 使用 asyncio.to_thread 避免阻塞事件循环
            video_result = await asyncio.to_thread(self.gen_video, project_id, cancel_event)

            # 再次检查取消
            await check_cancel()

            if video_result.get("cancelled"):
                raise asyncio.CancelledError(f"视频生成任务被取消: {project_id}")

            if video_result["success"]:
                update_progress(project_id, 100, "视频生成完成")
            return video_result

        except asyncio.CancelledError:
            # 任务被取消，重新抛出异常
            raise
        except Exception as e:
            print(f"视频生成过程中出错: {e}")
            task_data = TASKS.setdefault(project_id, {})
            if task_data.get("status") != "completed":
                task_data["status"] = "error"
            task_data["error"] = str(e)
            raise


pipelineManager = PipelineManager()


def getPipelineManager():
    return pipelineManager
