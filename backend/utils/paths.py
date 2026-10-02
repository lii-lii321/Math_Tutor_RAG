"""图片路径解析：库内存相对路径（相对 data_dir），读取时解析回绝对路径。

历史包袱：v2.10 之前 image_path 存的是机器相关绝对路径，换机即崩；
批 1 止血后新数据一律存 data_dir 相对路径，旧绝对路径在读取端兼容。
"""
from __future__ import annotations

from pathlib import Path

from backend.config import get_settings


def to_stored_path(absolute: Path) -> str:
    """把 data_dir 下的绝对路径转为库存相对路径（posix 风格）。"""
    data_dir = get_settings().data_dir
    try:
        rel = absolute.resolve().relative_to(data_dir)
    except ValueError:
        return str(absolute)  # 不在 data_dir 下（历史数据），原样保存
    return rel.as_posix()


def resolve_image_path(stored: str | None) -> Path | None:
    """库存路径 → 可读取的绝对路径；不存在时仍返回推导路径（调用方自判 exists）。"""
    if not stored:
        return None
    p = Path(stored)
    if p.is_absolute():
        return p
    return get_settings().data_dir / p
