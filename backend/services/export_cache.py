"""导出产物进程级缓存：错题本每次 rerun 都要为 st.download_button 备好
4~6 份整册 Word/PDF/Anki 字节流，翻页/排序/任意控件交互都会触发全量重生成
（demo 18 题实测 ~254ms/次，63 题达 ~397ms/次，随下载按钮一直挂在热路径上）。

缓存键 = 导出参数 + 当日日期 + 全量题面内容指纹（QuestionOut 全字段 JSON
序列化，含 image_hash）——内容未变的 rerun 零生成成本；生成器本身确定性、
仅日期戳随日变化，故把当日日期并入键，跨日自动失效，输出与实时生成一致。
生成逻辑零改动：命中复用字节、未命中走原实现、生成抛错不缓存（与直调一致）。
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from collections import OrderedDict
from typing import Callable

from backend.utils.logging import get_logger

logger = get_logger("export_cache")

# 单份整册导出（含原图）可达数 MB：限条目数控制内存上界（典型单页 4~6 份）
_MAX_ENTRIES = 8

_lock = threading.Lock()
_cache: "OrderedDict[str, bytes]" = OrderedDict()


def content_key(kind: str, questions, **options) -> str:
    """导出产物指纹：kind/选项/当日日期 + 每道题的全字段序列化。"""
    payload = {
        "v": 1,
        "kind": kind,
        "today": dt.date.today().isoformat(),
        "options": options,
        "questions": [q.model_dump(mode="json") for q in questions],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def cached_bytes(key: str, producer: Callable[[], bytes]) -> bytes:
    """键命中返回缓存字节；未命中执行 producer 并入缓存（异常不缓存）。"""
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    data = producer()
    with _lock:
        _cache[key] = data
        _cache.move_to_end(key)
        while len(_cache) > _MAX_ENTRIES:
            _cache.popitem(last=False)
    return data
