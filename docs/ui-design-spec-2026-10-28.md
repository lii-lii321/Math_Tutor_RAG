# MathMaster Edu UI 设计规范 v3（MUJI 克制风 · 令牌单一真源）

> 配套底稿：`data/ui_design/tokens.css`（完整可用的 `:root` / `[data-theme="dark"]` 变量段 + 组件类）。
> 实施员按本规范施工；本文所有行号引用均来自 2026-10-28 对当前代码的实读核对。
> 范围约束：只换样式实现与必要的类名增补；**控件 key、按钮文案、API 行为、既有测试断言的文案一律不动**。

---

## 0. 兼容红线（先读）

| 锁定项 | 依据 | 后果 |
|---|---|---|
| 类名 `mm-badge`、`mm-badge--blue/--warn/--bad/--ok`、`mm-empty` 不得改名/删除 | `tests/test_ui_primitives.py:11-33`（badge() 与 empty_state() 的 HTML 断言） | 改名即红测 |
| 变量 `--weak/--shaky/--good` 不得改名 | `frontend/common.py:80-88` mastery_color() 引用 | 全站掌握度色失效 |
| 变量 `--navy/--slate/--slate-light/--muted/--blue/--blue-soft/--card/--border/--bg` 不得删除 | 页面内联样式引用（`frontend/pages/auth.py:31-42`、`frontend/pages/dashboard.py:279` 等） | 内联样式失去取值 |
| 控件 key（如 `notebook_search`、`hero_start`）、按钮/提示文案 | 任务约束 + 既有测试断言文案 | 不在设计范围 |
| CSS 落地方式：并入 `frontend/assets/style.css`（`load_css()` 内联 `<style>`），**不要用 `@import`** | `frontend/common.py:15-17` | Streamlit 内联样式下相对路径 @import 不可靠 |

---

## 1. 设计原则（定稿五条）

1. **一套卡原语**：`st.container(border=True)` 与 `.mm-card` 是同一张卡，样式只写一份，深色只改变量。
2. **色彩语义单一真源**：状态色只有蓝/绿/琥珀/红四族，CSS 变量是唯一来源；Python 侧通过 `charts.semantic_colors()` 与 `common.mastery_color()` 取值（§7）。
3. **橙退役**：品牌强调 = 蓝且仅蓝。警告 = 琥珀（`--warn ≡ --shaky`），破坏性 = 红，无数据 = 灰。`#e8590c / #ff8a4c / #b45309(作为强调)` 全部退场。
4. **三档大数字 + 六档间距**：`2.6 / 2.0 / 1.5rem`，每屏至多一个 `--num-xl`；分区固定 `1.6rem`（`--space-5`），用留白分层而不是分隔线堆叠。
5. **反馈分级**：空态三档（引导/提示/庆祝）、中性状态用 `.mm-bar` 与 `.mm-chip`，`st.warning` 只留给真正的警告，primary 每视图至多一个。

---

## 2. 色板令牌（浅色 / 深色）

### 2.1 中性面与文字

| 令牌 | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--bg` | `#f8fafc` | `#0f172a` | 页面底 |
| `--card` | `#ffffff` | `#1e293b` | 卡面（旧名，锁定） |
| `--surface-sunken` | `#f1f5f9` | `#172033` | chip 底、行悬停、禁用底 |
| `--border` | `#e2e8f0` | `#334155` | 常规描边（旧名，锁定） |
| `--border-strong` | `#cbd5e1` | `#475569` | 次级按钮/悬停描边 |
| `--track` | `#e2e8f0` | `#334155` | 进度轨道 |
| `--ink` | `#1a365d` | `#f1f5f9` | 标题藏青（深色反白） |
| `--ink-body` | `#334155` | `#e2e8f0` | 正文 |
| `--ink-muted` | `#64748b` | `#94a3b8` | 次要文字/caption |
| `--ink-faint` | `#94a3b8` | `#7c8ba1` | 占位/无数据 |

旧名别名（保留勿删）：`--navy≡--ink`、`--slate≡--ink-body`、`--slate-light≡--ink-muted`、`--muted≡--ink-faint`、`--blue≡--brand`、`--blue-soft≡--brand-soft`。

### 2.2 品牌蓝（唯一行动/强调色）

| 令牌 | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--brand` | `#2563eb` | `#3b82f6` | 行动/链接/焦点/选中 |
| `--brand-strong` | `#1d4ed8` | `#60a5fa` | 文字级蓝/hover |
| `--brand-soft` | `#eff6ff` | `#172554` | 蓝底（选中 chip、头像） |
| `--brand-line` | `#bfdbfe` | `#1e40af` | 蓝描边 |
| `--brand-ring` | `rgba(37,99,235,.20)` | `rgba(59,130,246,.30)` | 焦点环 |

### 2.3 语义状态四族（每族四件套）

| 语义 | 主色 | soft（底） | line（描边） | ink（小字文字） |
|---|---|---|---|---|
| **薄弱/错误** `--weak*` | 浅 `#dc2626` / 深 `#f87171` | `#fef2f2` / `#3f1d1d` | `#fecaca` / `#7f1d1d` | `#b91c1c` / `#fca5a5` |
| **不稳固/警告** `--shaky*`（`--warn` 别名同源） | 浅 `#d97706` / 深 `#fbbf24` | `#fffbeb` / `#3b2f12` | `#fde68a` / `#92400e` | `#b45309` / `#fcd34d` |
| **已掌握/成功** `--good*` | 浅 `#059669` / 深 `#34d399` | `#ecfdf5` / `#0f2e24` | `#a7f3d0` / `#065f46` | `#047857` / `#6ee7b7` |
| **信息** `--info*` | 浅 `#2563eb` / 深 `#93c5fd` | `#eff6ff` / `#172554` | `#bfdbfe` / `#1e40af` | `#1d4ed8` / `#93c5fd` |
| **破坏性** `--bad*` | 与 weak 同红系，语义独立命名 | 同 weak | 同 weak | 同 weak |

**掌握度三档映射（与后端阈值同源，`common.mastery_color` 已是唯一映射，各页必须复用）**：
`mastery < WEAK_THRESHOLD → var(--weak)`；`< SHAKY_THRESHOLD → var(--shaky)`；否则 `var(--good)`。
违规现犯：`frontend/pages/notebook.py:117-123`（shaky=#94a3b8 灰、good=#2563eb 蓝）、`frontend/pages/mastery.py:17`（shaky=#94a3b8 灰）——实施员替换为 `mastery_color()`/变量映射（§8.5、§8.6）。

### 2.4 Hero 行动卡专用（两主题同值，深藏青底不随主题翻面）

| 令牌 | 值 | 用途 |
|---|---|---|
| `--hero-bg / --hero-ink / --hero-muted` | `#132339 / #eef2f7 / #9fb0c9` | hero 底/正文/次要 |
| `--hero-line` | `#24395c` | hero 内轨道/分隔 |
| `--hero-brand` | `#3b82f6` | hero 上蓝（今日目标未达成进度） |
| `--hero-ok` | `#34d399` | hero 上成功（目标达成/达标值） |
| `--hero-warn` | `#fbbf24` | hero 上逾期/警告（**取代 `#ff8a4c`**，`dashboard.py:302`） |

### 2.5 其他

| 令牌 | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `--highlight / --highlight-ink` | `#fef3c7 / #92400e` | `#4d3c14 / #fde68a` | 搜索命中高亮（`frontend/components.py:137` 的替代） |

**语义分工速查**：行动/链接/选中=蓝；成功/已掌握=绿；警告/不稳固/逾期=琥珀；薄弱/错误/破坏=红；无数据=灰。装饰性用色（provider 名、日期、次数计数）一律中性灰徽章，不占用语义色。

---

## 3. 字体与字号

- 字体栈（沿用现状，补 Noto Sans SC 兜底）：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans SC", sans-serif`；代码 `--font-mono: ui-monospace, "Cascadia Mono", Consolas, …`。
- 字重：`400 / 600 / 700`；行高 `--leading-none 1 / --leading-tight 1.25 / --leading-normal 1.6`。

### 3.1 字号阶梯

| 令牌 | 值 | 用途 | 对应元素 |
|---|---|---|---|
| `--text-xs` | 0.75rem | 徽章/图例/页脚 | `.mm-badge`、`.mm-chip` |
| `--text-sm` | 0.85rem | caption/次要/卡内节标题 | `.mm-muted`、`h5` |
| `--text-base` | 1rem | 正文/#### 小节 | `h4`（settings.py 的「#### 外观」等） |
| `--text-lg` | 1.15rem | 问候行/强调句 | `dashboard.py:279` 问候 span |
| `--text-xl` | 1.35rem | **页面标题** | `page_header` 的 h2（`common.py:100-105`） |

标题层级规则（tokens.css 已按选择器落好）：`h2`=页面标题（1.35rem）→ `h3`=小节（`st.subheader`，1.12rem）→ `h4`=卡内节（1rem）→ `h5`=小节标签（0.85rem 灰字，tutor.py:243-279 的 `#####` 全部被收编，Python 不用改）。
违例处理：`students.py:207` 用 page_header(h2) 当小节标题 → 改 `st.subheader`；`dashboard.py:228-231` 与问候行双标题 → **删 page_header，保留问候行**（问候行 1.35rem 即承担页面标题职能）。

### 3.2 大数字三档

| 令牌 | 值 | 使用处 |
|---|---|---|
| `--num-xl` | 2.6rem | 每屏至多一个的签名数字：复习页待复习数（`review.py:56` 的 mm-stat__value 即 2rem 档也可，见 §8.4）；看板侧栏 streak 大数字**删除**（§8.3） |
| `--num-lg` | 2rem | 统计卡 `.mm-stat__value`（原 2.2rem 收敛为 2rem） |
| `--num-md` | 1.5rem | hero KPI `.mm-kpi__value`（原 1.8rem 收敛为 1.5rem） |

---

## 4. 间距 / 圆角 / 阴影 / 动效

### 4.1 间距阶梯

| 令牌 | 值 | 使用规则 |
|---|---|---|
| `--space-1` | 0.25rem | 标签与值之间、徽章内微调 |
| `--space-2` | 0.5rem | 行内元素间、紧凑行内边距 |
| `--space-3` | 0.75rem | 卡内块与块之间 |
| `--space-4` | 1rem | 组件外边距、hr 上下 |
| `--space-5` | **1.6rem** | **分区固定区距**（`.mm-section`） |
| `--space-6` | 2.4rem | 登录页上方等大留白 |

垂直节奏规则：
- 分区间隔只有一种写法：元素加 `.mm-section`（margin-top: 1.6rem）。**禁止 `<br>` 垫高**：`dashboard.py:436`、`notebook.py:475`、`students.py:190/206`、`notebook.py:701` 全部替换。
- `st.divider` 只用于语义断章（保留 `mastery.py:295` 干预区前、`review.py:276` 历史区前；`app.py:155` 侧边栏裸 `<hr>` 走统一 hr 样式，可保留）。

### 4.2 圆角

| 令牌 | 值 | 用途 |
|---|---|---|
| `--radius-sm` | 8px | 缩略图、小控件 |
| `--radius-md` | 10px | 按钮、输入、`.mm-bar` |
| `--radius-lg` | 14px | **所有卡片**（含 st.container(border=True)） |
| `--radius-xl` | 16px | hero、登录大卡 |
| `--radius-full` | 999px | 徽章/pill/进度条 |

### 4.3 阴影与动效

- `--shadow-sm`：卡片常态（极轻）；`--shadow-md`：悬停（`0 6px 20px rgba(26,54,93,.08)`，沿用现值）。
- `--shadow-brand / --shadow-brand-hover`：primary 按钮投影（沿用现值）。
- 动效只有三种：按钮 `translateY(-1px)`（0.12s）、统计卡 `translateY(-2px)`（0.18s）、焦点环 3px。无其他炫技动效。

---

## 5. 组件规范

### 5.1 卡片（一套原语）

tokens.css 中 `.mm-card` 与 `div[data-testid="stVerticalBlockBorderWrapper"]` 共用同一规则（白卡 / `--border` 描边 / 14px 圆角 / `--card-pad` 内边距 / `--shadow-sm`）；`st.container(border=True)` 的全部使用点（mastery.py:102/222/277、students.py:50、tutor.py:242-278、notebook.py:150/261、review.py:79、settings.py:27/77/167/197/241）**无需改 Python** 即自动统一。
- 保留 `height:100%`（错题三列网格等高，原 style.css:285 行为）。
- 悬停浮起只给 `.mm-stat`；普通卡仅 hover 阴影。
- 删除死类：`.mm-welcome`（style.css:87-95 + theme.py:31）、`.mm-flashcard`（style.css:136-143 + theme.py:39；review 实际用 border 容器，review.py:79）、`.mm-hero__btn`（style.css:239-242）、`.mm-card--flat`（style.css:58）、`.mm-mastery__fill--weak`（style.css:133，无引用且颜色错误）。

### 5.2 徽章 / pill / chip（一套系统）

- `.mm-badge` 唯一徽章类，四档语义 tone：`--info`（新语义名）、`--warn`、`--bad`、`--ok`；**`--blue` 保留为 `--info` 的兼容别名**（页面现用名不动）。
- `.mm-badge--lg`：大号档（hero 内/引导空态）。
- `.mm-pill` 系列保留为兼容别名（规则与 badge 完全一致）；实施员把 `dashboard.py:391-399` 的 mm-pill 换成 `mm-badge` + `--bad/--warn/--ok`，换完可从 tokens.css 删别名。
- `.mm-chip` / `.mm-chip--active`：筛选回显 chip，**非交互样式，无 ✕**。`notebook.py:392-393` 的 `mm-badge--blue「xx ✕」` 假按钮 → `.mm-chip`；清除动作继续走独立按钮（notebook.py:414，key/文案不动）。
- 语义纠偏（装饰误用语义色）：
  - `settings.py:92-93` provider 名 → 中性 `.mm-badge`（ok 只表示「健康」，不表示「名称」）；`settings.py:82` 演示模式 warn 保留；`settings.py:101/106` ChromDB 状态 ok/warn 保留。
  - `notebook.py:179` 日期/到期 emoji 徽章 → 中性 `.mm-badge` 或纯文本；未读批注徽章（notebook.py:163-165）保留 `--bad`。
  - `graph.py:109` 次数徽章 → 保留 `--blue`（信息量，合规）。
  - `dashboard.py:180-186` 自绘 `●` 图例 → 用 `.mm-dot` + 语义色变量（与同页分段条一致）。

### 5.3 按钮（primary 纪律）

样式（tokens.css §11）：primary=品牌蓝+投影；secondary/默认=白卡描边、悬停染蓝；全按钮 10px 圆角；移动端 ≥44px（保留原媒体查询）。

| 页面 | primary 归属 | 处理 |
|---|---|---|
| dashboard | `▶ 开始今日复习`（dashboard.py:327） | 保留（现状正确） |
| notebook | **无 primary**（搜索是输入、导出是次级） | 导出四连（notebook.py:477-518）收进一个 `st.popover`，四个 `st.download_button` 全部 secondary；「🗑️ 批量删除」（notebook.py:585）保留 primary——破坏性但已有两步确认（notebook.py:584-590） |
| review | 评分四钮、显示解析、跳过 | 全部 secondary；完成态唯一行动（review.py:217「返回学情看板」/review.py:222「查看能力画像」）保留 primary（该状态下的唯一下一步） |
| mastery | — | `进入复习模式（按今日计划）`（mastery.py:292）改 secondary；干预卡按钮全 secondary |
| auth/settings | 每表单提交键 primary | 保留现状 |
| 侧边栏 | — | 「退出登录」secondary |

### 5.4 表单与焦点

- 焦点统一 3px 品牌环 `--brand-ring`（tokens.css §12）：覆盖 text_input / text_area / number_input / selectbox（baseweb select）/ chat_input / segmented_control / toggle。原 style.css:202-205 只盖了 textInput+textarea，为已修缺口。
- Streamlit 原生控件类名随版本变化，**实施时用 DevTools 核对一次选择器**（重点：`stSegmentedControl`、`stToggle`、`stChatInput`）。

### 5.5 进度条

- 掌握度横条：`.mm-mastery__track/--fill`，轨道 `--track` 6px、填充圆角 full；颜色由调用方传 `mastery_color()` 结果（HTML 内联 `var(--weak)` 等合法）。
- `st.progress`：tokens.css 按 `[data-testid="stProgress"]` 覆盖轨道/填充为 `--track`/`--brand`；**选择器需 DevTools 实测**（Streamlit 版本差异）。

### 5.6 Hero 行动卡（dashboard）

- 结构沿用 `mm-hero/__title/__sub/__kpi-row/__segbar`，颜色全部走 `--hero-*`（§2.4）。
- hero 内联硬编码替换点（`dashboard.py:295-326`）：`#ff8a4c`→`var(--hero-warn)`；`#34d399`→`var(--hero-ok)`；`#9fb0c9`→`var(--hero-muted)`；轨道 `#24395c`→`var(--hero-line)`；填充 `#3b82f6/#059669`→`var(--hero-brand)/var(--hero-ok)`。

### 5.7 空态与反馈（三档）

| 档 | 形态 | 使用场景 | 现犯修正 |
|---|---|---|---|
| 引导型 | `empty_state()`：图标+一句话+主按钮 | 页面级空数据（有明确下一步） | 保留 mastery.py:213、notebook.py:521 |
| 提示型 | `st.caption` 或 `.mm-empty--inline`（一行灰字） | 无下一步的空白区 | `dashboard.py:107/136/148/193/434/512`、`graph.py:100` 等已是 caption 的保持；`dashboard.py:385`、`tutor.py:75`、`students.py:165/170/176` 的 `st.info` 改 caption/引导型 |
| 庆祝型 | `st.success`（+可配 `st.balloons`） | 队列清空/全部完成/已保存 | 保留 review.py:204-207、221/225、mastery.py:273 |
| （中性） | `.mm-bar` / `.mm-chip` | 上下文提示，非空态非警告 | `notebook.py:580`「已选中 N 题」`st.warning` → `.mm-bar` |

- `st.warning` 仅真警告（notebook.py:589 删除确认、components.py:101 验证未通过——保留）。
- 文案截断：`notebook.py:403`（[:38] 包 `**…**`）与 `review.py:92/95`（[:220]）会腰斩 Markdown/LaTeX → 改用 `.mm-clamp-2/.mm-clamp-3` 包裹**完整** markdown，CSS 行数截断（提示文案不变）。

### 5.8 行基线（列表/队列）

- `.mm-queue-row`（复活原语）：`padding 0.55rem .5rem` + 底部 1px 分隔 + 悬停 `--surface-sunken`。使用点：dashboard 队列（dashboard.py:400-414）、mastery 今日计划行（mastery.py:277-291）、mastery 知识点行（mastery.py:222-260，此三处把 `st.columns(...)` 外包一层 `st.markdown` 类容器或给容器加类）。
- 多列行全部加 `vertical_alignment="center"`（Python 参数，实施员补），列内混排粗体 markdown 与 caption 的基线差由该参数收敛。

### 5.9 侧边栏

- 品牌块：`app.py:85-93` 的内联 `color:#1a365d`（深色侧边栏上不可读）→ 换 `.mm-brand/.mm-brand__title`（`var(--ink)`，深色自动反白）。
- 导航、全局搜索、用户块结构不动；`.user-avatar` 已变量化。

---

## 6. 深色模式机制

### 6.1 切换实现（theme.py 改造，实施员落）

现 `frontend/theme.py:10-45` 的 `_DARK_CSS`（变量重定义+逐组件覆盖）**整体删除**，改为只切属性（模式同 `common.keyboard_shortcuts` 的父文档注入，每帧重跑幂等）：

```python
from streamlit.components.v1 import html as _components_html

_DARK_JS = ("<script>var d=window.parent.document.documentElement;"
            "if(d.getAttribute('data-theme')!=='dark')d.setAttribute('data-theme','dark');</script>")
_LIGHT_JS = ("<script>var d=window.parent.document.documentElement;"
            "if(d.getAttribute('data-theme'))d.removeAttribute('data-theme');</script>")

def apply_theme() -> None:
    _components_html(_DARK_JS if st.session_state.get("dark_mode") else _LIGHT_JS, height=0)
```

`tokens.css` 的 `[data-theme="dark"]` 段成为唯一深色真源；页面里所有取 `var(--*)` 的内联样式自动翻面。

### 6.2 深色覆盖清单（tokens.css §14 已含）

stApp/侧边栏/标题/h5/hr/输入族/下拉弹层/卡片族（**含 stVerticalBlockBorderWrapper——审计确认的缺口**）/按钮族/页签/聊天/toast/alert/dataframe 边框。

### 6.3 可见性

深色开关保留在设置页（settings.py:29-33）；**建议**在侧边栏底部（app.py `_render_sidebar` 用户块上方）加一个同步 toggle（同一 `st.session_state["dark_mode"]`，注意两处控件需不同 key、同一回调写会话态），解决「多数用户见不到深色」的问题。此项为可选增补，不阻塞其余施工。

### 6.4 已知限制（如实声明）

`.streamlit/config.toml` 仍 `base="light"`：`st.dataframe` 画布（glide-data-grid，canvas 位图）无法纯 CSS 反色，tokens.css 仅加边框融入；st.progress 的 emotion 结构、alert 配色已做覆盖但需在运行中的 8585 实测确认。若未来要彻底原生深色，需在会话级切 config 主题（超出本规范范围）。
**以上深色结论均为代码/CSS 推导 + 本次未实测标注；实施后必须在 8585 用 demo 登录逐页截图核对。**

---

## 7. 图表令牌（Python 侧单源，实施员落）

Plotly 不认 CSS 变量（只吃字面量），HTML 内联样式可用 `var()`。约定：

1. `frontend/charts.py` 新增导出（与 `is_dark()` 同源）：

```python
def semantic_colors() -> dict:
    """语义色/序数色的唯一 Python 来源（Plotly 用；HTML 内联请用 var(--*)）。"""
    if is_dark():
        return {
            "weak": "#f87171", "shaky": "#fbbf24", "good": "#34d399",
            "info": "#93c5fd", "brand": "#3b82f6", "neutral": "#64748b",
            "ink": "#f1f5f9", "grid": "#334155",
            "seq": ["#60a5fa", "#3b82f6", "#1e3a8a"],   # 难度三档：浅→深
        }
    return {
        "weak": "#dc2626", "shaky": "#d97706", "good": "#059669",
        "info": "#2563eb", "brand": "#2563eb", "neutral": "#94a3b8",
        "ink": "#1a365d", "grid": "#e2e8f0",
        "seq": ["#93c5fd", "#2563eb", "#1a365d"],
    }
```

2. 替换映射表（审计指认的字面量全部收编）：

| 位置 | 现值 | 改为 |
|---|---|---|
| `dashboard.py:151` 掌握度环 | `#059669/#d97706/#dc2626` | `semantic_colors()` 的 good/shaky/weak |
| `dashboard.py:51` 难度环 | `#93c5fd/#2563eb/#1a365d` | `seq[0..2]`（easy→浅/medium→中/hard→深） |
| `dashboard.py:196-203` 正确率柱 | `#059669/#3b82f6/#e8590c` | `good`（≥80）/ `info`（≥60）/ **`shaky`（<60，橙退役）**；无数据 `#cbd5e1`→`--border-strong` 对应灰 `#94a3b8` |
| `dashboard.py:302` 逾期 KPI | `#ff8a4c` | `var(--hero-warn)` |
| `dashboard.py:520` 掌握度趋势线 | `#059669` | `good` |
| `dashboard.py:43` `_BLUE` | `#2563eb` | `brand` |
| `mastery.py:17` `_FILL_COLOR` | `#2563eb/#94a3b8/#dc2626` | `{"solid": "var(--brand)", "shaky": "var(--shaky)", "weak": "var(--weak)"}`（HTML 场景） |
| `notebook.py:117-123` `_mastery_parts` | `#dc2626/#94a3b8/#2563eb` | 删除本地映射，改调 `common.mastery_color()`（返回 `var(--*)`，HTML 直用） |
| `graph.py:13-18` 节点色 | 与基准一致 | 改引 `semantic_colors()` 保持单源（值不变） |
| `charts.py:44-48` 热力图色带 | 绿带 | 保留（绿=good 系，合规） |

3. 状态徽章 tone 对应：solid→`mm-badge--info`（原 --blue 类名保留亦可，二者同规则）、shaky→`--warn`、weak→`--bad`（mastery.py:11-15 已是，保留图标 🟦🟨🟥）。

---

## 8. 各页面布局要点

### 8.1 app.py（侧边栏）
品牌标题换 `.mm-brand`（app.py:85-93）；裸 `<hr>`（app.py:155）走统一 hr 样式；可选加深色快捷开关（§6.3）。

### 8.2 auth.py（登录/注册）
新增外层 `<div class="mm-auth">` 包住标题+tabs+特性卡（auth.py:14-47，类名增补允许），max-width 560px 居中，解决「窄标题+通栏表单」断裂（原 `.mm-login` max-width:420px 只包标题）。特性卡保留 `.mm-card`，内联 `var(--navy)/var(--slate-light)` 无需改（已兼容变量）。

### 8.3 dashboard.py（学情看板）
1. 删双标题：去掉 `page_header("学情看板", …)`（dashboard.py:228-231），保留问候行（276-285）。
2. 「连续学习」去重：hero KPI 已含（dashboard.py:305），**删侧栏大数字块**（dashboard.py:334-340），侧栏列只留热力图；`mm-streak__*` 类随删（tokens.css 中有注释标注）。
3. hero 内联色替换（§5.6）。
4. 队例行（400-414）：外层加 `.mm-queue-row`，`st.columns(..., vertical_alignment="center")`；mm-pill → mm-badge 语义 tone。
5. 图例 `●`（180-186）→ `.mm-dot` + `semantic_colors()`；`<br>`（436）→ `.mm-section`。

### 8.4 notebook.py（错题本）
1. `_mastery_parts`（117-123）→ `mastery_color()`。
2. chip 回显（392-393）→ `.mm-chip`（去 ✕）；列表视图掌握度内联色（220）随 mastery_color 自动一致。
3. 「已选中 N 题」（580）→ `.mm-bar`；批量操作四列保持。
4. 导出四连（477-518）收进一个 popover、全 secondary（§5.3）。
5. 卡片网格徽章行（177-181）：收敛为「难度 + 日期」两枚中性 badge，到期 emoji 纯文本；未读徽章保留 `--bad`。
6. 空态（521）保留引导型；`<br>`（475/701）→ `.mm-section`。
7. 详情解析/复习卡截断（403 与 review.py:92/95 同修，§5.7）。

### 8.5 review.py（今日复习）
进度卡（55-61）沿用 `mm-stat--accent`，值字号 `--num-xl`（本页签名数字）；解析截断（92/95）→ `.mm-clamp-3`；评分四钮 secondary、完成态唯一行动 primary（§5.3）；st.divider（276）保留；dataframe（292）深色为已知限制（§6.4）。

### 8.6 mastery.py（能力画像）
`_FILL_COLOR`（17）→ var 映射；行容器（222/277）自动统一卡原语 + `vertical_alignment="center"`；「进入复习模式」（292）改 secondary；success 空态（273）保留；divider（295）保留。

### 8.7 tutor.py（AI 录题）
`#####` 节标题（243-279）由全局 h5 样式收编为小节标签，**Python 不用改**；`st.info` 错因（274）保留（语义正确）。

### 8.8 graph.py（知识图谱）
节点色改引 `semantic_colors()`（值不变）；次数徽章（109）保留 blue；副标题🔴🟡🔵⚪ 文案不动。

### 8.9 students.py（学生总览）
`<br>`（190/206）→ `.mm-section`；`page_header` 当小节标题（207）→ `st.subheader`；stat_card/dataframe 沿用。

### 8.10 settings.py（设置）
provider 名徽章（92-93）改中性；外观卡保留深色开关（caption 文案不动）；`####` 节标题由全局 h4 样式统一。

---

## 9. 死样式清理清单

| 删除 | 位置 | 说明 |
|---|---|---|
| `.mm-welcome` | style.css:87-95、theme.py:31 | 无页面渲染 |
| `.mm-flashcard` | style.css:136-143、theme.py:39 | review 实际用 border 容器（review.py:79） |
| `.mm-hero__btn` | style.css:239-242 | CTA 已是蓝色 st.button（dashboard.py:327） |
| `.mm-card--flat` | style.css:58 | 零使用 |
| `.mm-mastery__fill--weak` | style.css:133 | 零使用且颜色错（琥珀≠薄弱红） |
| theme.py `_DARK_CSS` 全段 | theme.py:10-45 | 迁入 tokens.css `[data-theme=dark]`（§6.1） |
| `.mm-streak__*` | tokens.css（带注释） | 随 dashboard.py:334-340 删除后再删 |
| `.mm-pill` 别名 | tokens.css | dashboard.py:391-399 换成 mm-badge 后再删 |

---

## 10. 实施顺序与验收清单

**顺序**：① tokens.css 并入 style.css（浅色即全站统一）→ ② theme.py 切 `data-theme` → ③ 8585 用 demo 登录逐页深色截图核对（data/ui_shots/ 已有 before_*.png 基线）→ ④ Python 单源化（§7 表 + chip/bar/popover/queue-row 类名增补 + primary 纪律）→ ⑤ 死样式清理。

**验收**：
- [ ] `grep -nE "#[0-9a-fA-F]{6}" frontend/pages/*.py frontend/components.py frontend/common.py` 仅剩 charts.py（Plotly 字面量）与合法内联（应为 0 或仅注释）；`style.css` 内不再有裸 hex（全走变量，hero 段 `#ffffff` 文字除外）。
- [ ] `tests/test_ui_primitives.py` 通过（badge/empty 类名锁定项）。
- [ ] 同一「掌握度」语义在：看板环形图、错题卡掌握度条、画像行、图谱节点、队列 pill 中为同一色（对照 §2.3）。
- [ ] 每屏大数字 ≤ 两档且 `--num-xl` ≤ 1；看板无双标题、无重复 streak。
- [ ] 深色下：border 容器/徽章/chip/高亮/侧边栏标题全部可读（8585 实测截图）；已知限制（dataframe 画布）如实记录。
- [ ] 错题本导出收进单个 popover 且无 primary；「已选中 N 题」为中性条；筛选 chip 无 ✕。

---

## 附：tokens.css 段落索引

| 段 | 内容 |
|---|---|
| §1-2 | `:root` 浅色变量 / `[data-theme="dark"]` 深色变量 |
| §3 | 全局（标题阶梯、hr、mark 高亮、`.mm-section`、滚动条、focus-visible） |
| §4 | 卡片体系（border 容器统一 + mm-card + mm-stat + queue-row + streak 兼容） |
| §5 | 徽章/pill/chip/bar |
| §6 | Hero（含 --hero-* 全套） |
| §7 | 进度（mm-mastery + st.progress 覆盖） |
| §8-10 | 空态 / clamp 截断 / 登录与品牌块 / thumb |
| §11-13 | 按钮 / 表单焦点 / expander+页签+侧边栏 |
| §14 | 深色结构覆盖 |
| §15 | 移动端媒体查询（≤768px，保留既有行为） |
