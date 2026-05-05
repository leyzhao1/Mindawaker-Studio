"""
app/tts_engine/azure_tts.py
===========================
使用 Azure Speech SDK 实现的语音合成模块。
"""

import time
import wave
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk

from app.tts_engine.base_tts import BaseTTS
from app.utils.language_utils import resolve_language


DEFAULT_AZURE_VOICES = {
    "zh": "zh-CN-YunxiNeural",
    "en": "en-US-AndrewNeural",
}


class AzureTTS(BaseTTS):
    def __init__(self, region: str = "westus", key: str = ""):
        self.region = region
        self.key = key

    def synthesize(self, text: str, voice: str, output_dir: str = "app/assets/temp/audio", language: str = "") -> tuple[str, float]:
        resolved_language = resolve_language(text, requested_language=language)
        selected_voice = voice or DEFAULT_AZURE_VOICES.get(resolved_language, DEFAULT_AZURE_VOICES["zh"])
        #临时添加
        self.key = "c0e5d7074e9945919e5f150e5337e3d5"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_path = Path(output_dir) / f"azure_tts_{timestamp}.wav"

        speech_config = speechsdk.SpeechConfig(subscription=self.key, region=self.region)
        speech_config.speech_synthesis_voice_name = selected_voice
        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_path))
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            with wave.open(str(output_path), "rb") as f:
                frames = f.getnframes()
                rate = f.getframerate()
                duration = round(frames / float(rate), 2)
            return str(output_path), duration

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print("❌ 合成被取消")
            print("原因:", cancellation.reason)
            print("错误详情:", cancellation.error_details)
        return "", 0.0

    def release(self):
        pass
