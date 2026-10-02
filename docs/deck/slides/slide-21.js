/** Slide 18 -> no. Slide 21 -- Sidebar information architecture, before vs after */
const L = require('./_lib.js');

const BEFORE = ['学情看板', 'AI 录题', '错题本', '今日复习', '学生总览', '知识图谱', '能力画像', 'AI 助手', '设置'];
const AFTER = [
  { g: '今天', items: [['学情看板', 'active'], ['今日复习', 'badge18']] },
  { g: '学习', items: [['AI 录题', ''], ['错题本', ''], ['能力画像', '']] },
  { g: '探索', items: [['知识图谱', ''], ['AI 助手', '']] },
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '03  NAVIGATION');
  L.slideTitle(slide, theme, '侧边栏: 从 9 项平铺到三组分层', '每一组回答一个问题: 今天做什么 / 我在学什么 / 还能看什么');

  // ---------- BEFORE ----------
  slide.addShape('rect', {
    x: 0.5, y: 1.45, w: 4.15, h: 3.6,
    fill: { color: theme.light }, line: { color: L.LINE, width: 0.75 },
  });
  slide.addText('现状', {
    x: 0.7, y: 1.58, w: 1.2, h: 0.24, margin: 0,
    fontSize: 10, bold: true, color: L.WEAK, fontFace: L.CN, charSpacing: 1,
  });
  slide.addText('9 项平铺, 0 个分组', {
    x: 2.0, y: 1.58, w: 2.5, h: 0.24, margin: 0,
    fontSize: 8.5, color: theme.secondary, fontFace: L.CN, align: 'right',
  });

  BEFORE.forEach(function (t, i) {
    const y = 1.92 + i * 0.3;
    const on = i === 0;
    slide.addShape('rect', {
      x: 0.7, y: y, w: 3.75, h: 0.26,
      fill: { color: on ? L.BRAND_BG : 'FFFFFF' },
      line: { color: on ? L.BRAND_LN : L.LINE, width: 0.6 },
    });
    slide.addShape('rect', {
      x: 0.84, y: y + 0.1, w: 0.07, h: 0.07,
      fill: { color: on ? theme.accent : 'CBD5E1' }, line: { width: 0 },
    });
    slide.addText(t, {
      x: 1.02, y: y, w: 2.3, h: 0.26, margin: 0,
      fontSize: 8.5, color: on ? theme.accent : L.INK, bold: on, fontFace: L.CN, valign: 'middle',
    });
    if (i === 8) {
      slide.addText('低频', {
        x: 3.7, y: y, w: 0.6, h: 0.26, margin: 0,
        fontSize: 7.5, color: theme.secondary, fontFace: L.CN, align: 'right', valign: 'middle',
      });
    }
  });

  slide.addText('核心动作 (AI 录题) 与低频操作 (设置) 权重相同, 且没有"今天要做多少"的入口.', {
    x: 0.7, y: 4.7, w: 3.75, h: 0.26, margin: 0,
    fontSize: 8, color: L.WEAK, fontFace: L.CN, lineSpacingMultiple: 1.2,
  });

  // ---------- AFTER ----------
  slide.addShape('rect', {
    x: 5.15, y: 1.45, w: 4.1, h: 3.6,
    fill: { color: theme.light }, line: { color: L.GOOD_LN, width: 0.75 },
  });
  slide.addText('方案', {
    x: 5.35, y: 1.58, w: 1.2, h: 0.24, margin: 0,
    fontSize: 10, bold: true, color: L.GOOD, fontFace: L.CN, charSpacing: 1,
  });
  slide.addText('3 组分层 + 待办红点', {
    x: 6.55, y: 1.58, w: 2.5, h: 0.24, margin: 0,
    fontSize: 8.5, color: theme.secondary, fontFace: L.CN, align: 'right',
  });

  let y = 1.92;
  AFTER.forEach(function (grp) {
    slide.addText(grp.g, {
      x: 5.35, y: y, w: 3.7, h: 0.2, margin: 0,
      fontSize: 7.5, bold: true, color: theme.secondary, fontFace: L.CN, charSpacing: 1.2,
    });
    y += 0.2;
    grp.items.forEach(function (it) {
      const active = it[1] === 'active';
      slide.addShape('rect', {
        x: 5.35, y: y, w: 3.7, h: 0.27,
        fill: { color: active ? L.BRAND_BG : 'FFFFFF' },
        line: { color: active ? L.BRAND_LN : L.LINE, width: 0.6 },
      });
      slide.addShape('rect', {
        x: 5.49, y: y + 0.1, w: 0.07, h: 0.07,
        fill: { color: active ? theme.accent : 'CBD5E1' }, line: { width: 0 },
      });
      slide.addText(it[0], {
        x: 5.67, y: y, w: 2.4, h: 0.27, margin: 0,
        fontSize: 8.5, color: active ? theme.accent : L.INK, bold: active, fontFace: L.CN, valign: 'middle',
      });
      if (it[1] === 'badge18') {
        slide.addShape('roundRect', {
          x: 8.5, y: y + 0.06, w: 0.42, h: 0.17, rectRadius: 0.03,
          fill: { color: theme.accent }, line: { width: 0 },
        });
        slide.addText('18', {
          x: 8.5, y: y + 0.06, w: 0.42, h: 0.17, margin: 0,
          fontSize: 7, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle', fontFace: 'Arial',
        });
      }
      y += 0.31;
    });
    y += 0.05;
  });

  // Footnote lives outside the card so it can never print over a nav row.
  slide.addShape('roundRect', {
    x: 5.15, y: 5.12, w: 3.7, h: 0.36, rectRadius: 0.04,
    fill: { color: L.GOOD_BG }, line: { color: L.GOOD_LN, width: 0.6 },
  });
  slide.addText('设置与用户头像固定在底部; 教师专属的学生总览插在学习组之后.', {
    x: 5.28, y: 5.12, w: 3.45, h: 0.36, margin: 0,
    fontSize: 7.6, color: '047857', fontFace: L.CN, valign: 'middle',
  });

  L.pageBadge(slide, theme, 21);
}

module.exports = { createSlide: createSlide };
