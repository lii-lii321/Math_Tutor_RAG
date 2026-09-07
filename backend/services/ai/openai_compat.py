"""OpenAI 兼容提供商。

同一套实现即可对接 SiliconFlow / 通义千问 / 智谱 GLM / DeepSeek / OpenAI / Ollama，
只需更换 AI_BASE_URL 与 AI_MODEL，这是当前国内可自托管生态的主流接入方式。
"""
from __future__ import annotations

import base64

from openai import OpenAI

from backend.config import Settings
from backend.models.schemas import AIProviderInfo
from backend.services.ai.base import SYSTEM_PROMPT, BaseAIProvider


class OpenAICompatProvider(BaseAIProvider):
    def __init__(self, settings: Settings | None = None):
        super().__init__(settings)
        self._client = OpenAI(
            api_key=self.settings.ai_api_key or "not-configured",
            base_url=self.settings.ai_base_url,
            timeout=self.settings.ai_timeout_seconds,
            max_retries=0,  # 重试策略在 BaseAIProvider 内统一控制
        )

    def _complete(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        response = self._client.chat.completions.create(
            model=self.settings.ai_model,
            temperature=self.settings.ai_temperature,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("模型返回了空响应")
        return content

    def provider_info(self) -> AIProviderInfo:
        return AIProviderInfo(
            provider="openai_compatible",
            model=self.settings.ai_model,
            configured=bool(self.settings.ai_api_key),
            demo_mode=not bool(self.settings.ai_api_key),
        )
