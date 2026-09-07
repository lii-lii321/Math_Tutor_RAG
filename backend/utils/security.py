"""密码哈希与校验（bcrypt）。

不再存储明文密码：注册与种子用户一律写入 bcrypt 哈希。
"""
from __future__ import annotations

import bcrypt


def hash_password(plain: str, rounds: int = 12) -> str:
    if not plain:
        raise ValueError("password must not be empty")
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False
