/** Slide 15 -- Dark mode refactor + cross-page primitives (the prerequisite work) */
const L = require('./_lib.js');

const PRIMS = [
  ['badge(text, tone)', '6 个文件共 7 处各拼 f-string, 收敛成带 tone 的组件', '收 7 处'],
  ['empty_state(icon, title, action)', '4 种写法统一, 空状态同时给出下一步操作', '收 4 处'],
  ['stat_card() 回流', 'review.py / students.py 手写副本删掉, 统一走 common.py', '收 2 处'],
  ['mastery_color(token)', 'mastery.py 与 graph.py 的两套色表合并为单一来源', '收 1 处'],
  ['safe_call(service, fn)', '所有 service 调用包一层, 异常转成 error_card 而非 traceback', '收 7 页'],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '02  FOUNDATION');
  L.slideTitle(slide, theme, '先修地基: 深色模式变量化 + 五个跨页原语', '这五步做完, 后面每页改版才不会逐个漏改');

  // ---- Left: dark mode ----
  L.card(slide, theme, 0.5, 1.45, 4.35, 2.12);
  slide.addShape('rect', { x: 0.5, y: 1.45, w: 4.35, h: 0.05, fill: { color: L.SHAKY }, line: { width: 0 } });
  slide.addText('深色模式: 覆盖式改为变量对', {
    x: 0.7, y: 1.6, w: 4.0, h: 0.26, margin: 0,
    fontSize: 12, bold: true, color: theme.primary, fontFace: L.CN,
  });

  // Before
  slide.addShape('rect', {
    x: 0.7, y: 1.94, w: 1.85, h: 0.6,
    fill: { color: L.WEAK_BG }, line: { color: L.WEAK_LN, width: 0.75 },
  });
  slide.addText('现状 theme.py', {
    x: 0.7, y: 1.98, w: 1.85, h: 0.18, margin: 0,
    fontSize: 7.5, bold: true, color: L.WEAK, fontFace: L.CN,
  });
  slide.addText('20 条 !important\n逐个组件打补丁', {
    x: 0.7, y: 2.16, w: 1.85, h: 0.34, margin: 0,
    fontSize: 8, color: '92400E', fontFace: L.CN, lineSpacingMultiple: 1.15,
  });

  // Arrow
  slide.addText('>', {
    x: 2.6, y: 2.1, w: 0.3, h: 0.3, margin: 0,
    fontSize: 16, bold: true, color: L.MUTED, align: 'center', fontFace: 'Arial',
  });

  // After
  slide.addShape('rect', {
    x: 2.95, y: 1.94, w: 1.9, h: 0.6,
    fill: { color: L.GOOD_BG }, line: { color: L.GOOD_LN, width: 0.75 },
  });
  slide.addText('方案 CSS 变量对', {
    x: 2.95, y: 1.98, w: 1.9, h: 0.18, margin: 0,
    fontSize: 7.5, bold: true, color: L.GOOD, fontFace: L.CN,
  });
  slide.addText('[data-theme=dark]\n{ --card; --ink; --line }', {
    x: 2.95, y: 2.16, w: 1.9, h: 0.34, margin: 0,
    fontSize: 7, color: '047857', fontFace: 'Arial', lineSpacingMultiple: 1.15,
  });

  slide.addText('新组件只用变量, 自动适配双主题. 顺带修掉 settings.py:30 那句"刷新后失效"的半成品开关.', {
    x: 0.7, y: 2.62, w: 4.15, h: 0.46, margin: 0,
    fontSize: 8.8, color: theme.secondary, fontFace: L.CN, lineSpacingMultiple: 1.3,
  });

  // ---- Right: primitives ----
  slide.addText('五个跨页原语', {
    x: 5.1, y: 1.45, w: 4.4, h: 0.28, margin: 0,
    fontSize: 13, bold: true, color: theme.primary, fontFace: L.CN,
  });

  PRIMS.forEach(function (p, i) {
    const y = 1.8 + i * 0.68;
    slide.addShape('rect', {
      x: 5.1, y: y, w: 4.1, h: 0.6,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.6 },
    });
    slide.addShape('rect', { x: 5.1, y: y, w: 0.05, h: 0.6, fill: { color: theme.accent }, line: { width: 0 } });

    slide.addText(p[0], {
      x: 5.28, y: y + 0.05, w: 2.55, h: 0.24, margin: 0,
      fontSize: 8.5, bold: true, color: theme.primary, fontFace: 'Arial',
    });
    slide.addText(p[1], {
      x: 5.28, y: y + 0.28, w: 3.4, h: 0.3, margin: 0,
      fontSize: 7.6, color: theme.secondary, fontFace: L.CN, lineSpacingMultiple: 1.15,
    });

    slide.addShape('roundRect', {
      x: 8.42, y: y + 0.14, w: 0.66, h: 0.32, rectRadius: 0.04,
      fill: { color: L.BRAND_BG }, line: { color: L.BRAND_LN, width: 0.6 },
    });
    slide.addText(p[2], {
      x: 8.42, y: y + 0.14, w: 0.66, h: 0.32, margin: 0,
      fontSize: 7.5, bold: true, color: theme.accent, align: 'center', valign: 'middle', fontFace: L.CN,
    });
  });

  // Bottom banner
  slide.addShape('roundRect', {
    x: 0.5, y: 3.72, w: 4.35, h: 1.6, rectRadius: 0.06,
    fill: { color: L.BRAND_BG }, line: { color: L.BRAND_LN, width: 0.75 },
  });
  slide.addText('为什么必须先做', {
    x: 0.7, y: 3.86, w: 3.9, h: 0.24, margin: 0,
    fontSize: 10, bold: true, color: '1E3A8A', fontFace: L.CN,
  });
  slide.addText('49 处 HTML 字符串 + 8 处裸异常, 如果直接逐页改视觉, 这些点会被逐个漏改, 改完的版本会比分批改更不一致.', {
    x: 0.7, y: 4.14, w: 3.95, h: 1.06, margin: 0,
    fontSize: 8.5, color: '1E3A8A', fontFace: L.CN, lineSpacingMultiple: 1.3,
  });

  L.pageBadge(slide, theme, 15);
}

module.exports = { createSlide: createSlide };
