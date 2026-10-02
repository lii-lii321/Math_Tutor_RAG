/** Slide 07 -- P0-1: no error boundary, raw traceback on screen */
const L = require('./_lib.js');

const BARE = [
  ['graph.py:34 / :40', 'list_questions + dashboard_stats 全量拉取, 无 try 无 spinner'],
  ['mastery.py:57', 'mastery_profile 裸调用'],
  ['assistant.py:59', 'list_for_user 裸调用'],
  ['auth.py:57 / :90', '登录与注册裸调用, DB 挂掉直接打登录页'],
  ['review.py:41/45/102/182/225', '队列/快照/评分/历史共 5 处裸调用'],
  ['settings.py:79/171/184/206/215', '向量库可用性 / 标签删除 / 数据体检 6 处裸调用'],
  ['students.py:223', '每学生一次 list_questions, 40 人 = 40 次全表查询'],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  P0-1');
  L.slideTitle(slide, theme, '异常没有边界, traceback 直接打屏', '仓库里已有 review.png 记录了这次事故');

  // Evidence image
  slide.addShape('rect', {
    x: 5.25, y: 1.42, w: 3.95, h: 2.83,
    fill: { color: theme.light }, line: { color: L.LINE, width: 0.75 }, shadow: L.shadow(),
  });
  slide.addImage({ path: '../screenshots/review.png', x: 5.34, y: 1.51, w: 3.77, h: 2.65 });
  slide.addText('docs/screenshots/review.png -- 用户实际看到的画面', {
    x: 5.25, y: 4.3, w: 3.95, h: 0.22, margin: 0,
    fontSize: 8.5, color: L.MUTED, fontFace: L.CN, align: 'center',
  });

  // Root cause
  slide.addShape('roundRect', {
    x: 5.25, y: 4.62, w: 3.95, h: 0.72, rectRadius: 0.05,
    fill: { color: L.WEAK_BG }, line: { color: L.WEAK_LN, width: 0.75 },
  });
  slide.addText('根因', {
    x: 5.4, y: 4.72, w: 0.5, h: 0.2, margin: 0,
    fontSize: 9, bold: true, color: L.WEAK, fontFace: L.CN,
  });
  slide.addText('frontend/pages/review.py:101  st.image(question.image_path) 无 os.path.exists 检查, 也无 try 包裹', {
    x: 5.4, y: 4.92, w: 3.7, h: 0.36, margin: 0,
    fontSize: 8.5, color: L.INK, fontFace: 'Arial', lineSpacingMultiple: 1.2,
  });

  // Bare call list
  slide.addText('同一种模式遍布 7 个页面 -- service 调用没有安全包装', {
    x: 0.5, y: 1.42, w: 4.7, h: 0.26, margin: 0,
    fontSize: 11, bold: true, color: theme.primary, fontFace: L.CN,
  });

  BARE.forEach(function (b, i) {
    const y = 1.76 + i * 0.44;
    slide.addShape('rect', {
      x: 0.5, y: y, w: 4.7, h: 0.38,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.6 },
    });
    slide.addShape('rect', { x: 0.5, y: y, w: 0.05, h: 0.38, fill: { color: L.WEAK }, line: { width: 0 } });
    slide.addText(b[0], {
      x: 0.66, y: y, w: 1.62, h: 0.38, margin: 0,
      fontSize: 7.5, bold: true, color: L.WEAK, fontFace: 'Arial', valign: 'middle',
    });
    slide.addText(b[1], {
      x: 2.32, y: y, w: 2.8, h: 0.38, margin: 0,
      fontSize: 7.8, color: L.INK, fontFace: L.CN, valign: 'middle', lineSpacingMultiple: 1.1,
    });
  });

  // Fix proposal
  slide.addShape('roundRect', {
    x: 0.5, y: 4.9, w: 4.7, h: 0.44, rectRadius: 0.05,
    fill: { color: L.GOOD_BG }, line: { color: L.GOOD_LN, width: 0.75 },
  });
  slide.addText('第一批修复: 加一个 safe_call() 包装层 + 统一的 error_card 降级组件', {
    x: 0.66, y: 4.9, w: 4.4, h: 0.44, margin: 0,
    fontSize: 9, bold: true, color: L.GOOD, fontFace: L.CN, valign: 'middle',
  });

  L.pageBadge(slide, theme, 7);
}

module.exports = { createSlide: createSlide };
