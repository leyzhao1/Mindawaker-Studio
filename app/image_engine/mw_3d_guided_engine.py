import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from app.model.story_visual_schema import ShotRenderRequest, ShotRenderResponse


class MW3DGuidedEngine:
    def __init__(self, image_api_key: str = ""):
        self.base_url = image_api_key.strip() or "http://127.0.0.1:7000"
        self.base_url = self.base_url.rstrip("/")
        self.session = requests.Session()
        self.mw_project_dir = Path(__file__).resolve().parents[3] / "mw-3d-guided-t2i"

    def _resolve_source_path(self, output_path: str) -> Path:
        source_path = Path(output_path)
        if source_path.is_absolute():
            return source_path
        sibling_path = (self.mw_project_dir / source_path).resolve()
        if sibling_path.exists():
            return sibling_path
        return source_path

    def generate_images(
        self,
        prompt: str,
        n: int = 1,
        size: str = "512*512",
        output_dir: str = "app/assets/temp/images"
    ):
        print(f"[MW3DGuidedEngine.generate_images] start n={n} size={size} output_dir={output_dir}")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        created_files: List[str] = []

        for index in range(max(1, n)):
            print(f"[MW3DGuidedEngine.generate_images] building workflow index={index} url={self.base_url}/api/pipeline/full")
            response = self.session.post(
                f"{self.base_url}/api/pipeline/full",
                json={"text": prompt, "save_intermediate": False},
                timeout=300,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success"):
                raise ValueError(payload)

            workflow = payload.get("workflow")
            if not workflow:
                raise ValueError("mw full pipeline did not return workflow")

            print(f"[MW3DGuidedEngine.generate_images] generating image index={index} url={self.base_url}/api/generate")
            gen_response = self.session.post(
                f"{self.base_url}/api/generate",
                json={"workflow": workflow, "timeout": 300},
                timeout=600,
            )
            gen_response.raise_for_status()
            gen_payload = gen_response.json()
            if not gen_payload.get("success"):
                raise ValueError(gen_payload)

            source_path = self._resolve_source_path(gen_payload["output_path"])
            timestamp = int(time.time() * 1000)
            target_path = output_path / f"mw_3d_guided_{timestamp}_{index}.png"
            print(f"[MW3DGuidedEngine.generate_images] source_path={source_path} target_path={target_path}")
            if source_path.exists():
                target_path.write_bytes(source_path.read_bytes())
                created_files.append(str(target_path))
                print(f"[MW3DGuidedEngine.generate_images] copied to {target_path}")
            else:
                created_files.append(str(source_path))
                print(f"[MW3DGuidedEngine.generate_images] source path missing, keeping original path {source_path}")

        print(f"[MW3DGuidedEngine.generate_images] done created_files={created_files}")
        return created_files

    def build_characters(self, character_specs: List[Dict[str, Any]]) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/api/characters/build",
            json={"characters": character_specs},
            timeout=300,
        )
        response.raise_for_status()
        return response.json()

    def build_scenes(
        self,
        scene_specs: List[Dict[str, Any]],
        character_bindings: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/api/scenes/build",
            json={
                "scenes": scene_specs,
                "character_bindings": character_bindings or {},
            },
            timeout=300,
        )
        response.raise_for_status()
        return response.json()

    def render_shot(self, request: ShotRenderRequest) -> ShotRenderResponse:
        payload = request.model_dump(mode="json")
        shot_id = request.shot_id
        scene_ref = request.scene_ref
        try:
            print(f"[MW3DGuidedEngine.render_shot] start shot_id={shot_id} scene_ref={scene_ref} url={self.base_url}/api/shot/render")
            response = self.session.post(
                f"{self.base_url}/api/shot/render",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            print(f"[MW3DGuidedEngine.render_shot] success shot_id={shot_id}")
            return ShotRenderResponse(**result)
        except requests.Timeout as exc:
            print(f"[MW3DGuidedEngine.render_shot] timeout shot_id={shot_id}, fallback to generate_images: {exc}")
        except requests.RequestException as exc:
            print(f"[MW3DGuidedEngine.render_shot] request failed shot_id={shot_id}, fallback to generate_images: {type(exc).__name__}: {exc}")

        positive_prompt = request.prompt.positive
        image_paths = self.generate_images(
            prompt=positive_prompt,
            n=request.n,
            size=request.size,
        )
        return ShotRenderResponse(success=True, image_paths=image_paths)

    def release(self):
        self.session.close()
