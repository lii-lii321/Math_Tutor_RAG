/** Slide 19 -- Mockup: review */
const M = require('./_mock.js');

function createSlide(pres, theme) {
  M.mockSlide(pres, theme, {
    kicker: '03  MOCKUP 03',
    title: '今日复习: 专注模式 + 优雅降级',
    sub: '这是 P0 事故的现场 -- 这一页的改动优先级最高',
    img: 'assets/mock-review.png',
    changes: [
      ['图片读取失败时整个 traceback 渲染到闪卡上', 'error_card 降级: 切到 OCR 文本继续复习, 附折叠的原始异常供排查'],
      ['顶部只有一个孤零零的数字 18', '进度条 + 本轮已评计数, 3 / 18 的位置感明确'],
      ['评分按钮只有表情和文字, 决策成本高', '每个按钮直接预告下次复习时间: 明天 / 2 天后 / 6 天后 / 16 天后'],
      ['未 reveal 时评分区整块塌陷, 翻页时页面高度剧烈跳动', '按钮区位置固定, 图与解析区切换高度'],
      ['进度条首题显示 0%, 与旁边的 1 / N 自相矛盾', '进度按已完成数计算, 首题即为 1/N'],
    ],
    foot: 'SM-2 的 next_schedule 后端已经存在, 评分预览只是把它提到渲染层 -- 不需要新接口',
  }, 19);
}

module.exports = { createSlide: createSlide };
