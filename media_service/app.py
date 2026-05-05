from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from media_service.config.exceptions import setup_exception_handlers
from media_service.router.health_router import router as health_router
from media_service.router.index_router import router as index_router
from media_service.router.retrieval_router import router as retrieval_router
from media_service.router.tag_router import router as tag_router
from media_service.router.window_index_router import router as window_index_router


app = FastAPI(
    title="Media Tagging & Retrieval Service",
    description="Local media tagging and retrieval service with web interface",
    version="0.2.0",
)

setup_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建静态文件目录
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)

# 挂载静态文件服务
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 根路由返回前端页面
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """返回前端界面"""
    index_html = static_dir / "index.html"
    if index_html.exists():
        return HTMLResponse(content=index_html.read_text(encoding="utf-8"))
    else:
        # 如果index.html不存在，返回简单页面
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Media Service Frontend</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                .container { max-width: 800px; margin: 0 auto; }
                h1 { color: #333; }
                .message { background: #f0f0f0; padding: 20px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Media Service Frontend</h1>
                <div class="message">
                    <p>Frontend interface is being built. Please check back later.</p>
                    <p>API endpoints are available at:</p>
                    <ul>
                        <li><a href="/docs">/docs</a> - API documentation</li>
                        <li><a href="/tag">/tag/*</a> - Tagging endpoints</li>
                        <li><a href="/index">/index/*</a> - Index endpoints</li>
                        <li><a href="/window-index">/window-index/*</a> - Window index endpoints</li>
                        <li><a href="/retrieve">/retrieve/*</a> - Retrieval endpoints</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """)

app.include_router(health_router)
app.include_router(tag_router, prefix="/tag", tags=["tag"])
app.include_router(index_router, prefix="/index", tags=["index"])
app.include_router(window_index_router, prefix="/window-index", tags=["window-index"])
app.include_router(retrieval_router, prefix="/retrieve", tags=["retrieve"])
