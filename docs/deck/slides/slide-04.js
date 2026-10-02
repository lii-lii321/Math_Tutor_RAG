/** Slide 04 -- Project overview: layered architecture + scale metrics */
const L = require('./_lib.js');

const LAYERS = [
  ['frontend/', 'Streamlit 界面层', '9 个页面 + 公共组件', '16294A'],
  ['api/', 'FastAPI 网关', 'JWT 认证 / RBAC / 限流', '1E3A5F'],
  ['backend/services/', '应用服务层', 'QuestionService 七领域 Mixin + Agent + Job', '2C5A92'],
  ['backend/repositories/', '数据访问层', '用户 / 错题 / 统计', '3E7BD6'],
  ['backend/models/', 'ORM 与契约', 'SQLAlchemy 2.0 + Pydantic Schema', '7FA8E8'],
];

const METRICS = [
  ['358', 'pytest 用例'],
  ['79%', '覆盖率 (无门禁)'],
  ['147', 'Git 提交'],
  ['12', 'Alembic 迁移'],
  ['13', 'Agent 工具'],
  ['4', 'CI job'],
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  PROJECT');
  L.slideTitle(slide, theme, '项目速览', '分层清晰, 测试扎实 -- 问题不在架构, 而在界面层');

  // Layer stack
  LAYERS.forEach(function (ly, i) {
    const y = 1.5 + i * 0.72;
    slide.addShape('rect', {
      x: 0.5, y: y, w: 5.3, h: 0.62,
      fill: { color: theme.light }, line: { color: L.LINE, width: 0.75 },
    });
    slide.addShape('rect', { x: 0.5, y: y, w: 0.07, h: 0.62, fill: { color: ly[3] }, line: { width: 0 } });
    slide.addText(ly[0], {
      x: 0.72, y: y + 0.08, w: 2.05, h: 0.24, margin: 0,
      fontSize: 10.5, bold: true, color: theme.primary, fontFace: 'Arial',
    });
    slide.addText(ly[1], {
      x: 0.72, y: y + 0.3, w: 2.05, h: 0.24, margin: 0,
      fontSize: 9.5, color: theme.secondary, fontFace: L.CN,
    });
    slide.addText(ly[2], {
      x: 2.85, y: y, w: 2.85, h: 0.62, margin: 0,
      fontSize: 10, color: L.INK, fontFace: L.CN, valign: 'middle',
    });
  });

  slide.addText('数据层: SQLAlchemy ORM + ChromaDB 向量库 + 本地图片存储 + 可选 Redis 队列', {
    x: 0.5, y: 5.12, w: 5.3, h: 0.26, margin: 0,
    fontSize: 9.5, color: L.MUTED, fontFace: L.CN,
  });

  // Metrics grid
  METRICS.forEach(function (m, i) {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 6.15 + col * 1.15;
    const y = 1.5 + row * 1.28;
    slide.addText(m[0], {
      x: x, y: y, w: 1.1, h: 0.56, margin: 0,
      fontSize: 26, bold: true, color: theme.primary, fontFace: 'Arial', valign: 'middle',
    });
    slide.addText(m[1], {
      x: x, y: y + 0.56, w: 1.1, h: 0.4, margin: 0,
      fontSize: 9, color: theme.secondary, fontFace: L.CN, lineSpacingMultiple: 1.15,
    });
  });

  // Note card
  L.card(slide, theme, 6.05, 4.12, 3.15, 1.24, 'FFFFFF');
  slide.addShape('rect', { x: 6.05, y: 4.12, w: 3.15, h: 0.06, fill: { color: L.SHAKY }, line: { width: 0 } });
  slide.addText('一个需要先对齐的事实', {
    x: 6.25, y: 4.28, w: 2.8, h: 0.24, margin: 0,
    fontSize: 10.5, bold: true, color: L.SHAKY, fontFace: L.CN,
  });
  slide.addText('README 声称覆盖率约 90%, 实测 79% 且无门禁. 前端层零单测, 仅靠 5 条 E2E 冒烟.', {
    x: 6.25, y: 4.54, w: 2.8, h: 0.74, margin: 0,
    fontSize: 9.5, color: L.INK, fontFace: L.CN, lineSpacingMultiple: 1.3,
  });

  L.pageBadge(slide, theme, 4);
}

module.exports = { createSlide: createSlide };
