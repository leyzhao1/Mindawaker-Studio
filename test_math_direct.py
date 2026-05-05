import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"E:\ClaudeTest\Mindawaker")

import json
from app.configs.constants import SCENE_SHOT_IN_MATH_TEMPLATE
from app.text_engine.deepseek_model import DeepseekModel

# 模拟 math_pipeline 的逻辑
article = "1+1=2"


# 渲染模板
def render_template(template, **kwargs):
    text = template
    for key, value in kwargs.items():
        placeholder = "{{" + key + "}}"
        if isinstance(value, str):
            text = text.replace(placeholder, value)
        else:
            text = text.replace(placeholder, json.dumps(value, ensure_ascii=False))
    return text


prompt = render_template(SCENE_SHOT_IN_MATH_TEMPLATE, math_article=article)
print("=== PROMPT ===")
print(prompt)
print("=== END ===\n")

# 调用 Deepseek
print("Calling Deepseek...")
model = DeepseekModel()
try:
    result = model.invoke(prompt)
    print("Result:", result)
except Exception as e:
    print("Error:", e)
    import traceback

    traceback.print_exc()
