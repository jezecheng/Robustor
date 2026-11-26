"""AI 配置可用性测试：用一张小尺寸样图走一次真实视觉请求。

只验证「Base URL / Key / 模型」能否通、是否接受图片输入，不写库、不回传 Key。
每次测试也会记入 AI 用量日志（业务场景=连接测试），方便在「AI 用量」页核对
配置是否工作、一次测试消耗多少 token。
"""

from __future__ import annotations

import base64
import io
import time

import httpx
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from .usage import record_ai_usage

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


def probe(
    base_url: str,
    model: str,
    api_key: str,
    *,
    session: Session | None = None,
    provider_name: str = "",
    provider_id: str | None = None,
) -> dict:
    started = time.perf_counter()

    def finish(
        result: dict, *, success: bool, usage: dict | None = None, error: str | None = None
    ) -> dict:
        record_ai_usage(
            session,
            scene="连接测试",
            provider_name=provider_name or "连接测试",
            provider_id=provider_id,
            model=model,
            success=success,
            error=error,
            latency_ms=int(result.get("latency_ms") or 0),
            usage=usage,
        )
        return result

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
        message = f"连接失败：{type(exc).__name__}: {exc}"[:300]
        return finish(
            {"ok": False, "latency_ms": int((time.perf_counter() - started) * 1000), "message": message},
            success=False,
            error=message,
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        message = f"HTTP {response.status_code}: {response.text[:200]}"
        return finish(
            {"ok": False, "latency_ms": latency_ms, "message": message},
            success=False,
            error=message,
        )

    try:
        body = response.json()
        usage = body.get("usage")
        content = body["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        message = "响应不是 OpenAI Chat Completions 格式"
        return finish(
            {"ok": False, "latency_ms": latency_ms, "message": message},
            success=False,
            error=message,
        )

    text = str(content or "").strip()
    if not text:
        message = "模型返回了空内容"
        return finish(
            {"ok": False, "latency_ms": latency_ms, "message": message},
            success=False,
            usage=usage,
            error=message,
        )
    return finish(
        {"ok": True, "latency_ms": latency_ms, "message": f"模型已响应：{text[:60]}"},
        success=True,
        usage=usage,
    )
