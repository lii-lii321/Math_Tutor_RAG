/** Slide 12 -- Divider 02 */
const L = require('./_lib.js');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  L.divider(slide, theme, '02', '设计原则与系统', '改版过程中出现取舍冲突时, 按优先级从上往下判');
  slide.addShape('rect', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28,
    fill: { color: '0F1F3A' }, line: { color: '2C5A92', width: 0.75 },
  });
  slide.addText('12', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28, margin: 0,
    fontSize: 10, color: '8FB4DC', align: 'center', valign: 'middle', fontFace: L.CN,
  });
}

module.exports = { createSlide: createSlide };
