# 性能基准 (Performance Benchmark)

测试环境：Windows 11 笔记本（本地 SQLite WAL）、Uvicorn 单进程、Locust 20 并发虚拟用户、30 秒采样。
工具：`locustfile.py`（读多写少负载：列表 6 : 看板 3 : 到期 2 : 语义搜索 1 : 健康检查 1）。

## 基准结果（2026-09-19，268 请求，0 失败）

| 端点 | 请求 | 平均 | 中位 | P95 | 最大 | req/s |
|---|---|---|---|---|---|---|
| GET /api/questions（列表） | 118 | 58ms | **10ms** | 190ms | 1026ms | 4.2 |
| GET /api/stats/dashboard | 65 | 40ms | **12ms** | 130ms | 608ms | 2.3 |
| GET /api/review/due | 28 | 45ms | **10ms** | 120ms | 767ms | 1.0 |
| GET /api/questions?keyword（语义） | 20 | 651ms | 270ms | 3200ms | 3153ms | 0.7 |
| POST /api/auth/login（bcrypt 刻意慢） | 20 | 2343ms | 2300ms | 2400ms | 2427ms | 0.7 |
| **聚合** | **268** | **264ms** | **12ms** | **2300ms** | — | **9.5** |

## 关键结论

1. **核心读接口 P50 ≈ 10ms**：SQL 下推（标签/关键词过滤在数据库完成）+ WAL 模式后，列表与看板在 20 并发下保持个位数至低双位数毫秒。
2. **语义搜索是重尾**（P50 270ms / P95 3.2s）：首查含嵌入模型冷启动；热路径约 250-400ms，主要耗时在本地嵌入计算。生产部署建议接入远程嵌入 API（`EMBEDDING_BASE_URL`）。
3. **登录 2.3s 是设计使然**：bcrypt（12 rounds）+ 失败延迟 1s 是刻意的安全开销，非性能问题。
4. **零失败**：30 秒 20 并发下无错误、无 5xx、无锁等待超时（WAL + busy timeout 生效）。

## 已做的性能工作

- 列表/到期/计数全部 SQL 下推（避免 Python 侧全量过滤）
- SQLite WAL + busy timeout 30s（多线程写安全）
- 图片上传自动压缩（≤1600px JPEG）
- AI 解析异步任务化（不占请求线程）

## 检索评测（Recall@K）

工具：`python -m scripts.eval_retrieval`。方法：以每道错题的标签为查询，检验目标题是否出现在 top-K（18 条查询，2026-09-19）。

| K | 关键词 | 向量 | RRF 融合 |
|---|---|---|---|
| 1 | 44% | 11% | 39% |
| 3 | 61% | 22% | 56% |
| 5 | 72% | 33% | 61% |

**诚实结论**：在本数据集（查询=精确标签、且大量错题共享同一标签，如 8 题同属「一元二次方程」）上，关键词单路已接近上限，RRF 融合反而被弱向量路稀释。

**何时融合有价值**：查询是自然语言（同义词/错别字/跨题描述）而非精确标签时——关键词 LIKE 命中不了，向量路提供独有召回，融合才有增益。因此实现保留为**双路融合可配置**，评测脚本可持续跟踪。

改进方向：本地 ONNX 嵌入对短中文标签区分度低 → 接入远程 bge-m3 嵌入（已支持）或加 rerank 精排（已留钩子）后重测。

## 复现

```bash
uvicorn api.main:app --port 8000
pip install locust
locust -f locustfile.py --host http://localhost:8000 --headless -u 20 -r 5 -t 30s --csv benchmark
```
