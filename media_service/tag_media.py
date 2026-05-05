from __future__ import annotations

import argparse
from pathlib import Path

from media_service.config.settings import default_media_library_root, default_annotation_root
from media_service.service.tagging_service import TaggingService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatically tag image/video assets and output JSON annotations.")
    parser.add_argument("--input", default=str(default_media_library_root()), help="Input directory to recursively scan.")
    parser.add_argument("--output", default=str(default_annotation_root()), help="Output directory for JSON annotation files.")
    parser.add_argument("--no-overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = TaggingService()
    summary = service.process_directory(
        input_dir=Path(args.input).resolve(),
        output_dir=Path(args.output).resolve(),
        overwrite=not args.no_overwrite,
        recursive=True,
    )
    print(summary)


if __name__ == "__main__":
    main()
