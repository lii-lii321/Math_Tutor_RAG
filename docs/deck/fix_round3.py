"""QA fix round 3.

Blocking: _mock.js put the image frame on top of the subtitle band and gave the
"before" line a box too short for a 2-line wrap, so the bold "after" line printed
through it. Both live in the shared template, so one fix repairs slides 17-20.
"""
import pathlib

DECK = pathlib.Path(__file__).resolve().parent / "slides"


def patch(name, pairs):
    p = DECK / name
    src = p.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in src:
            print(f"  MISS {name}: {old[:70]!r}")
            continue
        src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8")
    print(f"  patched {name}")


# --- shared mockup template: clear the subtitle, give "before" room to wrap ---
patch("_mock.js", [
    ("const IMG_Y = 1.12;\nconst IMG_MAX_H = 4.1;", "const IMG_Y = 1.4;\nconst IMG_MAX_H = 3.92;"),
    ("  const rowH = 0.62;", "  const rowH = 0.68;"),
    ("    const y = 1.44 + i * rowH;", "    const y = 1.4 + i * rowH;"),
    ("    slide.addText(c[0], {\n      x: COL_X + 0.14, y: y - 0.02, w: COL_W - 0.14, h: 0.24, margin: 0,\n      fontSize: 8, color: L.MUTED, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.1,\n    });",
     "    slide.addText(c[0], {\n      x: COL_X + 0.14, y: y - 0.02, w: COL_W - 0.14, h: 0.3, margin: 0,\n      fontSize: 7.5, color: L.MUTED, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.1,\n    });"),
    ("    slide.addText(c[1], {\n      x: COL_X + 0.14, y: y + 0.2, w: COL_W - 0.14, h: 0.34, margin: 0,\n      fontSize: 9.2, bold: true, color: theme.primary, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.18,\n    });",
     "    slide.addText(c[1], {\n      x: COL_X + 0.14, y: y + 0.29, w: COL_W - 0.14, h: 0.36, margin: 0,\n      fontSize: 9, bold: true, color: theme.primary, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.16,\n    });"),
    ("    const fy = 1.44 + cfg.changes.length * rowH + 0.06;", "    const fy = 1.4 + cfg.changes.length * rowH + 0.04;"),
    ("      x: COL_X, y: fy, w: COL_W, h: 0.62, rectRadius: 0.05,", "      x: COL_X, y: fy, w: COL_W, h: 0.5, rectRadius: 0.05,"),
    ("    slide.addText(cfg.foot, {\n      x: COL_X + 0.14, y: fy + 0.06, w: COL_W - 0.28, h: 0.5, margin: 0,\n      fontSize: 8.2, color: '047857', fontFace: L.CN, lineSpacingMultiple: 1.25,\n    });",
     "    slide.addText(cfg.foot, {\n      x: COL_X + 0.14, y: fy + 0.05, w: COL_W - 0.28, h: 0.42, margin: 0,\n      fontSize: 7.8, color: '047857', fontFace: L.CN, lineSpacingMultiple: 1.2,\n    });"),
    ("  slide.addText('关键改动', {\n    x: COL_X, y: 1.12, w: COL_W, h: 0.24, margin: 0,",
     "  slide.addText('关键改动', {\n    x: COL_X, y: 1.4, w: COL_W, h: 0.22, margin: 0,"),
])

# --- P15: 7 spots live in 6 files, not 7 pages ---
patch("slide-15.js", [
    ("'7 个页面各拼各的 f-string, 收敛成一个带 tone 参数的组件'",
     "'6 个文件共 7 处各拼 f-string, 收敛成带 tone 的组件'"),
])

# --- P6: disambiguate the two page counts that sit on the same slide ---
patch("slide-06.js", [
    ("'i18n 框架存在但 8 个页面 0 处使用'", "'i18n 框架存在, 全部 8 个页面 0 处使用'"),
    ("['7', '个页面存在裸 service 调用', 'graph / mastery / assistant / auth / review 等'],",
     "['7', '个页面有裸 service 调用', 'graph / mastery / assistant / auth / review 等'],"),
])

# --- P21: 3px of slack above the card edge was too thin ---
patch("slide-21.js", [
    ("    x: 0.7, y: 4.74, w: 3.75, h: 0.28, margin: 0,", "    x: 0.7, y: 4.7, w: 3.75, h: 0.26, margin: 0,"),
])

# --- P9: wireframe still 1.5in wide, so it clipped the card edge ---
patch("slide-09.js", [
    ("  const wf = { x: 3.18, y: 1.62, w: 1.4, h: 1.5, fill: 'F8FAFC', ln: L.LINE };",
     "  const wf = { x: 3.12, y: 1.62, w: 1.35, h: 1.5, fill: 'F8FAFC', ln: L.LINE };"),
    ("      x: x, y: y + i * 0.155, w: 1.5, h: 0.13,", "      x: x, y: y + i * 0.155, w: 1.35, h: 0.13,"),
    ("    slide.addText('0 个分组', {\n    x: x, y: y + 1.42, w: 1.5, h: 0.16, margin: 0,",
     "    slide.addText('0 个分组', {\n    x: x, y: y + 1.42, w: 1.35, h: 0.16, margin: 0,"),
    ("  x = wf.x + 4.6; y = wf.y;\n  slide.addShape('rect', {\n    x: x, y: y, w: 1.5, h: 0.92,",
     "  x = wf.x + 4.5; y = wf.y;\n  slide.addShape('rect', {\n    x: x, y: y, w: 1.35, h: 0.92,"),
    ("  slide.addShape('rect', {\n    x: x, y: y + 1.0, w: 1.5, h: 0.36,", "  slide.addShape('rect', {\n    x: x, y: y + 1.0, w: 1.35, h: 0.36,"),
    ("  slide.addText('列表在这', {\n    x: x, y: 1.0 + y, w: 1.5, h: 0.36, margin: 0,",
     "  slide.addText('列表在这', {\n    x: x, y: 1.0 + y, w: 1.35, h: 0.36, margin: 0,"),
    ("  slide.addText('60% 屏幕', {\n    x: x, y: y + 1.42, w: 1.5, h: 0.16, margin: 0,",
     "  slide.addText('60% 屏幕', {\n    x: x, y: y + 1.42, w: 1.35, h: 0.16, margin: 0,"),
    ("  x = wf.x + 4.6; y = wf.y + 1.97;", "  x = wf.x + 4.5; y = wf.y + 1.97;"),
    ("    slide.addShape('rect', {\n      x: x, y: y + i * 0.3, w: 1.5, h: 0.24,", "    slide.addShape('rect', {\n      x: x, y: y + i * 0.3, w: 1.35, h: 0.24,"),
    ("  slide.addText('7 类 / 1 行', {\n    x: x, y: y + 1.3, w: 1.5, h: 0.16, margin: 0,",
     "  slide.addText('7 类 / 1 行', {\n    x: x, y: y + 1.3, w: 1.35, h: 0.16, margin: 0,"),
    ("  slide.addText('无主次', {\n    x: x, y: y + 1.3, w: 1.5, h: 0.16, margin: 0,",
     "  slide.addText('无主次', {\n    x: x, y: y + 1.3, w: 1.35, h: 0.16, margin: 0,"),
])
