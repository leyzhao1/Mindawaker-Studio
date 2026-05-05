from __future__ import annotations

import json
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

import cv2

from media_service.model.schemas import ContentTag
from media_service.analyzers.providers.base_provider import BaseContentProvider

logger = logging.getLogger(__name__)


if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")


class QwenVLContentProvider(BaseContentProvider):
    def __init__(self, model_name: str, model_source: str | None = None, cache_dir: str | None = None, device: str = "auto", max_new_tokens: int = 256) -> None:
        self.model_name = model_name
        self.model_source = model_source or model_name
        self.cache_dir = cache_dir
        self.device = device
        self.max_new_tokens = max_new_tokens
        self._model = None
        self._processor = None

    def analyze_image(self, path: Path) -> ContentTag:
        logger.info("Qwen analyze image: %s", path)
        payload = self._infer_image(path)
        return self._to_content_tag(payload)

    def analyze_video(self, path: Path, frame_count: int = 6) -> ContentTag:
        logger.info("Qwen analyze video: %s frame_count=%s", path, frame_count)
        frame_results = []
        for frame_path in self._extract_video_frames(path, frame_count=frame_count):
            try:
                frame_results.append(self.analyze_image(frame_path))
            finally:
                frame_path.unlink(missing_ok=True)
        if not frame_results:
            return ContentTag(caption=f"video content from {path.stem}")
        return self.summarize_frames(frame_results)

    def summarize_frames(self, frame_results: Iterable[ContentTag]) -> ContentTag:
        results = list(frame_results)
        if not results:
            return ContentTag()
        captions = [item.caption for item in results if item.caption and item.caption != "unknown"]
        objects = self._merge_terms(item.objects for item in results)
        scene_tags = self._merge_terms(item.scene_tags for item in results)
        action_tags = self._merge_terms(item.action_tags for item in results)
        caption = captions[0] if captions else "unknown"
        if len(captions) > 1:
            caption = "; ".join(dict.fromkeys(captions))[:400]
        return ContentTag(
            caption=caption,
            objects=objects,
            scene_tags=scene_tags,
            action_tags=action_tags,
        )

    def _extract_video_frames(self, path: Path, frame_count: int = 6) -> list[Path]:
        logger.info("Extract video frames: path=%s requested_frames=%s", path, frame_count)
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {path}")
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                logger.warning("Video has no readable frames: %s", path)
                return []
            indices = self._sample_indices(total_frames, frame_count)
            logger.info("Sampled %s frame indices from %s total frames for %s", len(indices), total_frames, path)
            output_paths: list[Path] = []
            for index in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    temp_path = Path(tmp.name)
                cv2.imwrite(str(temp_path), frame)
                output_paths.append(temp_path)
            return output_paths
        finally:
            cap.release()

    def _sample_indices(self, total_frames: int, frame_count: int) -> list[int]:
        if frame_count <= 1 or total_frames <= 1:
            return [0]
        if frame_count >= total_frames:
            return list(range(total_frames))
        step = (total_frames - 1) / (frame_count - 1)
        return [round(step * i) for i in range(frame_count)]

    def _infer_image(self, path: Path) -> dict:
        logger.info("Run vision inference for %s", path)
        processor, model = self._load_components()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": str(path.resolve())},
                    {"type": "text", "text": self._prompt()},
                ],
            }
        ]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = self._process_vision_info(messages)
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        if self.device != "cpu":
            inputs = inputs.to(model.device)
        generated_ids = model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        generated_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]
        output_text = processor.batch_decode(generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
        return self._extract_json(output_text)

    def _load_components(self):
        if self._processor is not None and self._model is not None:
            return self._processor, self._model
        logger.info("Load Qwen model: source=%s cache_dir=%s device=%s", self.model_source, self.cache_dir, self.device)
        try:
            import torch
            from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
        except ImportError as exc:
            logger.exception("Missing Qwen dependencies during model load")
            raise RuntimeError("Missing content model dependencies. Install torch, transformers, pillow, and accelerate.") from exc
        processor_kwargs = {}
        model_kwargs = {"torch_dtype": torch.float16 if torch.cuda.is_available() else torch.float32}
        if self.cache_dir:
            processor_kwargs["cache_dir"] = self.cache_dir
            model_kwargs["cache_dir"] = self.cache_dir
        self._processor = AutoProcessor.from_pretrained(self.model_source, **processor_kwargs)
        logger.info("Loaded Qwen processor from %s", self.model_source)
        device_map = "auto" if self.device == "auto" else None
        if device_map:
            model_kwargs["device_map"] = device_map
        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(self.model_source, **model_kwargs)
        if self.device == "cpu":
            self._model = self._model.to("cpu")
        elif self.device not in {"auto", "cpu"}:
            self._model = self._model.to(self.device)
        logger.info("Loaded Qwen model successfully: source=%s", self.model_source)
        return self._processor, self._model

    def _process_vision_info(self, messages):
        try:
            from qwen_vl_utils import process_vision_info
        except ImportError as exc:
            raise RuntimeError("Missing qwen-vl-utils dependency.") from exc
        return process_vision_info(messages)

    def _prompt(self) -> str:
        return (
            "Analyze the media and return only JSON with keys: caption, objects, scene_tags, action_tags. "
            "caption must be a short sentence. objects, scene_tags, action_tags must be arrays of short strings. "
            "Do not include markdown fences or extra commentary."
        )

    def _extract_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start:end + 1])
        return {"caption": text or "unknown", "objects": [], "scene_tags": [], "action_tags": []}

    def _to_content_tag(self, payload: dict) -> ContentTag:
        def normalize_list(value) -> list[str]:
            if not isinstance(value, list):
                return []
            items = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    items.append(text)
            return list(dict.fromkeys(items))[:20]

        caption = str(payload.get("caption") or "unknown").strip() or "unknown"
        return ContentTag(
            caption=caption,
            objects=normalize_list(payload.get("objects")),
            scene_tags=normalize_list(payload.get("scene_tags")),
            action_tags=normalize_list(payload.get("action_tags")),
        )

    def _merge_terms(self, groups: Iterable[Iterable[str]]) -> list[str]:
        merged = []
        for group in groups:
            for item in group:
                text = str(item).strip()
                if text and text not in merged:
                    merged.append(text)
        return merged[:20]
