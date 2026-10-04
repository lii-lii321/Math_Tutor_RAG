"""图片路径解析：库内存 key（相对 data_dir 或 S3 桶内对象名），读取经存储后端。

历史包袱：v2.10 之前 image_path 存的是机器相关绝对路径，换机即崩；
批 1 止血后新数据一律存 data_dir 相对路径，旧绝对路径在读取端兼容。
批 12 起读写走 backend.services.storage 抽象：local 后端 key 即相对路径
（零迁移），s3 后端展示走预签名 URL、导出临时落地本地。
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
    """库存路径 → 可读取的绝对路径；不存在时仍返回推导路径（调用方自判 exists）。

    仅适用于 local 后端与本地体检逻辑；展示/导出请用下面的存储感知助手。
    """
    if not stored:
        return None
    p = Path(stored)
    if p.is_absolute():
        return p
    return get_settings().data_dir / p


def display_image_source(stored: str | None) -> str | None:
    """展示用图片来源：本地绝对路径字符串或 S3 预签名 URL；缺失返回 None。

    st.image 同时接受路径与 URL，前端统一走这一个入口。
    """
    if not stored:
        return None
    from backend.services.storage import get_storage

    return get_storage().display_source(stored)


def materialize_image(stored: str | None) -> Path | None:
    """导出 / OCR / 分享卡用：确保图片以本地文件存在（s3 时下载到缓存）。"""
    if not stored:
        return None
    from backend.services.storage import get_storage

    return get_storage().materialize(stored)
