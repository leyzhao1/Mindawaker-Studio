import os
from datetime import timedelta
import ffmpeg

class SubtitleService:
    def __init__(self):
       pass

    def _format_time(self, seconds: float) -> str:
        """将秒数格式化为 SRT 时间戳格式 00:00:00,000"""
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        ms = int((td.total_seconds() - total_seconds) * 1000)
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    def generate_srt(self, segments,output_dir:str, filename="subtitles.srt"):
        """
        根据 [ {text, duration}, ... ] 生成字幕文件
        """
        srt_path = os.path.join(output_dir, filename)
        with open(srt_path, "w", encoding="utf-8") as f:
            current_time = 0.0
            for i, seg in enumerate(segments, start=1):
                start = self._format_time(current_time)
                end = self._format_time(current_time + seg["duration"])
                text = seg["text"].strip().replace("\n", " ")
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
                current_time += seg["duration"]
        print(f"✅ 字幕文件已生成：{srt_path}")
        return srt_path

    def burn_subtitles(self, video_path: str, srt_path: str, output_path=None, font="SimHei", fontsize=28):
        """
        将字幕烧录进视频 (生成新视频)
        """
        if output_path is None:
            base, ext = os.path.splitext(video_path)
            output_path = f"{base}_subtitled{ext}"

        (
            ffmpeg
            .input(video_path)
            .output(
                output_path,
                # vf=f"subtitles='{srt_path}':force_style='FontName={font},FontSize={fontsize},PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&'"
                vf=f"subtitles='{srt_path}':fontsdir='/usr/share/fonts/truetype/wqy':force_style='FontName=WenQuanYi Zen Hei,FontSize=15,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&'",
            )
            .run(overwrite_output=True)
        )
        print(f"🎬 已为视频添加字幕：{output_path}")
        return output_path
