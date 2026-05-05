from __future__ import annotations

import os,time
import subprocess
from pathlib import Path
from typing import List, Sequence, Optional


def _run(cmd: List[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\nCMD: {' '.join(cmd)}\nSTDERR:\n{p.stderr}")

def _run_ffmpeg_with_progress(cmd, timeout=600):
    print("CMD:", " ".join(map(str, cmd)))

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,   # 合并 stderr -> stdout
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    start = time.time()
    last = []
    for line in proc.stdout:
        line = line.rstrip("\n")
        # print(line)
        last.append(line)
        if len(last) > 200:
            last.pop(0)

        if time.time() - start > timeout:
            proc.kill()
            raise TimeoutError("ffmpeg timeout. Last logs:\n" + "\n".join(last))
def _ensure_exists(p: str | Path, what: str) -> str:
    p = str(p)
    if not os.path.exists(p):
        raise FileNotFoundError(f"{what} not found: {p}")
    return p






def create_math_video(
    image_files: Sequence[str],
    audio_files: Sequence[str],
    text_layers: Sequence[str],
    math_layers: Sequence[str],
    durations: Sequence[float],
    video_path: str,
    *,
    resolution: tuple[int, int] = (1920, 1080),
    fps: int = 30,
    work_dir: str | Path = "./_math_video_tmp",
    keep_shot_files: bool = False,
) -> str:
    """
    将每个 shot 的素材合成并拼接为最终视频（透明背景）。

    参数（shot 级别）必须同长度：
      image_files[a]  : persona PNG（推荐透明）
      audio_files[a]  : 该 shot 配音
      text_layers[a]  : 透明文字层视频（mov，带 alpha；若没有可给空字符串）
      math_layers[a]  : 透明公式层视频（mov，带 alpha；若没有可给空字符串）
      durations[a]    : 该 shot 时长（秒）

    输出：
      video_path: 最终 mp4 文件路径（H.264 + AAC，透明背景）
    """
    W, H = resolution
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    n = len(image_files)
    if not (len(audio_files) == len(text_layers) == len(math_layers) == len(durations) == n):
        raise ValueError("All shot-level arrays must have the same length.")

    shot_videos: List[Path] = []

    for i in range(n):
        persona_img = _ensure_exists(image_files[i], f"image_files[{i}]")
        audio = _ensure_exists(audio_files[i], f"audio_files[{i}]")

        # text/math layer 允许为空：用透明空色视频代替
        text_layer = text_layers[i]
        math_layer = math_layers[i]
        print("text_layer",text_layer)
        print("math_layer",math_layer)
        d = float(durations[i])
        if d <= 0:
            raise ValueError(f"durations[{i}] must be > 0, got {d}")

        # 透明背景（不使用背景图像）

        # 如果 text/math layer 不存在，就生成透明空层
        def ensure_layer(layer_path: str, name: str) -> str:
            if layer_path and os.path.exists(layer_path):
                return layer_path
            # 生成透明空层（ProRes 4444，带 alpha）
            out = work_dir / f"empty_{name}_{i}.mov"
            base = f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d}"
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", base,
                "-c:v", "prores_ks", "-profile:v", "4444",
                "-pix_fmt", "yuva444p10le",
                "-t", f"{d}",
                str(out),
            ]
            _run_ffmpeg_with_progress(cmd)
            return str(out)

        text_layer = ensure_layer(text_layer, "text")
        math_layer = ensure_layer(math_layer, "math")

        # 人物位置居中
        x_expr, y_expr = "(W-w)/2", "(H-h)/2"

        # 输出分镜视频
        out_shot = work_dir / f"shot_{i:04d}.mp4"

        # 输入：
        # 0: bg image (loop to duration)
        # 1: persona image (loop)
        # 2: text_layer mov (alpha)
        # 3: math_layer mov (alpha)
        # 4: audio
        #
        # 组合：
        # bg -> overlay persona -> overlay text -> overlay math
        filter_complex = ("\""
            f"[0:v]scale={W}:{H},format=rgba[bg];"
            f"[1:v]format=rgba[per];"
            f"[bg][per]overlay=x={x_expr}:y={y_expr}:format=auto[v1];"
            f"[v1][2:v]overlay=0:0:format=auto[v2];"
            f"[v2][3:v]overlay=0:0:format=auto[v]"
            "\""
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black@0.0:s={W}x{H}:r={fps}:d={d}",
            "-stream_loop", "-1", "-t", f"{d}", "-i", persona_img,
            "-i", text_layer,
            "-i", math_layer,
            "-i", audio,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "4:a:0",
            "-r", str(fps),
            "-t", f"{d}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_shot),
        ]
        _run_ffmpeg_with_progress(cmd)

        shot_videos.append(out_shot)

    # concat 拼接
    concat_list = work_dir / "concat_list.txt"
    with concat_list.open("w", encoding="utf-8") as f:
        for p in shot_videos:
            # concat demuxer 要求：file 'path'
            f.write(f"file '{p.as_posix()}'\n")

    video_path = str(video_path)
    Path(video_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        video_path,
    ]
    _run_ffmpeg_with_progress(cmd)

    if not keep_shot_files:
        # 清理中间分镜视频（保留空层 mov / concat_list 也没问题，但你可以全删）
        for p in shot_videos:
            try:
                p.unlink()
            except Exception:
                pass

    return video_path
