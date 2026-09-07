"""应用配置中心。

所有配置通过 pydantic-settings 从环境变量 / .env 读取，
类型与取值范围在启动时即完成校验，避免配置错误潜伏到运行期。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = "MathMaster Edu"
    app_version: str = "2.0.0"
    debug: bool = False
    data_dir: Path = PROJECT_ROOT / "data"

    # ---------- 数据库 ----------
    # SQLite 开箱即用；切换 MySQL 示例：
    # DATABASE_URL=mysql+pymysql://user:password@localhost:3306/math_tutor?charset=utf8mb4
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'math_tutor.db').as_posix()}"

    # ---------- 认证 ----------
    bcrypt_rounds: int = Field(default=12, ge=4, le=31)
    seed_admin_username: str = "admin"
    seed_admin_password: str = "admin123"
    seed_demo_username: str = "demo"
    seed_demo_password: str = "demo123"

    # ---------- AI 提供商 ----------
    # openai_compatible: 任何兼容 OpenAI Chat Completions 的服务
    #   (SiliconFlow / Qwen / GLM / DeepSeek / OpenAI / Ollama ...)
    # gemini: Google Gemini（需要 google-genai 包）
    # mock:   无 Key 演示模式，返回固定结构化结果
    ai_provider: Literal["openai_compatible", "gemini", "mock"] = "mock"
    ai_base_url: str = "https://api.siliconflow.cn/v1"
    ai_api_key: str = ""
    ai_model: str = "Qwen/Qwen2.5-VL-32B-Instruct"
    ai_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    ai_max_retries: int = Field(default=3, ge=1, le=10)
    ai_timeout_seconds: float = Field(default=90.0, gt=0)

    # ---------- RAG / 向量库 ----------
    chroma_dir: Path = PROJECT_ROOT / "data" / "chroma"
    rag_enabled: bool = True
    embedding_model: str = "BAAI/bge-m3"
    embedding_base_url: str = ""  # 留空则使用 ChromaDB 内置本地嵌入模型
    embedding_api_key: str = ""
    rag_top_k: int = Field(default=3, ge=1, le=20)

    # ---------- 复习算法 (SM-2) ----------
    review_default_ease: float = Field(default=2.5, ge=1.3)
    review_again_minutes: int = Field(default=10, ge=1)

    @field_validator("data_dir", "chroma_dir", mode="after")
    @classmethod
    def _expand_paths(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.rag_enabled:
            self.chroma_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """进程级单例配置。"""
    return Settings()
