"""
FastAPI 服务端 - 为 MindAwaker 提供 HTTP API 接口
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.llm.shot_parser import ShotParser
from app.llm.prompt_builder import PromptBuilder
from app.scene.scene_builder import SceneBuilder
from app.scene.instance_builder import build_instance_from_shot_json
from app.scene.spatial_projector import (
    build_projector_from_camera_config, project_instance_objects,
    project_scene_data_objects, _save_mask_image,
)
from app.comfy.workflow_loader import create_workflow, create_regional_prompt_workflow
from app.comfy.client import ComfyUIClient
from app.pipeline.hierarchical_pipeline import HierarchicalPipeline
from app.pipeline.character_consistency import CharacterIdentity
from app.pipeline.character_library import CharacterDefinition
from app.schema.scene_hierarchy import SceneBlueprint, BlueprintObject
from app.scene.depth_renderer_headless import render_depth_headless

CHARACTER_TYPES = {"child", "adult", "boy", "girl", "man", "woman"}
TEMPLATE_ALIASES = {
    "room": "indoor_room",
    "indoor": "indoor_room",
    "house": "indoor_room",
    "street": "street",
    "city": "street",
    "bridge": "bridge_river",
    "river": "bridge_river",
}


def normalize_template_name(template_name: str) -> str:
    template = (template_name or "indoor_room").strip().lower()
    return TEMPLATE_ALIASES.get(template, template if template else "indoor_room")


def build_blueprint_objects(scene_spec: Dict[str, Any]) -> List[BlueprintObject]:
    objects = []
    for obj in scene_spec.get("objects", []):
        object_id = obj.get("id") or obj.get("object_id") or obj.get("name")
        object_type = obj.get("type") or obj.get("object_type") or "object"
        if not object_id:
            continue
        relation = obj.get("relation")
        description = obj.get("description")
        attributes = obj.get("attributes") or {}
        objects.append(
            BlueprintObject(
                id=str(object_id),
                type=str(object_type),
                relation=relation,
                description=description,
                attributes=attributes,
            )
        )
    return objects


def build_scene_metadata(scene_spec: Dict[str, Any]) -> Dict[str, Any]:
    metadata = {
        "location": scene_spec.get("location", ""),
        "time": scene_spec.get("time", ""),
        "emotion": scene_spec.get("emotion", ""),
        "chain_id": scene_spec.get("chain_id", ""),
        "style_prompt": scene_spec.get("style_prompt", ""),
        "source_scene_ids": scene_spec.get("source_scene_ids", []),
    }
    return metadata


def build_scene_character_bindings(
    scene_spec: Dict[str, Any],
    character_lookup: Dict[str, str],
) -> Dict[str, str]:
    bindings = {}
    explicit_bindings = scene_spec.get("character_bindings") or {}
    for object_id, source_character_id in explicit_bindings.items():
        bindings[str(object_id)] = character_lookup.get(source_character_id, source_character_id)

    for obj in scene_spec.get("objects", []):
        object_id = obj.get("id") or obj.get("object_id") or obj.get("name")
        source_character_id = obj.get("character_id")
        object_type = (obj.get("type") or obj.get("object_type") or "").lower()
        if not object_id:
            continue
        if source_character_id:
            bindings[str(object_id)] = character_lookup.get(source_character_id, source_character_id)
        elif object_type in CHARACTER_TYPES and str(object_id) in character_lookup:
            bindings[str(object_id)] = character_lookup[str(object_id)]

    return bindings


app = FastAPI(
    title="MindAwaker 3D-Guided T2I API",
    description="Structured narrative to controllable visual generation engine",
    version="0.1.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_dir = project_root / "web"
if web_dir.exists():
    app.mount("/web", StaticFiles(directory=str(web_dir)), name="web")

data_dir = project_root / "data"
if data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")

# 全局配置
CONFIG = {
    "comfy_url": "http://127.0.0.1:8188",
    "llm_provider": "deepseek",
    "output_dir": "./data/outputs"
}

# 初始化组件
shot_parser = ShotParser(provider=CONFIG["llm_provider"])
comfy_client = ComfyUIClient(server_url=CONFIG["comfy_url"])


# ========== 数据模型 ==========

class TextInput(BaseModel):
    text: str
    save_intermediate: bool = True


class ShotJSONInput(BaseModel):
    shot_json: dict
    save_intermediate: bool = True


class GenerateRequest(BaseModel):
    workflow: dict
    timeout: int = 300


class WorkflowBuildRequest(BaseModel):
    shot_json: dict
    save_intermediate: bool = True
    use_regional: bool = False
    mask_filenames: Optional[Dict[str, str]] = None


class DepthRenderRequest(BaseModel):
    scene_data: dict
    method: str = "auto"
    upload_to_comfy: bool = True


class DocumentLoadRequest(BaseModel):
    path: str


class DocumentSaveRequest(BaseModel):
    path: str
    data: Any


class CharacterSpec(BaseModel):
    character_id: str
    name: str = ""
    object_type: str = "adult"
    description: str = ""
    visual_core: str = ""
    key_features: List[str] = Field(default_factory=list)
    is_main_character: bool = True
    style_tags: List[str] = Field(default_factory=list)


class CharactersBuildRequest(BaseModel):
    characters: List[CharacterSpec] = Field(default_factory=list)


class SceneSpecInput(BaseModel):
    world_scene_id: str
    source_scene_ids: List[str] = Field(default_factory=list)
    template: str = "indoor_room"
    style_id: str = "default"
    location: str = ""
    time: str = ""
    emotion: str = ""
    chain_id: str = ""
    objects: List[Dict[str, Any]] = Field(default_factory=list)
    scene_visual_overrides: Dict[str, str] = Field(default_factory=dict)
    character_bindings: Dict[str, str] = Field(default_factory=dict)
    style_prompt: str = ""


class ScenesBuildRequest(BaseModel):
    scenes: List[SceneSpecInput] = Field(default_factory=list)
    character_bindings: Dict[str, str] = Field(default_factory=dict)


pipeline = HierarchicalPipeline(
    comfy_url=CONFIG["comfy_url"],
    llm_provider=CONFIG["llm_provider"],
    output_dir=CONFIG["output_dir"],
)


def _resolve_output_path(path_str: str) -> Path:
    output_root = (project_root / CONFIG["output_dir"]).resolve()
    target = Path(path_str).expanduser()
    if not target.is_absolute():
        target = (project_root / target).resolve()
    else:
        target = target.resolve()

    if output_root != target and output_root not in target.parents:
        raise HTTPException(status_code=400, detail="Only paths under output_dir are allowed")

    if target.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Only .json document paths are allowed")

    return target


# ========== API 路由 ==========

@app.get("/")
async def root():
    """根路径 - 服务状态"""
    return {
        "service": "MindAwaker 3D-Guided T2I",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


@app.post("/api/doc/load")
async def load_doc(request: DocumentLoadRequest):
    try:
        target = _resolve_output_path(request.path)
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"Document not found: {target}")

        with open(target, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return {
            "success": True,
            "path": str(target),
            "data": data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/doc/save")
async def save_doc(request: DocumentSaveRequest):
    try:
        target = _resolve_output_path(request.path)
        target.parent.mkdir(parents=True, exist_ok=True)

        with open(target, 'w', encoding='utf-8') as f:
            json.dump(request.data, f, indent=2, ensure_ascii=False)

        return {
            "success": True,
            "path": str(target),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/parse")
async def parse_text(input_data: TextInput):
    """
    将自然语言文本解析为 Shot JSON
    """
    try:
        shot_json = shot_parser.parse(input_data.text)

        # 保存到文件
        if input_data.save_intermediate:
            output_dir = Path(CONFIG["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot_path = output_dir / f"shot_{timestamp}.json"

            with open(shot_path, 'w', encoding='utf-8') as f:
                json.dump(shot_json, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "shot_json": shot_json,
                "saved_to": str(shot_path)
            }

        return {
            "success": True,
            "shot_json": shot_json
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _build_camera_from_shot(shot_json: Dict[str, Any]) -> Dict[str, Any]:
    """从 shot_json 构建相机配置"""
    from app.scene.templates import get_template

    VIEW_CAMERA_POSITIONS = {
        "front": (0, 2, 5),
        "side": (5, 2, 0),
        "top": (0, 8, 0),
        "three_quarter": (4, 3, 4),
        "low_angle": (4, 0.5, 4),
        "high_angle": (4, 6, 4),
    }

    template = get_template(shot_json.get("template", "indoor_room"))
    camera_def = shot_json.get("camera", {})
    view = camera_def.get("view", "side")

    default_pos = VIEW_CAMERA_POSITIONS.get(
        view,
        template.default_camera.get("position", (8, 3, 8)) if template else (8, 3, 8)
    )

    if "position" in camera_def:
        pos = camera_def["position"]
        default_pos = (
            pos.get("x", default_pos[0]),
            pos.get("y", default_pos[1]),
            pos.get("z", default_pos[2]),
        )

    target = camera_def.get(
        "target",
        template.default_camera.get("target", [0, 1, 0]) if template else [0, 1, 0],
    )
    if isinstance(target, dict):
        target = (target.get("x", 0), target.get("y", 1), target.get("z", 0))

    fov = camera_def.get(
        "fov",
        template.default_camera.get("fov", 50) if template else 50,
    )

    return {
        "position": list(default_pos),
        "target": list(target),
        "fov": fov,
    }


def _build_lighting_from_shot(shot_json: Dict[str, Any]) -> Dict[str, Any]:
    """从 shot_json 构建光照配置"""
    lighting_presets = {
        "day": {"ambient": "#ffffff", "intensity": 1.0, "directional": True},
        "night": {"ambient": "#1a1a2e", "intensity": 0.3, "directional": False},
        "sunset": {"ambient": "#ff8c42", "intensity": 0.7, "directional": True},
        "indoor_warm": {"ambient": "#ffe4b5", "intensity": 0.8, "directional": False},
        "indoor_cool": {"ambient": "#b0c4de", "intensity": 0.7, "directional": False},
    }
    lighting_def = shot_json.get("lighting", {})
    lighting_type = lighting_def.get("type", "indoor_warm")
    return lighting_presets.get(lighting_type, lighting_presets["indoor_warm"])


@app.post("/api/scene/build")
async def build_scene(input_data: ShotJSONInput):
    """
    从 Shot JSON 构建 3D 场景数据（使用 InstanceBuilder）
    """
    try:
        shot_json = input_data.shot_json

        # 使用 InstanceBuilder 构建场景对象
        instance = build_instance_from_shot_json(shot_json)
        scene_data = instance.to_threejs_scene()

        # 补充 camera 和 lighting（InstanceBuilder 不产出这两个字段）
        scene_data["camera"] = _build_camera_from_shot(shot_json)
        scene_data["lighting"] = _build_lighting_from_shot(shot_json)

        # 保存到文件
        if input_data.save_intermediate:
            output_dir = Path(CONFIG["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            scene_path = output_dir / f"scene_{timestamp}.json"

            with open(scene_path, 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "scene_data": scene_data,
                "saved_to": str(scene_path),
            }

        return {
            "success": True,
            "scene_data": scene_data,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ProjectRequest(BaseModel):
    shot_json: dict
    scene_data: Optional[dict] = None
    width: int = 1024
    height: int = 1024
    upload_masks: bool = True


@app.post("/api/scene/project")
async def project_scene(request: ProjectRequest):
    """
    将 shot_json 中的 3D 对象投影到 2D 屏幕空间

    返回每个对象的 bbox 和 mask 预览。
    当 upload_masks=True 时，保存 mask 图像并上传到 ComfyUI。
    """
    try:
        from app.schema.scene_hierarchy import SceneBlueprint

        shot_json = request.shot_json

        if request.scene_data and isinstance(request.scene_data.get("objects"), list):
            # 使用 scene_data 中的实际对象位置和相机（反映用户编辑）
            camera_config = (
                request.scene_data["camera"]
                if isinstance(request.scene_data.get("camera"), dict)
                else _build_camera_from_shot(shot_json)
            )
            regions = project_scene_data_objects(
                request.scene_data, camera_config,
                width=request.width, height=request.height,
            )
        else:
            # 回退：从 shot_json 重建 instance
            blueprint = SceneBlueprint.from_shot_json(shot_json)
            instance = pipeline.instance_cache.get_or_build_instance(blueprint)
            camera_config = _build_camera_from_shot(shot_json)
            regions = project_instance_objects(
                instance, camera_config, width=request.width, height=request.height
            )

        mask_filenames = {}
        if request.upload_masks and regions:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            mask_dir = project_root / "data" / "masks"
            mask_dir.mkdir(parents=True, exist_ok=True)

            for region in regions:
                mask_name = f"mask_{timestamp}_{region.object_id}.png"
                mask_path = mask_dir / mask_name
                _save_mask_image(region.mask, str(mask_path))

                try:
                    comfy_client.upload_image(str(mask_path), name=mask_name)
                    mask_filenames[region.object_id] = mask_name
                except Exception as e:
                    print(f"Failed to upload mask {mask_name}: {e}")

        return {
            "success": True,
            "camera": camera_config,
            "regions": [
                {
                    "object_id": r.object_id,
                    "object_type": r.object_type,
                    "bbox": list(r.bbox),
                    "center_2d": list(r.center_2d),
                    "depth_mean": r.depth_mean,
                }
                for r in regions
            ],
            "mask_filenames": mask_filenames,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/prompt/regional")
async def build_regional_prompts(input_data: ShotJSONInput):
    """
    从 Shot JSON 构建区域提示词集

    返回：
    - global_positive: 全局正向提示词（背景/环境）
    - global_negative: 全局负向提示词
    - regions: {object_id: {positive, negative, type}}
    """
    try:
        builder = PromptBuilder(input_data.shot_json)
        regional = builder.build_regional_prompt_set()

        if input_data.save_intermediate:
            output_dir = Path(CONFIG["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_path = output_dir / f"regional_prompt_{timestamp}.json"
            with open(prompt_path, 'w', encoding='utf-8') as f:
                json.dump(regional, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "regional_prompts": regional,
                "saved_to": str(prompt_path),
            }

        return {"success": True, "regional_prompts": regional}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/prompt/build")
async def build_prompt(input_data: ShotJSONInput):
    """
    从 Shot JSON 构建生成提示词
    """
    try:
        builder = PromptBuilder(input_data.shot_json)
        prompts = builder.export_prompts()

        if input_data.save_intermediate:
            output_dir = Path(CONFIG["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prompt_path = output_dir / f"prompt_{timestamp}.json"

            with open(prompt_path, 'w', encoding='utf-8') as f:
                json.dump(prompts, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "prompts": prompts,
                "saved_to": str(prompt_path),
            }

        return {
            "success": True,
            "prompts": prompts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflow/build")
async def build_workflow(request: WorkflowBuildRequest):
    """
    从 Shot JSON 构建完整的 ComfyUI 工作流

    当 use_regional=True 且 mask_filenames 不为空时，使用区域提示词工作流，
    将每个物体的提示词约束在其投影 mask 区域内。
    """
    try:
        prompt_builder = PromptBuilder(request.shot_json)

        if request.use_regional and request.mask_filenames:
            # 区域提示词工作流
            regional = prompt_builder.build_regional_prompt_set()

            region_prompts = {}
            region_masks = {}
            for obj_id, prompt_data in regional["regions"].items():
                if obj_id in request.mask_filenames:
                    region_prompts[obj_id] = prompt_data["positive"]
                    region_masks[obj_id] = request.mask_filenames[obj_id]

            if region_prompts:
                workflow = create_regional_prompt_workflow(
                    global_positive=regional["global_positive"],
                    global_negative=regional["global_negative"],
                    region_prompts=region_prompts,
                    region_masks=region_masks,
                    depth_image_path="",
                    seed=42,
                )
                prompts = {
                    "global_positive": regional["global_positive"],
                    "global_negative": regional["global_negative"],
                    "regions": region_prompts,
                }
            else:
                # 回退到普通工作流
                prompts = prompt_builder.export_prompts()
                workflow = create_workflow(
                    positive_prompt=prompts["positive"],
                    negative_prompt=prompts["negative"],
                    depth_image_path="",
                    width=1024,
                    height=1024,
                    seed=42
                )
        else:
            # 普通全图工作流
            prompts = prompt_builder.export_prompts()
            workflow = create_workflow(
                positive_prompt=prompts["positive"],
                negative_prompt=prompts["negative"],
                depth_image_path="",
                width=1024,
                height=1024,
                seed=42
            )

        # 保存到文件
        if request.save_intermediate:
            output_dir = Path(CONFIG["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            workflow_path = output_dir / f"workflow_{timestamp}.json"

            with open(workflow_path, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "workflow": workflow,
                "prompts": prompts,
                "saved_to": str(workflow_path)
            }

        return {
            "success": True,
            "workflow": workflow,
            "prompts": prompts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/depth/render")
async def render_depth_map(request: DepthRenderRequest):
    """从 scene_data 渲染 depth map，并可选上传到 ComfyUI"""
    try:
        method = (request.method or "auto").strip().lower()
        if method not in {"auto", "playwright", "simple"}:
            raise HTTPException(status_code=400, detail="method must be one of: auto, playwright, simple")

        depth_dir = project_root / "data" / "depth"
        depth_dir.mkdir(parents=True, exist_ok=True)
        depth_path = depth_dir / "depth_map.png"

        success = await asyncio.to_thread(
            render_depth_headless,
            scene_data=request.scene_data,
            output_path=str(depth_path),
            method=method,
        )
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Depth render failed. If Playwright is unavailable, try method='simple' or install Playwright.",
            )

        uploaded = None
        if request.upload_to_comfy:
            uploaded = comfy_client.upload_image(str(depth_path), name="depth_map.png")

        return {
            "success": True,
            "saved_path": str(depth_path),
            "method_used": method,
            "uploaded": uploaded,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate")
async def generate_image(request: GenerateRequest):
    """
    使用 ComfyUI 生成图像
    """
    try:
        filename = comfy_client.generate(
            request.workflow,
            timeout=request.timeout
        )

        if not filename:
            raise HTTPException(status_code=500, detail="Generation failed")

        # 保存到输出目录
        output_dir = Path(CONFIG["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"output_{timestamp}.png"

        if comfy_client.save_image(filename, str(output_path)):
            return {
                "success": True,
                "filename": filename,
                "output_path": str(output_path)
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save image")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/characters/build")
async def build_characters(request: CharactersBuildRequest):
    try:
        results = []
        for character in request.characters:
            mw_character_id = character.character_id
            existing = pipeline.character_manager.get_character(mw_character_id)
            registered = existing is None

            if registered:
                pipeline.character_manager.register_character(
                    character_id=mw_character_id,
                    description=character.description or character.visual_core or character.name,
                    seed=42,
                    name=character.name,
                    key_features=character.key_features,
                    is_main_character=character.is_main_character,
                    object_type=character.object_type,
                )

            char = pipeline.character_manager.get_character(mw_character_id)
            if char is None:
                raise ValueError(f"Failed to register character: {mw_character_id}")

            if pipeline.character_library.get_character(mw_character_id) is None:
                pipeline.character_library.add_character(
                    CharacterDefinition(
                        character_id=mw_character_id,
                        name=character.name or mw_character_id,
                        object_type=character.object_type,
                        key_features=character.key_features,
                        description=character.description or character.visual_core or character.name,
                        is_main_character=character.is_main_character,
                        match_keywords=[character.name] if character.name else [],
                    )
                )

            results.append(
                {
                    "source_character_id": character.character_id,
                    "mw_character_id": mw_character_id,
                    "registered": registered,
                    "reference_images": char.reference_images,
                    "description": char.description,
                }
            )

        return {"success": True, "characters": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scenes/build")
async def build_scenes(request: ScenesBuildRequest):
    try:
        scenes = []
        character_lookup = dict(request.character_bindings)
        for scene_spec in request.scenes:
            scene_payload = scene_spec.model_dump()
            template = normalize_template_name(scene_payload.get("template", "indoor_room"))
            objects = build_blueprint_objects(scene_payload)
            blueprint = SceneBlueprint(
                template=template,
                objects=objects,
                metadata=build_scene_metadata(scene_payload),
            )
            bindings = build_scene_character_bindings(scene_payload, character_lookup)
            instance = pipeline.instance_cache.get_or_build_instance(
                blueprint,
                style_id=scene_payload.get("style_id", "default"),
                character_bindings=bindings,
            )
            scenes.append(
                {
                    "source_scene_id": scene_payload.get("world_scene_id"),
                    "blueprint_id": blueprint.blueprint_id,
                    "instance_id": instance.instance_id,
                    "template": instance.template,
                    "character_bindings": {
                        object_id: binding.character_id
                        for object_id, binding in instance.character_bindings.items()
                    },
                    "source_scene_ids": scene_payload.get("source_scene_ids", []),
                }
            )
        return {"success": True, "scenes": scenes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pipeline/full")
async def full_pipeline(
    input_data: TextInput,
    background_tasks: BackgroundTasks
):
    """
    完整流水线：文本 -> Shot JSON -> 场景 -> 提示词 -> 工作流
    （注意：深度图渲染需要手动完成）
    """
    try:
        # Step 1: Parse text
        shot_json = shot_parser.parse(input_data.text)

        # Step 2: Build scene
        builder = SceneBuilder(shot_json)
        scene_data = builder.export_to_threejs()

        # Step 3: Build prompts
        prompt_builder = PromptBuilder(shot_json)
        prompts = prompt_builder.export_prompts()

        # Step 4: Build workflow
        workflow = create_workflow(
            positive_prompt=prompts["positive"],
            negative_prompt=prompts["negative"],
            depth_image_path="depth_map.png",
            width=1024,
            height=1024,
            seed=42
        )

        # Save all intermediate files
        if input_data.save_intermediate:
            output_dir = Path(CONFIG["output_dir"])
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            files = {
                "shot": output_dir / f"shot_{timestamp}.json",
                "scene": output_dir / f"scene_{timestamp}.json",
                "workflow": output_dir / f"workflow_{timestamp}.json"
            }

            with open(files["shot"], 'w', encoding='utf-8') as f:
                json.dump(shot_json, f, indent=2, ensure_ascii=False)

            with open(files["scene"], 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=2, ensure_ascii=False)

            with open(files["workflow"], 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "shot_json": shot_json,
                "scene_data": scene_data,
                "prompts": prompts,
                "workflow": workflow,
                "saved_files": {
                    k: str(v) for k, v in files.items()
                },
                "next_step": "Render depth map using web renderer, then call /api/generate"
            }

        return {
            "success": True,
            "shot_json": shot_json,
            "scene_data": scene_data,
            "prompts": prompts,
            "workflow": workflow,
            "next_step": "Render depth map using web renderer, then call /api/generate"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/templates")
async def list_templates():
    """列出可用的场景模板"""
    from app.scene.templates import list_templates, get_template_info

    templates = {}
    for name in list_templates():
        templates[name] = get_template_info(name)

    return {"templates": templates}


@app.get("/api/objects")
async def list_objects():
    """列出可用的物体类型"""
    from app.scene.object_library import list_object_types, OBJECT_LIBRARY

    return {
        "objects": list_object_types(),
        "details": {
            name: {
                "geometry_type": obj.geometry_type,
                "size": obj.size,
                "tags": obj.tags
            }
            for name, obj in OBJECT_LIBRARY.items()
        }
    }


# 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000)
