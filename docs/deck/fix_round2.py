"""QA fix round 2: remaining overlaps and one number inconsistency."""
import pathlib

DECK = pathlib.Path(r"D:\Math_Tutor_RAG\docs\deck\slides")


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


# P6: section label was sitting on the bucket card's bottom border;
#     and the bare-service page count must match the 7 rows listed on P7.
patch("slide-06.js", [
    ("      x: x, y: y, w: 2.75, h: 2.34, rectRadius: 0.06,", "      x: x, y: y, w: 2.75, h: 2.25, rectRadius: 0.06,"),
    ("      const yy = y + 0.66 + j * 0.42;", "      const yy = y + 0.64 + j * 0.38;"),
    ("        x: x + 0.33, y: yy - 0.03, w: 2.28, h: 0.42, margin: 0,",
     "        x: x + 0.33, y: yy - 0.03, w: 2.28, h: 0.38, margin: 0,"),
    ("        fontSize: 9, color: L.INK, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.2,",
     "        fontSize: 8.6, color: L.INK, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.18,"),
    ("    x: 0.5, y: 3.72, w: 3, h: 0.26, margin: 0,", "    x: 0.5, y: 3.82, w: 3, h: 0.24, margin: 0,"),
    ("    const x = 0.5 + i * 2.22;\n    const y = 4.02;", "    const x = 0.5 + i * 2.22;\n    const y = 4.14;"),
    ("      x: x, y: y, w: 2.05, h: 1.24,", "      x: x, y: y, w: 2.05, h: 1.16,"),
    ("['8', '个页面存在裸 service 调用', 'graph / mastery / assistant / auth / review 等'],",
     "['7', '个页面存在裸 service 调用', 'graph / mastery / assistant / auth / review 等'],"),
])

# P21: the hairline divider rendered as a heavy black bar; drop it.
p = DECK / "slide-21.js"
src = p.read_text(encoding="utf-8")
old_line = "  slide.addShape('rect', { x: 0.7, y: 4.66, w: 3.75, h: 0.012, fill: { color: L.LINE }, line: { width: 0 } });\n"
if old_line in src:
    src = src.replace(old_line, "")
    p.write_text(src, encoding="utf-8")
    print("  patched slide-21.js (removed hairline)")
else:
    print("  MISS slide-21.js hairline")
