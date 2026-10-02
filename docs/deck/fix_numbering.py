"""One-off: align section kickers with the four divider slides, and fix TOC page hints."""
import pathlib
import re

DECK = pathlib.Path(r"D:\Math_Tutor_RAG\docs\deck\slides")

# Kicker renumbering so content kickers match the 01-04 divider numbering.
KICKERS = {
    "slide-06.js": ("'02  DIAGNOSIS'", "'01  DIAGNOSIS'"),
    "slide-07.js": ("'02  P0-1'", "'01  P0-1'"),
    "slide-08.js": ("'02  P0-2'", "'01  P0-2'"),
    "slide-09.js": ("'02  P1'", "'01  P1'"),
    "slide-10.js": ("'02  P2'", "'01  P2'"),
    "slide-11.js": ("'02  EVIDENCE'", "'01  EVIDENCE'"),
    "slide-13.js": ("'03  PRINCIPLES'", "'02  PRINCIPLES'"),
    "slide-14.js": ("'03  TOKENS'", "'02  TOKENS'"),
    "slide-15.js": ("'03  FOUNDATION'", "'02  FOUNDATION'"),
    "slide-17.js": ("'04  MOCKUP 01'", "'03  MOCKUP 01'"),
    "slide-18.js": ("'04  MOCKUP 02'", "'03  MOCKUP 02'"),
    "slide-19.js": ("'04  MOCKUP 03'", "'03  MOCKUP 03'"),
    "slide-20.js": ("'04  MOCKUP 04'", "'03  MOCKUP 04'"),
    "slide-21.js": ("'04  NAVIGATION'", "'03  NAVIGATION'"),
}

for fname, (old, new) in KICKERS.items():
    p = DECK / fname
    src = p.read_text(encoding="utf-8")
    if old not in src:
        print(f"SKIP (not found): {fname} {old}")
        continue
    p.write_text(src.replace(old, new), encoding="utf-8")
    print(f"OK {fname}: {old} -> {new}")

# TOC: align the four section rows with the divider titles and their slide numbers.
toc = DECK / "slide-02.js"
src = toc.read_text(encoding="utf-8")
NEW_SECTIONS = """const SECTIONS = [
  ['01', '项目与现状', '现状速览 / 能力全景 / 问题诊断 / 现状实拍'],
  ['02', '设计原则与系统', '四条原则 / 色彩 token / 跨页基建'],
  ['03', '成品设计', '四页高保真 / 侧边栏前后对比'],
  ['04', '落地路径与风险', '六批路径 / 风险与边界 / 下一步'],
];"""
src = re.sub(
    r"const SECTIONS = \[.*?\n\];",
    NEW_SECTIONS,
    src,
    count=1,
    flags=re.DOTALL,
)
src = src.replace(
    "slide.addText('P' + (i + 4), {",
    "slide.addText('P' + [3, 12, 16, 22][i], {",
)
toc.write_text(src, encoding="utf-8")
print("OK slide-02.js: TOC sections + page hints")
