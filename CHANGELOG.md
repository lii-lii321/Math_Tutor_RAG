# 更新日志 (Changelog)

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [2.3.0] - 2026-09-15

### 新增（Agent 化）
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
