from __future__ import annotations

import argparse
import json
from pathlib import Path

from media_service.model.schemas import SearchRequest
from media_service.service.retrieval_service import RetrievalService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retrieve media from annotation JSON files")
    parser.add_argument("--text", required=True)
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--texts-file")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--prefer-media-type", default="auto", choices=["auto", "image", "video", "mixed"])
    parser.add_argument("--explain", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    texts = None
    if args.texts_file:
        texts = Path(args.texts_file).read_text(encoding="utf-8")
    service = RetrievalService()
    result = service.search(
        SearchRequest(
            text=args.text,
            texts=texts,
            annotation_root=str(Path(args.annotations).resolve()),
            top_k=args.top_k,
            prefer_media_type=args.prefer_media_type,
            explain=args.explain,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
