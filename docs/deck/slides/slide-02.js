/** Slide 02 -- Table of contents (sidebar navigation style) */
const L = require('./_lib.js');

const SECTIONS = [
  ['01', '项目与现状', '现状速览 / 能力全景 / 问题诊断 / 现状实拍'],
  ['02', '设计原则与系统', '四条原则 / 色彩 token / 跨页基建'],
  ['03', '成品设计', '四页高保真 / 侧边栏前后对比'],
  ['04', '落地路径与风险', '六批路径 / 风险与边界 / 下一步'],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, 'CONTENTS');
  L.slideTitle(slide, theme, '目录', '四个部分, 从现状到成品再到落地');

  SECTIONS.forEach(function (s, i) {
    const y = 1.6 + i * 0.92;

    // Number block
    slide.addShape('rect', {
      x: 0.5, y: y, w: 0.62, h: 0.72,
      fill: { color: theme.primary }, line: { width: 0 },
    });
    slide.addText(s[0], {
      x: 0.5, y: y, w: 0.62, h: 0.72, margin: 0,
      fontSize: 20, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle', fontFace: 'Arial',
    });

    // Title + description
    L.card(slide, theme, 1.2, y, 5.55, 0.72);
    slide.addText(s[1], {
      x: 1.42, y: y + 0.09, w: 3.4, h: 0.3, margin: 0,
      fontSize: 16, bold: true, color: theme.primary, fontFace: L.CN, valign: 'middle',
    });
    slide.addText(s[2], {
      x: 1.42, y: y + 0.38, w: 4.6, h: 0.26, margin: 0,
      fontSize: 10.5, color: theme.secondary, fontFace: L.CN, valign: 'middle',
    });

    // Page hint
    slide.addText('P' + [3, 12, 16, 22][i], {
      x: 6.85, y: y, w: 0.6, h: 0.72, margin: 0,
      fontSize: 12, color: L.MUTED, align: 'right', valign: 'middle', fontFace: 'Arial',
    });
  });

  // Right takeaway panel
  L.card(slide, theme, 7.7, 1.6, 1.8, 3.4, 'FFFFFF');
  slide.addShape('rect', { x: 7.7, y: 1.6, w: 1.8, h: 0.06, fill: { color: theme.accent }, line: { width: 0 } });
  slide.addText('本次范围', {
    x: 7.9, y: 1.82, w: 1.45, h: 0.28, margin: 0,
    fontSize: 12, bold: true, color: theme.primary, fontFace: L.CN,
  });
  const scope = [
    '保留 MUJI 配色',
    '重做信息层级',
    '新增错误边界',
    '收敛组件原语',
    '不改后端契约',
  ];
  scope.forEach(function (t, i) {
    slide.addShape('rect', { x: 7.9, y: 2.32 + i * 0.5, w: 0.07, h: 0.07, fill: { color: theme.accent } });
    slide.addText(t, {
      x: 8.07, y: 2.23 + i * 0.5, w: 1.35, h: 0.3, margin: 0,
      fontSize: 10.5, color: L.INK, fontFace: L.CN, valign: 'middle',
    });
  });

  L.pageBadge(slide, theme, 2);
}

module.exports = { createSlide: createSlide };
