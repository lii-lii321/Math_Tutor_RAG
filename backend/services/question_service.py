"""错题应用服务：编排 AI 解析、存储、向量索引、检索与复习的完整链路。

界面层只与本模块交互，不直接触碰仓储 / AI / 向量库实现。
实现按领域拆分在 question_mixins.py（录入 / 查询 / 编辑标签 / 复习 / 备份 / 统计），
本文件仅做组合与对外导出，保持拆分前完全一致的公共 API。
Session 策略：每次公开操作独立开短事务（session-per-operation），
与 Streamlit「脚本反复重跑 + 多线程渲染」的执行模型兼容。
"""
from __future__ import annotations

from backend.services.question_mixins import (
    BackupMixin,
    CoreMixin,
    EditTagMixin,
    EntryMixin,
    QueryMixin,
    ReviewMixin,
    StatsMixin,
    sanitize_tags,
)

__all__ = ["QuestionService", "sanitize_tags"]


class QuestionService(
    EntryMixin,
    QueryMixin,
    EditTagMixin,
    ReviewMixin,
    BackupMixin,
    StatsMixin,
    CoreMixin,
):
    """错题领域门面：组合各领域 Mixin，保持既有调用方零改动。"""
