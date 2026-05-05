from __future__ import annotations

import argparse

import uvicorn


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start media tagging and retrieval service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run("media_service.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
