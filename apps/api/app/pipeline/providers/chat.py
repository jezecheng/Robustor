"""打标用的 chat provider（OpenAI 兼容 /chat/completions）。

只有设置页存在「使用中」且能解出 Key 的配置时，`register.get_chat_provider` 才会实例化；
任何网络或解析异常统一抛 RuntimeError，由打标阶段降级回本地词表匹配，保证批量导入
不会因为模型故障中断。
"""

from __future__ import annotations

import json
import re

import httpx

TIMEOUT = 60.0


def chat_endpoint(base_url: str) -> str:
    """兼容两种配置写法：完整端点，或只写到 /v1 的 Base URL。"""
    url = (base_url or "").strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


def parse_json_object(content: str) -> dict:
    """从模型输出里抠出第一个 JSON 对象（允许 markdown 代码围栏）。"""
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in chat response")
    return json.loads(text[start : end + 1])


class ChatProvider:
    name = "chat"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = TIMEOUT,
    ) -> None:
        if not api_key:
            raise RuntimeError("chat provider requires api key")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

    def complete_json(self, system: str, user: str) -> dict:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = httpx.post(
                chat_endpoint(self.base_url), json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"chat completion failed: {type(exc).__name__}: {exc}") from exc
        return parse_json_object(content)
