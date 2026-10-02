/** Slide 24 -- Risks, trade-offs and explicit non-goals */
const L = require('./_lib.js');

const RISKS = [
  ['st.image 没有 hover 层', '卡片上的操作按钮无法像 Web 那样悬浮出现, 需要换交互方式或退回 st.checkbox'],
  ['position: sticky 不可靠', '底部常驻批量操作条在 Streamlit 容器里可能失效, 或需 components.html 模拟'],
  ['卡片点击展开详情', '网格视图下原位展开会让页面高度剧烈跳动, 建议点卡片跳独立详情页'],
  ['前端零单测', '5 条 E2E 冒烟不足以保护一次大改版, 建议先给跨页原语补最小单测'],
  ['49 处 HTML 字符串', '换渲染管线时必须一次性收口, 否则改版会逐个漏改'],
  ['两套掌握度口径', '看板启发式与引擎口径并存, 界面上会自相矛盾, 需先决定以哪套为准'],
];

const NONGOALS = [
  '不改后端 service 契约',
  '不改数据库 schema 与迁移链',
  '不改 AI provider 抽象层',
  '不动 RAG 检索与融合逻辑',
  '不删任何现有功能',
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '04  RISKS');
  L.slideTitle(slide, theme, '风险与边界', 'Streamlit 的能力边界, 以及本方案明确不改的东西');

  // Risks table
  slide.addShape('rect', { x: 0.5, y: 1.42, w: 6.15, h: 0.3, fill: { color: theme.primary }, line: { width: 0 } });
  slide.addText('风险点', { x: 0.62, y: 1.42, w: 2.0, h: 0.3, margin: 0, fontSize: 9, bold: true, color: 'FFFFFF', fontFace: L.CN, valign: 'middle' });
  slide.addText('影响与对策', { x: 2.7, y: 1.42, w: 3.8, h: 0.3, margin: 0, fontSize: 9, bold: true, color: 'FFFFFF', fontFace: L.CN, valign: 'middle' });

  RISKS.forEach(function (r, i) {
    const y = 1.76 + i * 0.56;
    slide.addShape('rect', {
      x: 0.5, y: y, w: 6.15, h: 0.52,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.6 },
    });
    slide.addShape('rect', { x: 0.5, y: y, w: 0.05, h: 0.52, fill: { color: L.SHAKY }, line: { width: 0 } });
    slide.addText(r[0], {
      x: 0.68, y: y, w: 1.95, h: 0.52, margin: 0,
      fontSize: 8.5, bold: true, color: L.INK, fontFace: L.CN, valign: 'middle', lineSpacingMultiple: 1.12,
    });
    slide.addText(r[1], {
      x: 2.7, y: y, w: 3.85, h: 0.52, margin: 0,
      fontSize: 7.8, color: theme.secondary, fontFace: L.CN, valign: 'middle', lineSpacingMultiple: 1.18,
    });
  });

  // Non-goals
  L.card(slide, theme, 6.85, 1.42, 2.45, 3.6, 'FFFFFF');
  slide.addShape('rect', { x: 6.85, y: 1.42, w: 2.45, h: 0.05, fill: { color: L.GOOD }, line: { width: 0 } });
  slide.addText('本方案不改', {
    x: 7.05, y: 1.6, w: 2.1, h: 0.26, margin: 0,
    fontSize: 12, bold: true, color: L.GOOD, fontFace: L.CN,
  });
  slide.addText('改版只动界面层, 以下边界保持不变:', {
    x: 7.05, y: 1.9, w: 2.1, h: 0.4, margin: 0,
    fontSize: 8.5, color: theme.secondary, fontFace: L.CN, lineSpacingMultiple: 1.25,
  });
  NONGOALS.forEach(function (n, i) {
    const y = 2.36 + i * 0.48;
    slide.addShape('roundRect', {
      x: 7.05, y: y, w: 2.1, h: 0.4, rectRadius: 0.04,
      fill: { color: L.GOOD_BG }, line: { color: L.GOOD_LN, width: 0.6 },
    });
    slide.addText(n, {
      x: 7.05, y: y, w: 2.1, h: 0.4, margin: 0,
      fontSize: 8.2, color: '047857', fontFace: L.CN, align: 'center', valign: 'middle',
    });
  });

  L.pageBadge(slide, theme, 24);
}

module.exports = { createSlide: createSlide };
