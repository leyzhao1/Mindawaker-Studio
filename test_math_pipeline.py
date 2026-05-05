import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\ClaudeTest\Mindawaker")

import json
from app.configs.constants import SCENE_SHOT_IN_MATH_TEMPLATE
from app.service.base_pipeline import BasePipeline
from app.langchain_pipeline.math_structure import MathSturctureChainGenerator
from app.service.math_pipeline import MathPipeline

# 测试 BasePipeline 方式
print("=== Testing MathPipeline (BasePipeline way) ===")

pipeline = MathPipeline()
pipeline.use_model("deepseek-chat", "sk-17c70c58e2344275b30466b9173a66ac")

try:
    scenes = pipeline.parse("1+1=2")
    print("Success! Scenes:", scenes)
except Exception as e:
    print("Error:", e)
    import traceback

    traceback.print_exc()
finally:
    pipeline.release_model()
