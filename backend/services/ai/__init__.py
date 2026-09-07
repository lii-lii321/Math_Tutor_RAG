"""AI 服务层：按配置选择提供商，界面层只依赖 BaseAIProvider 接口。

暴露两个稳定入口：
- get_ai_service(): 当前配置的提供商实例
- get_provider_status(): 供设置页展示的运行状态
"""
from __future__ import annotations

from backend.config import Settings, get_settings
from backend.models.schemas import AIProviderInfo
from backend.services.ai.base import BaseAIProvider
from backend.utils.logging import get_logger

logger = get_logger("ai.factory")


def get_ai_service(settings: Settings | None = None) -> BaseAIProvider:
    settings = settings or get_settings()
    provider = settings.ai_provider

    if provider == "openai_compatible" and settings.ai_api_key:
        from backend.services.ai.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(settings)

    if provider == "gemini" and settings.ai_api_key:
        try:
            from backend.services.ai.gemini import GeminiProvider

            return GeminiProvider(settings)
        except ImportError:
            logger.warning("google-genai 未安装，回退到演示模式")

    if provider == "mock":
        from backend.services.ai.mock import MockProvider

        return MockProvider(settings)

    logger.warning("AI 提供商 %s 未配置 API Key，进入演示模式", provider)
    from backend.services.ai.mock import MockProvider

    return MockProvider(settings)


def get_provider_status(settings: Settings | None = None) -> AIProviderInfo:
    settings = settings or get_settings()
    service = get_ai_service(settings)
    return service.provider_info()
