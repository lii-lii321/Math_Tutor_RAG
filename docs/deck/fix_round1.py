"""
One-off QA fix pass (round 1).

Blocking issues from the independent QA report:
  P6  P1/P2 last bullet clipped by card edge, badge count mismatch
  P9  body text overlapped and bisected by the wireframes
  P11 four screenshot captions invisible (2 covered, 2 pushed past page bottom)
  P21 green footnote printed on top of a nav item, left card text overflow

Should-fix items: muted contrast, badge overlaps, P14 threshold contradiction,
"8 pages" vs 7 rows, P23 chip colour scale, P1 cover wrap, P8/P15 dead space.
"""
import pathlib

DECK = pathlib.Path(r"D:\Math_Tutor_RAG\docs\deck\slides")


def patch(name, pairs, required=True):
    p = DECK / name
    src = p.read_text(encoding="utf-8")
    for old, new in pairs:
        if old not in src:
            if required:
                print(f"  MISS {name}: {old[:60]!r}")
            continue
        src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8")
    print(f"  patched {name}")


print("lib / shared")

# MUTED fails WCAG AA on white (2.56:1). Use the secondary slate instead.
patch("_lib.js", [("const MUTED = '94A3B8';", "const MUTED = '64748B';")])

# Centre mockup images: review.png is 1:1, the others are ~1.3:1, so widths differ.
patch("_mock.js", [
    ("  const ix = IMG_X;\n  const iy = IMG_Y + (IMG_MAX_H - h) / 2;",
     "  const ix = IMG_X + (IMG_MAX_W - w) / 2;\n  const iy = IMG_Y + (IMG_MAX_H - h) / 2;"),
    ("const COL_X = 6.42;\nconst COL_W = 3.08;",
     "const COL_X = 6.35;\nconst COL_W = 2.85;"),
    ("const IMG_MAX_W = 5.72;", "const IMG_MAX_W = 5.55;"),
])

print("individual slides")

# --- P6: taller buckets, tighter bullets so the 4th item fits; P2 count 6 -> 4 ---
patch("slide-06.js", [
    ("    tone: 'brand', code: 'P2', count: '6', label: '一致性债',",
     "    tone: 'brand', code: 'P2', count: '4', label: '一致性债',"),
    ("      x: x, y: y, w: 2.85, h: 2.0, rectRadius: 0.06,",
     "      x: x, y: y, w: 2.75, h: 2.34, rectRadius: 0.06,"),
    ("    slide.addShape('rect', { x: x, y: y, w: 2.85, h: 0.05, fill: { color: t.fg }, line: { width: 0 } });",
     "    slide.addShape('rect', { x: x, y: y, w: 2.75, h: 0.05, fill: { color: t.fg }, line: { width: 0 } });"),
    ("      x: x + 2.0, y: y + 0.1, w: 0.7, h: 0.42, margin: 0,",
     "      x: x + 1.9, y: y + 0.1, w: 0.7, h: 0.42, margin: 0,"),
    ("      const yy = y + 0.62 + j * 0.42;",
     "      const yy = y + 0.66 + j * 0.42;"),
    ("        x: x + 0.33, y: yy - 0.03, w: 2.35, h: 0.42, margin: 0,",
     "        x: x + 0.33, y: yy - 0.03, w: 2.28, h: 0.42, margin: 0,"),
    ("    const x = 0.5 + i * 3.05;\n    const y = 1.48;\n    const toneMap",
     "    const x = 0.5 + i * 2.95;\n    const y = 1.48;\n    const toneMap"),
    ("    const x = 0.5 + i * 2.3;\n    const y = 4.0;",
     "    const x = 0.5 + i * 2.22;\n    const y = 4.02;"),
    ("      x: x, y: y, w: 2.1, h: 1.28,", "      x: x, y: y, w: 2.05, h: 1.24,"),
    ("  slide.addText('量化后的技术债', {\n    x: 0.5, y: 3.68, w: 3, h: 0.28, margin: 0,",
     "  slide.addText('量化后的技术债', {\n    x: 0.5, y: 3.72, w: 3, h: 0.26, margin: 0,"),
])

# --- P9: body text must not run under the wireframes; pull right column in ---
patch("slide-09.js", [
    ("    L.card(slide, theme, c.x, c.y, 4.4, 1.85);", "    L.card(slide, theme, c.x, c.y, 4.15, 1.85);"),
    ("    slide.addShape('rect', { x: c.x, y: c.y, w: 0.05, h: 1.85,",
     "    slide.addShape('rect', { x: c.x, y: c.y, w: 0.05, h: 1.85,"),
    ("      x: c.x + 0.22, y: c.y + 0.72, w: 4.0, h: 0.95, margin: 0,",
     "      x: c.x + 0.22, y: c.y + 0.72, w: 2.28, h: 0.98, margin: 0,"),
    ("  const wf = { x: 3.2, y: 1.62, w: 1.5, h: 1.5, fill: 'F8FAFC', ln: L.LINE };",
     "  const wf = { x: 3.18, y: 1.62, w: 1.4, h: 1.5, fill: 'F8FAFC', ln: L.LINE };"),
])

# --- P7: page count must match the 7 rows actually listed ---
patch("slide-07.js", [
    ("同一种模式遍布 8 个页面 -- service 调用没有安全包装",
     "同一种模式遍布 7 个页面 -- service 调用没有安全包装"),
    ("    x: 5.35, y: 4.62, w: 4.15, h: 0.72, rectRadius: 0.05,",
     "    x: 5.25, y: 4.62, w: 3.95, h: 0.72, rectRadius: 0.05,"),
    ("    x: 5.35, y: 1.42, w: 4.15, h: 2.83,", "    x: 5.25, y: 1.42, w: 3.95, h: 2.83,"),
    ("slide.addImage({ path: '../screenshots/review.png', x: 5.44, y: 1.51, w: 3.97, h: 2.65 });",
     "slide.addImage({ path: '../screenshots/review.png', x: 5.34, y: 1.51, w: 3.77, h: 2.65 });"),
    ("    x: 5.35, y: 4.3, w: 4.15, h: 0.22, margin: 0,",
     "    x: 5.25, y: 4.3, w: 3.95, h: 0.22, margin: 0,"),
    ("    x: 5.5, y: 4.72, w: 0.5, h: 0.2, margin: 0,", "    x: 5.4, y: 4.72, w: 0.5, h: 0.2, margin: 0,"),
    ("    x: 5.5, y: 4.92, w: 3.9, h: 0.36, margin: 0,", "    x: 5.4, y: 4.92, w: 3.7, h: 0.36, margin: 0,"),
])

# --- P8: cards were only ~55% filled ---
patch("slide-08.js", [
    ("  L.card(slide, theme, 0.5, 1.45, 4.4, 3.75);", "  L.card(slide, theme, 0.5, 1.45, 4.15, 3.4);"),
    ("  L.card(slide, theme, 5.1, 1.45, 4.4, 3.75);", "  L.card(slide, theme, 5.1, 1.45, 4.15, 3.4);"),
    ("slide.addShape('rect', { x: 0.5, y: 1.45, w: 4.4, h: 0.05,", "slide.addShape('rect', { x: 0.5, y: 1.45, w: 4.15, h: 0.05,"),
    ("slide.addShape('rect', { x: 5.1, y: 1.45, w: 4.4, h: 0.05,", "slide.addShape('rect', { x: 5.1, y: 1.45, w: 4.15, h: 0.05,"),
])

# --- P14: thresholds contradicted themselves in three places ---
patch("slide-14.js", [
    ("'掌握度 < 50%, 与后端 WEAK_THRESHOLD 同源'", "'掌握度 < 40%, 与后端 WEAK_THRESHOLD 同源'"),
    ("'掌握度 50%-75% 或待复习, 与 SHAKY_THRESHOLD 同源'", "'掌握度 40%-70% 或待复习, 与 SHAKY_THRESHOLD 同源'"),
    ("'掌握度 > 75% 或数学验证通过'", "'掌握度 > 70% 或数学验证通过'"),
    ("  L.card(slide, theme, 6.8, 1.42, 2.7, 1.95);", "  L.card(slide, theme, 6.75, 1.42, 2.5, 1.95);"),
    ("slide.addShape('rect', { x: 6.8, y: 1.42, w: 2.7, h: 0.05,", "slide.addShape('rect', { x: 6.75, y: 1.42, w: 2.5, h: 0.05,"),
    ("    x: 7.0, y: 1.58, w: 2.3, h: 0.26, margin: 0,", "    x: 6.95, y: 1.58, w: 2.1, h: 0.26, margin: 0,"),
    ("      x: 7.0, y: y, w: 0.6, h: 0.2, margin: 0,", "      x: 6.95, y: y, w: 0.6, h: 0.2, margin: 0,"),
    ("      x: 7.62, y: y, w: 0.75, h: 0.2, margin: 0,", "      x: 7.5, y: y, w: 0.75, h: 0.2, margin: 0,"),
    ("    L.bar(slide, 7.0, y + 0.22, 2.3, 0.1, t[3], t[0]);", "    L.bar(slide, 6.95, y + 0.22, 2.1, 0.1, t[3], t[0]);"),
    ("    x: 6.8, y: 3.5, w: 2.7, h: 1.78, rectRadius: 0.06,", "    x: 6.75, y: 3.5, w: 2.5, h: 1.78, rectRadius: 0.06,"),
    ("    x: 7.0, y: 3.66, w: 2.3, h: 0.24, margin: 0,", "    x: 6.95, y: 3.66, w: 2.1, h: 0.24, margin: 0,"),
    ("    x: 7.0, y: 3.96, w: 2.32, h: 1.2, margin: 0,", "    x: 6.95, y: 3.96, w: 2.12, h: 1.2, margin: 0,"),
])

# --- P15: left column had ~1in of dead space; right rows ran under the badge ---
patch("slide-15.js", [
    ("  L.card(slide, theme, 0.5, 1.45, 4.35, 1.72);", "  L.card(slide, theme, 0.5, 1.45, 4.35, 2.12);"),
    ("    x: 0.5, y: 3.32, w: 4.35, h: 0.86, rectRadius: 0.06,", "    x: 0.5, y: 3.72, w: 4.35, h: 1.6, rectRadius: 0.06,"),
    ("    x: 0.7, y: 3.42, w: 3.9, h: 0.22, margin: 0,", "    x: 0.7, y: 3.86, w: 3.9, h: 0.24, margin: 0,"),
    ("    x: 0.7, y: 3.64, w: 3.95, h: 0.48, margin: 0,",
     "    x: 0.7, y: 4.14, w: 3.95, h: 1.06, margin: 0,"),
    ("      x: 5.1, y: y, w: 4.4, h: 0.6,", "      x: 5.1, y: y, w: 4.1, h: 0.6,"),
    ("      x: 8.72, y: y + 0.14, w: 0.66, h: 0.32, rectRadius: 0.04,",
     "      x: 8.42, y: y + 0.14, w: 0.66, h: 0.32, rectRadius: 0.04,"),
    ("      x: 8.72, y: y + 0.14, w: 0.66, h: 0.32, margin: 0,",
     "      x: 8.42, y: y + 0.14, w: 0.66, h: 0.32, margin: 0,"),
    ("'收 8 页'", "'收 7 页'"),
])

# --- P4: note card ran under the badge ---
patch("slide-04.js", [
    ("  L.card(slide, theme, 6.15, 4.12, 3.35, 1.26, 'FFFFFF');",
     "  L.card(slide, theme, 6.05, 4.12, 3.15, 1.24, 'FFFFFF');"),
    ("slide.addShape('rect', { x: 6.15, y: 4.12, w: 3.35, h: 0.06,", "slide.addShape('rect', { x: 6.05, y: 4.12, w: 3.15, h: 0.06,"),
    ("    x: 6.35, y: 4.28, w: 3.0, h: 0.24, margin: 0,", "    x: 6.25, y: 4.28, w: 2.8, h: 0.24, margin: 0,"),
    ("    x: 6.35, y: 4.54, w: 3.0, h: 0.74, margin: 0,", "    x: 6.25, y: 4.54, w: 2.8, h: 0.74, margin: 0,"),
])

# --- P5: orphan characters from wrapping ---
patch("slide-05.js", [
    ("'SHA-256 图片去重, 命中则跳过 AI'", "'SHA-256 图片去重, 命中跳过 AI'"),
    ("'今日计划 = SM-2 到期优先 + 薄弱知识点补位'", "'今日计划 = SM-2 到期 + 薄弱补位'"),
    ("'班级多租户: 教师建班后检索与总览收紧为本班'", "'班级多租户: 建班后检索收紧为本班'"),
    ("'services -> repositories -> models 三层分层'", "'services / repositories / models 分层'"),
    ("'4 job CI: lint / 三版本矩阵 / 启动冒烟 / Docker'", "'4 job CI: lint / 版本矩阵 / 冒烟 / Docker'"),
    ("    const x = 0.5 + col * 3.05;\n    const y = 1.48 + row * 1.92;",
     "    const x = 0.5 + col * 2.95;\n    const y = 1.48 + row * 1.92;"),
    ("    L.card(slide, theme, x, y, 2.85, 1.76);", "    L.card(slide, theme, x, y, 2.75, 1.76);"),
    ("slide.addShape('rect', { x: x, y: y, w: 2.85, h: 0.05,", "slide.addShape('rect', { x: x, y: y, w: 2.75, h: 0.05,"),
    ("    slide.addText(t, {\n        x: x + 0.33, y: yy - 0.02, w: 2.36, h: 0.3, margin: 0,",
     "    slide.addText(t, {\n        x: x + 0.33, y: yy - 0.02, w: 2.26, h: 0.3, margin: 0,"),
])

# --- P10: full-width rows ran under the badge ---
patch("slide-10.js", [
    ("    x: 0.5, y: 1.42, w: 9.0, h: 0.32,", "    x: 0.5, y: 1.42, w: 8.75, h: 0.32,"),
    ("      x: 0.5, y: y, w: 9.0, h: 0.48,", "      x: 0.5, y: y, w: 8.75, h: 0.48,"),
    ("    x: 0.5, y: 4.98, w: 9.0, h: 0.42, rectRadius: 0.05,", "    x: 0.5, y: 4.98, w: 8.75, h: 0.42, rectRadius: 0.05,"),
    ("    x: 0.7, y: 4.98, w: 8.7, h: 0.42, margin: 0,", "    x: 0.7, y: 4.98, w: 8.4, h: 0.42, margin: 0,"),
])

# --- P24: right card ran under the badge ---
patch("slide-24.js", [
    ("  L.card(slide, theme, 6.95, 1.42, 2.55, 3.85, 'FFFFFF');", "  L.card(slide, theme, 6.85, 1.42, 2.45, 3.6, 'FFFFFF');"),
    ("slide.addShape('rect', { x: 6.95, y: 1.42, w: 2.55, h: 0.05,", "slide.addShape('rect', { x: 6.85, y: 1.42, w: 2.45, h: 0.05,"),
    ("    x: 7.15, y: 1.6, w: 2.2, h: 0.26, margin: 0,", "    x: 7.05, y: 1.6, w: 2.1, h: 0.26, margin: 0,"),
    ("    x: 7.15, y: 1.9, w: 2.2, h: 0.4, margin: 0,", "    x: 7.05, y: 1.9, w: 2.1, h: 0.4, margin: 0,"),
    ("    const y = 2.38 + i * 0.52;", "    const y = 2.36 + i * 0.48;"),
    ("      x: 7.15, y: y, w: 2.15, h: 0.42, rectRadius: 0.04,", "      x: 7.05, y: y, w: 2.1, h: 0.4, rectRadius: 0.04,"),
    ("      x: 7.15, y: y, w: 2.15, h: 0.42, margin: 0,", "      x: 7.05, y: y, w: 2.1, h: 0.4, margin: 0,"),
])

# --- P23: one workload label had two colours; body text not top-aligned ---
patch("slide-23.js", [
    ("    no: '1', name: '止血', effort: '小', tone: 'weak',", "    no: '1', name: '止血', effort: '小', tone: 'good',"),
    ("    no: '4', name: '导航', effort: '中', tone: 'brand',", "    no: '4', name: '导航', effort: '中', tone: 'shaky',"),
    ("    no: '5', name: '页面', effort: '中', tone: 'brand',", "    no: '5', name: '页面', effort: '中', tone: 'shaky',"),
    ("    const x = 0.5 + col * 3.05;\n    const y = 1.48 + row * 1.94;",
     "    const x = 0.5 + col * 2.95;\n    const y = 1.48 + row * 1.94;"),
    ("    L.card(slide, theme, x, y, 2.85, 1.78);", "    L.card(slide, theme, x, y, 2.75, 1.78);"),
    ("slide.addShape('rect', { x: x, y: y, w: 2.85, h: 0.05,", "slide.addShape('rect', { x: x, y: y, w: 2.75, h: 0.05,"),
    ("    L.chip(slide, b.tone, b.effort, x + 2.24, y + 0.2, 0.44, 0.26);",
     "    L.chip(slide, b.tone, b.effort, x + 2.16, y + 0.2, 0.44, 0.26);"),
    ("      x: x + 0.18, y: y + 0.56, w: 2.5, h: 0.22, margin: 0,\n      fontSize: 7, color: L.MUTED, fontFace: 'Arial',",
     "      x: x + 0.18, y: y + 0.56, w: 2.4, h: 0.22, margin: 0,\n      fontSize: 7, color: theme.secondary, fontFace: L.CN,"),
    ("      x: x + 0.18, y: y + 0.8, w: 2.5, h: 0.9, margin: 0,\n      fontSize: 8.6, color: L.INK, fontFace: L.CN, lineSpacingMultiple: 1.3,",
     "      x: x + 0.18, y: y + 0.8, w: 2.4, h: 0.92, margin: 0,\n      fontSize: 8.6, color: L.INK, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.3,"),
])

# --- P1: cover meta value wrapped and broke the baseline ---
patch("slide-01.js", [
    ("['范围', '4 个核心页面 + 设计系统']", "['范围', '4 核心页 + 设计系统']"),
    ("    const x = 0.75 + i * 1.62;", "    const x = 0.75 + i * 1.58;"),
    ("      x: x, y: 4.76, w: 1.55, h: 0.36, margin: 0,", "      x: x, y: 4.76, w: 1.52, h: 0.36, margin: 0,"),
])

print("done")
