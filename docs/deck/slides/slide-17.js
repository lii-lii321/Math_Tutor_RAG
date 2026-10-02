/** Slide 17 -- Mockup: dashboard */
const M = require('./_mock.js');

function createSlide(pres, theme) {
  M.mockSlide(pres, theme, {
    kicker: '03  MOCKUP 01',
    title: '学情看板: 把数据变成决策',
    sub: '第一屏直接回答"今天该做什么", 其余图表收进折叠区',
    img: 'assets/mock-dashboard.png',
    changes: [
      ['欢迎横幅 + 4 张统计卡 + 4 个操作按钮 = 8 个等权重盒子', '今日行动卡: 主线一句话 + 可点的开始按钮 + 4 个内联 KPI'],
      ['六个 Plotly 图表同尺寸同位置纵向堆叠', 'metric 条 (一行五个数字) + 2 个主图, 其余进 <details> 折叠'],
      ['薄弱知识点只给百分比和一条橙条', '加掌握度总览色环, 薄弱 Top 3 带题量并可直接跳错题本'],
      ['点图表色条才能进错题本', '今日复习队列: 每题带缩略图和推荐理由, 逾期/到期/星标分色'],
    ],
    foot: '后端数据已够用 -- stats 已返回 due / weak_tags / streak / mastered, 重排不需改契约',
  }, 17);
}

module.exports = { createSlide: createSlide };
