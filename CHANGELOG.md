# 更新日志 (Changelog)

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [2.13.0] - 2026-10-04

### 新增
- **错题本卡片网格视图**：工具条 📋/🔲 视图切换；3 列缩略卡 = 原图缩略（无图考点占位）
  + 标签/星标/未读徽章 + 难度/复习态/日期 + 掌握度条，「查看」走 st.dialog 弹窗
  （复用四页签详情）；选中复选框跨视图共享状态；列表视图抽为 `_render_list_view`
- **对象存储抽象**（`backend/services/storage.py`）：图片读写经 `StorageBackend` 协议——
  `local`（data_dir 本地盘，默认，与既有数据零迁移）或 `s3`（S3 兼容：MinIO / OSS / COS，
  boto3 可选依赖）；s3 模式展示走预签名 URL、导出/OCR/分享卡经 `materialize_image`
  落地本地缓存；key 与库存 image_path 一一对应，切换仅改 .env
  （`STORAGE_BACKEND=s3` + `S3_ENDPOINT/S3_BUCKET/S3_ACCESS_KEY/S3_SECRET_KEY`）
- s3 模式下数据体检自动跳过本地孤儿图片扫描（附说明）；新测试 `tests/test_storage.py`

### 加固与质量
- **Plotly 主题收敛**：`frontend/charts.py` 单点来源（font/grid/ink/layout/热力图色带），
  dashboard 与能力画像雷达图全部接入；深色模式热力图零值格改卡片色
- **检索金标集持续门禁**（提升路线 #4）：`tests/test_retrieval_quality.py`——12 条
  金标语料（专属用户隔离）双问法进 CI：关键词路 Recall@1 = 100%（确定性）、
  混合路（真实向量检索）Recall@3 ≥ 60% 门禁（实测基线 67%，MiniLM 中文意译
  短板如实记录于 PERFORMANCE.md）、关键词命中在混合路不丢失（阈值语义边界钉子）
- **降级防线测试补齐**（提升路线 #2）：reaper 状态回收 2 用例 + Redis 限流回退
  1 用例（断言确实尝试过 Redis 后回退）；验证器异常不再纯静默——
  record_event 遥测留痕 + warning 日志（提升路线 #3，v2.11 静默失效教训转化为防线）
- **Mimosa 审计 8 项发现全部对账**（`docs/安全审计对账.md`）：5 修复
  （slides 编译脚本去动态 require + 输出边界断言、两示例脚本 BASE 回环校验、
  locust SystemRandom）、2 误报有据、1 有意为之；运行时核心路径零发现
- 测试 353 → 376 全绿（+storage 6 +defense 4 +金标 3 + 图表批零破坏）

## [2.12.0] - 2026-10-01

### 新增（家校闭环批次）
- **教师批注未读红点**：学生错题本顶栏未读横幅 + 列表 🔴N 标记；打开批注区自动清零
  （已读回执 `comment_read_states` 以批注 ID 为水位线，单调比较不受时间戳同秒精度影响；
  仅统计教师所发且题目归属本人的批注，仅在有未读时落库避免写放大）。
  API：`GET /questions/{id}/comments/unread`、`POST /questions/{id}/comments/read`
- **班级周报**：`WeeklyReportService` 按班级聚合窗口期（1~31 天）学情——新增错题/复习次数/
  复习正确率/当前待复习（归档口径与 mastered 同源）+ 薄弱知识点 Top3（看板口径 <50%）；
  Markdown 预览 + Word 一键导出下发家长；API `GET /classes/{id}/weekly-report`（教师专属，
  非本人班级统一 404）。学生总览页新增「📣 班级周报」入口
- 迁移 `2c8cbae11edf`；测试 335 → 353 全绿

## [2.11.0] - 2026-09-29

### 安全与正确性（专家批次 + 数学验证批次）
- **批注 IDOR 修复**：批注列表/写入补归属校验（题目 owner 或教师；其他学生 404 不泄露存在性），
  兑现 ARCHITECTURE 既有契约；跨用户用例补齐
- **JWT 生命周期**：User.token_version + 迁移——改密/登出即吊销全部旧令牌（`POST /api/auth/logout`）；
  AUTH_SECRET 默认值启动告警
- **错误信封**：SSE 不再外泄原始异常（固定文案+日志）、502 消息脱敏、全局 500 处理器
- **导航 P0 修复**：页面注册表抽为 `frontend/nav.py` 单一来源，`go_to("mastery")` 不再抛 StopIteration
- **数学验证引擎三处生产级 bug**（上线以来静默失效，测试全覆盖时暴露）：
  隐式乘法转换从未传入解析器（"2x" 类答案全部解析失败）、导数验证器签名与统一 3 参调用不符
  （TypeError 被静默吞掉、从未运行）、数值验证器集合运算优先级写反（恒返回 None）；
  numeric 兜底接线：化简失败/判不一时数值复核（恒等→uncertain 不误判 failed）；
  新增 22 用例全覆盖五个模块
- **移动端**：AI 录题新增应用内拍摄（camera_input）、复习页题图自适应宽度
- **文档对账**：测试数四处统一（以实际收集数为准）、路线图勾掉已交付项、ARCHITECTURE 补
  v2.3→v2.10 演进与掌握度新公式、新增精简英文 README

## [2.10.0] - 2026-09-29

### 新增
- **错题星标收藏**：详情页一键星标、卡片标题 ⭐ 标识、「⭐ 仅看星标」筛选（SQL 下推，
  语义检索管线末端同步过滤）；`toggle_star` 服务 + 迁移 `7f0da979939c`
- **批量操作增强**：错题本批量改难度 / 批量移除标签（同步清理知识点同名项与向量元数据），
  批量区重排为「删除 / 改难度 / 移除标签 / 追加标签 + 导出独立行」
- **分享卡片重新设计**：浅灰画布浮层卡片（投影 + 圆角）、难度/标签/考点胶囊标签、
  题图自动嵌入、「先想一想，再对答案」分隔语、内容限量截断——适配朋友圈/群聊转发
- **PostgreSQL 兼容验证通过（Batch 09 数据库部分）**：11 版本迁移链 + 收集到 287 个用例的测试套件 +
  API 实机冒烟（注册/建题/检索/画像）全部在 PG 16 上验证；compose 新增 postgres 服务
  （profile 隔离）；测试套件支持 `DATABASE_URL` 外部指向 PG
- **README 界面速览全部换新**：8 张当前 UI 实拍（@2x 高清），覆盖全部核心页面

### 修复（真实用户走查）
- **计划模式评分后丢失**：计划标记入会话态，评分 rerun 不再静默退回到期队列；
  计划清空自动退出；能力画像计划项可直达指定题（游标跳转），看板「开始复习」显式退出计划模式
- **项目搬迁后图片全挂**：DB 中 image_path 为旧绝对路径时给出缺失兜底提示（复习页），
  开发库存量路径一次性改写修复

## [2.9.0] - 2026-09-28

### 新增（运维自愈 + AI 评测）
- **数据体检与修复**（设置页）：一键核对三类真实使用中最常见的数据漂移——
  向量索引缺失（语义搜索召回不到）、向量索引残留（题目已删索引还在）、孤儿图片文件；
  支持一键修复（重建缺失索引 + 清理残留 + 可选清理孤儿图片，仅作用于本人数据）。
  新增 `DataHealthService`（`backend/services/data_health.py`）与
  `QuestionVectorStore.indexed_ids_for_user()`；5 个测试覆盖「漂移注入 → 体检发现 → 修复归零」闭环
- **AI Tutor 评测脚手架**（`scripts/eval_tutor.py`，手册 §十二 AI Evaluation）：
  4 个预置场景（薄弱诊断/今日计划/练习卷/找题）跑真实 function calling 全流程，
  校验工具编排命中，LLM-as-judge 四维评分（正确/工具/可操作/清晰），JSON 报告落
  `data/eval_tutor_report.json`；未配置 Key 时明确退出，评分自评局限性已在脚本头注明

## [2.8.0] - 2026-09-28

### 体验升级（真实用户视角的功能 / 交互 / 界面打磨）
- **错题本掌握度透视**：新增「仅看薄弱」开关（有复习记录且掌握度 <50%）与
  「掌握度最低」排序；每张错题卡标题显示彩色掌握度角标（`mastery_by_question` 服务方法）
- **复习「计划模式」**：能力画像页「进入复习模式」直达按掌握度引擎排好的队列
  （到期题优先 + 薄弱知识点加固），闪卡上显示推荐理由徽章；完成后引导回看画像
- **知识图谱掌握度着色**：节点颜色=标签掌握度（🔴薄弱 🟡不稳固 🔵已掌握 ⚪无数据），
  侧栏新增「薄弱知识群」一键直达错题本
- **单题导出与复制**：错题详情新增「导出本题 Word（详解版）」与「复制/分享」面板
- **老数据自愈回填**：旧版本录入的题目知识点只存在 JSON 列、M2M 关联为空，
  首次访问能力画像时自动补建关联（一次性、幂等），升级用户画像立即生效而非空白
- **能力画像页**：新增薄弱知识点雷达图（取掌握度最低 8 个，MUJI 配色、透明底）；
  每个知识点一行「📝」按钮直达错题本对应筛选；掌握条改用全局 `mm-mastery` 样式类，
  空状态改为居中引导卡
- **教师端班级管理落地 UI**：学生总览页新增「班级管理」面板（建班 / 按用户名加学生 /
  移出 / 删班，全部带 toast 反馈）；总览表与统计卡支持按班级筛选；
  `ClassService.class_student_ids()` 单班成员查询（归属校验）
- **学情看板**：欢迎语按时段变化（早上好/中午好/下午好/晚上好）；
  快捷操作区补第 4 个入口「🎯 今日计划」直达能力画像页
- **复习页**：评分后的下次复习安排改为 `st.toast` 原生通知（替代页面内文字残留）
- **AI 助手页**：空会话时提供 3 个快捷提问按钮（薄弱分析 / 生成练习卷 / 今日安排），
  点击即发送
- **登录页**：三张特性卡改用主题样式类（`mm-card` + CSS 变量），深色模式不再白底突兀；
  第三张卡更新为「掌握度画像」
- **深色模式补齐**：warn/bad/ok 徽标、掌握条文字、闪卡、空状态卡片的暗色覆盖
- **设置页**：新增「关于」区块（版本号与文档指引）

## [2.7.0] - 2026-09-27

### 新增（安全加固 + 多租户，Batch 10）
- **观测摘要**：`GET /api/stats/observability`——AI 调用次数/成功率/平均延迟（遥测 JSONL 汇总）
  + 异步任务失败率（jobs 表统计），对应手册 §十一的可观测性最小闭环
- **双令牌**：access 默认 30 分钟 + refresh 默认 7 天（`REFRESH_TOKEN_EXPIRE_DAYS`）；
  `POST /api/auth/refresh` 换新令牌对（rotation-lite）；令牌携带 `typ` 声明，
  refresh 不能当 access 用、反之亦然；历史令牌按 access 平滑兼容
- **CORS 环境化**：`CORS_ORIGINS` 逗号分隔指定来源，默认 `*`（仅限开发）
- **核心端点请求限流**：滑动窗口计数器（`backend/utils/request_limiter.py`）+
  依赖工厂 `rate_limit(scope)`——agent 对话 10 次/分、AI 录题 20 次/分
  （`RATE_LIMIT_AGENT_PER_MIN` / `RATE_LIMIT_ANALYZE_PER_MIN`，0 关闭），超限 429
- **默认口令治理**：种子口令可用 `SEED_ADMIN_PASSWORD` / `SEED_DEMO_PASSWORD` 覆盖；
  检测到默认口令时启动告警
- **班级多租户**（10.5 简化：单组织，班级即可见性单元）：`classes` / `class_members`
  两张表（迁移 `55c91901b5d9`）+ `ClassService` + `POST/GET /api/classes`、
  `POST /api/classes/{id}/members`、`DELETE .../members/{student_id}`、`DELETE /api/classes/{id}`
  （仅教师，403 兜底）；教师建立班级后，语义检索范围与学生总览收紧为「自己班级的学生」，
  未建班教师保持旧的「全部学生」行为（向后兼容）

## [2.6.0] - 2026-09-27

### 新增（异步任务生产化，Batch 08）
- **JobQueue 后端抽象**（`backend/jobs/`）：`JobQueue` Protocol + 双实现——
  默认 `ThreadedJobQueue`（进程内线程，单实例零依赖）；配置 `REDIS_URL` 切换 `RQJobQueue`
  （任务入 Redis，独立 Worker 消费，Web/Worker 各自横向扩容），可选依赖缺失时告警回退线程
- **任务执行与队列解耦**：`backend/jobs/tasks.py` 模块级任务函数（Worker 按点分路径调用），
  双后端共用同一份执行逻辑；`python -m backend.jobs.worker` 一键拉起 RQ Worker
- **任务取消**：`POST /api/jobs/{id}/cancel`（仅 pending 可取消，409 兜底）+ Worker 取任务时
  二次校验状态的双重取消语义；状态机补齐 `cancelled`
- **离线验证**：fakeredis + RQ `SimpleWorker` burst 模式在 CI 内全链路验证
  （入队 → 消费 → jobs 表落终态 / 已取消任务被跳过），无需真实 Redis；
  `rq/redis/fakeredis` 进 requirements-dev，生产可选依赖单独 `requirements-queue.txt`

## [2.5.0] - 2026-09-27

### 新增（Agent → AI Tutor，Batch 07）
- **对话持久化**：`conversations` / `conversation_messages` 两张表（迁移 `74fbffade73a`）——
  用户/助手原文 + 工具调用审计行（tool_name），支持跨端「继续刚才的学习」；
  对话标题取首条用户消息自动生成；单对话 400 条防御性上限
- **AgentSession 会话绑定**：`AgentSession(user_id, conversation_id=...)` 从服务端历史重建 LLM 上下文
  （仅回放 user/assistant 文本，工具行不进上下文）；`chat` / `chat_stream` 结束后自动落库，
  持久化失败仅告警不影响对话
- **Tutor 工具 +5**（Agent/MCP 共 13 个）：`get_learning_profile`（画像总览）、
  `get_weak_knowledge_points`、`get_recent_mistakes`、`get_review_history`、
  `generate_practice_set`（指定知识点专项卷 / 自适应卷）；系统提示词升级为 AI Tutor 角色
- **对话 API**：`POST/GET /api/conversations`、`GET /api/conversations/{id}/messages`、
  `DELETE /api/conversations/{id}`、`POST /api/conversations/{id}/chat/stream`（SSE + 服务端持久化）
- **AI 助手页**：历史对话选择条（新建/恢复），恢复时从服务端载入消息与 Agent 上下文
- 模型修正：`questions.verification_methods` ORM 与 `7d967aaa71b5` 迁移统一为可空列，
  消除后续 autogenerate 的常驻伪 diff

## [2.4.0] - 2026-09-27

### 新增（知识点掌握度引擎 + 自适应复习）
- **知识点规范化建模**：`knowledge_points` 表（唯一名称、自引用父级）+ `question_knowledge_points` 多对多关联（迁移 `b09bda59c235`）；
  录入（手动 / 拍照 AI）、编辑、标签重命名 / 删除时自动同步关联（get-or-create，幂等）
- **掌握度引擎**（`backend/services/mastery.py`）：单题掌握度 = 复习日志的时间加权平均
  （again 0 / hard 0.6 / good 0.85 / easy 1.0，最近一次权重 1.0、向前按 0.65 衰减，未复习计 0.2）；
  知识点掌握度 = 关联题目均值；三档状态 薄弱 / 不稳固 / 已掌握（0.4 / 0.7 分界）
- **自适应今日计划**：SM-2 到期题优先（逾期越久优先级越高），剩余名额由薄弱知识点加固补齐；
  已掌握归档题（reps≥3 且 interval≥21 天）不进入计划；到期池 SQL 下推（`due_at IS NULL OR due_at <= now`）
- **能力画像前端页**：知识点掌握度横条 + 状态徽标（新增 `mm-badge--bad`）+ 到期计数；
  右栏生成今日计划（可调题数），一键进入复习模式
- **API**：`GET /api/review/mastery`（画像，薄弱排前）、`GET /api/review/today?size=`（计划条目含推荐理由与优先级）
- **Agent 工具 +2**：`get_mastery_profile` / `get_today_review_plan`（Tool-use Agent 与 MCP Server 同步可用，共 8 个工具）

### 修复
- 迁移 `b09bda59c235` 曾被 autogenerate 误 diff 出 `verification_methods/verified_at` 重复 DDL
  （开发库当时缺列所致），全新库升级必炸——已移除，验证列由 `7d967aaa71b5` 唯一负责

## [2.3.0] - 2026-09-15

### 新增（Agent 化）
- **SSE 流式对话**：`POST /api/agent/chat/stream`（text/event-stream）；`AgentSession.chat_stream`
  流式解析增量文本与分片工具调用（按 index 聚合），前端 `st.write_stream` 打字机效果
- **异步录题队列**：`POST /api/questions/analyze/async` 提交即返回 job_id（202），
  后台线程执行，`GET /api/jobs/{id}` 轮询状态/结果；`jobs` 表 + 迁移；队列协议与 Celery 兼容可平滑替换
- **MCP Server**（`mcp_server.py`）：错题本作为 Model Context Protocol 工具服务器，
  Claude Desktop / Cursor 等 MCP 客户端可直接调用（搜索/录题/评分/到期列表/周报/标签统计）。
  接入配置见模块文档；用户通过 `MM_USER_ID` / `MM_USERNAME` 绑定
- **Tool-use 对话 Agent**（`backend/services/agent.py`）：OpenAI function calling 循环
  （最多 8 轮防死循环），LLM 自主编排错题本工具调用；工具执行异常回传 LLM 自纠
- **「AI 助手」前端页**：自然语言驱动错题本；无 Key 时本地规则应答（周报/待复习/搜索三类意图），零配置可体验
- **Agent 工具层**（`backend/services/agent_tools.py`）：`AgentTool`（openai_schema/mcp_schema/`__call__`）统一双协议定义，6 个工具按用户隔离

### 修复
- `semantic_search` 的 `rag_top_k` 配置被默认参数覆盖、chromadb `count(where=)` 兼容性 → 查询重构

## [2.2.0] - 2026-09-13

### 新增
- **键盘快捷键（复习页）**：空格/回车显示解析，1/2/3/4 对应四种评分
- **重复图片去重**：同图重复上传自动复用既有错题（SHA-256 按用户隔离），跳过 AI 调用
- **错题本筛选升级**：仅看待复习 / 仅看已掌握 🏆 开关 + 四种排序（最新/最早/复习次数最少/最近复习）
- **复习页内编辑**：发现解析有误可直接修改（编辑表单抽取为共享组件）
- **OCR 文字层（可选）**：录题时识别原图文字入库（`OCR_ENABLED=true` + `pip install rapidocr-onnxruntime`），原图手写题面可被关键词/语义搜索命中
- **变式题一键入库**：举一反三的变式练习可存为新错题，进入复习循环
- **搜索命中预览**：详情页显示关键词首个命中片段（转义高亮）
- **学生周报（含环比）**：看板横幅展示本周录入/复习/正确率/活跃天数，附上周对比
- **掌握度 30 天趋势曲线**：按天回放历史复习记录计算
- **教师批注**：错题下的留言（`comments` 表 + 迁移 + 服务 + `GET/POST/DELETE /api/questions/{id}/comments`），作者本人或教师可删
- **深色模式**：设置页会话级切换（MUJI 暗色 CSS 覆盖）
- **PDF 导出**：reportlab + 内置 CID 中文字体，题目在前、卷末参考答案
- **CSV 导出（API）**：`GET /api/questions/export/csv`（UTF-8 BOM）
- **限流器接口化**：`RateLimiter` Protocol + `InMemoryRateLimiter` / `RedisRateLimiter`（多实例部署即插即用）
- **PWA**：manifest + 最小 Service Worker（可添加到主屏幕）
- **i18n 框架**：`frontend/i18n.py` 集中文案 + `t()` 回退机制（导航已接入）
- **Sentry 接入点**：配置 `SENTRY_DSN` 即启用（可选依赖）

### 变更
- **QuestionService 拆分**：662 行单类按领域拆为 7 个 Mixin 组合（录入/查询/编辑标签/复习/备份/统计/核心），公共 API 零改动
- **到期查询 SQL 下推**：`due_for_review` 不再全量加载后过滤
- **列表检索 SQL 下推**：标签/关键词过滤下推到 SQL；JSON 列改用非转义 UTF-8 存储（修复中文标签 LIKE 失配）
- **图片落盘压缩**：上传图片自动缩至最长边 1600px 的 JPEG（quality 85）
- **前端迁移**：37 处弃用的 `use_container_width` 全部迁移到 `width` API
- 可复用展示组件集中到 `frontend/components.py`；文案集中到 `frontend/i18n.py`

### 修复
- `rag_top_k` 配置被 `semantic_search` 默认参数永久覆盖
- 插入 Comment 模型时 `Question.is_due` 方法错位导致复习流程崩溃
- 批注列表跨会话惰性加载抛 `DetachedInstanceError`（改为同查询取齐 role）
- 教师看板「待复习/已掌握」混入学生错题的口径问题

### 工程化
- **Playwright E2E 入 CI**：登录/导航/教师页/AI 录题全流程/追问对话 5 条冒烟；失败自动截图上传 artifact——首跑即暴露 `streamlit-agraph` 缺失于 requirements 的打包问题
- Alembic 迁移：baseline / ocr_text / comments 三个迁移 + 空库冒烟测试
- CI 新增 boot-smoke 内 E2E 步骤与前端依赖版本诊断输出

## [2.1.0] - 2026-09-08 ~ 2026-09-13

### 新增
- **登录失败限流**：同一用户名 5 分钟内失败 5 次后临时锁定（进程内实现，多实例部署可换 Redis）
- **FastAPI 网关**（`api/`）：REST API 与 Streamlit 共享同一套 backend 服务层
  - JWT 认证（PyJWT，`AUTH_SECRET` 配置，默认 7 天有效）
  - `POST /api/auth/login | register`
  - `GET/POST /api/questions`（列表语义搜索 / multipart 图片 AI 解析 / 文本手动录入）
  - `GET/PATCH/DELETE /api/questions/{id}`、`GET /api/questions/{id}/similar`
  - `GET /api/questions/export`、`POST /api/questions/import`（JSON 备份）
  - `GET /api/review/due`、`POST /api/review/{id}/grade`、`POST /api/review/{id}/followup`
  - `GET /api/stats/dashboard`、`GET /api/stats/tag-graph`
  - OpenAPI 文档自动生成（`/docs`）；docker-compose 新增 `api` 服务
- **知识图谱页**：错题标签共现力导向图（streamlit-agraph，离线可用），附最强关联知识点对排行
- **手动录入**：AI 录题页新增「手动录入」Tab，文本题目同样入库并参与向量检索
- **数据备份**：设置页与 API 支持错题 JSON 导出/导入（服务层逐条校验，空内容自动跳过）
- **学生总览（教师专属）**：全班错题量/待复习/复习进度/平均掌握度/最近活跃汇总表 + 逐个学生的知识点分布；API `GET /api/stats/students`（学生 403）
- **学习日历**：GitHub 风格 90 天热力图（周一对齐，hover 显示当日题量）
- **复习正确率趋势**：近 30 天 记得/秒懂占比折线（仅有复习记录的日期）
- **掌握归档**：连续记牢 ≥3 次且间隔 ≥21 天的错题自动移出每日复习池（🏆 徽章），防止复习池被熟题淹没
- **复习历史**：复习页可查看最近 20 次评分记录与下次间隔
- **导出双模式**：重做版（原图+留白）/ 详解版（含解析答案与变式）
- **手动录入 AI 补全**：勾选后 AI 分析题目文本，补全留空的答案/标签/考点（用户填写优先）
- **学习连击**：看板展示连续学习天数（录入或复习均计为活跃，允许今天未开始时从昨天回溯）
- **看板交互**：知识点分布改为可点击的横向条形图，点击色条直达错题本并自动带上标签筛选；新增「开始复习 / 录一道错题 / 复习最薄弱知识点」快捷入口
- **复习体验**：进度条与本轮评分计数、⏭️ 跳过按钮、完成一轮后的总结（撒花 + 记得/秒懂占比）、卡片显示上次复习时间
- **错题本**：分页浏览、列表 ⏰/✅/🏆 复习状态徽章、勾选错题单独导出复习卷、空状态带快捷操作、教师可按学生筛选
- **评分间隔预览**：评分按钮下方显示各评分对应的下次复习时间；错题详情内支持单题重测
- **录入体验**：AI 录题与手动录入成功后可一键跳转错题本；注册后自动登录
- **界面美化**：卡片/按钮悬停反馈、聚焦描边统一品牌蓝、自定义滚动条、登录页特性卡片、侧边栏版本号、toast 轻提示、MUJI 细节打磨
- **移动端**：侧边栏窄屏自动折叠
- **教师口径修正**：教师看板的待复习/已掌握按自己的题计（全班总量另行呈现）；教师编辑/重测学生题目会得到明确提示
- **CI 冒烟**：新增 Streamlit 与 API 启动健康检查任务
- `scripts/seed_demo.py`（演示数据）、`scripts/smoke_api.py`（live API 冒烟测试）

### 修复
- `create_manual_question` 空内容校验下沉到服务层（导入空条目自动跳过）
- 教师错题本「全部学生」视角误用自己的题池导致空列表
- 教师看板「待复习/已掌握」混入学生错题的口径问题

### 测试
- 测试用例 47 → 68（新增 API 网关集成 13 个、备份往返 6 个、限流 4 个）

## [2.0.0] - 2026-09-07

生产级重写，详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

### 新增
- 分层架构：backend（config / models / repositories / services / utils）+ frontend（6 页面）
- AI 提供商抽象：OpenAI 兼容（SiliconFlow / 通义 / GLM / DeepSeek / Ollama）/ Gemini / Mock 演示模式；Pydantic 结构化输出 + 稳健 JSON 提取 + 重试
- RAG：ChromaDB 错题向量库，相似题召回（举一反三）、语义搜索、故障自动降级
- SM-2 间隔重复复习调度 + 标签掌握度分析
- bcrypt 密码哈希、注册/登录/改密；SQLite 默认（WAL）+ `DATABASE_URL` 切换 MySQL
- pytest 测试套件、ruff、GitHub Actions CI（lint + 3.10-3.12 矩阵 + Docker 构建）、Dockerfile / docker-compose
- 双语 README（真实截图 + Mermaid 架构图）、docs/ARCHITECTURE.md、.env.example、MIT LICENSE

### 移除
- 旧版 `src/` 混合脚本、调试脚本、WIP 文档、pip freeze 式 160 项依赖清单
