"""
ComfyUI Workflow 加载器
支持从配置文件读取模型和参数
"""
import json
from typing import Dict, Any, Optional
from pathlib import Path

# 可选导入验证器
try:
    from .workflow_validator import validate_and_fix_workflow, WorkflowValidator
    VALIDATOR_AVAILABLE = True
except ImportError:
    VALIDATOR_AVAILABLE = False

# 配置文件路径
CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "default.yaml"


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    import yaml
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}


def get_workflow_template_vae_loader(config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    获取使用独立 VAELoader 的工作流模板（解决某些模型不含 VAE 的问题）
    """
    if config is None:
        config = load_config()

    comfy_config = config.get("comfyui", {})
    models = comfy_config.get("models", {})
    gen_params = comfy_config.get("generation", {})
    cn_params = comfy_config.get("controlnet_params", {})

    checkpoint = models.get("checkpoint", "sd_xl_base_1.0.safetensors")
    vae = models.get("vae", "")  # 可选的独立 VAE
    controlnet = models.get("controlnet", "control_v11f1p_sd15_depth.pth")
    width = gen_params.get("width", 1024)
    height = gen_params.get("height", 1024)
    steps = gen_params.get("steps", 30)
    cfg = gen_params.get("cfg", 7.5)
    sampler_name = gen_params.get("sampler_name", "dpmpp_2m")
    scheduler = gen_params.get("scheduler", "karras")
    seed = gen_params.get("seed", 42)
    cn_strength = cn_params.get("strength", 1.0)
    cn_start = cn_params.get("start_percent", 0)
    cn_end = cn_params.get("end_percent", 1)

    # 如果指定了独立 VAE，使用 VAELoader
    if vae:
        vae_node_id = "11"
        vae_ref = [vae_node_id, 0]
    else:
        # 否则使用 CheckpointLoaderSimple 的 VAE 输出
        vae_ref = ["1", 2]

    workflow = {
        "1": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {"text": "", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {"text": "", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {"image": "depth_map.png"},
            "class_type": "LoadImage"
        },
        "6": {
            "inputs": {"control_net_name": controlnet},
            "class_type": "ControlNetLoader"
        },
        "7": {
            "inputs": {
                "strength": cn_strength,
                "conditioning": ["2", 0],
                "control_net": ["6", 0],
                "image": ["5", 0]
            },
            "class_type": "ControlNetApply"
        },
        "8": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "9": {
            "inputs": {
                "samples": ["8", 0],
                "vae": vae_ref
            },
            "class_type": "VAEDecode"
        },
        "10": {
            "inputs": {"filename_prefix": "mw_output", "images": ["9", 0]},
            "class_type": "SaveImage"
        }
    }

    # 如果使用独立 VAE，添加 VAELoader 节点
    if vae:
        workflow[vae_node_id] = {
            "inputs": {"vae_name": vae},
            "class_type": "VAELoader"
        }

    return workflow


def get_workflow_template(config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    获取工作流模板，从配置中读取模型和参数

    Args:
        config: 配置字典，为 None 时自动加载

    Returns:
        工作流模板字典
    """
    if config is None:
        config = load_config()

    comfy_config = config.get("comfyui", {})
    models = comfy_config.get("models", {})
    gen_params = comfy_config.get("generation", {})
    cn_params = comfy_config.get("controlnet_params", {})

    # 使用配置中的值，提供默认值
    checkpoint = models.get("checkpoint", "sd_xl_base_1.0.safetensors")
    controlnet = models.get("controlnet", "control_v11f1p_sd15_depth.pth")
    width = gen_params.get("width", 1024)
    height = gen_params.get("height", 1024)
    steps = gen_params.get("steps", 30)
    cfg = gen_params.get("cfg", 7.5)
    sampler_name = gen_params.get("sampler_name", "dpmpp_2m")
    scheduler = gen_params.get("scheduler", "karras")
    seed = gen_params.get("seed", 42)
    cn_strength = cn_params.get("strength", 1.0)
    cn_start = cn_params.get("start_percent", 0)
    cn_end = cn_params.get("end_percent", 1)

    # ComfyUI requires string references like ["1", 0] not [1, 0]
    # 注意：使用字符串节点 ID 引用（ComfyUI API 要求）
    return {
        "1": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {"text": "", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {"text": "", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {"image": "depth_map.png"},
            "class_type": "LoadImage"
        },
        "6": {
            "inputs": {"control_net_name": controlnet},
            "class_type": "ControlNetLoader"
        },
        "7": {
            "inputs": {
                "strength": cn_strength,
                "conditioning": ["2", 0],
                "control_net": ["6", 0],
                "image": ["5", 0]
            },
            "class_type": "ControlNetApply"
        },
        "8": {
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["7", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "9": {
            "inputs": {
                "samples": ["8", 0],
                "vae": ["1", 2]
            },
            "class_type": "VAEDecode"
        },
        "10": {
            "inputs": {"filename_prefix": "mw_output", "images": ["9", 0]},
            "class_type": "SaveImage"
        }
    }


# 向后兼容：保留 DEFAULT_WORKFLOW 供旧代码使用
DEFAULT_WORKFLOW = get_workflow_template()


class WorkflowLoader:
    """工作流加载器"""

    def __init__(self, workflow_path: Optional[str] = None, config_path: Optional[str] = None):
        self.workflow_path = workflow_path
        self.config_path = config_path or str(CONFIG_PATH)
        self.workflow = None
        self.config = None

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if self.config is not None:
            return self.config

        import yaml
        config_file = Path(self.config_path)
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = {}

        return self.config

    def load(self) -> Dict[str, Any]:
        """加载工作流"""
        if self.workflow is not None:
            return self.workflow

        if self.workflow_path and Path(self.workflow_path).exists():
            with open(self.workflow_path, 'r', encoding='utf-8') as f:
                self.workflow = json.load(f)
        else:
            # 使用配置文件生成模板
            config = self._load_config()
            self.workflow = get_workflow_template(config)

        return self.workflow

    def save_default(self, output_path: str):
        """保存默认工作流到文件"""
        config = self._load_config()
        workflow = get_workflow_template(config)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)

    def update_prompts(self, positive: str, negative: str = "") -> Dict[str, Any]:
        """更新提示词"""
        workflow = self.load().copy()

        # 更新正向提示词（节点 2）
        if "2" in workflow:
            workflow["2"]["inputs"]["text"] = positive

        # 更新负向提示词（节点 3）
        if "3" in workflow:
            workflow["3"]["inputs"]["text"] = negative

        return workflow

    def update_depth_image(self, image_path: str) -> Dict[str, Any]:
        """更新深度图路径"""
        workflow = self.load().copy()

        if "5" in workflow:
            workflow["5"]["inputs"]["image"] = image_path

        return workflow

    def update_seed(self, seed: int) -> Dict[str, Any]:
        """更新随机种子"""
        workflow = self.load().copy()

        if "8" in workflow:
            workflow["8"]["inputs"]["seed"] = seed

        return workflow

    def update_size(self, width: int, height: int) -> Dict[str, Any]:
        """更新输出尺寸"""
        workflow = self.load().copy()

        if "4" in workflow:
            workflow["4"]["inputs"]["width"] = width
            workflow["4"]["inputs"]["height"] = height

        return workflow


def create_workflow(
    positive_prompt: str,
    negative_prompt: str = "",
    depth_image_path: str = "depth_map.png",
    width: Optional[int] = None,
    height: Optional[int] = None,
    seed: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
    validate: bool = True
) -> Dict[str, Any]:
    """
    便捷函数：创建完整的工作流配置

    Args:
        positive_prompt: 正向提示词
        negative_prompt: 负向提示词
        depth_image_path: 深度图路径
        width: 输出宽度（覆盖配置）
        height: 输出高度（覆盖配置）
        seed: 随机种子（覆盖配置，-1 表示随机）
        config: 配置字典（为 None 时自动加载）
        validate: 是否验证工作流

    Returns:
        完整的工作流配置字典
    """
    # 使用配置文件中的模板
    workflow = get_workflow_template(config).copy()

    # 更新提示词
    if "2" in workflow:
        workflow["2"]["inputs"]["text"] = positive_prompt
    if "3" in workflow:
        workflow["3"]["inputs"]["text"] = negative_prompt

    # 更新深度图
    if "5" in workflow:
        workflow["5"]["inputs"]["image"] = depth_image_path

    # 更新尺寸（如果指定）
    if width is not None and "4" in workflow:
        workflow["4"]["inputs"]["width"] = width
    if height is not None and "4" in workflow:
        workflow["4"]["inputs"]["height"] = height

    # 更新种子（如果指定）
    if seed is not None:
        if "8" in workflow:
            workflow["8"]["inputs"]["seed"] = seed if seed >= 0 else 42

    # 验证和修复工作流
    if validate and VALIDATOR_AVAILABLE:
        workflow = validate_and_fix_workflow(workflow)

    return workflow


def create_regional_prompt_workflow(
    global_positive: str,
    global_negative: str,
    region_prompts: Dict[str, str],
    region_masks: Dict[str, str],
    depth_image_path: str = "depth_map.png",
    width: int = 1024,
    height: int = 1024,
    seed: int = 42,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    创建区域提示词工作流（不依赖 IP-Adapter，无需参考图）

    使用 ConditioningSetMask + ConditioningCombine 将每个区域的提示词限制
    在投影 mask 范围内，实现 per-object 的空间约束。

    Args:
        global_positive: 全局/背景正向提示词
        global_negative: 全局/背景负向提示词
        region_prompts: {object_id: positive_prompt} 每个区域的提示词
        region_masks: {object_id: /path/to/mask.png} 每个区域的 mask 文件
        depth_image_path: 深度图路径（可选，空字符串表示不使用 ControlNet）
        width: 图像宽度
        height: 图像高度
        seed: 随机种子
        config: 配置字典

    Returns:
        完整工作流字典
    """
    workflow = get_workflow_template(config).copy()

    # 更新基础参数
    if "2" in workflow:
        workflow["2"]["inputs"]["text"] = global_positive
    if "3" in workflow:
        workflow["3"]["inputs"]["text"] = global_negative
    if depth_image_path and "5" in workflow:
        workflow["5"]["inputs"]["image"] = depth_image_path
    if "4" in workflow:
        workflow["4"]["inputs"]["width"] = width
        workflow["4"]["inputs"]["height"] = height
    if "8" in workflow and seed >= 0:
        workflow["8"]["inputs"]["seed"] = seed

    node_id = 200

    # 全局正向 conditioning（通过 ControlNetApply 或直接 CLIPTextEncode）
    global_cond_ref = ["7", 0] if depth_image_path else ["2", 0]

    # 为每个区域创建 CLIPTextEncode + LoadImage(mask) + ConditioningSetMask
    region_conditionings = []

    for obj_id, prompt_text in region_prompts.items():
        if obj_id not in region_masks:
            continue

        mask_path = region_masks[obj_id]

        # CLIPTextEncode 当前区域提示词
        clip_id = str(node_id)
        workflow[clip_id] = {
            "inputs": {"text": prompt_text, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode",
        }
        node_id += 1

        # LoadImage 加载mask（需要转为MASK类型）
        mask_load_id = str(node_id)
        workflow[mask_load_id] = {
            "inputs": {"image": mask_path},
            "class_type": "LoadImage",
        }
        node_id += 1

        # ConditioningSetMask: 将提示词限制在 mask 区域
        setmask_id = str(node_id)
        workflow[setmask_id] = {
            "inputs": {
                "conditioning": [clip_id, 0],
                "mask": [mask_load_id, 1],
                "strength": 1.0,
                "set_cond_area": "default",
            },
            "class_type": "ConditioningSetMask",
        }
        region_conditionings.append([setmask_id, 0])
        node_id += 1

    # 将全局 conditioning 和所有区域 conditioning 合并
    # ConditioningCombine 一次合并 2 个，需要链式连接
    prev_cond = global_cond_ref

    for region_cond in region_conditionings:
        combine_id = str(node_id)
        workflow[combine_id] = {
            "inputs": {
                "conditioning_1": prev_cond,
                "conditioning_2": region_cond,
            },
            "class_type": "ConditioningCombine",
        }
        prev_cond = [combine_id, 0]
        node_id += 1

    # 最终合并结果 → KSampler
    if "8" in workflow:
        workflow["8"]["inputs"]["positive"] = prev_cond

    return workflow


def create_simple_workflow(
    positive_prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    seed: int = 42,
    checkpoint: str = "sd_xl_base_1.0_0.9vae(1).safetensors"
) -> Dict[str, Any]:
    """
    创建无 ControlNet 的简化工作流（用于测试模型兼容性）

    Args:
        positive_prompt: 正向提示词
        negative_prompt: 负向提示词
        width: 图像宽度
        height: 图像高度
        seed: 随机种子
        checkpoint: checkpoint 模型名称

    Returns:
        简化工作流字典
    """
    return {
        "1": {
            "inputs": {"ckpt_name": checkpoint},
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {"text": positive_prompt, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "3": {
            "inputs": {"text": negative_prompt, "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "4": {
            "inputs": {"width": width, "height": height, "batch_size": 1},
            "class_type": "EmptyLatentImage"
        },
        "5": {
            "inputs": {
                "seed": seed,
                "steps": 30,
                "cfg": 7.5,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0]
            },
            "class_type": "KSampler"
        },
        "6": {
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            "class_type": "VAEDecode"
        },
        "7": {
            "inputs": {"filename_prefix": "mw_output", "images": ["6", 0]},
            "class_type": "SaveImage"
        }
    }
