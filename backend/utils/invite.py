"""教师邀请码校验（纯函数，fail-closed，供认证服务与单测共用）。

双语义存储（由配置值形态自动判定）：
- 配置为 64 位 hex → 视为 sha256 摘要，与候选码的 sha256 hexdigest 比对；
- 其他非空值 → 明文比对。

安全约定：
- 比较使用 secrets.compare_digest（常量时间，抑制时序侧信道）；
- 比较前两侧统一 encode("utf-8")——compare_digest 的 str 形态对非 ASCII
  字符抛 TypeError，bytes 化后中文邀请码（如「教研组2024」）可安全校验；
- 配置为空一律 False（fail-closed：教师注册关闭）。

明文模式请避免 64 位 hex 字符串：会被按摘要语义比对（歧义记档于
docs/DEPLOYMENT.md 与 backend/config.py 注释）。
"""
from __future__ import annotations

import hashlib
import secrets

_HEX_DIGEST_LENGTH = 64


def _is_sha256_hex(value: str) -> bool:
    """判定配置值是否为 64 位 hex（sha256 摘要形态）。"""
    if len(value) != _HEX_DIGEST_LENGTH:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def verify_invite_code(candidate: str, configured: str) -> bool:
    """校验候选邀请码与配置值是否匹配；配置为空一律 False（fail-closed）。"""
    if not configured:
        return False
    candidate_bytes = candidate.encode("utf-8")
    if _is_sha256_hex(configured):
        digest = hashlib.sha256(candidate_bytes).hexdigest()
        return secrets.compare_digest(digest.encode("utf-8"), configured.encode("utf-8"))
    return secrets.compare_digest(candidate_bytes, configured.encode("utf-8"))
