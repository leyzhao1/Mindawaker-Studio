"""
数学动画 Pipeline
生成透明背景的数学动画片段，用于叠加到故事视频上
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from pydantic import TypeAdapter

from app.langchain_pipeline.math_structure import (
    Storyboard,
    Scene,
    Shot,
    Math,
    MathSturctureChainGenerator,
)
from app.configs.constants import SCENE_SHOT_IN_MATH_TEMPLATE
from app.service.base_pipeline import BasePipeline
from app.service.animate_math_layers import animate_math_layers_sync, animate_math_layers


class MathPipeline(BasePipeline):
    """
    数学动画生成 Pipeline

    职责：
    - 解析数学文章为结构化场景/分镜
    - 生成透明背景的数学动画（无背景图、无角色图、无音频）

    输出：
    - 分镜列表（含公式动画配置、旁白文本、预估时长）
    """

    def __init__(self):
        super().__init__(MathSturctureChainGenerator)

    def parse(self, article: str) -> List[Scene]:
        """
        解析数学文章为结构化场景列表

        Returns:
            List[Scene]: 场景列表，每个场景包含多个分镜（shots）
        """
        prompt = self._render_template(SCENE_SHOT_IN_MATH_TEMPLATE, math_article=article)
        raw = self._call_llm(prompt)

        # 清洗 markdown 包裹
        cleaned = raw.replace("```json", "").replace("```", "")
        data = json.loads(cleaned)

        if not isinstance(data, list):
            raise TypeError("LLM output 'data' must be a list of scenes")

        scenes_adapter = TypeAdapter(List[Scene])
        scenes: List[Scene] = scenes_adapter.validate_python(data)

        return scenes

    def generate(self, article: str) -> Dict[str, Any]:
        """
        执行完整数学动画生成流程

        Args:
            article: 数学文章内容

        Returns:
            Dict 包含：
            - segments: 分镜列表，每个分镜包含：
                - narration: 旁白文本（用于故事层TTS）
                - math: 公式动画配置
                - text_overlays: 文字层配置
                - duration: 预估时长（秒）
            - scenes: 原始场景数据（如需调试）
        """
        scenes = self.parse(article)

        segments = []
        for scene_idx, scene in enumerate(scenes):
            for shot in scene.shots:
                # 计算预估时长（基于公式复杂度，简单估算）
                duration = self._estimate_duration(shot.math)

                segments.append(
                    {
                        "scene_idx": scene_idx,
                        "shot_id": shot.shot_id,
                        "narration": shot.narration,  # 旁白文本
                        "math": shot.math,  # 公式动画配置
                        "text_overlays": shot.text_overlays,  # 文字层
                        "duration": duration,
                        "type": "math",
                    }
                )

        return {
            "segments": segments,
            "total_duration": sum(s["duration"] for s in segments),
            "scene_count": len(scenes),
            "shot_count": len(segments),
        }

    def _estimate_duration(self, math: Math) -> float:
        """
        估算公式动画时长
        简单规则：每个公式 3-5 秒，根据复杂度调整
        """
        formula_count = len(math.formulas) if math.formulas else 1

        # 基础时长 + 每个公式时长
        base_duration = 5.0  # 开场白
        per_formula = 4.0  # 每个公式展示+推导

        return base_duration + formula_count * per_formula


def run_math_pipeline(
    article: str,
    model_name: str = "deepseek-chat",
    api_key: str = "",
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    数学动画生成管道

    返回结构化结果，包含旁白、动画文件、场景和分镜信息。
    """
    import asyncio
    import time

    # 初始化pipeline并解析文章
    pipeline = MathPipeline()
    pipeline.use_model(model_name, api_key)

    try:
        # 如果文章为空，返回空结果
        if not article or not article.strip():
            return {
                "lines": [],
                "math_animations": [],
                "scenes": [],
                "segments": [],
                "script_files": [],
                "output_dir": "",
            }

        # 解析文章为场景结构（带重试）
        max_retries = 3
        scenes = None
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                scenes = pipeline.parse(article)
                break
            except Exception as e:
                last_exc = e
                print(f"[MathPipeline] 解析失败（尝试 {attempt}/{max_retries}）: {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)

        if scenes is None:
            raise RuntimeError(f"数学文章解析失败，已重试 {max_retries} 次: {last_exc}")

        # 收集所有shots和旁白文本
        all_shots = []
        lines = []
        segments = []
        for scene_idx, scene in enumerate(scenes):
            for shot_idx, shot in enumerate(scene.shots):
                all_shots.append((scene_idx, shot))
                lines.append(shot.narration)
                segments.append(
                    {
                        "scene_idx": scene_idx,
                        "shot_idx": shot_idx,
                        "shot_id": shot.shot_id,
                        "narration": shot.narration,
                        "math": shot.math,
                        "text_overlays": shot.text_overlays,
                        "duration": pipeline._estimate_duration(shot.math),
                        "type": "math",
                    }
                )

        print(f"[MathPipeline] parsed scenes={len(scenes)} total_shots={len(all_shots)}")
        if output_dir is None:
            output_dir = Path.cwd() / "app" / "assets" / "projects" / "math_pipeline_temp" / f"math_anim_{int(time.time() * 1000)}"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[MathPipeline] animation output_dir={output_dir}")

        async def _run_animation():
            return await animate_math_layers(all_shots, output_dir)

        loop = asyncio.new_event_loop()
        try:
            math_animation_files = loop.run_until_complete(_run_animation())
        except Exception:
            raise
        finally:
            loop.close()

        script_files = [str(path).replace("\\", "/") for path in sorted(output_dir.glob("*_manim.py"))]

        return {
            "lines": lines,
            "math_animations": math_animation_files,
            "scenes": scenes,
            "segments": segments,
            "script_files": script_files,
            "output_dir": str(output_dir).replace("\\", "/"),
        }

    except Exception:
        raise
    finally:
        pipeline.release_model()
