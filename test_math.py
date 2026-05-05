import sys

sys.path.insert(0, r"E:\ClaudeTest\Mindawaker")
import asyncio


async def test():
    from app.service.math_pipeline import run_math_pipeline

    article = "1+1=2"
    try:
        result = await asyncio.to_thread(
            run_math_pipeline, article, "deepseek-chat", "sk-17c70c58e2344275b30466b9173a66ac"
        )
        print("Result:", result)
    except Exception as e:
        print("Error:", e)
        import traceback

        traceback.print_exc()


asyncio.run(test())
