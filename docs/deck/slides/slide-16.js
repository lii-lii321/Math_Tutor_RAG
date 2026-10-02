/** Slide 16 -- Divider 03 */
const L = require('./_lib.js');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  L.divider(slide, theme, '03', '成品设计', '四张高保真, 侧边栏与顶栏在四页之间保持一致');
  slide.addShape('rect', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28,
    fill: { color: '0F1F3A' }, line: { color: '2C5A92', width: 0.75 },
  });
  slide.addText('16', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28, margin: 0,
    fontSize: 10, color: '8FB4DC', align: 'center', valign: 'middle', fontFace: L.CN,
  });
}

module.exports = { createSlide: createSlide };
