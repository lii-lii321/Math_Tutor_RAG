/** Slide 11 -- Current UI, four real screenshots (captions must stay on-canvas) */
const L = require('./_lib.js');

const SHOTS = [
  { file: '../screenshots/dashboard.png', cap: '学情看板', note: '横幅占 1/4 屏; 8 个等权重盒子' },
  { file: '../screenshots/notebook.png', cap: '错题本', note: '筛选区占首屏大半; 列表无缩略图' },
  { file: '../screenshots/review.png', cap: '今日复习', note: '崩溃态: traceback 直接打屏' },
  { file: '../screenshots/tutor.png', cap: 'AI 录题', note: '上传控件仅 40px 高; 下方 45% 浪费' },
];

// Image box is deliberately smaller so cap + note fit inside the page.
const W = 2.25;
const H = 1.5;
const POS = [
  [0.5, 1.4], [2.95, 1.4],
  [0.5, 3.4], [2.95, 3.4],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  EVIDENCE');
  L.slideTitle(slide, theme, '现状实拍', '取自 docs/screenshots/, v2.9.0');

  SHOTS.forEach(function (s, i) {
    const p = POS[i];
    slide.addShape('rect', {
      x: p[0], y: p[1], w: W, h: H,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.75 }, shadow: L.shadow(),
    });
    slide.addImage({ path: s.file, x: p[0] + 0.04, y: p[1] + 0.04, w: W - 0.08, h: H - 0.08 });
    slide.addText(s.cap, {
      x: p[0], y: p[1] + H + 0.04, w: W, h: 0.19, margin: 0,
      fontSize: 10, bold: true, color: theme.primary, fontFace: L.CN,
    });
    slide.addText(s.note, {
      x: p[0], y: p[1] + H + 0.24, w: W, h: 0.2, margin: 0,
      fontSize: 7.5, color: theme.secondary, fontFace: L.CN,
    });
  });

  // Right column
  L.card(slide, theme, 5.4, 1.4, 3.85, 1.75);
  slide.addShape('rect', { x: 5.4, y: 1.4, w: 3.85, h: 0.05, fill: { color: theme.accent }, line: { width: 0 } });
  slide.addText('四张图共同暴露的问题', {
    x: 5.6, y: 1.56, w: 3.45, h: 0.24, margin: 0,
    fontSize: 11.5, bold: true, color: theme.primary, fontFace: L.CN,
  });
  L.bullets(slide, theme, [
    '没有一个页面回答"我现在该做什么"',
    '视觉层级靠盒子堆叠, 不是靠留白和权重',
    '状态信息没有颜色编码, 全部退化成文字',
  ], 5.6, 1.88, 3.5, { size: 9, gap: 0.4 });

  L.card(slide, theme, 5.4, 3.4, 3.85, 1.75, L.SHAKY_BG);
  slide.addShape('rect', { x: 5.4, y: 3.4, w: 3.85, h: 0.05, fill: { color: L.SHAKY }, line: { width: 0 } });
  slide.addText('但配色本身是对的', {
    x: 5.6, y: 3.56, w: 3.45, h: 0.24, margin: 0,
    fontSize: 11.5, bold: true, color: L.SHAKY, fontFace: L.CN,
  });
  slide.addText('MUJI 藏青 + 克制留白的判断是准确的, 无紫无炫技动效. 本方案予以保留, 改的是层级与密度, 不是审美口味.', {
    x: 5.6, y: 3.88, w: 3.5, h: 1.1, margin: 0,
    fontSize: 9, color: '92400E', fontFace: L.CN, lineSpacingMultiple: 1.35,
  });

  L.pageBadge(slide, theme, 11);
}

module.exports = { createSlide: createSlide };
