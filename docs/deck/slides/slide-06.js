/** Slide 06 -- Diagnosis overview: severity buckets + quantified debt */
const L = require('./_lib.js');

const BUCKETS = [
  {
    tone: 'weak', code: 'P0', count: '2', label: '体验事故',
    items: ['异常无边界, traceback 直接打屏', '图片路径不可移植, 换机必崩'],
  },
  {
    tone: 'shaky', code: 'P1', count: '4', label: '效率损失',
    items: ['9 个导航项平铺, 无主次', '错题本筛选区吃掉首屏 60%', '6 个图表等权重纵向平铺', '列表项 7 类信息挤在一行纯文本'],
  },
  {
    tone: 'brand', code: 'P2', count: '4', label: '一致性债',
    items: ['统计卡 3 套实现 / 空状态 4 种写法', '状态色 2 套映射 (shaky 一红一灰)', 'i18n 框架存在, 9 个页面 0 处使用', '深色模式靠 20 条 !important 打补丁'],
  },
];

const NUMBERS = [
  ['49', '处 unsafe_allow_html', '其中 4 处把 AI 生成内容当 HTML 渲染'],
  ['7', '个页面有裸 service 调用', 'graph / mastery / assistant / auth / review 等'],
  ['9', '个平级导航项', '核心动作与低频设置视觉权重相同'],
  ['5', '条 E2E 用例', '前端层零单测, 改版无回归保护'],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  DIAGNOSIS');
  L.slideTitle(slide, theme, '诊断总览', '10 个问题, 全部有代码位置与截图依据');

  // Severity buckets
  BUCKETS.forEach(function (b, i) {
    const x = 0.5 + i * 2.95;
    const y = 1.48;
    const toneMap = {
      weak: { fg: L.WEAK, bg: L.WEAK_BG, ln: L.WEAK_LN },
      shaky: { fg: L.SHAKY, bg: L.SHAKY_BG, ln: L.SHAKY_LN },
      brand: { fg: theme.accent, bg: L.BRAND_BG, ln: L.BRAND_LN },
    };
    const t = toneMap[b.tone];

    slide.addShape('roundRect', {
      x: x, y: y, w: 2.75, h: 2.25, rectRadius: 0.06,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.75 }, shadow: L.shadow(),
    });
    slide.addShape('rect', { x: x, y: y, w: 2.75, h: 0.05, fill: { color: t.fg }, line: { width: 0 } });

    L.chip(slide, b.tone, b.code, x + 0.18, y + 0.18, 0.44, 0.24);
    slide.addText(b.count, {
      x: x + 1.9, y: y + 0.1, w: 0.7, h: 0.42, margin: 0,
      fontSize: 24, bold: true, color: t.fg, align: 'right', fontFace: 'Arial',
    });
    slide.addText(b.label, {
      x: x + 0.7, y: y + 0.2, w: 1.25, h: 0.24, margin: 0,
      fontSize: 11, bold: true, color: theme.primary, fontFace: L.CN, valign: 'middle',
    });

    b.items.forEach(function (it, j) {
      const yy = y + 0.64 + j * 0.38;
      slide.addShape('rect', { x: x + 0.2, y: yy + 0.08, w: 0.05, h: 0.05, fill: { color: t.fg } });
      slide.addText(it, {
        x: x + 0.33, y: yy - 0.03, w: 2.28, h: 0.38, margin: 0,
        fontSize: 8.6, color: L.INK, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.18,
      });
    });
  });

  // Quantified debt strip
  slide.addText('量化后的技术债', {
    x: 0.5, y: 3.82, w: 3, h: 0.24, margin: 0,
    fontSize: 12, bold: true, color: theme.primary, fontFace: L.CN,
  });

  NUMBERS.forEach(function (n, i) {
    const x = 0.5 + i * 2.22;
    const y = 4.14;
    slide.addShape('rect', {
      x: x, y: y, w: 2.05, h: 1.16,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.75 },
    });
    slide.addText(n[0], {
      x: x + 0.16, y: y + 0.1, w: 1.8, h: 0.5, margin: 0,
      fontSize: 30, bold: true, color: theme.accent, fontFace: 'Arial',
    });
    slide.addText(n[1], {
      x: x + 0.16, y: y + 0.58, w: 1.85, h: 0.24, margin: 0,
      fontSize: 9.5, bold: true, color: L.INK, fontFace: L.CN,
    });
    slide.addText(n[2], {
      x: x + 0.16, y: y + 0.8, w: 1.85, h: 0.4, margin: 0,
      fontSize: 8, color: theme.secondary, fontFace: L.CN, lineSpacingMultiple: 1.15,
    });
  });

  L.pageBadge(slide, theme, 6);
}

module.exports = { createSlide: createSlide };
