# 🔐 环境变量配置指南

## 快速开始

1. **创建 `.env` 文件**
   ```bash
   # 在项目根目录创建 .env 文件
   # Windows: copy NUL .env
   # Linux/Mac: touch .env
   ```

2. **复制模板内容**
   
   在项目根目录创建 `.env` 文件，并填写以下内容：

   ```env
   # ==================== 数据库配置 ====================
   DB_SERVER=.
   DB_USER=sa
   DB_PASSWORD=你的数据库密码
   DB_DATABASE=MathTutorDB

   # ==================== API Keys ====================
   GOOGLE_API_KEY=你的Google_API_Key
   OPENAI_API_KEY=你的OpenAI_API_Key（可选）

   # ==================== 网络代理配置 ====================
   # 如果不需要代理，可以留空或删除这两行
   HTTP_PROXY=http://127.0.0.1:7890
   HTTPS_PROXY=http://127.0.0.1:7890
   ```

3. **填写实际值**
   - `DB_PASSWORD`: 你的 SQL Server 数据库密码
   - `GOOGLE_API_KEY`: 你的 Google Gemini API Key
   - `OPENAI_API_KEY`: （可选）用于测试脚本
   - `HTTP_PROXY` / `HTTPS_PROXY`: 如果需要代理访问，填写代理地址

## ⚠️ 重要提示

- `.env` 文件已被 `.gitignore` 忽略，不会被提交到 Git 仓库
- **不要**将 `.env` 文件上传到 GitHub 或其他公共仓库
- 如果团队协作，请使用 `.env.example` 作为模板分享配置结构

## 📝 配置说明

### 数据库配置
- `DB_SERVER`: SQL Server 服务器地址（本地使用 `.`）
- `DB_USER`: 数据库用户名（默认 `sa`）
- `DB_PASSWORD`: **必须填写**，数据库密码
- `DB_DATABASE`: 数据库名称（默认 `MathTutorDB`）

### API Keys
- `GOOGLE_API_KEY`: **必须填写**，用于 AI 解析错题功能
- `OPENAI_API_KEY`: 可选，仅用于 `scripts/debug_key.py` 测试

### 代理配置
- `HTTP_PROXY`: HTTP 代理地址（如：`http://127.0.0.1:7890`）
- `HTTPS_PROXY`: HTTPS 代理地址（如：`http://127.0.0.1:7890`）
- 如果不需要代理，可以留空或删除这两行

## 🔍 验证配置

配置完成后，可以运行以下脚本验证：

```bash
# 测试数据库连接
python scripts/test_db.py

# 测试 Google API 连接
python scripts/check_google.py

# 测试 OpenAI API（如果配置了）
python scripts/debug_key.py
```
