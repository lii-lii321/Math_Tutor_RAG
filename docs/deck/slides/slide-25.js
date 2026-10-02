/** Slide 25 -- Closing: recommended next step + open decisions */
const L = require('./_lib.js');

const NEXT = [
  ['先修 P0', '错误边界 + 图片相对路径. 纯防御性代码, 当天可合, 与视觉改版完全解耦.', 'weak'],
  ['再评审成品', '四张 mockup 逐页确认交互细节, 尤其是错题本卡片网格的落地方式.', 'shaky'],
  ['最后动代码', '按六批路径推进, 每批独立发布, 不做大爆炸式改版.', 'good'],
];

const DECISIONS = [
  '看板与引擎两套掌握度口径, 界面上以哪套为准?',
  '错题本卡片点击后, 原位展开还是跳独立详情页?',
  '是否给前端跨页原语补最小单测, 作为改版的回归保护?',
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  slide.addShape('rect', { x: 0, y: 0, w: 10, h: 0.1, fill: { color: theme.accent }, line: { width: 0 } });
  slide.addShape('rect', { x: 0, y: 0, w: 0.14, h: 5.625, fill: { color: '0F1F3A' }, line: { width: 0 } });

  slide.addText('下一步', {
    x: 0.7, y: 0.62, w: 4, h: 0.6, margin: 0,
    fontSize: 32, bold: true, color: 'FFFFFF', fontFace: L.CN,
  });
  slide.addText('建议先做与视觉无关的那一批', {
    x: 0.7, y: 1.24, w: 5, h: 0.28, margin: 0,
    fontSize: 12.5, color: '8FB4DC', fontFace: L.CN,
  });

  NEXT.forEach(function (n, i) {
    const x = 0.7 + i * 3.0;
    const y = 1.78;
    const toneMap = {
      weak: { fg: 'FF9B9B', bg: '2A1620' },
      shaky: { fg: 'FCD34D', bg: '2A2314' },
      good: { fg: '6EE7B7', bg: '102A22' },
    };
    const t = toneMap[n[2]];
    slide.addShape('roundRect', {
      x: x, y: y, w: 2.75, h: 1.62, rectRadius: 0.06,
      fill: { color: t.bg }, line: { color: t.fg, width: 0.75 },
    });
    slide.addText('0' + (i + 1), {
      x: x + 0.2, y: y + 0.16, w: 0.5, h: 0.26, margin: 0,
      fontSize: 12, bold: true, color: t.fg, fontFace: 'Arial',
    });
    slide.addText(n[0], {
      x: x + 0.2, y: y + 0.44, w: 2.4, h: 0.3, margin: 0,
      fontSize: 14, bold: true, color: 'FFFFFF', fontFace: L.CN,
    });
    slide.addText(n[1], {
      x: x + 0.2, y: y + 0.8, w: 2.38, h: 0.72, margin: 0,
      fontSize: 8.5, color: 'A9BCD4', fontFace: L.CN, lineSpacingMultiple: 1.32,
    });
  });

  // Open decisions
  slide.addText('需要你拍板的三个问题', {
    x: 0.7, y: 3.68, w: 4, h: 0.3, margin: 0,
    fontSize: 13, bold: true, color: 'FFFFFF', fontFace: L.CN,
  });
  DECISIONS.forEach(function (d, i) {
    const y = 4.05 + i * 0.38;
    slide.addShape('rect', { x: 0.72, y: y + 0.08, w: 0.07, h: 0.07, fill: { color: theme.accent } });
    slide.addText(d, {
      x: 0.9, y: y - 0.02, w: 8.4, h: 0.3, margin: 0,
      fontSize: 10, color: 'C8D8EA', fontFace: L.CN, valign: 'top',
    });
  });

  // Badge
  slide.addShape('rect', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28,
    fill: { color: '0F1F3A' }, line: { color: '2C5A92', width: 0.75 },
  });
  slide.addText('25', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28, margin: 0,
    fontSize: 10, color: '8FB4DC', align: 'center', valign: 'middle', fontFace: L.CN,
  });
}

module.exports = { createSlide: createSlide };
