"""OCR 服务（可选特性）：对错题原图做文字识别。

依赖 rapidocr-onnxruntime（未安装或初始化失败时安全降级为空文本）。
识别文本入库后参与语义/关键词搜索，让原图中的手写题面可被检索。
"""
from __future__ import annotations

from functools import lru_cache

from backend.config import get_settings
from backend.utils.logging import get_logger

logger = get_logger("ocr")


@lru_cache(maxsize=1)
def _get_engine():
    """惰性加载 RapidOCR 引擎（进程级单例）。"""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        logger.info("rapidocr-onnxruntime 未安装，OCR 已禁用")
        return None
    try:
        return RapidOCR()
    except Exception as exc:  # noqa: BLE001 - 模型加载失败不阻断主流程
        logger.warning("OCR 引擎初始化失败: %s", exc)
        return None


def extract_text(image_path: str) -> str:
    """识别图片中的文字；任何失败返回空串（不阻断录题主流程）。"""
    if not get_settings().ocr_enabled:
        return ""
    try:
        engine = _get_engine()
        if engine is None:
            return ""
        result, _ = engine(image_path)
        if not result:
            return ""
        return "\n".join(line[1] for line in result if len(line) >= 2)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR 识别失败: %s", exc)
        return ""
