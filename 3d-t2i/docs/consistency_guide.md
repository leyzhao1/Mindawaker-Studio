# 多视角一致性生成指南

## 问题背景

在使用3D引导的文本到图像生成时，当描述的场景内容相同但视角不同时（如"侧面角度" vs "俯视角度"），会出现两个问题：

1. **结构不一致**：3D场景中物体的位置每次都有细微差别
2. **渲染不一致**：生成的人物角色外观每次都不一样

## 解决方案概述

我们提供了两个层面的解决方案：

### 1. 场景缓存 (Scene Cache)
- **作用**：确保相同场景内容复用相同的3D结构
- **原理**：基于场景内容（物体及其关系）生成唯一哈希作为缓存key
- **效果**：不同视角的物体位置完全一致

### 2. 角色一致性 (Character Consistency)
- **作用**：确保多视角下角色外观一致
- **三种方法**：
  - **Fixed Seed**: 固定随机种子，最简单但效果有限
  - **IP-Adapter**: 使用参考图像引导生成，效果最好
  - **Reference Only**: 使用ControlNet reference模式，无需额外模型

## 快速开始

### 基础用法

```python
from app.pipeline.consistent_pipeline import ConsistentPipeline

# 创建pipeline
pipeline = ConsistentPipeline(
    comfy_url="http://127.0.0.1:8188",
    consistency_method="fixed_seed"  # 或 "ip_adapter"
)

# 生成第一个视角（自动缓存场景和角色）
result1 = pipeline.run_from_text(
    "一个小孩站在桌子旁边，桌子上有个花盆，侧面角度"
)

# 生成第二个视角（复用缓存的场景结构）
result2 = pipeline.run_from_text(
    "一个小孩站在桌子旁边，桌子上有个花盆，俯视角度"
)
```

### 批量生成多视角

```python
# 一次性生成多个视角，自动保持一致性
results = pipeline.generate_multiple_views(
    base_description="一个小孩站在桌子旁边，桌子上有个花盆",
    views=["side", "top", "front", "three_quarter"],
    consistency_method="ip_adapter"
)

# 结果包含所有视角的图像
for view, result in results["views"].items():
    print(f"{view}: {result['output_image']}")
```

## 三种一致性方法对比

### 方法1: Fixed Seed（固定种子）

```python
pipeline = ConsistentPipeline(consistency_method="fixed_seed")
```

**优点**：
- 无需额外配置
- 实现简单

**缺点**：
- 只能保证部分一致性
- 视角变化大时效果差
- 人物细节仍可能有差异

**适用场景**：快速测试、对一致性要求不高的场景

---

### 方法2: IP-Adapter（推荐）

```python
pipeline = ConsistentPipeline(consistency_method="ip_adapter")
```

**安装要求**：
```bash
# 在ComfyUI中安装IP-Adapter节点包
cd ComfyUI/custom_nodes
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus

# 下载IP-Adapter模型
# 将模型放到 ComfyUI/models/ipadapter/
# 下载地址：https://huggingface.co/h94/IP-Adapter
```

**工作原理**：
1. 第一个视角生成后，自动保存为参考图像
2. 后续视角使用IP-Adapter加载参考图像
3. IP-Adapter在生成过程中引导人物特征保持一致

**优点**：
- 效果最好
- 可以控制强度
- 支持多张参考图

**缺点**：
- 需要额外安装节点包
- 需要下载模型文件

**适用场景**：对角色一致性要求高的生产环境

---

### 方法3: Reference Only

```python
pipeline = ConsistentPipeline(consistency_method="reference_only")
```

**安装要求**：
- 需要ControlNet inpaint模型

**工作原理**：
- 使用ControlNet的reference-only模式
- 将第一张图作为风格/内容参考

**优点**：
- 不需要额外安装节点（如果有ControlNet）
- 实现相对简单

**缺点**：
- 效果不如IP-Adapter稳定
- 可能影响深度ControlNet的效果

**适用场景**：无法安装IP-Adapter时的备选方案

## 高级用法

### 手动管理角色

```python
from app.pipeline.character_consistency import CharacterConsistencyManager

# 创建角色管理器
manager = CharacterConsistencyManager()

# 注册角色（带参考图）
manager.register_character(
    character_id="child_001",
    description="a 5-year-old boy, red t-shirt, blue shorts",
    reference_images=["path/to/reference.png"],
    seed=42
)

# 在pipeline中使用
pipeline = ConsistentPipeline()
pipeline.character_manager = manager
```

### 清除缓存

```python
# 清除场景缓存（保留角色信息）
pipeline.scene_cache.clear_cache()

# 强制重新生成场景（忽略缓存）
result = pipeline.run_from_text(
    "...",
    force_new_scene=True
)
```

### 自定义缓存目录

```python
pipeline = ConsistentPipeline(
    cache_dir="./my_cache",  # 场景和角色缓存
    output_dir="./my_outputs"
)
```

## 缓存机制详解

### 场景缓存

缓存基于场景内容的哈希值：
```python
# 包含在哈希计算中
template, objects, lighting, style_prompt

# 不包含（可以变化而不影响缓存）
camera.view, camera.position
```

这意味着：
- `"侧面角度"` 和 `"俯视角度"` 共享同一个3D结构缓存
- 改变物体类型或位置会生成新的缓存

### 角色缓存

角色ID基于场景中的第一个人物类型对象：
```python
# 以下描述会识别为同一角色
"一个小孩站在桌子旁边，桌子上有个花盆，侧面角度"
"一个小孩站在桌子旁边，桌子上有个花盆，俯视角度"

# 改变风格会识别为不同角色
"一个小孩站在桌子旁边，桌子上有个花盆，侧面角度，卡通风格"
```

## 故障排除

### 问题：缓存不生效

检查：
1. 确认两次调用的objects完全相同（包括id）
2. 检查缓存目录权限
3. 使用`force_new_scene=False`（默认）

### 问题：IP-Adapter报错

解决：
1. 确认ComfyUI_IPAdapter_plus已正确安装
2. 检查模型路径：`ComfyUI/models/ipadapter/`
3. 确认工作流节点ID不冲突

### 问题：角色仍不一致

建议：
1. 在prompt中加入角色描述细节
2. 使用更高强度的IP-Adapter（修改`ipadapter_strength`）
3. 提供更高质量的参考图

## 最佳实践

1. **先生成侧面视角**：侧面视角通常能最好地展示角色特征，适合作为参考
2. **使用IP-Adapter**：如果对一致性要求高，建议配置IP-Adapter
3. **适当增强prompt**：即使使用技术手段，也应在prompt中描述角色特征
4. **管理参考图像**：定期清理旧的参考图像，保持角色管理器整洁

## 示例代码

完整示例见：`examples/consistency_demo.py`

```python
# 展示不同一致性方法的效果对比
from app.pipeline.consistent_pipeline import ConsistentPipeline

base_desc = "一个小孩站在桌子旁边，桌子上有个花盆"
views = ["side", "top", "front"]

for method in ["fixed_seed", "ip_adapter"]:
    print(f"\n使用 {method}:")
    pipeline = ConsistentPipeline(consistency_method=method)

    results = pipeline.generate_multiple_views(
        base_description=base_desc,
        views=views
    )
```
