# 安全策略 (Security Policy)

## 报告漏洞

请勿公开提交安全漏洞。通过 GitHub 私下联系仓库所有者（lii-lii321），或使用 [Security Advisories](https://github.com/lii-lii321/Math_Tutor_RAG/security/advisories/new) 私密报告。我们会在 72 小时内响应。

## 已知的安全设计

- 密码使用 bcrypt 哈希存储（rounds 可配），从不落明文
- 登录失败固定延迟 + 同账号限流（5 次/5 分钟，进程内实现）
- REST API 使用 JWT（`AUTH_SECRET` 签名）；生产部署务必设置强随机密钥
- 所有 SQL 经 SQLAlchemy 参数化；界面/API 入参经 Pydantic 校验
- 上传图片有 MIME 白名单与 10MB 大小限制

## 部署安全清单

- [ ] `.env` 中 `AUTH_SECRET` 为强随机值（≥32 字节）：`python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] 修改种子账号默认密码（admin/admin123、demo/demo123）
- [ ] 反向代理配置 TLS；按需收紧 `api/main.py` 的 CORS 允许来源
- [ ] 数据目录（`data/`）不暴露公网；定期备份
