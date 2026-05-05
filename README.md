# Mindawaker

AI 视频生成系统 - 基于 FastAPI + React 的现代化解决方案

## ✨ 功能特性

- 🤖 **AI 驱动**: 支持 DeepSeek、OpenAI、Flux 等多种 AI 模型
- 🎬 **视频生成**: 文案 → 音频 → 图像 → 视频 一站式合成
- 🛑 **随时撤回**: 支持取消正在进行的生成任务
- 📊 **实时进度**: WebSocket 实时推送生成进度
- 💾 **任务持久化**: SQLite 存储，服务重启不丢失进度
- 🎨 **现代化 UI**: React + Tailwind CSS + shadcn/ui
- 📝 **统一日志**: 结构化日志，支持文件轮转
- 🛡️ **异常处理**: 全局异常捕获，友好的错误信息

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
