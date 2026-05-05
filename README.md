# Mindawaker Studio

端到端 AI 视频生成系统 — 三个子项目协作完成从文本到视频的全链路

## 项目结构

| 子项目 | 说明 | 核心技术 |
|--------|------|---------|
| `app/` + `mindawaker-web/` | **Mindawaker** 主应用 | FastAPI + Next.js + LangChain + FFmpeg |
| `media_service/` | **多粒度窗口检索** | Qwen2.5-VL-7B + OpenCV + 两阶段级联检索 |
| `3d-t2i/` | **3D 引导多视角生成** | ComfyUI + Zero123++ + Poisson 融合 |

## ✨ 核心能力

- **叙事一致性**: LLM 三阶段解析（角色→场景→镜头），结构化 prompt 注入
- **语义级视频检索**: 多粒度时间窗口（2s/5s/10s）索引，粗排语义 F1 → 精排 6 维打分
- **3D 一致性**: 深度引导多视角图像生成 + Poisson 混合
- **全链路合成**: 文本 → TTS 音频 → 背景检索 → 3D 角色 → FFmpeg 多轨合成

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone <repository-url>
cd mindawaker
```

### 2. 配置环境

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 API 密钥
```

### 3. 启动后端

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python start.py --reload

# 或使用 make
make run
```

后端服务将运行在 http://localhost:8000

API 文档: http://localhost:8000/docs

### 4. 启动前端

```bash
cd mindawaker-web

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将运行在 http://localhost:3000

## 🧪 测试

```bash
# 运行所有测试
pytest tests/ -v

# 或使用 make
make test
```

## 🎨 代码格式化

```bash
# 格式化代码
black app/ tests/ --line-length 100
ruff check app/ tests/ --fix

# 代码检查
ruff check app/ tests/
mypy app/ --ignore-missing-imports

# 或使用 make
make format
make lint
```

## 📁 项目结构

```
mindawaker/
├── app/                      # 后端应用
│   ├── config/              # 配置文件
│   │   ├── logging_config.py    # 日志配置
│   │   ├── exceptions.py        # 异常处理
│   │   ├── paths.py             # 路径配置
│   │   └── settings.py          # 设置配置
│   ├── model/               # 数据模型 (Pydantic)
│   ├── router/              # API 路由
│   ├── service/             # 业务逻辑
│   │   ├── task_manager.py      # 任务管理器
│   │   ├── video_job.py         # 视频生成任务
│   │   └── ...
│   ├── tts_engine/          # TTS 引擎
│   ├── image_engine/        # 图像生成引擎
│   ├── langchain_pipeline/  # LangChain 管道
│   └── main.py              # 应用入口
├── mindawaker-web/          # React 前端
│   ├── src/
│   │   ├── app/             # Next.js 应用
│   │   ├── components/      # React 组件
│   │   ├── hooks/           # 自定义 Hooks
│   │   └── lib/             # 工具函数
│   └── package.json
├── tests/                   # 单元测试
├── requirements.txt         # Python 依赖
├── pyproject.toml          # Python 项目配置
├── Makefile                # 常用命令
└── start.py                # 启动脚本
```

## 🔌 API 接口

### 视频生成

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/video/compose` | 创建视频任务 |
| POST | `/video/cancel/{task_id}` | 取消任务 |
| GET | `/video/task/{task_id}` | 获取任务状态 |
| WS | `/video/ws/{task_id}` | WebSocket 实时进度 |

### 项目管理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/project/create` | 创建项目 |
| POST | `/project/save` | 保存项目 |
| POST | `/project/load` | 加载项目 |

## 📝 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CORS_ORIGINS` | 允许的跨域域名 | `http://localhost:3000` |
| `HF_HOME` | HuggingFace 缓存路径 | `./cache/huggingface` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_DIR` | 日志目录 | `app/assets/logs` |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License
