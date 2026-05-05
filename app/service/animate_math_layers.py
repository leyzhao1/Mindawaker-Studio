"""
数学动画生成模块 - 使用 manim 生成透明背景的公式动画
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional
import json
import sys

from app.langchain_pipeline.math_structure import Shot, Math, Formula, MathPlan


_REQUIRED_MANIM_VERSION = "0.18.1"


def _assert_manim_version(expected_version: str = _REQUIRED_MANIM_VERSION) -> None:
    try:
        import manim  # type: ignore

        current_version = str(getattr(manim, "__version__", "")).strip()
    except Exception as exc:
        raise RuntimeError(
            f"无法读取 manim.__version__，期望 {expected_version}。请确认运行环境已安装 manim=={expected_version}。原始错误: {exc}"
        )

    # if current_version != expected_version:
    #     raise RuntimeError(
    #         f"manim版本不匹配：当前 {current_version or 'unknown'}，期望 {expected_version}。"
    #         f"请切换到正确环境或安装 manim=={expected_version} 后重试。"
    #     )


async def animate_math_layers(
    shots_with_indices: List[Tuple[int, Shot]],  # (scene_idx, shot)
    output_dir: Path,
    resolution: Tuple[int, int] = (1920, 1080),
    fps: int = 30,
) -> List[str]:
    """
    为每个shot生成数学动画视频

    参数:
        shots_with_indices: 包含场景索引和shot对象的列表
        output_dir: 输出目录（动画视频将保存于此）
        resolution: 视频分辨率 (宽, 高)
        fps: 帧率

    返回:
        动画视频文件路径列表（按输入顺序对应每个shot）
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    animation_files = []

    for i, (scene_idx, shot) in enumerate(shots_with_indices):
        shot_id = f"shot_{i:04d}"
        formula_count = len(shot.math.formulas) if shot.math and shot.math.formulas else 0
        print(f"[MathAnim] start {shot_id} scene={scene_idx} formulas={formula_count} plan={shot.math.plan if shot.math else None}")
        anim_path = await _render_shot_animation(
            shot_id=shot_id,
            shot=shot,
            output_dir=output_dir,
            resolution=resolution,
            fps=fps,
        )
        print(f"[MathAnim] done  {shot_id} -> {anim_path if str(anim_path) else '[empty layer]'}")
        animation_files.append(str(anim_path))

    print(f"[MathAnim] finished all shots count={len(animation_files)} output_dir={output_dir}")

    return animation_files


async def _render_shot_animation(
    shot_id: str,
    shot: Shot,
    output_dir: Path,
    resolution: Tuple[int, int],
    fps: int,
) -> Path:
    """
    渲染单个shot的数学动画
    """
    # 输出文件路径（透明背景视频）
    output_path = output_dir / f"{shot_id}.mov"

    # 如果没有公式，不生成占位视频，后续合成阶段会自动走“仅褐色背景”分支
    if not shot.math.formulas:
        print(f"[MathAnim] {shot_id} has no formulas, skip rendering and use empty math layer")
        return Path("")

    print(f"[MathAnim] {shot_id} rendering manim script with {len(shot.math.formulas)} formulas")

    # 根据math.plan选择动画策略
    plan = shot.math.plan

    # 生成manim Python脚本
    script_content = _generate_manim_script(
        shot_id=shot_id, formulas=shot.math.formulas, plan=plan, resolution=resolution, fps=fps
    )

    # 临时Python脚本文件
    script_path = output_dir / f"{shot_id}_manim.py"
    script_path.write_text(script_content, encoding="utf-8")

    # 调用manim渲染
    output_path = await _run_manim_render(script_path, output_path, resolution, fps)

    # 验证输出文件
    if not output_path.exists():
        raise RuntimeError(f"渲染完成但输出文件不存在: {output_path}")

    file_size = output_path.stat().st_size
    if file_size < 1000:  # 小于1KB的文件很可能是错误的
        raise RuntimeError(f"输出文件太小（{file_size}字节），渲染可能失败: {output_path}")

    return output_path


def _generate_manim_script(
    shot_id: str,
    formulas: List[Formula],
    plan: Optional[MathPlan],
    resolution: Tuple[int, int],
    fps: int,
) -> str:
    """
    生成manim场景脚本
    """
    # 导入manim模块
    imports = """
from manim import *
import numpy as np

config.media_width = "100%"
config.media_embed = True
"""

    # 场景类定义
    scene_class = f"""
class {shot_id.capitalize()}Scene(Scene):
    def construct(self):
        # 设置透明背景
        self.camera.background_color = "#00000000"

        # 创建公式对象
        formula_objects = []
"""

    # 添加公式创建代码
    for idx, formula in enumerate(formulas):
        # 转义LaTeX字符串
        latex_str = formula.latex.replace("\\", "\\\\")
        scene_class += f"""
        formula_{idx} = MathTex(r"{latex_str}", color=WHITE)
        formula_objects.append(formula_{idx})
"""

    # 根据plan添加动画
    if not plan:
        # 默认：同时显示所有公式
        scene_class += """
        # 同时显示所有公式
        group = VGroup(*formula_objects)
        group.arrange(DOWN, buff=0.5)
        self.play(Write(group))
        self.wait(2)
"""
    elif plan == MathPlan.sequential_reveal:
        # 顺序显示
        scene_class += """
        # 顺序显示公式
        for i, formula in enumerate(formula_objects):
            if i == 0:
                formula.move_to(ORIGIN)
            else:
                formula.next_to(formula_objects[i-1], DOWN, buff=0.5)
            self.play(Write(formula))
            self.wait(0.5)
        self.wait(1)
"""
    elif plan == MathPlan.write_then_hold:
        # 手写效果后保持
        scene_class += """
        # 手写效果
        group = VGroup(*formula_objects)
        group.arrange(DOWN, buff=0.5)
        self.play(Write(group, run_time=2))
        self.wait(3)
"""
    elif plan == MathPlan.stepwise_reveal_and_highlight:
        # 分步显示并高亮
        scene_class += """
        # 分步显示并高亮
        for i, formula in enumerate(formula_objects):
            formula.move_to(ORIGIN)
            self.play(Write(formula))
            self.play(formula.animate.set_color(YELLOW))
            self.wait(0.5)
            self.play(formula.animate.set_color(WHITE))
            if i < len(formula_objects) - 1:
                self.play(FadeOut(formula))
        self.play(FadeIn(formula_objects[-1]))
        self.wait(1)
"""
    elif plan == MathPlan.transform_and_highlight:
        # 变换并高亮
        scene_class += """
        # 变换并高亮
        if len(formula_objects) >= 2:
            self.play(Write(formula_objects[0]))
            self.wait(0.5)
            for i in range(1, len(formula_objects)):
                self.play(Transform(formula_objects[0], formula_objects[i]))
                self.play(formula_objects[0].animate.set_color(YELLOW))
                self.wait(0.5)
                self.play(formula_objects[0].animate.set_color(WHITE))
            self.wait(1)
        else:
            self.play(Write(formula_objects[0]))
            self.wait(2)
"""
    elif plan == MathPlan.substitute_and_emphasize:
        # 替换并强调
        scene_class += """
        # 替换并强调
        for i, formula in enumerate(formula_objects):
            formula.move_to(ORIGIN)
            if i == 0:
                self.play(Write(formula))
            else:
                self.play(ReplacementTransform(formula_objects[i-1], formula))
                self.play(formula.animate.scale(1.2))
                self.wait(0.3)
                self.play(formula.animate.scale(1/1.2))
            self.wait(0.5)
        self.wait(1)
"""
    elif plan == MathPlan.final_reveal_and_hold:
        # 最终显示并保持
        scene_class += """
        # 最终显示并保持
        group = VGroup(*formula_objects)
        group.arrange(DOWN, buff=0.5)
        self.play(FadeIn(group))
        self.wait(3)
"""
    else:
        # 默认动画
        scene_class += """
        # 默认动画
        group = VGroup(*formula_objects)
        group.arrange(DOWN, buff=0.5)
        self.play(Write(group))
        self.wait(2)
"""

    # 结束场景
    scene_class += """
        # 淡出
        self.play(FadeOut(*self.mobjects))
"""

    # 完整脚本
    script = imports + scene_class
    return script


async def _run_manim_render(
    script_path: Path,
    output_path: Path,
    resolution: Tuple[int, int],
    fps: int,
) -> Path:
    """
    调用manim命令行渲染动画
    """
    _assert_manim_version()

    scene_name = f"{output_path.stem.capitalize()}Scene"
    media_dir = output_path.parent / f"_manim_media_{output_path.stem}"

    import shutil
    shutil.rmtree(media_dir, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "manim",
        "-ql",
        "-t",
        "--media_dir",
        str(media_dir),
        "--disable_caching",
        "--flush_cache",
        str(script_path),
        scene_name,
    ]
    print(f"[MathAnim] running manim: {' '.join(cmd)}")
    print(f"[MathAnim] python executable: {sys.executable}")
    print(f"[MathAnim] target output: {output_path}")
    print(f"[MathAnim] media dir: {media_dir}")
    print(f"[MathAnim] requested resolution={resolution} fps={fps}")

    env = dict(**__import__('os').environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["MANIM_DISABLE_VERSION_CHECK"] = "1"
    env["MANIM_RENDERER"] = env.get("MANIM_RENDERER", "cairo")
    env["MANIM_DISABLE_CACHING"] = "1"
    warning_filter = "ignore:.*manim.__main__.*:RuntimeWarning"
    existing_warning_filters = env.get("PYTHONWARNINGS", "")
    env["PYTHONWARNINGS"] = f"{existing_warning_filters},{warning_filter}" if existing_warning_filters else warning_filter

    print(f"[MathAnim] env MANIM_RENDERER={env['MANIM_RENDERER']}")


    timeout = 300
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        print(f"[MathAnim] manim timeout after {timeout}s for {script_path}")
        raise RuntimeError(f"manim渲染超时（{timeout}秒）: {cmd}\n请检查公式LaTeX语法是否正确")

    stdout_text = stdout.decode(errors="replace")
    stderr_text = stderr.decode(errors="replace")
    filtered_stderr_lines = [
        line
        for line in stderr_text.splitlines()
        if "manim.__main__' found in sys.modules" not in line
    ]
    stderr_text_filtered = "\n".join(filtered_stderr_lines).strip()
    print(f"[MathAnim] manim returncode={process.returncode} for {script_path.name}")
    if stdout_text.strip():
        print(f"[MathAnim] manim stdout:\n{stdout_text}")
    if stderr_text_filtered:
        print(f"[MathAnim] manim stderr:\n{stderr_text_filtered}")

    if process.returncode != 0:
        raise RuntimeError(
            f"manim渲染失败: {cmd}\nstdout: {stdout.decode()}\nstderr: {stderr_text_filtered or stderr.decode()}"
        )

    # manim输出路径会随质量/格式变化，不能只写死找 .mov 和 480p15
    script_stem = script_path.stem.replace("_manim", "")
    possible_dirs = [
        media_dir / "videos" / script_path.stem,
        media_dir / "videos" / script_stem,
        media_dir / "videos" / script_path.stem.replace("_manim", ""),
    ]

    source_file = None
    candidate_extensions = (".mov", ".mp4", ".webm")

    for d in possible_dirs:
        if d.exists():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() in candidate_extensions:
                    source_file = f
                    break
        if source_file:
            break

    if not source_file:
        for f in media_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in candidate_extensions:
                source_file = f
                break

    if not source_file:
        raise RuntimeError(
            f"manim渲染完成但未找到输出文件\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    if source_file.suffix.lower() != output_path.suffix.lower():
        converted_output = output_path.with_suffix(source_file.suffix.lower())
        source_file.replace(converted_output)
        output_path = converted_output
    else:
        source_file.replace(output_path)

    # 清理临时media目录
    import shutil

    shutil.rmtree(media_dir, ignore_errors=True)
    return output_path



async def _create_empty_animation(
    output_path: Path,
    duration: float,
    resolution: Tuple[int, int],
    fps: int,
) -> None:
    """
    创建透明空视频（没有公式时使用）
    """
    # 使用ffmpeg创建透明视频
    width, height = resolution
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black@0.0:s={width}x{height}:r={fps}:d={duration}",
        "-c:v",
        "prores_ks",
        "-profile:v",
        "4444",
        "-pix_fmt",
        "yuva444p10le",
        "-t",
        f"{duration}",
        str(output_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"创建透明空视频失败: {cmd}\nstderr: {stderr.decode()}")


# 同步版本包装（兼容现有代码）
def animate_math_layers_sync(
    shots_with_indices: List[Tuple[int, Shot]],
    output_dir: Path,
    resolution: Tuple[int, int] = (1920, 1080),
    fps: int = 30,
) -> List[str]:
    """
    animate_math_layers 的同步版本
    """
    return asyncio.run(animate_math_layers(shots_with_indices, output_dir, resolution, fps))
