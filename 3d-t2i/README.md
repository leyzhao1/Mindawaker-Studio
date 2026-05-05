# MindAwaker - 3D-Guided Text-to-Image Engine

结构化叙事到可控视觉生成引擎。

> 输入自然语言 → 解析为结构化镜头 → 构建粗3D场景 → 导出深度图 → 控制生成图像

## ✨ 核心特性

- **结构化生成**: 自然语言解析为结构化场景描述
- **3D引导**: 粗粒度3D场景控制图像构图
- **多视角一致**: 同一场景多视角生成，保持结构和角色一致
- **分层架构**: Scene Blueprint → Instance → Shot 三层分离
- **确定性生成**: 相同场景描述总是生成相同的3D布局

## 项目结构

```
mw-3d-guided-t2i/
├── app/                          # Python 后端
│   ├── api/server.py             # FastAPI 服务
│   ├── llm/                      # LLM 模块
│   │   ├── shot_parser.py        # 文本 → Shot JSON
│   │   └── prompt_builder.py     # JSON → Prompt
│   ├── scene/                    # 场景模块
│   │   ├── templates.py          # 场景模板
│   │   ├── scene_builder.py      # JSON → 3D 场景（旧版）
│   │   ├── instance_builder.py   # Blueprint → Instance（新版）
│   │   └── object_library.py     # 物体库
│   ├── comfy/                    # ComfyUI 模块
│   │   ├── client.py             # API 客户端
│   │   └── workflow_loader.py    # 工作流配置
│   └── pipeline/                 # 流水线
│       ├── run_single_shot.py    # 单镜头生成（旧版）
│       ├── consistent_pipeline.py # 一致性Pipeline
│       ├── hierarchical_pipeline.py # 分层架构Pipeline（推荐）
│       ├── scene_cache.py        # 场景缓存
│       └── character_consistency.py # 角色一致性
├── web/                          # 前端
│   └── threejs_depth_renderer/   # Three.js 深度渲染器
├── data/                         # 数据目录
│   ├── inputs/                   # 输入文本
│   ├── outputs/                  # 最终输出
│   ├── cache/                    # 场景缓存
│   │   ├── instances/            # Scene Instance缓存
│   │   └── characters/           # 角色缓存
│   └── depth/                    # 深度图
├── configs/                      # 配置文件
│   └── default.yaml
├── examples/                     # 示例代码
│   ├── consistency_demo.py       # 一致性生成演示
│   └── hierarchical_demo.py      # 分层架构演示
└── docs/                         # 文档
    ├── consistency_guide.md      # 一致性使用指南
    └── hierarchical_architecture.md # 分层架构设计
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt

# 可选：安装Playwright实现自动深度图渲染
pip install playwright
playwright install chromium
```

### 2. 使用分层架构Pipeline（推荐）

**生成多视角图像（自动保持结构和角色一致）：**

```python
from app.pipeline import HierarchicalPipeline

pipeline = HierarchicalPipeline()

# 一键生成多视角
shots = pipeline.create_multi_view_shots(
    description="一个小孩站在桌子旁边，花盆在桌子上",
    views=["侧面", "俯视", "正面"]
)

results = pipeline.render_shots(shots)

# 结果：三个视角共享同一个3D场景，角色外观一致
for shot, result in zip(shots, results):
    print(f"{shot.camera.view}: {result['output_image']}")
```

**命令行使用：**

```bash
# 运行示例
python examples/hierarchical_demo.py basic

# 查看所有演示
python examples/hierarchical_demo.py --help
```

### 3. 使用旧版Pipeline

```bash
# 完整流程（文本 -> 场景 -> 工作流）
python app/pipeline/run_single_shot.py --text "室内，一个孩子站在桌边，桌上有花盆，侧面视角"

# 包含生成
python app/pipeline/run_single_shot.py --text "..." --generate
```

## 分层架构详解

### 三层架构

```
Shot (镜头)
├── scene_id: 引用Scene Instance
└── camera: {view, pitch, yaw, distance, ...}
         │
         │ 引用
         ▼
Scene Instance (场景实例)
├── blueprint_id: 引用Blueprint
├── instance_id: 唯一标识
├── style_id: 样式标识
├── objects: [3D对象（含坐标）]
└── character_bindings: {角色绑定}
         ▲
         │ 构建
         │
Scene Blueprint (场景蓝图)
├── blueprint_id: 基于内容哈希
├── template: 模板类型
└── objects: [对象类型和关系]
```

**关键特性：**

1. **Blueprint与视角无关**: "侧面角度"和"俯视角度"共享相同的Blueprint
2. **Instance复用**: 多个Shots可以引用同一个Instance，保持3D结构一致
3. **角色绑定在Instance层**: 确保多视角下角色外观一致

### 使用示例

```python
from app.pipeline import HierarchicalPipeline
from app.schema import SceneBlueprint, BlueprintObject

pipeline = HierarchicalPipeline()

# 方法1: 从文本自动创建
shots = pipeline.create_multi_view_shots(
    "一个小孩站在桌子旁边，花盆在桌子上",
    views=["侧面", "俯视", "正面"]
)

# 方法2: 手动控制Scene Instance生命周期
blueprint = SceneBlueprint(
    template="indoor_room",
    objects=[
        BlueprintObject(id="child_1", type="child"),
        BlueprintObject(id="table_1", type="table"),
        BlueprintObject(id="flowerpot_1", type="flowerpot",
                       relation="on_top_of:table_1"),
    ]
)

# 构建Instance（会被缓存）
instance = pipeline.build_instance(blueprint, style_id="storybook_warm")

# 创建不同视角的Shots引用同一个Instance
from app.schema import Shot, CameraConfig

shot1 = Shot(scene_id=instance.instance_id,
             camera=CameraConfig(view="side"))
shot2 = Shot(scene_id=instance.instance_id,
             camera=CameraConfig(view="top"))

# 渲染
results = pipeline.render_shots([shot1, shot2])
```

## 多视角一致性

### 问题

相同场景不同视角生成时，经常遇到：
- **结构不一致**: 每次物体位置不同
- **渲染不一致**: 每次角色外观不同

### 解决方案

#### 1. 场景缓存（解决结构一致）

基于场景内容哈希缓存3D结构：

```python
# 第一次生成
def result1 = pipeline.run_from_text("...侧面...")
# Instance自动缓存

# 第二次生成
def result2 = pipeline.run_from_text("...俯视...")
# 复用同一个Instance，物体位置完全一致
```

#### 2. 角色一致性（解决渲染一致）

支持三种方法：

| 方法 | 效果 | 配置要求 | 使用场景 |
|------|------|----------|----------|
| **Fixed Seed** | ⭐⭐ | 无 | 快速测试 |
| **IP-Adapter** | ⭐⭐⭐⭐⭐ | 安装ComfyUI_IPAdapter_plus | 生产环境（推荐） |
| **Reference Only** | ⭐⭐⭐ | ControlNet | 备选方案 |

```python
# 使用IP-Adapter（效果最好）
pipeline = HierarchicalPipeline(consistency_method="ip_adapter")

# 第一个视角生成后自动保存参考图
result1 = pipeline.render_shot(shot1)

# 后续视角自动使用IP-Adapter保持一致
result2 = pipeline.render_shot(shot2)
```

完整文档：[docs/consistency_guide.md](docs/consistency_guide.md)

## 生成深度图

### 方法 A：自动渲染（推荐）

安装 Playwright 后即可自动在后台渲染深度图：

```bash
pip install playwright
playwright install chromium
```

然后在运行 pipeline 时会自动渲染深度图，无需打开浏览器。

### 方法 B：手动渲染

如果不想安装 Playwright，可以手动渲染。

**先启动前端页面（推荐用本地静态服务器）：**

```bash
# 在项目根目录执行
python -m http.server 9000 --directory web/threejs_depth_renderer
```

浏览器打开：

```text
http://127.0.0.1:9000/index.html
```

> 也可以直接双击 `web/threejs_depth_renderer/index.html`，但部分浏览器对 `file://` 下的 ES Module 加载有限制，建议优先使用本地服务器。

然后：

1. 点击 "Load Scene JSON"，加载生成的 `scene.json` 文件
2. 点击 "Export Depth Map"
3. 保存到 `data/depth/depth_map.png`

## 启动 API 服务

```bash
python app/api/server.py
```

服务将在 `http://localhost:7000` 启动。

## 前端界面（两个入口）

### 1) 全链路实验前端（推荐）

这个页面用于完整测试：
`parse → scene/build → prompt/build → workflow/build → depth(render/upload) → generate`

启动 API 后，浏览器打开：

```text
http://127.0.0.1:7000/web/test_frontend/index.html
```

**Step 5 两种方式：**
- **Generate Depth（推荐）**：调用 `/api/depth/render`，使用当前 scene_data 自动生成 `data/depth/depth_map.png`，并上传到 ComfyUI input。
- **Upload Depth（兜底）**：手工选择 `depth_map.png` 调用 `/api/depth/upload`。

> `Generate Depth` 默认 `method=auto`：优先 Playwright，无 Playwright 时可切换 simple 渲染（后端也会返回错误提示用于诊断）。

### 2) 深度图渲染前端

用于手动渲染/导出 depth map：

```text
http://127.0.0.1:7000/web/threejs_depth_renderer/index.html
```

> 说明：`test_frontend` 的接口地址是相对路径（如 `/api/parse`），建议通过 API 服务挂载的 `/web/...` 路径访问，而不是直接双击 HTML 文件。

**API 端点：**

| 端点 | 描述 |
|------|------|
| `POST /api/parse` | 文本解析为 Shot JSON |
| `POST /api/scene/build` | 构建 3D 场景 |
| `POST /api/prompt/build` | 构建生成提示词 |
| `POST /api/workflow/build` | 构建 ComfyUI 工作流 |
| `POST /api/depth/render` | 根据 scene_data 自动渲染 depth 图（可选上传） |
| `POST /api/depth/upload` | 上传已有 depth 图 |
| `POST /api/generate` | 生成图像 |
| `POST /api/pipeline/full` | 完整流水线 |

### 使用 API 示例

```bash
# 解析文本
curl -X POST "http://localhost:7000/api/parse" \
  -H "Content-Type: application/json" \
  -d '{"text": "室内，一个孩子站在桌边，桌上有花盆"}'

# 完整流水线
curl -X POST "http://localhost:7000/api/pipeline/full" \
  -H "Content-Type: application/json" \
  -d '{"text": "室内，一个孩子站在桌边，桌上有花盆"}'
```

## Shot JSON 格式

```json
{
  "template": "indoor_room",
  "camera": {
    "view": "side",
    "shot": "medium"
  },
  "objects": [
    {
      "id": "obj1",
      "type": "child",
      "position": "left"
    },
    {
      "id": "obj2",
      "type": "table",
      "position": "center"
    },
    {
      "id": "obj3",
      "type": "flowerpot",
      "relation": "on_top_of:obj2"
    }
  ],
  "lighting": {
    "type": "indoor_warm"
  },
  "style_prompt": "warm indoor lighting, storybook illustration"
}
```

## 配置

编辑 `configs/default.yaml`：

```yaml
comfyui:
  server_url: "http://127.0.0.1:8188"
  models:
    checkpoint: "sd_xl_base_1.0.safetensors"
    controlnet: "control_v11f1p_sd15_depth.pth"

llm:
  provider: "openai"
  model: "gpt-4o"

# 一致性配置
consistency:
  method: "fixed_seed"  # 或 "ip_adapter", "reference_only"
  cache_dir: "./data/cache"
```

## 工作流程

```
文本输入
   ↓
[LLM] Shot Parser
   ↓
Scene Blueprint（结构化描述，与视角无关）
   ↓
[Instance Builder] 构建 Scene Instance（3D坐标 + 样式 + 角色绑定）
   ↓
创建多个 Shots（不同相机配置）
   ↓
Three.js 渲染 depth（相同Instance，不同相机）
   ↓
[Prompt Builder] 生成提示词（含角色一致性增强）
   ↓
[ComfyUI] ControlNet (depth) + IP-Adapter（可选）
   ↓
输出图像（结构和角色一致的多个视角）
```

## 可用模板

- `indoor_room` - 室内房间
- `street` - 城市街道
- `bridge_river` - 河边桥梁

## 可用物体

- 人物：`child`, `adult`, `boy`, `girl`, `man`, `woman`
- 家具：`table`, `chair`
- 装饰：`flowerpot`, `book`, `lamp`
- 环境：`building`, `tree`, `car`, `bridge`, `river`

## 关系类型

- `on_top_of:target_id` - 在目标上方
- `beside:target_id` - 在目标旁边
- `beside_left:target_id` - 在目标左侧
- `beside_right:target_id` - 在目标右侧
- `in_front_of:target_id` - 在目标前方
- `behind:target_id` - 在目标后方
- `inside:target_id` - 在目标内部
- `near:target_id` - 在目标附近

## Troubleshooting / 问题排查

### 错误："tuple index out of range" 或 "prompt_outputs_failed_validation"

这个错误通常表示：
1. **深度图文件不存在** - 确保 `depth_map.png` 在正确位置
2. **模型未安装** - 确保 Checkpoint 和 ControlNet 模型已下载
3. **ComfyUI 未启动** - 确保 ComfyUI 服务正在运行

运行诊断脚本：
```bash
python debug_workflow.py
```

### 快速修复步骤

1. **确保深度图存在**：
```bash
# 检查文件
ls data/depth/depth_map.png

# 如果不存在，重新生成
python demo_single_shot.py "室内场景描述"
```

2. **确保模型已安装**：
```bash
# 检查 ComfyUI 模型目录
ls ComfyUI/models/checkpoints/
ls ComfyUI/models/controlnet/
```

3. **确保 ComfyUI 运行**：
```bash
cd ComfyUI
python main.py
```

4. **复制深度图到 ComfyUI input 目录**：
```bash
cp data/depth/depth_map.png ComfyUI/input/
```

### IP-Adapter 配置

如果使用 `consistency_method="ip_adapter"`，需要：

```bash
# 1. 安装ComfyUI节点
cd ComfyUI/custom_nodes
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus

# 2. 下载模型到 ComfyUI/models/ipadapter/
# 下载地址：https://huggingface.co/h94/IP-Adapter
```

## Current Limitations / 当前限制

1. **Parser 精度**: Rule-based parser 对环境词过滤不完善，复杂句式可能解析错误
2. **物体类型**: 仅支持 12 种基础物体，缺乏精细建模
3. **Relation 系统**: 仅支持基础的 on_top_of/beside/behind/in_front_of/inside
4. **深度图**: 自动渲染需要安装 Playwright；简化渲染器（无浏览器）效果较基础
5. **ComfyUI 依赖**: 需要本地运行 ComfyUI，且模型需要手动安装
6. **相机控制**: 支持预设视角和基本角度控制，暂不支持精确的目标跟踪
7. **多镜头**: 暂不支持多镜头叙事

## 开发计划

- [x] Phase 1: 核心框架（JSON → 场景 → depth → 生图）
- [x] Phase 1.5: 稳定性重构（Pydantic 模型、测试覆盖、配置化）
- [x] Phase 1.6: 多视角一致性（场景缓存 + 角色一致性）
- [x] Phase 1.7: 分层架构（Scene Blueprint → Instance → Shot）
- [ ] Phase 2: 改进 LLM Parser，接入 GPT-4/Claude
- [ ] Phase 3: 扩展模板系统和物体库
- [ ] Phase 4: 服务器端深度图渲染
- [ ] Phase 5: Web UI 和可视化编辑器

## Testing

运行测试：

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_shot_parser.py -v
pytest tests/test_scene_builder.py -v
pytest tests/test_prompt_builder.py -v
```

## 示例

### 快速体验完整流程

```bash
# 从文本生成所有中间文件
python demo_single_shot.py "室内，一个孩子站在桌边，桌上有花盆，侧面视角"
```

### 分层架构演示

```bash
# 基本多视角生成
python examples/hierarchical_demo.py basic

# 缓存复用演示
python examples/hierarchical_demo.py cache

# 手动Blueprint创建
python examples/hierarchical_demo.py blueprint

# 对比新旧架构
python examples/hierarchical_demo.py compare
```

### 一致性演示

```bash
# Fixed Seed方法
python examples/consistency_demo.py fixed_seed

# IP-Adapter方法（需要配置）
python examples/consistency_demo.py ip_adapter
```

## License

MIT
