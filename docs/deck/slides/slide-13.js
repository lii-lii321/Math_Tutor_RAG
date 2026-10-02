/** Slide 13 -- Four design principles */
const L = require('./_lib.js');

const PRINCIPLES = [
  {
    no: '01', title: '任务优先于功能',
    lead: '用户打开应用的第一问是"今天该复习什么"',
    body: '不是"这个应用有哪些功能". 看板第一屏必须给出可执行的下一步, 而不是一堆数字. 功能入口退居侧边栏.',
  },
  {
    no: '02', title: '数据必须可扫读',
    lead: '一行文本超过 3 类信息就该拆开',
    body: '掌握度用色环加颜色编码, 状态用图标. 颜色只承载一个含义: 红=薄弱 / 琥珀=待复习 / 绿=已掌握.',
  },
  {
    no: '03', title: '默认折叠次要',
    lead: '低频操作不该常驻在首屏',
    body: '筛选项 / 导出格式 / 难度分布收进抽屉或菜单, 用 chip 显式回显当前生效的条件, 让用户知道自己处在什么视图里.',
  },
  {
    no: '04', title: '保留 MUJI 骨相',
    lead: '克制的配色判断是对的',
    body: '本方案予以保留, 改的是层级与密度, 不是审美口味. 藏青标题 / 石板灰正文 / 蓝色点缀, 大量留白.',
  },
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '02  PRINCIPLES');
  L.slideTitle(slide, theme, '四条设计原则', '后面所有取舍都按这四条判');

  PRINCIPLES.forEach(function (p, i) {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 4.6;
    const y = 1.5 + row * 1.85;

    L.card(slide, theme, x, y, 4.4, 1.68);
    slide.addShape('rect', { x: x, y: y, w: 4.4, h: 0.05, fill: { color: theme.accent }, line: { width: 0 } });

    // Number
    slide.addShape('roundRect', {
      x: x + 0.22, y: y + 0.2, w: 0.42, h: 0.42, rectRadius: 0.05,
      fill: { color: theme.primary }, line: { width: 0 },
    });
    slide.addText(p.no, {
      x: x + 0.22, y: y + 0.2, w: 0.42, h: 0.42, margin: 0,
      fontSize: 12, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle', fontFace: 'Arial',
    });

    slide.addText(p.title, {
      x: x + 0.76, y: y + 0.18, w: 3.4, h: 0.28, margin: 0,
      fontSize: 14, bold: true, color: theme.primary, fontFace: L.CN, valign: 'middle',
    });
    slide.addText(p.lead, {
      x: x + 0.76, y: y + 0.46, w: 3.4, h: 0.22, margin: 0,
      fontSize: 9, color: theme.accent, fontFace: L.CN,
    });

    slide.addShape('rect', {
      x: x + 0.22, y: y + 0.78, w: 3.96, h: 0.012,
      fill: { color: L.LINE }, line: { width: 0 },
    });

    slide.addText(p.body, {
      x: x + 0.22, y: y + 0.88, w: 3.96, h: 0.7, margin: 0,
      fontSize: 9.5, color: theme.secondary, fontFace: L.CN, lineSpacingMultiple: 1.32,
    });
  });

  L.pageBadge(slide, theme, 13);
}

module.exports = { createSlide: createSlide };
