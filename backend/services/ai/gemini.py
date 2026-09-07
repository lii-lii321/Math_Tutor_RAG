"""Google Gemini 提供商（基于新一代 google-genai SDK）。"""
from __future__ import annotations

from backend.config import Settings
from backend.models.schemas import AIProviderInfo
from backend.services.ai.base import SYSTEM_PROMPT, BaseAIProvider


class GeminiProvider(BaseAIProvider):
    def __init__(self, settings: Settings | None = None):
        super().__init__(settings)
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - 环境缺包时给出清晰指引
            raise ImportError(
                "使用 Gemini 提供商需要安装 google-genai: pip install google-genai"
            ) from exc

        self._genai = genai
        self._client = genai.Client(api_key=self.settings.ai_api_key)
        self.model_name = self.settings.ai_model or "gemini-2.0-flash"

    def _complete(self, image_bytes: bytes, mime_type: str, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=[
                self._genai.types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=self._genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=self.settings.ai_temperature,
                response_mime_type="application/json",
            ),
        )
        if not response.text:
            raise ValueError("模型返回了空响应")
        return response.text

    def chat(self, messages: list[dict]) -> str:
        contents = [
            self._genai.types.Content(
                role="model" if m["role"] == "assistant" else "user",
                parts=[self._genai.types.Part(text=m["content"])],
            )
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=self._genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=self.settings.ai_temperature,
            ),
        )
        if not response.text:
            raise ValueError("模型返回了空响应")
        return response.text

    def provider_info(self) -> AIProviderInfo:
        return AIProviderInfo(
            provider="gemini",
            model=self.model_name,
            configured=bool(self.settings.ai_api_key),
            demo_mode=not bool(self.settings.ai_api_key),
        )
