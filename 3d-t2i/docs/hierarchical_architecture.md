# 分层架构设计文档

## 概述

新的分层架构将场景生成分为三个清晰的层次：

```
┌─────────────────────────────────────────────────────────────┐
│                        Shot (镜头)                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Camera: {view: "side", position: [...], target: [...]} │ │
│  │  scene_id: "inst_abc123_default"                      │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ 引用
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Scene Instance (场景实例)                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  blueprint_id: "blueprint_hash"                     │    │
│  │  instance_id: "inst_abc123_default"                 │    │
│  │  style_id: "storybook_warm"                         │    │
│  │                                                     │    │
│  │  Objects: [                                         │    │
│  │    {id: "child_1", type: "child", pos: [-1.2, 0, 0.3]}, │ │
│  │    {id: "table_1", type: "table", pos: [0, 0, 0]},      │ │
│  │    {id: "flowerpot_1", type: "flowerpot", pos: [0, 0.85, 0]} │
│  │  ]                                                  │    │
│  │                                                     │    │
│  │  Character Bindings: {                              │    │
│  │    "child_1": {character_id: "char_child_001", ...} │    │
│  │  }                                                  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ 构建
                            │
┌─────────────────────────────────────────────────────────────┐
│                  Scene Blueprint (场景蓝图)                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  blueprint_id: "blueprint_hash"                     │    │
│  │  template: "indoor_room"                            │    │
│  │                                                     │    │
│  │  Objects: [                                         │    │
│  │    {id: "child_1", type: "child"},                  │    │
│  │    {id: "table_1", type: "table"},                  │    │
│  │    {id: "flowerpot_1", type: "flowerpot",           │    │
│  │     relation: "on_top_of:table_1"}                  │    │
│  │  ]                                                  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 三层详解

### 1. Scene Blueprint (场景蓝图)

**定位**: 场景的纯语义描述，不含任何空间信息

**内容**:
```python
@dataclass
class SceneBlueprint:
    blueprint_id: str      # 基于内容哈希
    template: str          # "indoor_room"
    objects: List[BlueprintObject]  # 对象类型和关系
    metadata: Dict         # 样式提示词等
```

**特点**:
- **幂等性**: 相同描述总是生成相同的blueprint_id
- **与视角无关**: "侧面角度"和"俯视角度"的blueprint相同
- **可哈希**: 用于缓存查找

**创建方式**:
```python
# 从文本自动解析
blueprint = pipeline.parse_to_blueprint("一个小孩站在桌子旁边...")

# 手动创建
blueprint = SceneBlueprint(
    template="indoor_room",
    objects=[
        BlueprintObject(id="child_1", type="child"),
        BlueprintObject(id="table_1", type="table"),
        BlueprintObject(id="flowerpot_1", type="flowerpot",
                       relation="on_top_of:table_1"),
    ]
)
```

### 2. Scene Instance (场景实例)

**定位**: 实际3D场景，包含具体坐标和样式绑定

**内容**:
```python
@dataclass
class SceneInstance:
    blueprint_id: str      # 引用Blueprint
    instance_id: str       # 唯一标识
    template: str
    objects: List[InstanceObject]  # 含3D坐标
    style_id: str          # 样式标识
    character_bindings: Dict  # 角色绑定
```

**特点**:
- **确定性**: 相同Blueprint + Style总是生成相同的布局
- **可复用**: 多个Shots可以引用同一个Instance
- **角色绑定**: 一致性控制在Instance层

**缓存策略**:
```
缓存Key: {blueprint_id}_{style_id}
示例: "a3f7b2d8_storybook_warm"
```

这意味着:
- "侧面角度"和"俯视角度"共享同一个Instance缓存
- 改变style（如从"写实"到"卡通"）会创建新的Instance

### 3. Shot (镜头)

**定位**: 最小的渲染单元，只包含相机信息

**内容**:
```python
@dataclass
class Shot:
    shot_id: str
    scene_id: str          # 引用SceneInstance
    camera: CameraConfig   # 视角配置
```

**特点**:
- **轻量**: 只含相机，不含场景数据
- **可组合**: 多个Shots共享Instance
- **灵活**: 可以动态调整相机参数

## 工作流程

### 多视角生成流程

```
用户输入: "一个小孩站在桌子旁边，花盆在桌子上"
                    │
                    ▼
            ┌───────────────┐
            │  文本解析      │
            │ (LLM/规则)     │
            └───────┬───────┘
                    │
                    ▼
            Scene Blueprint
  ┌─────────────────┼─────────────────┐
  │                 │                 │
  ▼                 ▼                 ▼
Shot(侧面)      Shot(俯视)       Shot(正面)
  │                 │                 │
  └─────────────────┼─────────────────┘
                    │
                    ▼
          ┌─────────────────┐
          │  渲染深度图      │
          │  (不同相机位置)   │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │  ComfyUI生成     │
          │  (共享角色绑定)   │
          └────────┬────────┘
                   │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
    image_1   image_2   image_3
    (侧面)    (俯视)    (正面)
```

### 缓存复用流程

```
第一次请求: "...侧面角度"
    │
    ▼
Blueprint(哈希=a3f7b2d8)
    │
    ▼
Instance缓存检查: a3f7b2d8_default
    │ 不存在
    ▼
构建新Instance → 保存缓存
    │
    ▼
渲染Shot

第二次请求: "...俯视角度"
    │
    ▼
Blueprint(哈希=a3f7b2d8)  <- 相同！
    │
    ▼
Instance缓存检查: a3f7b2d8_default
    │ 存在！
    ▼
复用已有Instance
    │
    ▼
渲染Shot（不同相机）
```

## 代码示例

### 基本用法

```python
from app.pipeline import HierarchicalPipeline

pipeline = HierarchicalPipeline()

# 创建多视角Shots（自动复用Instance）
shots = pipeline.create_multi_view_shots(
    description="一个小孩站在桌子旁边，花盆在桌子上",
    views=["侧面", "俯视", "正面"]
)

# 渲染
results = pipeline.render_shots(shots)
```

### 显式控制Instance

```python
# 手动创建Blueprint
blueprint = SceneBlueprint(
    template="indoor_room",
    objects=[...]
)

# 构建Instance（显式控制）
instance = pipeline.build_instance(
    blueprint,
    style_id="storybook_warm",
    force_rebuild=False  # 使用缓存
)

# 创建特定视角的Shot
from app.schema.scene_hierarchy import Shot, CameraConfig

shot = Shot(
    scene_id=instance.instance_id,
    camera=CameraConfig(view="side", pitch=10, yaw=45)
)

result = pipeline.render_shot(shot)
```

### 角色一致性

```python
# 角色绑定在Instance层
instance = pipeline.build_instance(blueprint)

# 第一个视角生成后自动保存参考图
result1 = pipeline.render_shot(shot1)

# 后续视角自动使用IP-Adapter保持角色一致
result2 = pipeline.render_shot(shot2)  # 使用相同参考图
```

## 与旧架构对比

| 特性 | 旧架构 (ConsistentPipeline) | 新架构 (HierarchicalPipeline) |
|------|----------------------------|------------------------------|
| 缓存方式 | 自动基于哈希 | 显式Instance管理 |
| 复用粒度 | 整个场景 | Scene Instance |
| 角色绑定 | 全局管理 | Instance级绑定 |
| 相机控制 | 有限 | 完整（pitch/yaw/distance） |
| API复杂度 | 简单 | 中等 |
| 可控性 | 较低 | 较高 |
| 适用场景 | 快速使用 | 精细控制 |

## 最佳实践

### 1. 使用建议

**使用新架构当**:
- 需要精确控制多视角生成
- 需要管理多个Scene Instance
- 需要显式角色绑定

**使用旧架构当**:
- 快速原型开发
- 简单场景生成
- 不关心内部细节

### 2. 缓存管理

```python
# 清除特定Instance
pipeline.instance_cache.clear_cache()

# 强制重建Instance
instance = pipeline.build_instance(
    blueprint,
    force_rebuild=True
)
```

### 3. 样式管理

```python
# 不同样式 = 不同Instance
instance1 = pipeline.build_instance(blueprint, "storybook_warm")
instance2 = pipeline.build_instance(blueprint, "realistic_cool")

# 相同Blueprint + 不同Style = 独立缓存
```

## 文件结构

```
app/
├── schema/
│   ├── scene_hierarchy.py      # 三层数据模型
│   └── __init__.py
├── scene/
│   ├── instance_builder.py     # Blueprint → Instance
│   └── __init__.py
└── pipeline/
    ├── hierarchical_pipeline.py # 新Pipeline
    └── __init__.py

examples/
└── hierarchical_demo.py        # 使用示例

docs/
└── hierarchical_architecture.md # 本文档
```

## 迁移指南

从旧架构迁移:

```python
# 旧代码
from app.pipeline import ConsistentPipeline

pipeline = ConsistentPipeline()
result1 = pipeline.run_from_text("...侧面...")
result2 = pipeline.run_from_text("...俯视...")

# 新代码
from app.pipeline import HierarchicalPipeline

pipeline = HierarchicalPipeline()
shots = pipeline.create_multi_view_shots(
    "...",
    views=["侧面", "俯视"]
)
results = pipeline.render_shots(shots)
```

兼容层:
```python
# HierarchicalPipeline也支持旧API
pipeline = HierarchicalPipeline()
result = pipeline.run_from_text("...侧面...")  # 仍然可用
```
