/** Slide 23 -- Six-batch landing path */
const L = require('./_lib.js');

const BATCHES = [
  {
    no: '1', name: '止血', effort: '小', tone: 'good',
    files: 'review.py / tutor.py / 全站 service 调用',
    body: '加 safe_call 包装与 error_card 降级组件; 图片路径改存相对路径. 纯防御性代码, 不动任何视觉.',
  },
  {
    no: '2', name: '地基', effort: '中', tone: 'shaky',
    files: 'style.css / theme.py',
    body: 'CSS 变量化 + 三档掌握度语义色 + 深色模式改变量对. 不碰页面逻辑, 收益立竿见影.',
  },
  {
    no: '3', name: '原语', effort: '中', tone: 'shaky',
    files: 'common.py / components.py',
    body: '统一 badge / empty_state / stat_card, 抽出单一 mastery_color(). 做完这步再逐页改才不漏.',
  },
  {
    no: '4', name: '导航', effort: '中', tone: 'shaky',
    files: 'app.py / nav.py',
    body: '侧边栏按今天/学习/探索分组, 今日复习带待办数字. 需新增一个 due 计数查询.',
  },
  {
    no: '5', name: '页面', effort: '中', tone: 'shaky',
    files: 'dashboard / review / tutor',
    body: '看板行动卡与 metric 条; 复习页错误边界与评分预览; 录题页结构化结果卡.',
  },
  {
    no: '6', name: '难点', effort: '大', tone: 'weak',
    files: 'notebook.py',
    body: '卡片网格 + 工具条 + 常驻批量操作条. 需要新的卡片渲染函数, 改动最重但收益最大.',
  },
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '04  ROADMAP');
  L.slideTitle(slide, theme, '六批落地路径', '每批都能独立发布, 第一批当天就能合');

  BATCHES.forEach(function (b, i) {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.5 + col * 2.95;
    const y = 1.48 + row * 1.94;

    L.card(slide, theme, x, y, 2.75, 1.78);
    slide.addShape('rect', { x: x, y: y, w: 2.75, h: 0.05, fill: { color: theme.accent }, line: { width: 0 } });

    // Number
    slide.addShape('roundRect', {
      x: x + 0.18, y: y + 0.18, w: 0.3, h: 0.3, rectRadius: 0.04,
      fill: { color: theme.primary }, line: { width: 0 },
    });
    slide.addText(b.no, {
      x: x + 0.18, y: y + 0.18, w: 0.3, h: 0.3, margin: 0,
      fontSize: 11, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle', fontFace: 'Arial',
    });
    slide.addText(b.name, {
      x: x + 0.56, y: y + 0.18, w: 1.1, h: 0.3, margin: 0,
      fontSize: 13, bold: true, color: theme.primary, fontFace: L.CN, valign: 'middle',
    });
    L.chip(slide, b.tone, b.effort, x + 2.16, y + 0.2, 0.44, 0.26);

    slide.addText(b.files, {
      x: x + 0.18, y: y + 0.56, w: 2.4, h: 0.22, margin: 0,
      fontSize: 7, color: theme.secondary, fontFace: L.CN,
    });
    slide.addText(b.body, {
      x: x + 0.18, y: y + 0.8, w: 2.4, h: 0.92, margin: 0,
      fontSize: 8.6, color: L.INK, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.3,
    });
  });

  L.pageBadge(slide, theme, 23);
}

module.exports = { createSlide: createSlide };
