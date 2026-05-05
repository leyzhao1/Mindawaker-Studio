"""
主应用测试
"""
import pytest
from fastapi.testclient import TestClient


class TestHealthCheck:
    """健康检查测试"""

    def test_root_endpoint(self, client: TestClient):
        """测试根端点"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "routes" in data
        assert data["service"] == "mindawaker"

    def test_health_endpoint(self, client: TestClient):
        """测试健康检查端点"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestVideoRouter:
    """视频路由测试"""

    def test_create_video_task_missing_theme(self, client: TestClient):
        """测试缺少主题时的错误处理"""
        response = client.post("/video/compose", json={})
        assert response.status_code == 422  # Validation error

    def test_get_task_not_found(self, client: TestClient):
        """测试获取不存在的任务"""
        response = client.get("/video/task/non-existent-id")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_cancel_task_not_found(self, client: TestClient):
        """测试取消不存在的任务"""
        response = client.post("/video/cancel/non-existent-id")
        assert response.status_code == 404


class TestProjectRouter:
    """项目路由测试"""

    def test_create_project(self, client: TestClient):
        """测试创建项目"""
        response = client.post("/project/create?name=test-project&target=video")
        assert response.status_code == 200
        data = response.json()
        assert "project_id" in data

    def test_create_project_invalid_target(self, client: TestClient):
        """测试创建项目时无效的目标"""
        response = client.post("/project/create?name=test&target=invalid")
        # 应该返回空或错误
        assert response.status_code in [200, 400]
