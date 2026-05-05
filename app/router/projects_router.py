from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.configs.logging_config import get_logger
from app.service.pipeline_manager import getPipelineManager
from app.service.task_manager import get_task_manager
from app.router.video_router import rebuild_video_with_pipeline, rebuild_dirty_clips_with_pipeline, concat_clips_with_pipeline

router = APIRouter()
logger = get_logger(__name__)


class ApplyRedrawSelectionRequest(BaseModel):
    image_selected_history: Dict[str, int] = Field(default_factory=dict)
    audio_selected_history: Dict[str, int] = Field(default_factory=dict)


@router.post("/create")
async def create_project(name: str, target: str):
    piplineManager = getPipelineManager()
    project_id = piplineManager.create_project(name=name, target=target)
    logger.info(f"创建项目: {project_id}, 名称: {name}, 目标: {target}")
    return {"project_id": project_id}

@router.get("/list")
def list_projects():
    pipeline_manager = getPipelineManager()
    return pipeline_manager.list_projects()

@router.post("/save")
def save_project(project_id: str, backgroundTasks: BackgroundTasks):
    pipeline_manager = getPipelineManager()
    pipeline_manager.save_project(project_id=project_id)
    return {
        "project_id": project_id,
        "saved": True,
        "project": pipeline_manager.get_project_snapshot(project_id),
    }

@router.post("/load")
def load_project(project_id: str):
    pipeline_manager = getPipelineManager()
    data = pipeline_manager.load_project(project_id=project_id)
    if not data:
        raise HTTPException(status_code=404, detail="项目不存在或加载失败")
    return {"project_id": project_id, "loaded": True, "project": data}

@router.post("/rebuild")
async def rebuild_project(project_id: str):
    pipeline_manager = getPipelineManager()
    loaded = pipeline_manager.load_project(project_id=project_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="项目不存在或加载失败")

    task_manager = get_task_manager()
    task_id = await task_manager.create_task(
        project_id=project_id,
        task_type="video",
        job_func=rebuild_video_with_pipeline,
    )

    return {
        "project_id": project_id,
        "task_id": task_id,
        "status": "started",
        "message": "项目重建任务已启动",
        "project": pipeline_manager.get_project_snapshot(project_id),
    }


@router.post("/apply-redraw-selection")
def apply_redraw_selection(project_id: str, request: ApplyRedrawSelectionRequest):
    pipeline_manager = getPipelineManager()
    loaded = pipeline_manager.load_project(project_id=project_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="项目不存在或加载失败")

    try:
        project = pipeline_manager.apply_redraw_selection(
            project_id=project_id,
            image_selected_history=request.image_selected_history,
            audio_selected_history=request.audio_selected_history,
        )
    except (IndexError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "project_id": project_id,
        "saved": True,
        "project": project,
    }


@router.post("/rebuild-clips")
async def rebuild_project_clips(project_id: str):
    pipeline_manager = getPipelineManager()
    loaded = pipeline_manager.load_project(project_id=project_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="项目不存在或加载失败")

    task_manager = get_task_manager()
    task_id = await task_manager.create_task(
        project_id=project_id,
        task_type="video",
        job_func=rebuild_dirty_clips_with_pipeline,
    )

    return {
        "project_id": project_id,
        "task_id": task_id,
        "status": "started",
        "message": "视频段重建任务已启动",
        "project": pipeline_manager.get_project_snapshot(project_id),
    }


@router.post("/concat-clips")
async def concat_project_clips(project_id: str):
    pipeline_manager = getPipelineManager()
    loaded = pipeline_manager.load_project(project_id=project_id)
    if not loaded:
        raise HTTPException(status_code=404, detail="项目不存在或加载失败")

    task_manager = get_task_manager()
    task_id = await task_manager.create_task(
        project_id=project_id,
        task_type="video",
        job_func=concat_clips_with_pipeline,
    )

    return {
        "project_id": project_id,
        "task_id": task_id,
        "status": "started",
        "message": "视频段拼接任务已启动",
        "project": pipeline_manager.get_project_snapshot(project_id),
    }


@router.get("/{project_id}")
def get_project(project_id: str):
    pipeline_manager = getPipelineManager()
    if project_id not in pipeline_manager.projects:
        loaded = pipeline_manager.load_project(project_id)
        if not loaded:
            raise HTTPException(status_code=404, detail="项目不存在")
    return {"project": pipeline_manager.get_project_snapshot(project_id)}
