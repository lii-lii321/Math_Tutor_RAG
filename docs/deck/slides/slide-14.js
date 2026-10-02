/** Slide 14 -- Design tokens: colour system */
const L = require('./_lib.js');

const TOKENS = [
  ['16294A', '--navy', '品牌深色', '标题 / Hero / 主按钮底色. 较原 #1a365d 略深, 压得住大色块', '16294A'],
  ['2563EB', '--brand', '交互蓝', '可点击元素 / 当前选中态 / 进度条', '2563EB'],
  ['DC2626', '--weak', '薄弱', '掌握度 < 40%, 与后端 WEAK_THRESHOLD 同源', 'DC2626'],
  ['D97706', '--shaky', '不稳固', '掌握度 40%-70% 或待复习, 与 SHAKY_THRESHOLD 同源', 'D97706'],
  ['059669', '--good', '已掌握', '掌握度 > 70% 或数学验证通过', '059669'],
  ['F7F8FA', '--bg', '页面底色', '较 #f8fafc 略暖, 接近纸张', 'F7F8FA'],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '02  TOKENS');
  L.slideTitle(slide, theme, '色彩系统: 新增三档掌握度语义色', '阈值直接对齐后端引擎, 前端不再自己定义一套');

  // Table
  slide.addShape('rect', { x: 0.5, y: 1.42, w: 6.1, h: 0.3, fill: { color: theme.primary }, line: { width: 0 } });
  [['', 0.62, 0.72], ['Token', 1.4, 1.35], ['语义', 2.8, 0.95], ['用途', 3.8, 2.7]].forEach(function (h) {
    if (!h[0]) return;
    slide.addText(h[0], {
      x: h[1], y: 1.42, w: h[2], h: 0.3, margin: 0,
      fontSize: 9, bold: true, color: 'FFFFFF', fontFace: L.CN, valign: 'middle',
    });
  });

  TOKENS.forEach(function (t, i) {
    const y = 1.76 + i * 0.56;
    slide.addShape('rect', {
      x: 0.5, y: y, w: 6.1, h: 0.52,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.6 },
    });
    slide.addShape('roundRect', {
      x: 0.66, y: y + 0.11, w: 0.3, h: 0.3, rectRadius: 0.04,
      fill: { color: t[4] }, line: { color: 'E2E8F0', width: 0.5 },
    });
    slide.addText(t[0], {
      x: 1.04, y: y, w: 0.72, h: 0.52, margin: 0,
      fontSize: 7, color: theme.secondary, fontFace: 'Arial', valign: 'middle',
    });
    slide.addText(t[1], {
      x: 1.78, y: y, w: 1.0, h: 0.52, margin: 0,
      fontSize: 9, bold: true, color: theme.primary, fontFace: 'Arial', valign: 'middle',
    });
    slide.addText(t[2], {
      x: 2.8, y: y, w: 0.95, h: 0.52, margin: 0,
      fontSize: 9.5, color: L.INK, fontFace: L.CN, valign: 'middle',
    });
    slide.addText(t[3], {
      x: 3.8, y: y, w: 2.72, h: 0.52, margin: 0,
      fontSize: 7.6, color: theme.secondary, fontFace: L.CN, valign: 'middle', lineSpacingMultiple: 1.12,
    });
  });

  // Right: three-tier scale
  L.card(slide, theme, 6.75, 1.42, 2.5, 1.95);
  slide.addShape('rect', { x: 6.75, y: 1.42, w: 2.5, h: 0.05, fill: { color: theme.accent }, line: { width: 0 } });
  slide.addText('三档刻度', {
    x: 6.95, y: 1.58, w: 2.1, h: 0.26, margin: 0,
    fontSize: 11.5, bold: true, color: theme.primary, fontFace: L.CN,
  });
  const tiers = [
    [L.WEAK, '薄弱', '< 40%', 40],
    [L.SHAKY, '不稳固', '40% - 70%', 62],
    [L.GOOD, '已掌握', '> 70%', 92],
  ];
  tiers.forEach(function (t, i) {
    const y = 1.94 + i * 0.44;
    slide.addText(t[1], {
      x: 6.95, y: y, w: 0.6, h: 0.2, margin: 0,
      fontSize: 9, bold: true, color: t[0], fontFace: L.CN,
    });
    slide.addText(t[2], {
      x: 7.5, y: y, w: 0.75, h: 0.2, margin: 0,
      fontSize: 7.5, color: L.MUTED, fontFace: 'Arial', align: 'right',
    });
    L.bar(slide, 6.95, y + 0.22, 2.1, 0.1, t[3], t[0]);
  });

  // Key constraint
  slide.addShape('roundRect', {
    x: 6.75, y: 3.5, w: 2.5, h: 1.78, rectRadius: 0.06,
    fill: { color: L.WEAK_BG }, line: { color: L.WEAK_LN, width: 0.75 },
  });
  slide.addText('一条硬约束', {
    x: 6.95, y: 3.66, w: 2.1, h: 0.24, margin: 0,
    fontSize: 10.5, bold: true, color: L.WEAK, fontFace: L.CN,
  });
  slide.addText('三档色只用于表达掌握度与状态, 不用于装饰. 一个界面上红色出现超过 3 处, 就说明层级出了问题 -- 应该把它折叠进"薄弱"筛选, 而不是全量铺开.', {
    x: 6.95, y: 3.96, w: 2.12, h: 1.2, margin: 0,
    fontSize: 9, color: '92400E', fontFace: L.CN, lineSpacingMultiple: 1.35,
  });

  L.pageBadge(slide, theme, 14);
}

module.exports = { createSlide: createSlide };
