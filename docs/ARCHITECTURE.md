# 架构决策说明 (Architecture Notes)

本文记录重构与迭代中的关键技术决策，便于面试交流与后续演进。

## 0. 服务组合（v2.2）

`QuestionService` 曾是 662 行的单类，已按领域拆分为 Mixin 组合（`question_mixins.py`）：
`EntryMixin`（录入）/ `QueryMixin`（检索）/ `EditTagMixin`（编辑与标签）/ `ReviewMixin`（复习与追问）/ `BackupMixin`（备份导出）/ `StatsMixin`(统计) + `CoreMixin`（会话/配置/索引等基础设施）。
公共 API 不变，调用方零改动。

## 1. 总体分层

```
frontend (Streamlit views)
      │  只依赖
      ▼
services (应用服务层：QuestionService / AuthService / ReviewScheduler ...)
      │  通过
      ▼
repositories (数据访问层，SQLAlchemy ORM)
      │
      ▼
SQLite / MySQL / PostgreSQL  +  ChromaDB  +  文件存储
```

- **界面层零业务逻辑**：页面组件只做交互编排，所有写入/检索/调度都走服务层。可复用展示组件集中在 `frontend/components.py`（详情视图 / 重测 / 变式入库 / 命中高亮），文案集中在 `frontend/i18n.py`。
- **session-per-operation**：`QuestionService` 每个公开方法内部开短事务。Streamlit 的执行模型是「脚本反复重跑 + 多线程渲染」，持有长事务既容易跨请求泄漏又会出现 SQLite 写锁竞争。
- **依赖注入点**：`QuestionService(session_factory=...)` 接受会话工厂注入，测试可直接替换。

## 2. AI 提供商抽象

`BaseAIProvider` 定义唯一接口 `analyze_question(image, mime, hint) -> QuestionAnalysis`：

| 实现 | 适用 |
|---|---|
| `OpenAICompatProvider` | SiliconFlow / 通义 / GLM / DeepSeek / OpenAI / Ollama —— 国内生态主流接入方式 |
| `GeminiProvider` | Google Gemini（新一代 `google-genai` SDK） |
| `MockProvider` | 无 Key 演示模式，评审克隆即可跑通全链路 |

**结构化输出**：提示词要求严格 JSON；`parse_analysis` 兼容纯 JSON / ```json 围栏 / 前后夹杂说明文字三种形态，解析结果经 `QuestionAnalysis`（Pydantic）校验；失败按 `AI_MAX_RETRIES` 重试。选择「提示词 + 稳健解析」而非 JSON Schema 强约束，是因为兼容层覆盖的第三方服务商对 `response_format=json_schema` 支持参差。

## 3. RAG 设计

- **嵌入策略**：配置了远程嵌入接口（如 BGE-M3）则用之；否则用 ChromaDB 内置本地 ONNX 模型，保持零外部依赖、离线可用。
- **三个消费场景**：① 录题后相似题召回（举一反三）；② 错题本语义搜索与关键词检索双路合并去重；③（隐式）标签/考点文本参与嵌入，提升召回相关性。
- **降级策略**：向量库初始化/读写任何异常 → 记日志并降级为关键词检索，主流程永不阻断（`is_available()` 供设置页展示运行状态）。
- **一致性**：错题编辑后同步 `upsert` 向量；删除错题同步删除向量。

## 3.5 追问讲题（多轮对话）

`BaseAIProvider.answer_followup(context, history, question)` 围绕一道已解析错题构建消息序列：
`system（讲师人设 + 题目背景）→ 最近 12 条历史 → 当前问题`。截断历史防止 token 超限；
服务层先校验题目归属（`get_owned`）再发起对话；对话历史按题隔离存于 `st.session_state`。

## 4. SM-2 复习调度

- `grade ∈ {again, hard, good, easy}` 映射经典质量分 `q ∈ {0, 3, 4, 5}`。
- `q < 3`：进度重置（reps=0），`REVIEW_AGAIN_MINUTES`（默认 10 分钟）后重现。
- `q ≥ 3`：reps 1→间隔 1 天，reps 2→6 天，之后 `interval × ease`；ease 按 SM-2 公式演进，下限 1.3。
- 每次复习写入 `review_logs` 明细（grade/quality/前后间隔/ease），是掌握度估算的数据来源。

**掌握度定义**（时间加权，实现见 `backend/services/mastery.py`）：单题掌握度 = 该题复习日志按时间从旧到新的指数加权平均——每次评分先映射分数（`SCORE_BY_GRADE`：again 0.0 / hard 0.6 / good 0.85 / easy 1.0），最近一次权重 1.0、每往前一次权重 × `DECAY`（0.65），加权平均得 0~1 分；从未复习的题记 `UNREVIEWED_SCORE`（0.2）。知识点掌握度 = 其关联题目掌握度的均值，按 0.4 / 0.7 阈值分为薄弱 / 不稳固 / 已掌握三档。

**口径说明（两套并存）**：学情看板的标签掌握度横条与知识图谱着色走的是 `backend/services/stats.py` 的 `_tag_mastery` 轻量启发式（good/easy 占比 × 0.7 + 平均调度间隔归一化 × 0.3，30 天间隔视为充分巩固）；能力画像 / 今日计划 / 错题本薄弱筛选则走上面的时间加权引擎。调度间隔只进入前者，不进入引擎公式——引用时注意区分页面口径。

## 5. 数据与安全

- 默认 SQLite（WAL 模式 + busy timeout 30s，规避 Streamlit 多线程下的 `database is locked`）；`DATABASE_URL` 一键切换 MySQL/PostgreSQL。
- 密码仅存 bcrypt 哈希（rounds 可配）；登录失败固定延迟 1s 抑制枚举。
- 所有入参（注册表单、AI 响应、标签输入）经 Pydantic 校验；SQL 全部参数化。

## 6. 前端选型

保留 Streamlit（数据应用交付效率最高），配合：
- 组件级 MUJI 主题（藏青 #1a365d / 石板灰 #334155 / 蓝 #2563eb，禁紫、无炫技动效）；
- 图表用 Plotly（JS 随包分发，离线可用；弃用 streamlit-echarts 0.7 与新版 Streamlit 组件框架不兼容）；
- 侧边栏菜单用 streamlit-antd-components（仅保留稳定的 v1 组件用法）。

## 7. 工程化

- pytest：认证 / 仓储 / SM-2 / AI 解析 / RAG / 统计 / 导出 / API 网关全覆盖；测试环境通过环境变量指向临时 SQLite。
- CI：ruff → pytest（3.10/3.11/3.12）→ Docker 构建。
- Docker：`python:3.11-slim`，`/app/data` 卷持久化 SQLite + 图片 + 向量库；healthcheck 打到 `/_stcore/health`；`api` 服务以 uvicorn 提供 REST API。

## 8. FastAPI 网关（v2.1）

**动机**：Streamlit 界面与 API 共享同一套 backend 服务层，Web / 小程序 / 脚本多端复用，也便于日后前后端分离。

- **认证**：PyJWT 签发 Bearer 令牌（`AUTH_SECRET` ≥ 32 字节）；`HTTPBearer` 依赖注入解析，用户不存在/令牌过期统一 401。v2.1 时为单令牌（默认 7 天有效），v2.7 起升级为双令牌（access 默认 30 分钟 + refresh 默认 7 天，见 §11），此处 7 天不再是现行默认。
- **资源**：`api/routers/` 下共 10 个路由模块，由 `api/main.py` 统一注册——
  `auth`（注册 / 登录 / 双令牌刷新）、`questions`（列表与语义搜索、multipart 图片解析、文本录入、异步解析、JSON/CSV/DOCX 导出与导入、详情 / 编辑 / 删除、相似题召回）、`review`（到期 / 评分 / 追问 / 掌握度画像 / 今日计划 / 历史）、`stats`（看板、学生总览、标签共现图、观测摘要）、`tags`（标签列表 / 重命名 / 删除）、`comments`（错题批注增删查，挂在 `/api/questions/{id}/comments` 下）、`classes`（班级与成员管理）、`agent`（AI Tutor SSE 流式对话）、`conversations`（对话持久化 / 恢复 / SSE 追问）、`jobs`（异步任务状态查询 / 取消）。
- **复用而非复制**：路由只做参数校验与状态码转换，业务全部委托 `QuestionService` / `AuthService`，与界面层完全同源。
- **边界**：图片类型/大小白名单校验（MIME + 10MB）；跨用户访问返回 404（不泄露存在性）；OpenAPI 文档由 FastAPI 自动生成。

## 9. 知识图谱（v2.1）

标签共现网络：节点=标签（大小=错题数），边=两标签同题共现（粗细=次数），streamlit-agraph 力导向布局（JS 随包分发，离线可用）。
数据口径与 API `/api/stats/tag-graph` 一致：按用户错题集合统计 `C(tags, 2)` 组合计数，Top 15 标签入图。

## 10. 更多迭代（v2.2）

- **键盘快捷键**：Streamlit 无原生热键，通过同源组件 iframe 向父文档注册 keydown（每次重渲染重绑，幂等），按按钮文本点击。空格=显示解析、1-4=评分。
- **OCR 可选层**：`ocr.py` 惰性加载 RapidOCR；`OCR_ENABLED=false` 或依赖缺失时安全返回空串。识别文本存 `questions.ocr_text`（Alembic 迁移），参与向量嵌入与关键词 LIKE。
- **教师批注**：`comments` 表（级联删除），服务层同查询取齐 username/role 避免跨会话惰性加载；API 挂在 `/api/questions/{id}/comments` 下。
- **PDF 导出**：reportlab + `UnicodeCIDFont("STSong-Light")`——中文 PDF 无需分发字体文件。
- **E2E**：Playwright 冒烟（登录/导航/录题全流程/追问），失败自动截图上传 artifact。录题断言用 `state="attached"`（st.rerun 后折叠面板内容在 DOM 中但隐藏）。菜单标签被 `format_func='title'` title-case（「AI 录题」→「Ai 录题」），E2E 按渲染后文本匹配。
- **检索性能**：标签/关键词过滤下推 SQL（JSON 列 cast 后 LIKE）；引擎级 `json_serializer(ensure_ascii=False)` 使 SQLite 的 JSON 存储可读且可 LIKE 中文。
- **掌握度趋势**：按天回放「截至当日」的错题与复习记录，复用看板同口径的标签掌握度平均，纯计算无新表。

## 11. v2.3 → v2.10 演进要点

- **数学验证**（`backend/services/math_verifier/`）：录题时对 AI 给出的答案做确定性验算——`verify_answer` 依次尝试「代回原方程」（solution_substitution）与「求导互逆」（derivative_inverse）两类 SymPy 验证器，任一 failed 即 failed、任一 verified 即 verified、全部无法判定则 uncertain；结果（状态 / 置信度 / 方法）随题目落库（迁移 `7d967aaa71b5`），给 AI 解析加一道不受幻觉影响的校验闸门。
- **Agent / MCP**（v2.3 引入，v2.5 升级为 AI Tutor）：`backend/services/agent.py` 以 OpenAI function calling 循环（最多 8 轮）让 LLM 自主编排错题本工具；工具经 `AgentTool` 统一暴露 OpenAI 与 MCP 双协议 Schema，`mcp_server.py` 让 Claude Desktop / Cursor 等 MCP 客户端直接调用错题本（现共 13 个工具）；v2.5 起对话落库（`conversations` 两表），支持跨端恢复与 SSE 流式输出。
- **异步解析队列**（v2.3 → v2.6）：v2.3 新增 `/api/questions/analyze/async` 提交即返回 job_id（`jobs` 表落状态）；v2.6 抽象出 `JobQueue` 协议（`backend/jobs/`）——默认 `ThreadedJobQueue`（进程内线程，单实例零依赖），配置 `REDIS_URL` 即切换 `RQJobQueue` + 独立 Worker（`python -m backend.jobs.worker`），支持任务取消，CI 用 fakeredis 全链路验证，队列可选依赖隔离在 `requirements-queue.txt`。
- **双令牌 JWT**（v2.7）：access（默认 30 分钟）+ refresh（默认 7 天）双令牌，`POST /api/auth/refresh` 换发新令牌对（rotation-lite）；令牌携带 `typ` 声明，refresh 不能当 access 用、反之亦然，历史令牌按 access 平滑兼容；配套 `user token_version` 迁移支持令牌吊销。
- **班级多租户**（v2.7，简化形态：单组织、班级即可见性单元）：`classes` / `class_members` 两表（迁移 `55c91901b5d9`）+ `ClassService` 与 5 个管理端点（仅教师可操作，403 兜底）；教师建班后，语义检索范围与学生总览收紧为「自己班级的学生」，未建班教师保持旧的「全部学生」行为，向后兼容。
- **掌握度引擎**（v2.4）：`knowledge_points` 表 + 多对多关联（迁移 `b09bda59c235`）落地规范化知识点模型；`MasteryEngine`（`backend/services/mastery.py`）按复习日志时间加权计算单题 / 知识点掌握度（见 §4），并生成「SM-2 到期优先 + 薄弱知识点加固」的今日计划（条目带推荐理由与优先级）；老数据首次访问自动补建关联，后续版本在其上叠加错题本薄弱筛选与掌握度角标（`mastery_by_question` 复用同一加权公式）与计划模式；学情看板与知识图谱着色的标签级掌握度则走 stats.py 的轻量启发式（见 §4 口径说明）。
- **数据体检**（v2.9，`backend/services/data_health.py`）：一键核对三类真实使用中最常见的数据漂移——向量索引缺失（语义搜索召回不到）、向量索引残留（题目已删索引还在）、孤儿图片文件；支持一键修复（重建缺失索引 + 清理残留 + 可选清理孤儿图片，仅作用于本人数据），配套 `QuestionVectorStore.indexed_ids_for_user()`。

## 12. v2.14 → v2.18 演进要点

- **错题本筛选进 URL 与迁移门控**（v2.14，`frontend/query_state.py`）：11 个 `nb_*` 参数（关键词/标签/排序/视图/语义/四个筛选 toggle/学生/页码）由纯函数编解码（不依赖 streamlit，单测直测），口径为「URL → 实例化前种 session_state → 控件 → on_change 回调写回」，默认值不写 URL、非法值回退默认；生命周期走迁移门控——app.py 记 `_last_page`，仅「离开错题本」那一帧清 URL 参数与控件会话键，首帧不清理（带参 URL 未登录打开 → 登录 → 进错题本筛选仍生效），同页重跑不清理。复习卡片区（进度/题卡/解析/评分/跳过）包 `@st.fragment`，「显示解析」「跳过」只重跑片段，评分保留整页 rerun 保侧边栏徽标准确；全库禁用 `st.rerun(scope="fragment")`（整页上下文调用必抛 StreamlitInvalidLayoutContextError，单测 grep 防回潮）。
- **激励系统与用户级配置**（v2.15，迁移 `7d1e5c49ab02`）：`users.daily_goal` 可空列（NULL 回退 `get_settings().daily_goal`，保留 env 语义）+ `user_milestones` 表（`(user_id, code)` 唯一，每枚里程碑每用户至多一条）；`backend/services/milestone.py` 的 `evaluate` 复用 dashboard_stats 统计（total/mastered/streak）免二次查询，先查已达成集合仅插新增保证幂等；看板渲染时补发新达成 toast（评分当下复习页不弹为既定语义）+ MUJI 徽章墙。
- **完整备份双格式**（v2.16，`backend/services/full_backup.py`）：v1 JSON（题面文字，`export_user_data`/`import_user_data` 与 API 端点契约零改动）与 v2 zip（manifest 全字段 + 原图 + 复习日志）并存；v2 导入直写 ORM 恢复 SM-2 调度状态/星标/笔记/难度（修复 v1 只收 4 字段静默丢进度），图片**按新属主 key 重建**（原 key 内嵌原属主 id `images/u{user_id}/…`，直接复用会与原用户共享存储对象、被孤儿图清理连坐 404），zip slip 防护（拒绝绝对路径/盘符/`..`）、值域逐条跳过计数、image_hash + 内容指纹双重幂等。
- **单语决策与死框架移除**（v2.17）：`frontend/i18n.py` 删除，nav 标签改 zh 字面量（与原 t() zh 输出逐字相同，零用户可见变化）；空状态手写 `.mm-empty` HTML 清零、收敛到 `common.empty_state` 原语；移动端为纯 CSS `@media (max-width: 768px)`（容器/卡片收紧、44px 触控目标），零 Python 布局改动。
- **个人周报复用聚合**（v2.18，`weekly_report.build_for_user`）：窗口计算抽 `_window_bounds` 与班级版 build() 共用（days 夹取 1-31），单行聚合直接复用 `_student_row`/`_weak_tags`（正确率=good+easy 占比、overdue 排除已归档、薄弱标签看板同口径）；`render_markdown_self`/`generate_word_report_self` 无「学生」列、accuracy None →「—」空数据安全；看板惰性生成 + session_state 缓存。
- **完整备份 API 双端点**（v2.19，commit `7642db9`）：`GET /api/questions/export/full`（application/zip + Content-Disposition）与 `POST /api/questions/import/full`（UploadFile，超 100MB 413、非法包 422，返回五计数）——路由注册在 `/{question_id}` 之前防路径参数捕获；此前「暂仅界面入口」的边界就此收口。
- **Anki 牌组导出**（v2.20，`backend/services/anki_export.py` + 硬依赖 genanki>=0.13）：deck_id/model_id 固定随机 int（Anki 端按 id 合并），note guid 取 sha256(content|answer) 指纹（与完整备份 `_fingerprint` 同源，重导出更新原卡不堆积）；正面原图优先经 storage materialize 双后端取路径（缺失回退题面文字），背面解析+答案+标签；错题本导出区第四列惰性生成。

**明确不做**（逐项附理由）：

- **复习评分的 fragment 余量**（队列行/批量操作条）：dashboard 四个跳转按钮（:328 hero / :414 队列行 / :416 全部 / :432 薄弱标签）全为页面跳转、notebook 批量操作后本需全量刷新，无可省重算，包 fragment 无收益（评分卡片区已于 v2.14 完成 0→1）。
- **个人周报 API 端点**：班级版 `/api/classes/{id}/weekly-report` 模式可平移，但当前仅前端自查场景有需求，避免无消费方的接口面（列下批候选）。
- **OpenTelemetry 观测埋点**：现有 AI 遥测 + 结构化日志已覆盖当前排查需求，OTel SDK 侵入面大，保留在路线图。
