/** Slide 03 -- Divider 01 */
const L = require('./_lib.js');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  L.divider(slide, theme, '01', '项目与现状', '一个功能密度很高, 但界面层级没有跟上产品演进的全栈项目');
  slide.addShape('rect', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28,
    fill: { color: '0F1F3A' }, line: { color: '2C5A92', width: 0.75 },
  });
  slide.addText('03', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28, margin: 0,
    fontSize: 10, color: '8FB4DC', align: 'center', valign: 'middle', fontFace: L.CN,
  });
}

module.exports = { createSlide: createSlide };
