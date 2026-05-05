"""
Pytest 配置文件
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def sample_video_config():
    """示例视频配置"""
    return {
        "theme": "测试主题",
        "style": "温柔",
        "text_model_name": "deepseek",
        "text_api_key": "test_key",
        "image_model_name": "flux",
        "image_api_key": "test_key",
        "audio_model_name": "azure",
        "audio_api_key": "test_key",
        "voice": "me2",
        "size": "1024*1024",
        "n": 1,
    }
