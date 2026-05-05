from __future__ import annotations

import asyncio
from typing import Callable

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.configs.logging_config import get_logger
from app.model.video_retrieval_schema import VideoRetrievalRequest
from app.service.pipeline_manager import getPipelineManager
from app.service.task_manager import TaskStatus, get_task_manager

router = APIRouter()
logger = get_logger(__name__)
pipeline_manager = getPipelineManager()


async def generate_video_retrieval_with_pipeline(project_id: str, config: dict, cancel_event: asyncio.Event, progress_cb: Callable[[dict], None]):
    return await pipeline_manager.async_generate_video_retrieval(
        project_id=project_id,
        config=config,
        cancel_event=cancel_event,
        progress_cb=progress_cb,
    )


@router.post("/compose")
async def create_video_retrieval_task(request: VideoRetrievalRequest, project_id: str = ""):
    style = (request.style or "").strip().lower()
    if style == "story":
        raise HTTPException(status_code=400, detail="video retrieval 不再支持 story 风格")

    task_manager = get_task_manager()
    if not project_id:
        project_id = pipeline_manager.create_project(name="video_retrieval_task", target="video_retrieval")
        if not project_id:
            raise HTTPException(status_code=500, detail="创建视频检索项目失败")

    config = request.model_dump()
    config["media_prompt_style"] = config.get("media_prompt_style") or "retrieval_default"
    task_id = await task_manager.create_task(
        project_id=project_id,
        task_type="video_retrieval",
        job_func=generate_video_retrieval_with_pipeline,
        config=config,
    )
    return {
        "task_id": task_id,
        "project_id": project_id,
        "status": "started",
        "message": "视频检索生成任务已启动，请通过 WebSocket 或轮询接口获取进度",
    }


@router.post("/cancel/{task_id}")
async def cancel_video_retrieval_task(task_id: str):
    task_manager = get_task_manager()
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
        return {
            "cancelled": False,
            "task_id": task_id,
            "message": f"任务状态为 {task.status}，无法取消",
        }

    success = await task_manager.cancel_task(task_id)
    return {
        "cancelled": success,
        "task_id": task_id,
        "message": "任务已取消" if success else "取消失败",
    }


@router.get("/task/{task_id}")
async def get_video_retrieval_task_status(task_id: str):
    task_manager = get_task_manager()
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "task_id": task.id,
        "project_id": task.project_id,
        "type": task.type,
        "status": task.status,
        "pipeline_status": task.pipeline_status,
        "progress": task.progress,
        "stage": task.stage,
        "message": task.message,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "result": task.result,
        "error": task.error,
        "done": task.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.ERROR],
    }


@router.websocket("/ws/{task_id}")
async def task_websocket(websocket: WebSocket, task_id: str):
    await websocket.accept()
    task_manager = get_task_manager()
    task = await task_manager.get_task(task_id)
    if not task:
        await websocket.send_json({"error": "Task not found", "task_id": task_id})
        await websocket.close()
        return

    logger.info(f"Video retrieval WebSocket connected for task {task_id}, current status: {task.status}")

    try:
        async for data in task_manager.subscribe_progress(task_id):
            await websocket.send_json(data)
            if data.get("status") in [TaskStatus.COMPLETED, TaskStatus.CANCELLED, TaskStatus.ERROR]:
                await websocket.close()
                break
    except WebSocketDisconnect:
        logger.info(f"Video retrieval WebSocket disconnected for task {task_id}")
    except Exception as e:
        logger.error(f"Video retrieval WebSocket error for task {task_id}: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()
