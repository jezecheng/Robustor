"""VLM OCR provider（默认不启用）：只有 OCR_PROVIDER=vlm 且 VLM_API_KEY 存在时由 register 实例化。

全部配置只读环境变量，绝不把 key 写进代码：
- VLM_BASE_URL：完整 chat/completions 端点，缺省 https://api.openai.com/v1/chat/completions
- VLM_API_KEY：Bearer token
- VLM_MODEL：默认 gpt-4o-mini
任何网络/解析异常统一抛 RuntimeError，交由上层兜底。
"""

from __future__ import annotations

import base64
import json
import os
import re

import httpx

DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"
TIMEOUT = 20.0

SYSTEM_PROMPT = (
    "You are an OCR engine for math homework photos. Read the cropped region and "
    "return strict JSON only, no markdown fences."
)

HINT_TEXT = {
    "stem": "printed problem statement",
    "answer": "student's handwritten solution",
    "correction": "teacher or student correction written in blue ink",
    "mark": "teacher's grading symbol (tick, cross, score or plus/minus)",
}


def _user_prompt(hint: str) -> str:
    kind = HINT_TEXT.get(hint, hint)
    return (
        f"Region type: {kind}.\n"
        "Transcribe its content into LaTeX (plain text is fine when it is not math).\n"
        'Respond with JSON: {"latex": "...", "confidence": 0.0} '
        "where confidence is your certainty between 0 and 1."
    )


def _parse_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in VLM response")
    return json.loads(text[start : end + 1])


class VlmOcrProvider:
    name = "vlm"

    def __init__(self) -> None:
        self.api_key = os.environ.get("VLM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("VLM_API_KEY is not set")
        self.base_url = os.environ.get("VLM_BASE_URL") or DEFAULT_BASE_URL
        self.model = os.environ.get("VLM_MODEL", "gpt-4o-mini")

    def recognize(self, image_bytes: bytes, hint: str) -> tuple[str, float]:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _user_prompt(hint)},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = httpx.post(
                self.base_url, json=payload, headers=headers, timeout=TIMEOUT
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = _parse_json(content)
            latex = str(data.get("latex", ""))
            confidence = float(data.get("confidence", 0.0))
        except Exception as exc:  # noqa: BLE001 - 统一转 RuntimeError 由上层兜底
            raise RuntimeError(f"vlm ocr failed: {type(exc).__name__}: {exc}") from exc
        return latex, round(min(1.0, max(0.0, confidence)), 3)
