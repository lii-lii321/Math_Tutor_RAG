# 📘 MathMaster Edu — Smart Wrong-Question Notebook (Vision LLM + RAG)

> **中文文档（完整版）：[README.md](README.md)** | English (condensed)

Take a photo of a wrong answer, and let AI do the rest: the problem is recognized and parsed into a structured record (knowledge points, step-by-step explanation, answer, difficulty, common mistakes, variations), the answer is verified with SymPy, the record is embedded into a vector store for semantic retrieval, per-topic mastery is estimated from review logs, and reviews are scheduled with the SM-2 spaced-repetition algorithm.

## Highlights

| Capability | Description |
|---|---|
| 📸 **AI photo entry** | Upload a handwritten worksheet photo; a Vision LLM returns a structured analysis constrained by a Pydantic schema |
| 🔁 **Multi-provider** | One provider abstraction for SiliconFlow / Qwen / Zhipu GLM / DeepSeek / OpenAI / Ollama — switch via `AI_BASE_URL` + `AI_MODEL`; Gemini uses its own provider (set `AI_PROVIDER=gemini`); runs in demo mode without any API key |
| ✅ **Math verification** | AI answers are checked deterministically with SymPy (solution substitution, derivative inverse) before being stored |
| 🧠 **RAG retrieval** | ChromaDB vector store: similar-question recall ("learn by analogy") and semantic search over your notebook, with automatic fallback to keyword search |
| 🤖 **Agent + MCP** | A tool-use chat agent (function-calling loop) plus an MCP server so Claude Desktop / Cursor can query the notebook directly (13 tools) |
| 📊 **Dashboard & weekly report** | Mastery distribution, weak-topic Top N, 14-day entry trend, learning calendar heatmap — plus a self-service weekly report (7/14/30-day windows) with Markdown preview and Word export (v2.18) |
| 🎯 **Mastery & spaced repetition** | Time-weighted mastery per topic from review logs, an adaptive daily plan (SM-2 due first + weak-topic reinforcement), SM-2 flashcard review, a user-set daily goal and milestone badges (v2.15), plus Anki deck export (.apkg, re-export updates existing cards) (v2.20) |
| 👨‍🏫 **Teacher side** | Class management and per-student overviews (question volume, due reviews, mastery, recent activity) |
| 🔌 **FastAPI gateway** | REST API sharing the same backend services as the Streamlit UI: JWT with access + refresh tokens, OpenAPI docs, async parsing jobs (in-process threads by default, Redis/RQ optional) |
| 💾 **Full backup** | One-click zip backup: questions + original images + SM-2 progress + stars/notes + review logs; import restores every field and rebuilds images under a new owner key; legacy JSON import still supported (without images) (v2.16) |
| 🌙 **UX details** | Dark mode, mobile-responsive layout (≤768px) with 44px touch targets (v2.17), shareable notebook filters via URL + sidebar global search (v2.14), PWA installable |
| 🧪 **Engineering** | pytest (439 collected tests) + Playwright E2E, ruff, import-linter layering gate, CI (lint + Python 3.10–3.12 matrix + coverage gate 75% + smoke + E2E + Docker), 13 Alembic migrations, Docker Compose deployment, SQLite default (PostgreSQL 16 compatibility validated via `DATABASE_URL`) |

## Quick Start

**Local (Python 3.10+):**

```bash
git clone https://github.com/lii-lii321/Math_Tutor_RAG.git
cd Math_Tutor_RAG

python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS/Linux

streamlit run app.py
```

Open http://localhost:8501 and sign in with a seed account (`admin` / `admin123` as teacher, `demo` / `demo123` as student). Without AI keys configured, the app runs in demo mode with built-in sample analyses.

**Docker:**

```bash
docker compose up -d --build
# Web: http://localhost:8501 · REST API docs: http://localhost:8000/docs
```

**API gateway only:**

```bash
uvicorn api.main:app --port 8000
```

To enable a real model, copy `.env.example` to `.env` and set `AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` (any OpenAI-compatible service, Gemini, or local Ollama).

## More

Architecture decisions, roadmap, deployment guide, and screenshots: see the **[Chinese README](README.md)**.
