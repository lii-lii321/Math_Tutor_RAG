/** Slide 20 -- Mockup: tutor */
const M = require('./_mock.js');

function createSlide(pres, theme, ) {
  M.mockSlide(pres, theme, {
    kicker: '03  MOCKUP 04',
    title: 'AI 录题: 让主入口值得更多视觉权重',
    sub: '这是用户使用频次最高的动作, 现在却是一个 40px 的原生控件',
    img: 'assets/mock-tutor.png',
    changes: [
      ['上传控件是 40px 高的原生 file_uploader', '大面积拖拽区, 明确写清格式与大小限制'],
      ['解析结果是一整块 Markdown', '五段结构化结果卡: 考点 / 讲解 / 答案 / 易错 / 举一反三'],
      ['解析中只在局部重建, 刷新或切页结果全丢', '逐题状态缩略图: 已解析 / 解析中 62%, 进度可见可恢复'],
      ['tutor.py:205 的 st.image 没有 exists 检查', '解析结果原图同样走 error_card 降级'],
      ['三个 tab 下大片留白', '左右两栏: 上传与选项在左, 状态与结果在右, 屏幕利用率翻倍'],
    ],
    foot: '解析结果本就是固定的五段结构, 拆成卡片不需要改后端 schema',
  }, 20);
}

module.exports = { createSlide: createSlide };
