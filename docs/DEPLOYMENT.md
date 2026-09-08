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

## 4. AI 提供商配置

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

## 5. 数据备份与迁移

- **界面**：设置 → 数据备份 → 导出备份 (JSON) / 导入备份
- **API**：`GET /api/questions/export`、`POST /api/questions/import`
- 题目原图存于 `data/images/`，向量库存于 `data/chroma/`；Docker 部署时两者均在数据卷内，直接备份卷即可

## 6. 常见问题

| 现象 | 处理 |
|---|---|
| 登录后白屏 | 检查浏览器控制台；确认 `.streamlit/config.toml` 存在且未损坏 |
| AI 解析 502 | 检查 `AI_API_KEY` 是否有效、模型是否有视觉能力（VL 系列而非纯文本模型） |
| `database is locked` | 已内置 WAL + 30s busy timeout；仍出现请确认没有多个进程共用同一 SQLite 文件且频繁写 |
| 向量库不可用 | 设置页会显示降级提示；检查 `data/chroma` 目录权限，或删除该目录重启（会重建索引，需重新录题） |
| GitHub 连接失败 | 网络间歇受限；稍后重试或配置代理后 `git push` |
