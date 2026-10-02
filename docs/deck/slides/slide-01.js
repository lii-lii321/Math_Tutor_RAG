/** Slide 01 -- Cover */
const L = require('./_lib.js');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  // Decorative blocks
  slide.addShape('rect', { x: 0, y: 0, w: 10, h: 0.14, fill: { color: theme.accent }, line: { width: 0 } });
  slide.addShape('rect', { x: 7.15, y: 0.14, w: 2.85, h: 5.485, fill: { color: '0F1F3A' }, line: { width: 0 } });
  slide.addShape('rect', { x: 7.9, y: 1.15, w: 1.35, h: 0.05, fill: { color: '2C5A92' }, line: { width: 0 } });
  slide.addShape('rect', { x: 7.9, y: 1.35, w: 0.75, h: 0.05, fill: { color: '2C5A92' }, line: { width: 0 } });

  // Brand mark
  slide.addShape('roundRect', {
    x: 0.75, y: 0.85, w: 0.46, h: 0.46, rectRadius: 0.08,
    fill: { color: theme.accent }, line: { width: 0 },
  });
  slide.addText('M', {
    x: 0.75, y: 0.85, w: 0.46, h: 0.46, margin: 0,
    fontSize: 19, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle', fontFace: 'Arial',
  });
  slide.addText('MathMaster Edu', {
    x: 1.33, y: 0.85, w: 3.2, h: 0.46, margin: 0,
    fontSize: 15, bold: true, color: 'FFFFFF', valign: 'middle', fontFace: L.CN,
  });

  // Title
  slide.addText('界面重设计方案', {
    x: 0.75, y: 1.85, w: 6.1, h: 0.95, margin: 0,
    fontSize: 50, bold: true, color: 'FFFFFF', fontFace: L.CN, fit: 'shrink',
  });
  slide.addText('从功能平铺走向任务驱动', {
    x: 0.75, y: 2.82, w: 6.1, h: 0.42, margin: 0,
    fontSize: 19, color: '8FB4DC', fontFace: L.CN,
  });

  slide.addShape('rect', { x: 0.75, y: 3.45, w: 0.55, h: 0.045, fill: { color: theme.accent }, line: { width: 0 } });

  slide.addText('一次针对信息架构 / 视觉层级 / 交互密度的整体重做', {
    x: 0.75, y: 3.68, w: 5.9, h: 0.34, margin: 0,
    fontSize: 12.5, color: 'A9BCD4', fontFace: L.CN,
  });

  // Meta
  const meta = [
    ['版本', 'v1.0 设计稿'],
    ['日期', '2026-10-01'],
    ['范围', '4 核心页 + 设计系统'],
    ['状态', '待评审 / 未落代码'],
  ];
  meta.forEach(function (m, i) {
    const x = 0.75 + i * 1.58;
    slide.addText(m[0], {
      x: x, y: 4.55, w: 1.5, h: 0.2, margin: 0,
      fontSize: 9, color: '5E7FA6', fontFace: L.CN, charSpacing: 0.8,
    });
    slide.addText(m[1], {
      x: x, y: 4.76, w: 1.52, h: 0.36, margin: 0,
      fontSize: 10.5, color: 'D6E2F0', fontFace: L.CN, lineSpacingMultiple: 1.2,
    });
  });

  // Right panel headline stat
  slide.addText('9', {
    x: 7.9, y: 1.85, w: 1.6, h: 0.7, margin: 0,
    fontSize: 46, bold: true, color: 'FFFFFF', fontFace: 'Arial',
  });
  slide.addText('个页面重新设计', {
    x: 7.9, y: 2.52, w: 1.9, h: 0.24, margin: 0,
    fontSize: 10.5, color: '8FB4DC', fontFace: L.CN,
  });

  slide.addText('2', {
    x: 7.9, y: 3.0, w: 1.6, h: 0.7, margin: 0,
    fontSize: 46, bold: true, color: L.WEAK, fontFace: 'Arial',
  });
  slide.addText('个 P0 体验事故', {
    x: 7.9, y: 3.67, w: 1.9, h: 0.24, margin: 0,
    fontSize: 10.5, color: '8FB4DC', fontFace: L.CN,
  });

  slide.addText('6', {
    x: 7.9, y: 4.12, w: 1.6, h: 0.7, margin: 0,
    fontSize: 46, bold: true, color: '3E7BD6', fontFace: 'Arial',
  });
  slide.addText('批落地路径', {
    x: 7.9, y: 4.79, w: 1.9, h: 0.24, margin: 0,
    fontSize: 10.5, color: '8FB4DC', fontFace: L.CN,
  });
}

module.exports = { createSlide: createSlide };
