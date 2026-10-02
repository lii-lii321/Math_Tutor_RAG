/** Slide 05 -- Capability panorama (3x2 card grid) */
const L = require('./_lib.js');

const MODULES = [
  {
    no: '01', title: 'AI 录题', tone: 'brand',
    items: ['多提供商抽象: SiliconFlow / 通义 / GLM / DeepSeek / Ollama / Gemini', 'Pydantic Schema 约束结构化输出, 三级兜底解析', '拍照 + 批量上传 + Word 导入 (确定性门禁优先, 100 题上限)', 'SHA-256 图片去重, 命中跳过 AI'],
  },
  {
    no: '02', title: '复习调度', tone: 'brand',
    items: ['SM-2 间隔重复 (Anki 同源), ease 下限 1.3', '知识点掌握度引擎: 复习日志时间加权 + 遗忘衰减', '今日计划 = SM-2 到期 + 薄弱补位', '已归档题 (reps>=3 且间隔>=21 天) 不入池'],
  },
  {
    no: '03', title: '检索与 RAG', tone: 'brand',
    items: ['关键词下推 + 向量深候选池 -> RRF(k=60) 融合', '批量 Hydrate 防 N+1, 末端分页不丢题', '举一反三: 解析自动嵌入并召回相似历史错题', '向量库三处降级关键词, 离线评测 Recall/MRR/NDCG'],
  },
  {
    no: '04', title: '学情分析', tone: 'good',
    items: ['90 天热力图 / 正确率趋势 / 掌握度成长曲线', '薄弱知识点排行与雷达图', '知识图谱: 标签共现力导向, 节点着色=掌握度', '周报聚合 + 环比 + Markdown/Word 导出'],
  },
  {
    no: '05', title: 'AI 助手 / Agent', tone: 'good',
    items: ['13 工具 Tool-use Agent, 最多 8 轮自主编排', 'SSE 流式打字机 + 对话持久化与跨端续聊', 'MCP Server 可被 Claude Desktop / Cursor 调用', '无 Key 时本地规则应答, 流程不中断'],
  },
  {
    no: '06', title: '家校闭环 + 工程化', tone: 'good',
    items: ['班级多租户: 建班后检索收紧为本班', '教师批注 + 未读红点 (以批注 ID 为水位线)', 'services / repositories / models 分层', '4 job CI: lint / 版本矩阵 / 冒烟 / Docker'],
  },
];

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, '01  PRODUCT');
  L.slideTitle(slide, theme, '产品能力全景', '功能已经很完整 -- 这正是界面承压的原因');

  MODULES.forEach(function (m, i) {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.5 + col * 2.95;
    const y = 1.48 + row * 1.92;

    L.card(slide, theme, x, y, 2.75, 1.76);
    slide.addShape('rect', { x: x, y: y, w: 2.75, h: 0.05, fill: { color: theme.accent }, line: { width: 0 } });

    slide.addText(m.no, {
      x: x + 0.18, y: y + 0.14, w: 0.4, h: 0.26, margin: 0,
      fontSize: 13, bold: true, color: theme.accent, fontFace: 'Arial',
    });
    slide.addText(m.title, {
      x: x + 0.58, y: y + 0.13, w: 2.1, h: 0.28, margin: 0,
      fontSize: 13.5, bold: true, color: theme.primary, fontFace: L.CN,
    });

    m.items.forEach(function (t, j) {
      const yy = y + 0.48 + j * 0.3;
      slide.addShape('rect', { x: x + 0.2, y: yy + 0.07, w: 0.05, h: 0.05, fill: { color: L.MUTED } });
      slide.addText(t, {
        x: x + 0.33, y: yy - 0.02, w: 2.26, h: 0.3, margin: 0,
        fontSize: 8.2, color: L.INK, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.2,
      });
    });
  });

  L.pageBadge(slide, theme, 5);
}

module.exports = { createSlide: createSlide };
