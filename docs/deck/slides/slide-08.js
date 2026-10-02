/** Slide 08 -- P0-2: non-portable image paths + AI content rendered as HTML */
const L = require('./_lib.js');

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  P0-2');
  L.slideTitle(slide, theme, '图片路径不可移植, AI 内容被当 HTML 渲染', '两个问题都直接指向"数据可信度"');

  // ---- Left card: path ----
  L.card(slide, theme, 0.5, 1.45, 4.15, 3.4);
  slide.addShape('rect', { x: 0.5, y: 1.45, w: 4.15, h: 0.05, fill: { color: L.WEAK }, line: { width: 0 } });
  L.chip(slide, 'weak', 'P0', 0.72, 1.66, 0.42, 0.24);
  slide.addText('图片路径存的是绝对路径', {
    x: 1.24, y: 1.64, w: 3.4, h: 0.28, margin: 0,
    fontSize: 13.5, bold: true, color: theme.primary, fontFace: L.CN, valign: 'middle',
  });

  // Code block
  slide.addShape('rect', {
    x: 0.72, y: 2.06, w: 3.96, h: 0.62,
    fill: { color: 'F8FAFC' }, line: { color: L.LINE, width: 0.6 },
  });
  slide.addText("DB 实际存储值:\nC:\\Users\\liyun\\.zcode\\workspace\\default\\\nMath_Tutor_RAG\\data\\images\\u2\\20260915.jpg", {
    x: 0.85, y: 2.1, w: 3.75, h: 0.56, margin: 0,
    fontSize: 7.2, color: L.WEAK, fontFace: 'Arial', lineSpacingMultiple: 1.15,
  });

  L.bullets(slide, theme, [
    { t: '换机器必崩', d: '截图里的报错就是这条路径失效' },
    { t: 'v2.10.0 只做了兜底提示', d: '根因未改, 一次改写脚本不是修复' },
    { t: '建议改存相对路径', d: 'data/images/xxx.jpg, 读取时用 __file__ 拼接' },
  ], 0.72, 2.86, 4.0, { size: 9.5, gap: 0.62, markerColor: L.WEAK });

  // ---- Right card: HTML injection ----
  L.card(slide, theme, 5.1, 1.45, 4.15, 3.4);
  slide.addShape('rect', { x: 5.1, y: 1.45, w: 4.15, h: 0.05, fill: { color: L.SHAKY }, line: { width: 0 } });
  L.chip(slide, 'shaky', 'P0', 5.32, 1.66, 0.42, 0.24);
  slide.addText('AI 生成内容被当 HTML 渲染', {
    x: 5.84, y: 1.64, w: 3.4, h: 0.28, margin: 0,
    fontSize: 13.5, bold: true, color: theme.primary, fontFace: L.CN, valign: 'middle',
  });

  slide.addShape('rect', {
    x: 5.32, y: 2.06, w: 3.96, h: 0.62,
    fill: { color: 'F8FAFC' }, line: { color: L.LINE, width: 0.6 },
  });
  slide.addText("review.py:158  st.markdown(content_markdown[:220],\n                            unsafe_allow_html=True)\ntutor.py:215    同样把 analysis.analysis 直接渲染", {
    x: 5.45, y: 2.1, w: 3.75, h: 0.56, margin: 0,
    fontSize: 7.2, color: L.SHAKY, fontFace: 'Arial', lineSpacingMultiple: 1.15,
  });

  L.bullets(slide, theme, [
    { t: '全项目 49 处 unsafe_allow_html', d: 'settings.py 一个文件就占 12 处' },
    { t: 'assistant.py:166 泄漏内部细节', d: '把原始异常字符串直接展示给用户' },
    { t: '改版换渲染管线时必须一起收口', d: '否则会逐个漏改' },
  ], 5.32, 2.86, 4.0, { size: 9.5, gap: 0.62, markerColor: L.SHAKY });

  L.pageBadge(slide, theme, 8);
}

module.exports = { createSlide: createSlide };
