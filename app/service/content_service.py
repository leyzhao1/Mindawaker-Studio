"""
ContentGenerationService
统一内容生成服务入口
支持：story / math / text / hybrid 模式
"""
from typing import Dict, Any, List, Optional
from enum import Enum

from app.configs.logging_config import get_logger
from app.service.story_pipeline import StoryPipeline, run_story_pipeline
from app.service.math_pipeline import MathPipeline, run_math_pipeline
from app.langchain_pipeline.text_generation_chain import LangChainTextGenerator

logger = get_logger(__name__)


class ContentType(str, Enum):
    """内容类型"""
    STORY = "story"           # 故事视频
    MATH = "math"             # 数学动画
    TEXT = "text"             # 纯文本生成
    HYBRID = "hybrid"         # 混合编排（预留）


class ContentGenerationService:
    """
    统一内容生成服务

    根据 style 参数路由到对应 Pipeline：
    - story: StoryPipeline（背景+角色+分镜）
    - math: MathPipeline（透明数学动画）
    - text: LangChainTextGenerator（纯文案）
    - hybrid: 混合编排（未来实现）
    """

    def __init__(self):
        self._text_generator: Optional[LangChainTextGenerator] = None

    # ==================== 统一入口 ====================

    def generate(self, style: str, **kwargs) -> Dict[str, Any]:
        """
        统一生成入口

        Args:
            style: 内容类型 (story/math/text/hybrid)
            **kwargs: 根据类型不同传入不同参数

        Returns:
            标准化的生成结果
        """
        return self._generate_text(**kwargs)
        # style_lower = style.lower()

        # if style_lower == ContentType.STORY:
        #     return self._generate_story(**kwargs)

        # elif style_lower == ContentType.MATH:
        #     return self._generate_math(**kwargs)

        # elif style_lower == ContentType.TEXT:
        #     return self._generate_text(**kwargs)

        # elif style_lower == ContentType.HYBRID:
        #     # 预留：混合编排
        #     raise NotImplementedError("Hybrid mode not yet implemented")

        # else:
        #     raise ValueError(f"Unsupported style: {style}. Use: story/math/text/hybrid")

    # ==================== 各类型实现 ====================

    def _generate_story(
        self,
        story: str,
        model_name: str,
        api_key: str,
        style_tokens: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成故事视频内容

        Args:
            story: 故事文本（可包含 {{MATH:article_id}} 标记）
            model_name: 模型名称
            api_key: API密钥
            style_tokens: 视觉风格词

        Returns:
            包含 segments（分镜列表）的结果
        """
        logger.info(f"Generating story content with model: {model_name}")

        # 检查是否包含数学标记
        import re
        math_markers = re.findall(r'\{\{MATH:(.*?)\}\}', story)
        if math_markers:
            logger.info(f"Detected {len(math_markers)} math markers: {math_markers}")

        result = run_story_pipeline(
            story=story,
            model_name=model_name,
            api_key=api_key,
            style_tokens=style_tokens,
            math_model_name=model_name,  # 使用相同模型处理数学标记
            math_api_key=api_key
        )

        result["style"] = "story"
        result["has_math_markers"] = len(math_markers) > 0
        result["math_articles"] = math_markers

        return result

    def _generate_math(
        self,
        article: str,
        model_name: str = "deepseek-chat",
        api_key: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成数学动画内容

        Args:
            article: 数学文章内容
            model_name: 模型名称（默认 deepseek-chat）
            api_key: API密钥

        Returns:
            包含 lines（旁白文本列表）和 math_animations（动画文件路径列表）的结果
        """
        logger.info(f"Generating math animation with model: {model_name}")

        math_result = run_math_pipeline(
            article=article,
            model_name=model_name,
            api_key=api_key
        )

        result = {
            "lines": math_result.get("lines", []),
            "math_animations": math_result.get("math_animations", []),
            "style": "math",
            "scenes": math_result.get("scenes", []),
            "segments": math_result.get("segments", []),
            "script_files": math_result.get("script_files", []),
        }

        return result

    def _generate_text(
        self,
        theme: str,
        model_name: str,
        api_key: str,
        style: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成纯文本内容

        Args:
            theme: 主题
            model_name: 模型名称
            api_key: API密钥
            style: 文案风格模板

        Returns:
            生成的文案文本
        """
        logger.info(f"Generating text content with model: {model_name}")

        if self._text_generator is None:
            self._text_generator = LangChainTextGenerator()

        self._text_generator.select_model(model_name, api_key)

        try:
            text = self._text_generator.generate(theme=theme, style=style, language=language)
            print("received text=====>", text)
            return {
                "style": "text",
                "theme": theme,
                "content": text,
                "model": model_name,
                "language": language,
            }
        finally:
            self._text_generator.unload_model()

    def polish_media_prompts(
        self,
        text: str,
        model_name: str,
        api_key: str,
        language: Optional[str] = None,
        media_model_name: str = "",
        media_prompt_style: Optional[str] = None,
        texts: Optional[str] = None,
    ) -> str:
        """
        打磨 media prompt（通用工具方法）

        Args:
            text: 原始文本
            model_name: 模型名称
            api_key: API密钥

        Returns:
            优化后的提示词
        """
        if self._text_generator is None:
            self._text_generator = LangChainTextGenerator()

        self._text_generator.select_model(model_name, api_key)

        try:
            return self._text_generator.polish_media_prompts(
                text,
                language=language,
                media_model_name=media_model_name,
                media_prompt_style=media_prompt_style,
                texts=texts,
            )
        finally:
            self._text_generator.unload_model()

    def polish_prompts(self, text: str, model_name: str, api_key: str, language: Optional[str] = None, image_model_name: str = "") -> str:
        return self.polish_media_prompts(
            text=text,
            model_name=model_name,
            api_key=api_key,
            language=language,
            media_model_name=image_model_name,
            media_prompt_style="image_default",
        )

    # ==================== 混合编排（预留） ====================

    def generate_hybrid(
        self,
        story: str,
        math_articles: Dict[str, str],
        model_name: str,
        api_key: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        混合编排：故事 + 数学动画叠加

        预留接口，未来实现：
        1. 解析故事结构
        2. 生成数学动画
        3. 时间轴对齐
        4. 输出合成配置

        Args:
            story: 故事文本（含 {{MATH:article_id}} 标记）
            math_articles: article_id -> 数学文章内容的映射
            model_name: 模型名称
            api_key: API密钥
        """
        logger.info("Hybrid generation not yet implemented")
        raise NotImplementedError(
            "Hybrid mode will be implemented in future version. "
            "For now, generate story and math separately and compose manually."
        )


# ==================== 便捷函数 ====================

def get_content_service() -> ContentGenerationService:
    """获取服务实例（单例）"""
    return ContentGenerationService()
