/** Slide 09 -- P1: information architecture (four structural problems) */
const L = require('./_lib.js');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  P1');
  L.slideTitle(slide, theme, '信息架构: 功能都平铺出来了, 但没有主次', '四个问题都指向同一件事 -- 用户打开应用的第一问没有得到回答');

  const cards = [
    { x: 0.5, y: 1.45, t: '9 个导航项完全平级', d: 'AI 录题 (核心动作) 与 设置 (低频) 视觉权重相同, 也没有"今天该做什么"的入口.' },
    { x: 5.1, y: 1.45, t: '筛选区吃掉首屏 60%', d: '5 个 toggle + 2 个下拉 + 搜索框默认全关, 等于白占空间, 真正的列表被推到折叠线以下.' },
    { x: 0.5, y: 3.42, t: '6 个图表等权重平铺', d: '知识点分布/薄弱/录入趋势/日历/正确率/难度 同尺寸同位置堆叠, 核心指标被稀释.' },
    { x: 5.1, y: 3.42, t: '一行塞了 7 类信息', d: '到期标记+星标+标签+难度+日期+掌握度+未读批注 串成纯文本, 扫读成本极高.' },
  ];

  cards.forEach(function (c) {
    L.card(slide, theme, c.x, c.y, 4.15, 1.85);
    slide.addShape('rect', { x: c.x, y: c.y, w: 0.05, h: 1.85, fill: { color: L.SHAKY }, line: { width: 0 } });

    slide.addText(c.t, {
      x: c.x + 0.22, y: c.y + 0.14, w: 2.55, h: 0.5, margin: 0,
      fontSize: 12, bold: true, color: theme.primary, fontFace: L.CN, lineSpacingMultiple: 1.15,
    });
    slide.addText(c.d, {
      x: c.x + 0.22, y: c.y + 0.72, w: 2.28, h: 0.98, margin: 0,
      fontSize: 9.5, color: theme.secondary, fontFace: L.CN, lineSpacingMultiple: 1.32,
    });
  });

  // ---- Mini wireframes inside each card (right side) ----
  const wf = { x: 3.12, y: 1.62, w: 1.35, h: 1.5, fill: 'F8FAFC', ln: L.LINE };

  // 1: flat nav list
  let x = wf.x, y = wf.y;
  for (let i = 0; i < 9; i++) {
    const on = i === 0;
    slide.addShape('rect', {
      x: x, y: y + i * 0.155, w: 1.35, h: 0.13,
      fill: { color: on ? L.BRAND_BG : 'FFFFFF' }, line: { width: 0 },
    });
    slide.addShape('rect', {
      x: x + 0.04, y: y + i * 0.155 + 0.05, w: on ? 0.5 : 0.38, h: 0.035,
      fill: { color: on ? theme.accent : 'CBD5E1' }, line: { width: 0 },
    });
  }
  slide.addText('0 个分组', {
    x: x, y: y + 1.42, w: 1.35, h: 0.16, margin: 0,
    fontSize: 7, bold: true, color: L.WEAK, fontFace: L.CN, align: 'center',
  });

  // 2: filter eating the fold
  x = wf.x + 4.5; y = wf.y;
  slide.addShape('rect', {
    x: x, y: y, w: 1.35, h: 0.92,
    fill: { color: L.WEAK_BG }, line: { color: L.WEAK_LN, width: 0.75, dashType: 'dash' },
  });
  for (let i = 0; i < 5; i++) {
    slide.addShape('rect', {
      x: x + 0.08, y: y + 0.1 + i * 0.15, w: 0.34, h: 0.08,
      fill: { color: 'FCA5A5' }, line: { width: 0 },
    });
    slide.addShape('rect', {
      x: x + 0.5, y: y + 0.1 + i * 0.15, w: 0.92, h: 0.08,
      fill: { color: 'FECACA' }, line: { width: 0 },
    });
  }
  slide.addShape('rect', {
    x: x, y: y + 1.0, w: 1.35, h: 0.36,
    fill: { color: 'FFFFFF' }, line: { color: L.LINE, width: 0.6 },
  });
  slide.addText('列表在这', {
    x: x, y: 1.0 + y, w: 1.35, h: 0.36, margin: 0,
    fontSize: 7.5, color: L.MUTED, fontFace: L.CN, align: 'center', valign: 'middle',
  });
  slide.addText('60% 屏幕', {
    x: x, y: y + 1.42, w: 1.35, h: 0.16, margin: 0,
    fontSize: 7, bold: true, color: L.WEAK, fontFace: L.CN, align: 'center',
  });

  // 3: six equal charts
  x = wf.x; y = wf.y + 1.97;
  for (let i = 0; i < 6; i++) {
    const cx = x + (i % 2) * 0.78;
    const cy = y + Math.floor(i / 2) * 0.42;
    slide.addShape('rect', {
      x: cx, y: cy, w: 0.7, h: 0.34,
      fill: { color: 'FFFFFF' }, line: { color: L.LINE, width: 0.6 },
    });
    slide.addShape('rect', {
      x: cx + 0.06, y: cy + 0.08, w: 0.58, h: 0.18,
      fill: { color: 'CBD5E1' }, line: { width: 0 },
    });
  }
  slide.addText('无主次', {
    x: x, y: y + 1.3, w: 1.35, h: 0.16, margin: 0,
    fontSize: 7, bold: true, color: L.WEAK, fontFace: L.CN, align: 'center',
  });

  // 4: one-line info pile
  x = wf.x + 4.5; y = wf.y + 1.97;
  for (let i = 0; i < 4; i++) {
    slide.addShape('rect', {
      x: x, y: y + i * 0.3, w: 1.35, h: 0.24,
      fill: { color: 'FFFFFF' }, line: { color: L.LINE, width: 0.6 },
    });
    const segs = [[0.12, 'F59E0B'], [0.3, 'CBD5E1'], [0.22, 'CBD5E1'], [0.18, 'CBD5E1'], [0.12, 'CBD5E1']];
    let ox = x + 0.05;
    for (let s = 0; s < segs.length; s++) {
      slide.addShape('rect', {
        x: ox, y: y + i * 0.3 + 0.1, w: segs[s][0] * 1.4, h: 0.05,
        fill: { color: segs[s][1] }, line: { width: 0 },
      });
      ox += segs[s][0] * 1.4 + 0.02;
    }
  }
  slide.addText('7 类 / 1 行', {
    x: x, y: y + 1.3, w: 1.35, h: 0.16, margin: 0,
    fontSize: 7, bold: true, color: L.WEAK, fontFace: L.CN, align: 'center',
  });

  L.pageBadge(slide, theme, 9);
}

module.exports = { createSlide: createSlide };
