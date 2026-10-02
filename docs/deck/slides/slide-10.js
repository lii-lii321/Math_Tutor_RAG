/** Slide 10 -- P2: consistency debt, the same thing implemented N ways */
const L = require('./_lib.js');

const DEBT = [
  ['3 套', '统计卡实现', 'common.py stat_card() / review.py:120 手写 / students.py:174 手写(还带多余闭合标签)'],
  ['4 种', '空状态写法', 'st.info / st.success 表达无数据 / 手写 .mm-empty / st.caption'],
  ['2 套', '状态色映射', 'mastery.py:9 shaky=#94a3b8  vs  graph.py:12 shaky=#d97706'],
  ['3 套', '标题层级', 'page_header / st.subheader / st.markdown("####"), students.py 一页两个 page_header'],
  ['7 处', '徽章裸拼字符串', 'review / tutor / mastery / graph / assistant / settings 各写各的 f-string'],
  ['0 处', 'i18n 实际使用', '框架存在, 但 9 个页面全是硬编码中文'],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  P2');
  L.slideTitle(slide, theme, '一致性债: 同一个东西有 N 种实现', '这类债在改版时会被放大 -- 每处都要单独改, 漏一处就不一致');

  // Table header
  slide.addShape('rect', {
    x: 0.5, y: 1.42, w: 8.75, h: 0.32,
    fill: { color: theme.primary }, line: { width: 0 },
  });
  ['现状', '对象', '具体位置与症状'].forEach(function (h, i) {
    const xs = [0.62, 1.55, 3.0];
    const ws = [0.85, 1.4, 6.3];
    slide.addText(h, {
      x: xs[i], y: 1.42, w: ws[i], h: 0.32, margin: 0,
      fontSize: 9.5, bold: true, color: 'FFFFFF', fontFace: L.CN, valign: 'middle',
    });
  });

  DEBT.forEach(function (d, i) {
    const y = 1.78 + i * 0.52;
    slide.addShape('rect', {
      x: 0.5, y: y, w: 8.75, h: 0.48,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.6 },
    });
    slide.addText(d[0], {
      x: 0.62, y: y, w: 0.85, h: 0.48, margin: 0,
      fontSize: 15, bold: true, color: theme.accent, fontFace: 'Arial', valign: 'middle',
    });
    slide.addText(d[1], {
      x: 1.55, y: y, w: 1.4, h: 0.48, margin: 0,
      fontSize: 10.5, bold: true, color: L.INK, fontFace: L.CN, valign: 'middle',
    });
    slide.addText(d[2], {
      x: 3.0, y: y, w: 6.3, h: 0.48, margin: 0,
      fontSize: 8.8, color: theme.secondary, fontFace: L.CN, valign: 'middle', lineSpacingMultiple: 1.15,
    });
  });

  // Consequence callout
  slide.addShape('roundRect', {
    x: 0.5, y: 4.98, w: 8.75, h: 0.42, rectRadius: 0.05,
    fill: { color: L.BRAND_BG }, line: { color: L.BRAND_LN, width: 0.75 },
  });
  slide.addShape('rect', { x: 0.5, y: 4.98, w: 0.05, h: 0.42, fill: { color: theme.accent }, line: { width: 0 } });
  slide.addText('结论: 改版前必须先做跨页基建 -- 统一 badge() / empty_state() / stat_card() 三个原语, 抽出单一 mastery_color() 映射', {
    x: 0.7, y: 4.98, w: 8.4, h: 0.42, margin: 0,
    fontSize: 9.5, bold: true, color: '1E3A8A', fontFace: L.CN, valign: 'middle',
  });

  L.pageBadge(slide, theme, 10);
}

module.exports = { createSlide: createSlide };
