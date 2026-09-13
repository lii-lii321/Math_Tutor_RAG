"""A1 迁移：use_container_width → Streamlit 新 width API（一次性脚本）。

规则（依据 Streamlit 1.63 弃用告警）：
- use_container_width=True  → width="stretch"
- use_container_width=False → width="content"（若同行已有 width= 则直接删除该参数）
"""
import pathlib
import re

changed_files = []
for f in pathlib.Path(".").rglob("*.py"):
    s = str(f)
    if any(part in s for part in (".venv", "data", "__pycache__", "scripts")):
        continue
    src = f.read_text(encoding="utf-8")
    original = src

    # 已有 width= 的行：先删掉 use_container_width 参数
    def drop_redundant(match: re.Match) -> str:
        line = match.group(0)
        if re.search(r"\bwidth=", line):
            line = re.sub(r"\s*,?\s*use_container_width=(True|False)", "", line)
        return line

    src = re.sub(r"^.*use_container_width=(True|False).*$", drop_redundant, src, flags=re.M)
    # 其余：按布尔值替换
    src = src.replace("use_container_width=True", 'width="stretch"')
    src = src.replace("use_container_width=False", 'width="content"')

    if src != original:
        f.write_text(src, encoding="utf-8")
        changed_files.append(str(f))

for path in changed_files:
    print("updated", path)
print(f"total {len(changed_files)} files")
