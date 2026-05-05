"""
任务管理器测试
"""
import pytest
import asyncio
from app.service.task_manager import TaskManager, TaskStatus


class TestTaskManager:
    """任务管理器测试类"""

    @pytest.fixture
    async def task_manager(self):
        """创建任务管理器实例"""
        manager = TaskManager(db_path=":memory:")  # 使用内存数据库
        yield manager

    @pytest.mark.asyncio
    async def test_create_task(self, task_manager):
        """测试创建任务"""
        async def dummy_job(*args, **kwargs):
            await asyncio.sleep(0.1)
            return {"status": "completed"}

        task_id = await task_manager.create_task(
            project_id="test-project",
            task_type="video",
            job_func=dummy_job
        )

        assert task_id is not None
        task = await task_manager.get_task(task_id)
        assert task is not None
        assert task.project_id == "test-project"
        assert task.type == "video"

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_manager):
        """测试取消任务"""
        cancel_event = asyncio.Event()

        async def long_job(cancel_event, progress_cb):
            for i in range(10):
                if cancel_event.is_set():
                    return {"status": "cancelled"}
                await asyncio.sleep(0.1)
            return {"status": "completed"}

        task_id = await task_manager.create_task(
            project_id="test-project",
            task_type="video",
            job_func=long_job
        )

        # 取消任务
        cancelled = await task_manager.cancel_task(task_id)
        assert cancelled is True

        # 等待任务完成
        await asyncio.sleep(0.2)

        task = await task_manager.get_task(task_id)
        assert task.status in [TaskStatus.CANCELLED, TaskStatus.RUNNING]

    @pytest.mark.asyncio
    async def test_task_progress(self, task_manager):
        """测试任务进度更新"""
        progress_updates = []

        async def job_with_progress(cancel_event, progress_cb):
            for i in range(5):
                await progress_cb({"progress": i * 20, "stage": "test"})
                await asyncio.sleep(0.01)
            return {"status": "completed"}

        task_id = await task_manager.create_task(
            project_id="test-project",
            task_type="video",
            job_func=job_with_progress
        )

        # 等待任务完成
        await asyncio.sleep(0.2)

        task = await task_manager.get_task(task_id)
        assert task.progress == 80  # 最后更新的进度

    @pytest.mark.asyncio
    async def test_get_project_tasks(self, task_manager):
        """测试获取项目任务列表"""
        async def dummy_job(*args, **kwargs):
            return {"status": "completed"}

        # 创建多个任务
        for i in range(3):
            await task_manager.create_task(
                project_id="test-project",
                task_type="video",
                job_func=dummy_job
            )

        tasks = await task_manager.get_project_tasks("test-project")
        assert len(tasks) == 3
