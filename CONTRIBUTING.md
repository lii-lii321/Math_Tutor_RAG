# 贡献指南 (Contributing)

感谢参与 MathMaster Edu！请遵循以下约定。

## 开发环境

```bash
git clone https://github.com/lii-lii321/Math_Tutor_RAG.git
cd Math_Tutor_RAG
python -m venv .venv && .venv\Scripts\pip install -r requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt         # macOS/Linux
```

## 常用命令

```bash
streamlit run app.py          # Web 界面
uvicorn api.main:app --port 8000   # REST API（文档 /docs）
pytest -q                     # 单元/集成测试
pytest -q --cov=backend --cov=api   # 带覆盖率
ruff check . --fix            # 静态检查 + 自动修复
pytest tests/e2e -q -m e2e    # E2E（需运行中的应用 + playwright install chromium）

# 数据库 schema 变更
alembic revision --autogenerate -m "变更描述"
alembic upgrade head
```

## 约定

- **架构分层**：界面（frontend/）→ 应用服务（backend/services/）→ 仓储（backend/repositories/）→ 模型（backend/models/）。界面层不写业务逻辑；新功能先加服务方法再接 UI/API。
- **QuestionService 按领域拆分为 Mixin**（question_mixins.py），新增领域方法请放入对应 Mixin。
- **schema 变更**必须走 Alembic 迁移，禁止只改模型不生成迁移。
- **提交信息**：`feat:/fix:/refactor:/docs:/test:/chore:` 前缀（约定式提交）。
- **测试**：新功能必须带测试；`ruff check .` 必须零告警；覆盖率不低于现有水平（当前 ~92%）。
- **UI 风格**：MUJI 极简——藏青标题 / 石板灰正文 / 蓝色点缀，**不使用紫色**，克制动效。

## 提交前自查

1. `ruff check .` 通过
2. `pytest -q` 全绿
3. 涉及 schema 的变更附 Alembic 迁移
4. README / CHANGELOG 需要时同步更新
