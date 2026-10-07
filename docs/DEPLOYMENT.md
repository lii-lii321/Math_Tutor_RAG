# 部署指南 (Deployment Guide)

## 部署形态总览

| 形态 | 适用场景 | 说明 |
|---|---|---|
| 本地运行 | 演示 / 日常使用 | `streamlit run app.py`，SQLite + 内置嵌入模型，零外部依赖 |
| Docker Compose | 云服务器 / 局域网 | Web + API 双服务，数据卷持久化 |
| Streamlit Cloud | 纯前端演示 | 仅 Web 层；演示模式（无 Key）或配 Secret |

## 1. 本地运行

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

streamlit run app.py          # Web: http://localhost:8501
uvicorn api.main:app --port 8000   # API: http://localhost:8000/docs（可选）
```

首次启动自动建表并创建种子账号（`SEED_*` 环境变量可改），请立即在「设置」中修改密码。

## 2. Docker Compose（推荐）

```bash
cp .env.example .env    # 填入 AI_API_KEY 与强随机 AUTH_SECRET
docker compose up -d --build
```

- Web: `8501`；API: `8000`
- 数据（SQLite、图片、Chroma 向量库）持久化在 `mathmaster-data` 卷
- 健康检查：`curl http://localhost:8501/_stcore/health`、`curl http://localhost:8000/health`

生产建议：

1. `AUTH_SECRET` 用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成；
2. 用 Nginx/Caddy 反向代理并配置 TLS，收紧 CORS（`api/main.py` 中 `allow_origins`）；
3. 挂载卷注意备份（见下文数据备份）。

## 3. 切换 MySQL（可选）

```env
DATABASE_URL=mysql+pymysql://mathmaster:mathmaster@localhost:3306/math_tutor?charset=utf8mb4
```

- 需要安装驱动：`pip install pymysql`
- 取消 `docker-compose.yml` 中 mysql 服务的注释即可联动
- 表结构由 SQLAlchemy `create_all` 自动创建；已有 SQLite 数据可用「设置 → 数据备份」导出 JSON 后在新库导入

### 数据库迁移（Alembic）

schema 变更通过 Alembic 管理（`migrations/`）：

```bash
# 全新环境：建表到最新版本
alembic upgrade head

# 已有的旧库（由 create_all 创建、无迁移记录）：补盖章后即可跟进后续迁移
alembic stamp head

# 修改 ORM 模型后生成迁移脚本
alembic revision --autogenerate -m "描述变更"

# 回退一个版本
alembic downgrade -1
```

数据库 URL 优先级：`alembic -x url=...` > 环境变量 `DATABASE_URL` > `backend/config.py`。

### PostgreSQL（Batch 09，已验证）

```env
DATABASE_URL=postgresql+psycopg2://mathmaster:mathmaster@localhost:5433/math_tutor
```

- 驱动：`pip install psycopg2-binary`
- compose 已内置 PG 服务（profile 隔离，不影响默认 SQLite 启动）：

```bash
docker compose --profile postgres up -d postgres   # 等待 healthy
alembic upgrade head                               # 全部迁移在 PG 16 上验证通过
pytest                                             # 252 用例全绿（DATABASE_URL 指向 PG）
```

- 迁移链（9 个版本）、ORM、服务层与 REST API 均已在 PostgreSQL 16 上验证；
  测试套件可通过 `DATABASE_URL` 环境变量直接指向 PG 运行（`tests/conftest.py` 已支持外部覆盖）

## 4. 对象存储（v2.13，可选）

图片的存储后端由 `STORAGE_BACKEND` 决定：

- **local（默认）**：存 `data/images/` 本地磁盘，随数据卷备份，零配置
- **s3**：S3 兼容对象存储（MinIO / 阿里云 OSS / 腾讯云 COS / AWS S3），
  展示走预签名 URL，导出与 OCR 自动落地本地缓存（`data/objcache/`）

```bash
pip install boto3        # 可选依赖，仅 s3 模式需要
```

```env
STORAGE_BACKEND=s3
S3_ENDPOINT=http://localhost:9000        # MinIO 本地示例；OSS/COS 换对应外部端点
S3_BUCKET=mathtutor
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_REGION=                                # AWS S3 必填（如 us-east-1），其余可留空
```

- 库内 `image_path` 统一存 key（local=相对路径，s3=桶内对象名），两种后端之间
  迁移只需搬运对象 + 改环境变量，无需改数据库
- s3 模式下「数据体检」自动跳过本地孤儿图片扫描（对象在远端桶内管理）

## 5. 异步任务队列（Batch 08）

AI 录题等耗时任务的执行后端由 `REDIS_URL` 决定：

- **未配置（默认）**：进程内 daemon 线程执行，单实例部署零依赖
- **配置 Redis**：任务经 RQ 队列进入 Redis，由独立 Worker 进程消费，Web 与 Worker 可各自横向扩容

```bash
pip install -r requirements-queue.txt      # rq + redis（可选依赖）

# .env
REDIS_URL=redis://localhost:6379/0

# 启动 Worker（与 Web 进程共享同一份代码与数据库配置）
python -m backend.jobs.worker
```

- 任务状态机：`pending → running → success / failed / cancelled`，`jobs` 表是唯一状态源
- Worker 取任务时二次校验状态，已取消的任务直接跳过；`POST /api/jobs/{id}/cancel` 仅可取消 pending 任务
- CI 用 fakeredis 离线验证 RQ 链路（入队 → burst 消费 → 状态落库），无需真实 Redis

## 6. AI 提供商配置

任选一家 OpenAI 兼容服务（`.env`）：

```env
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.siliconflow.cn/v1
AI_API_KEY=sk-xxxx
AI_MODEL=Qwen/Qwen2.5-VL-32B-Instruct
```

中文检索效果更佳可再配远程嵌入（可选）：

```env
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_API_KEY=sk-xxxx
EMBEDDING_MODEL=BAAI/bge-m3
```

不配置任何 Key 时应用以演示模式运行（MockProvider），便于验收部署是否成功。

## 7. 数据备份与迁移

- **界面**：设置 → 数据备份 → 导出备份 (JSON) / 导入备份
- **完整备份 (ZIP，v2.16)**：设置 → 数据备份 → 生成完整备份——zip 内含
  题目全字段（SM-2 调度状态、星标、笔记）、原图与逐次复习日志；导入按
  扩展名自动分流（JSON→轻量恢复、ZIP→完整恢复），图片按新属主 key 重新
  落存储，local / S3 双后端同路径
- **API**：`GET /api/questions/export`、`POST /api/questions/import`
  （v1 JSON 契约，**不含图片**；完整备份自 v2.19 起开放 API 双端点
  `GET/POST /api/questions/export/full`、`/import/full`，含图片与复习进度）
- 题目原图存于 `data/images/`，向量库存于 `data/chroma/`；Docker 部署时两者均在数据卷内，直接备份卷即可

## 8. 教师邀请码（TEACHER_INVITE_CODE）

教师自助注册默认关闭（配置为空 = fail-closed）。配置后注册教师必须携带匹配的 invite_code，比较为常量时间 bytes 比对（非 ASCII 中文码安全）。

- **推荐存 sha256 摘要**（配置值为 64 位 hex 时自动按摘要语义比对）：
  `python -c "import hashlib;print(hashlib.sha256('你的邀请码'.encode()).hexdigest())"`，把输出粘到 `TEACHER_INVITE_CODE=`——泄露配置文件不会泄露码本身。
- **轮换**：改 `TEACHER_INVITE_CODE` 并重启进程即生效（无状态，无数据库迁移）。
- **64-hex 明文歧义提醒**：若把 64 位 hex 字符串当明文码配置，会被按摘要语义比对（候选码需 sha256 后等于该值才通过）——明文模式请避免 64-hex 字符串。

## 9. 常见问题

| 现象 | 处理 |
|---|---|
| 登录后白屏 | 检查浏览器控制台；确认 `.streamlit/config.toml` 存在且未损坏 |
| AI 解析 502 | 检查 `AI_API_KEY` 是否有效、模型是否有视觉能力（VL 系列而非纯文本模型） |
| `database is locked` | 已内置 WAL + 30s busy timeout；仍出现请确认没有多个进程共用同一 SQLite 文件且频繁写 |
| 向量库不可用 | 设置页会显示降级提示；检查 `data/chroma` 目录权限，或删除该目录重启（会重建索引，需重新录题） |
| GitHub 连接失败 | 网络间歇受限；稍后重试或配置代理后 `git push` |
