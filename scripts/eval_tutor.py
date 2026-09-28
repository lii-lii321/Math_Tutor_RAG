"""AI Tutor 回答质量评测（手册 §十二：AI Evaluation）。

对预置场景跑真实 AgentSession（function calling 全流程），再用 LLM-as-judge
按四个维度打分（1-5）：事实正确 / 工具使用 / 可操作性 / 表达清晰。
报告写入 data/eval_tutor_report.json，控制台输出各场景均分。

运行（需配置真实 AI_API_KEY，mock 模式无意义会直接退出）：
    python scripts/eval_tutor.py              # 全部场景
    python scripts/eval_tutor.py --scene weak # 指定场景

说明：评测会消耗真实 API 配额；评分由同一模型自评，存在自评偏乐观的局限，
结果用于回归对比（同一版本改动前后的相对变化），不作为绝对质量承诺。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCENES: list[dict] = [
    {
        "id": "weak",
        "title": "薄弱点诊断",
        "prompt": "我最近数学哪里最薄弱？分析原因并给出未来 7 天的复习建议。",
        "expect_tools": ["get_learning_profile", "get_weak_knowledge_points", "get_recent_mistakes"],
    },
    {
        "id": "plan",
        "title": "今日计划",
        "prompt": "今天的复习计划是什么？我大概有 20 分钟时间。",
        "expect_tools": ["get_today_review_plan", "list_due_questions"],
    },
    {
        "id": "practice",
        "title": "生成练习卷",
        "prompt": "针对我最薄弱的知识点，出 5 道题的练习卷。",
        "expect_tools": ["generate_practice_set", "get_weak_knowledge_points"],
    },
    {
        "id": "search",
        "title": "找题",
        "prompt": "帮我把和二次函数有关的错题都找出来。",
        "expect_tools": ["search_questions"],
    },
]

JUDGE_PROMPT = """你是严格的教研员。根据「用户问题」和「AI Tutor 回答」，按四个维度各打 1-5 分：
- correctness：事实与学情引用是否正确、无编造
- tool_use：是否恰当使用了工具获取真实数据（凭空作答应扣分）
- actionability：建议是否具体可执行（含知识点/题量/时间）
- clarity：结构化程度与表达清晰度

只输出 JSON：{{"correctness": n, "tool_use": n, "actionability": n, "clarity": n, "comment": "一句话"}}
"""


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", help="仅跑指定场景 id", default=None)
    args = parser.parse_args()

    from backend.config import get_settings

    settings = get_settings()
    if not settings.ai_api_key:
        print("未配置 AI_API_KEY——Tutor 评测需要真实模型（mock 模式无意义）。")
        return 1

    from backend.database import SessionLocal, init_db
    from backend.models.orm import User
    from backend.services.agent import AgentSession

    init_db(seed_users=True)
    with SessionLocal() as session:
        demo = session.query(User).filter_by(username=settings.seed_demo_username).one()
        user_id = demo.id

    scenes = [s for s in SCENES if not args.scene or s["id"] == args.scene]
    results: list[dict] = []

    for scene in scenes:
        print(f"\n=== 场景：{scene['title']} ===")
        agent = AgentSession(user_id=user_id)
        started = time.perf_counter()
        reply = agent.chat(scene["prompt"])
        elapsed = round(time.perf_counter() - started, 1)
        tools_used = [
            entry.get("tool_call", {}).get("function", {}).get("name", "")
            for entry in agent.history
            if entry.get("role") == "tool"
        ]
        tools_used = [name for name in tools_used if name]
        hit = len(set(tools_used) & set(scene["expect_tools"])) > 0
        print(f"耗时 {elapsed}s · 工具调用 {tools_used or '无'}")
        print(reply[:400])

        score = _judge(settings, scene["prompt"], reply)
        results.append(
            {
                "id": scene["id"],
                "title": scene["title"],
                "latency_s": elapsed,
                "tools_used": tools_used,
                "expected_tool_hit": hit,
                "reply": reply,
                "scores": score,
            }
        )
        print(f"评分：{json.dumps(score, ensure_ascii=False)}")

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": settings.ai_model,
        "scenes": results,
        "avg_scores": _avg(results),
    }
    out = Path(settings.data_dir) / "eval_tutor_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {out}")
    print(f"均分：{json.dumps(report['avg_scores'], ensure_ascii=False)}")
    return 0


def _judge(settings, user_question: str, reply: str) -> dict:
    """LLM 自评：失败时返回全 0 并带错误标记，不阻断整体评测。"""
    from openai import OpenAI

    try:
        client = OpenAI(
            api_key=settings.ai_api_key or "not-configured",
            base_url=settings.ai_base_url,
            timeout=settings.ai_timeout_seconds,
        )
        response = client.chat.completions.create(
            model=settings.ai_model,
            messages=[
                {"role": "system", "content": JUDGE_PROMPT.format()},
                {"role": "user", "content": f"用户问题：{user_question}\n\n回答：{reply}"},
            ],
        )
        content = response.choices[0].message.content or "{}"
        start, end = content.find("{"), content.rfind("}") + 1
        return json.loads(content[start:end])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200], "correctness": 0, "tool_use": 0, "actionability": 0, "clarity": 0}


def _avg(results: list[dict]) -> dict:
    dims = ["correctness", "tool_use", "actionability", "clarity"]
    valid = [r for r in results if "error" not in r.get("scores", {})]
    if not valid:
        return {dim: None for dim in dims}
    return {
        dim: round(sum(r["scores"].get(dim, 0) for r in valid) / len(valid), 2)
        for dim in dims
    }


if __name__ == "__main__":
    raise SystemExit(_main())
