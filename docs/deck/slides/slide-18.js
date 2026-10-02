/** Slide 18 -- Mockup: notebook */
const M = require('./_mock.js');

function createSlide(pres, theme) {
  M.mockSlide(pres, theme, {
    kicker: '03  MOCKUP 02',
    title: '错题本: 让列表本身可扫读',
    sub: '筛选收进工具条, 题目用缩略图卡片, 信息分四层',
    img: 'assets/mock-notebook.png',
    changes: [
      ['5 个 toggle + 2 个下拉 + 搜索框常驻, 占首屏约 60%', '一行工具条: 搜索 + 视图切换 + 筛选抽屉 + 更多菜单'],
      ['当前生效的筛选条件看不出来', 'chip 回显: 语义搜索 x  仅看待复习 x  难度:中等 x  + 添加筛选'],
      ['expander 标题一行塞 7 类信息, 无缩略图', '三列卡片: 缩略图 / 标签 / 掌握度色环 / 到期状态, 四层分离'],
      ['导出三个大按钮占满一行 (低频操作)', '收进工具条右侧 ... 菜单; 批量操作改为常驻底部操作条'],
      ['分页器在列表上方, 视线要来回跳', '分页移到列表下方, 并显示命中数量与每页条数'],
    ],
    foot: 'Streamlit 的 st.image 无法 hover 出操作层, 勾选框需另想办法 -- 这是该页最大的落地约束',
  }, 18);
}

module.exports = { createSlide: createSlide };
