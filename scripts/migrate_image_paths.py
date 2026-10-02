"""一次性迁移：questions.image_path 绝对路径 → data_dir 相对路径（批 1 止血）。"""

import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.config import get_settings
from backend.database import SessionLocal
from backend.models.orm import Question

settings = get_settings()
data_dir = settings.data_dir
fixed = 0
checked = 0

with SessionLocal() as session:
    for q in session.query(Question).all():
        if not q.image_path:
            continue
        checked += 1
        p = Path(q.image_path)
        if p.is_absolute():
            try:
                rel = p.resolve().relative_to(data_dir)
            except ValueError:
                print("跳过（不在 data_dir 下且文件状态未知）:", q.id, q.image_path)
                continue
            q.image_path = rel.as_posix()
            fixed += 1
    session.commit()

print(f"checked={checked} fixed={fixed}")
