# API 快速上手（curl）

文档：`http://localhost:8000/docs`（启动 API 后自动生成）

```bash
# 登录获取 JWT
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "password": "demo123"}'

# 之后所有请求带：-H "Authorization: Bearer <access_token>"

# 列出错题（分页 + 关键词语义搜索）
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/questions?limit=10&keyword=判别式"

# 手动录入文本错题
curl -s -X POST http://localhost:8000/api/questions/text \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"content_markdown": "解方程 x^2=9", "answer": "±3", "tags": ["方程"]}'

# 图片 AI 解析（multipart）
curl -s -X POST http://localhost:8000/api/questions/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -F "image=@错题.jpg" -F "tags=期末复习"

# 到期错题 / 评分（again|hard|good|easy）/ 追问
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/review/due
curl -s -X POST http://localhost:8000/api/review/1/grade \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"grade": "good"}'

# 统计：看板 / 标签共现 / 学生总览（教师）
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/stats/dashboard
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/stats/tag-graph
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/stats/students

# 备份导出 / Word 卷
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/questions/export
curl -s -H "Authorization: Bearer $TOKEN" -o 复习卷.docx \
  http://localhost:8000/api/questions/export/docx
```
