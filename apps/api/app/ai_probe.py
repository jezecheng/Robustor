"""AI 配置可用性测试：用一张小尺寸样图走一次真实视觉请求。

只验证「Base URL / Key / 模型」能否通、是否接受图片输入，不写库、不回传 Key。
"""

from __future__ import annotations

import base64
import io
import time

import httpx
from PIL import Image, ImageDraw, ImageFont

TIMEOUT = 25.0
PROMPT = "图中写的是什么数字？只回复数字本身。"


def _sample_image() -> str:
    image = Image.new("RGB", (128, 64), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:  # 老版本 Pillow 没有 size 参数
        font = ImageFont.load_default()
    draw.text((10, 6), "42", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def probe(base_url: str, model: str, api_key: str) -> dict:
    started = time.perf_counter()
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{_sample_image()}"},
                    },
                ],
            }
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        response = httpx.post(base_url, json=payload, headers=headers, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - 网络/超时统一转成可读信息
        return {
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "message": f"连接失败：{type(exc).__name__}: {exc}"[:300],
        }

    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "message": f"HTTP {response.status_code}: {response.text[:200]}",
        }

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "message": "响应不是 OpenAI Chat Completions 格式",
        }

    text = str(content or "").strip()
    if not text:
        return {"ok": False, "latency_ms": latency_ms, "message": "模型返回了空内容"}
    return {"ok": True, "latency_ms": latency_ms, "message": f"模型已响应：{text[:60]}"}
