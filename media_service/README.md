# media_service

本项目提供一个本地 HTTP 服务，用于媒体文件打标、建立索引和文本检索。

默认通过 FastAPI + Uvicorn 在 `6000` 端口启动。

## 安装依赖

```bash
python -m pip install -r "E:/ClaudeTest/media_service/requirements.txt"
```

内容分析默认使用 `Qwen/Qwen2.5-VL-7B-Instruct`。

首次运行时模型会从 Hugging Face 下载。建议优先使用 GPU；如需强制 CPU，可设置环境变量：

```bash
export MEDIA_SERVICE_CONTENT_DEVICE=cpu
```

Windows PowerShell 可用：

```powershell
$env:MEDIA_SERVICE_CONTENT_DEVICE = "cpu"
```

可选配置项：

- `MEDIA_SERVICE_CONTENT_PROVIDER`，默认 `qwen2_5_vl`
- `MEDIA_SERVICE_CONTENT_MODEL`，默认 `Qwen/Qwen2.5-VL-7B-Instruct`
- `MEDIA_SERVICE_CONTENT_MODEL_ROOT`，默认 `/root/autodl-tmp/models`
- `MEDIA_SERVICE_CONTENT_MODEL_PATH`，默认 `/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct`
- `MEDIA_SERVICE_CONTENT_DEVICE`，默认 `auto`
- `MEDIA_SERVICE_CONTENT_MAX_NEW_TOKENS`，默认 `256`
- `MEDIA_SERVICE_CONTENT_VIDEO_FRAME_COUNT`，默认 `6`
- `MEDIA_SERVICE_DEFAULT_MEDIA_LIBRARY_ROOT`，默认 `E:/ClaudeTest/media_service_test_assets`
- `MEDIA_SERVICE_DEFAULT_ANNOTATION_ROOT`，默认 `E:/ClaudeTest/media_service_test_assets/scan_out`

其中：
- `MEDIA_SERVICE_CONTENT_MODEL_PATH` 用来指定模型“加载路径”
- `MEDIA_SERVICE_CONTENT_MODEL_ROOT` 用来指定 Hugging Face 的缓存/下载目录
- 如果 `MEDIA_SERVICE_CONTENT_MODEL_PATH` 存在，就优先从本地路径加载；否则回退到 `MEDIA_SERVICE_CONTENT_MODEL`
- 如果接口里不传 `input_dir` / `output_dir` / `annotation_root`，会自动使用上面的默认素材库和默认 JSON 目录

例如你想固定成：

```bash
export MEDIA_SERVICE_CONTENT_MODEL_ROOT=/root/autodl-tmp/models
export MEDIA_SERVICE_CONTENT_MODEL_PATH=/root/autodl-tmp/models/Qwen2.5-VL-7B-Instruct
export MEDIA_SERVICE_DEFAULT_MEDIA_LIBRARY_ROOT=E:/ClaudeTest/media_service_test_assets
export MEDIA_SERVICE_DEFAULT_ANNOTATION_ROOT=E:/ClaudeTest/media_service_test_assets/scan_out
```

如果后续要接其它模型，可在 `media_service/analyzers/providers/` 下新增 provider，并在 `media_service/analyzers/content.py` 中注册。


## 启动服务

```bash
python -m media_service.start
```

可选参数：

```bash
python -m media_service.start --host 0.0.0.0 --port 6000 --reload
```

服务启动后可访问：

- `GET /`
- `GET /health`

## 主要接口

### 1. 扫描目录并生成标注

`POST /tag/scan`

请求体：

```json
{
  "input_dir": "E:/path/to/media",
  "output_dir": "E:/path/to/annotations",
  "overwrite": true,
  "recursive": true
}
```

### 2. 对单个文件打标

`POST /tag/file`

请求体：

```json
{
  "file_path": "E:/path/to/media/example.png",
  "input_root": "E:/path/to/media",
  "output_dir": "E:/path/to/annotations",
  "overwrite": true
}
```

返回结果中会包含：

- `annotation`: 当前文件的标注内容
- `output`: 写出的 JSON 路径

### 3. 构建索引

`POST /index/build`

请求体：

```json
{
  "annotation_root": "E:/path/to/annotations"
}
```

### 4. 查看索引统计

`GET /index/stats?annotation_root=E:/path/to/annotations`

### 5. 构建窗口索引（目录）

`POST /window-index/scan`

请求体：

```json
{
  "input_dir": "E:/path/to/media",
  "output_dir": "E:/path/to/scan_out",
  "overwrite": true,
  "recursive": true,
  "window_sizes_sec": [2.0, 5.0, 10.0],
  "stride_ratio": 0.5,
  "sample_fps": 1.0,
  "max_frames_per_window": 8,
  "min_window_coverage_ratio": 0.5,
  "enable_semantic_caption": false
}
```

输出目录会在 `scan_out/window_indices/` 下生成窗口索引 JSON，同时维护 `manifest.json`（`source_path -> index_file`）。

### 6. 构建窗口索引（单文件）

`POST /window-index/file`

请求体：

```json
{
  "file_path": "E:/path/to/media/demo.mp4",
  "input_root": "E:/path/to/media",
  "output_dir": "E:/path/to/scan_out",
  "window_sizes_sec": [2.0, 5.0, 10.0],
  "stride_ratio": 0.5,
  "sample_fps": 1.0,
  "max_frames_per_window": 8,
  "min_window_coverage_ratio": 0.5,
  "enable_semantic_caption": false
}
```

### 7. 文本检索

`POST /retrieve/search`

文件级检索请求体：

```json
{
  "text": "calm image",
  "annotation_root": "E:/path/to/annotations",
  "top_k": 3,
  "prefer_media_type": "image",
  "explain": true,
  "search_mode": "file_level"
}
```

窗口级检索请求体：

```json
{
  "text": "转场到城市街道",
  "annotation_root": "E:/path/to/annotations",
  "window_annotation_root": "E:/path/to/scan_out",
  "top_k": 3,
  "search_mode": "window_level",
  "ranking_strategy": "cascade_v1",
  "coarse_top_n": 50,
  "fine_top_k": 10
}
```

返回中 `source_scope` 表示命中来源：

- `file`：整文件命中
- `window`：窗口命中（同时返回 `window_id/start_sec/end_sec/window_level`）

### 8. 批量检索

`POST /retrieve/batch`

如需启用顺序连贯重排，设置：

```json
{
  "search_mode": "window_level",
  "ranking_strategy": "cascade_sequence_v1",
  "window_level_preferred": true
}
```

### 9. 单条解释

`POST /retrieve/explain`

## 推荐调用顺序

1. `POST /tag/scan` 或 `POST /tag/file`
2. `POST /index/build`
3. `GET /index/stats`
4. `POST /retrieve/search`

## 本地验证结果

已验证以下链路可用：

1. `GET /health`
2. `POST /tag/file`
3. `POST /tag/scan`
4. `POST /index/build`
5. `GET /index/stats`
6. `POST /retrieve/search`

验证使用的本地测试目录示例：

- 输入目录：`E:/ClaudeTest/media_service_test_assets`
- 标注输出目录：`E:/ClaudeTest/media_service_test_assets/scan_out`

## 说明

当前内容分析默认通过 `Qwen2.5-VL-7B` 生成 `caption`、`objects`、`scene_tags`、`action_tags`。

如果模型依赖未安装、模型下载失败或运行环境不满足推理要求，`ContentAnalyzer` 会回退到最小可用结果，避免整个打标流程直接崩溃。视频内容分析当前采用“抽帧 + 图片模型聚合”的方式，便于后续替换为其它 provider。