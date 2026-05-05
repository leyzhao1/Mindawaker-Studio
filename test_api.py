import requests
import json

resp = requests.post(
    "https://api.deepseek.com/v1/chat/completions",
    json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": "say hello"}],
        "temperature": 0.3,
        "request_timeout": 30,
    },
    headers={
        "Authorization": "Bearer sk-17c70c58e2344275b30466b9173a66ac",
        "Content-Type": "application/json",
    },
)
import sys

sys.stdout.reconfigure(encoding="utf-8")
print(resp.status_code)
print(resp.text.encode("utf-8").decode("utf-8"))
