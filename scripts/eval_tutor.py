"""AI Tutor 回答质量评测（手册 §十二：AI Evaluation）。

对预置场景跑真实 AgentSession（function calling 全流程），产出两层结果：
1. 程序化硬断言（提升项 #15，不经模型判断）：
   - expected_tool_hit：必需工具至少命中一个；
   - citation_ok：回复引用的 #ID 未出现警告（复用 agent.citation_warning
     的白名单逻辑，抽工具结果重建校验依据）；
   - 数据落地：回答中的统计数字必须能在本轮工具结果文本中找到出处
     （找不到按未验证计，不阻断）。
   硬断言不过记 hard_pass=False，与自评分开列。
2. LLM-as-judge 四维打分（1-5）。

报告写入 data/eval_tutor_report.json，控制台输出各场景均分。

运行（需配置真实 AI_API_KEY，mock 模式无意义会直接退出）：
    python scripts/eval_tutor.py              # 全部场景
    python scripts/eval_tutor.py --scene weak # 指定场景

说明：评测会消耗真实 API 配额；打分由同一模型自评，存在自评偏乐观的局限，
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


def _tools_from_history(agent) -> list[str]:
    """从会话历史提取实际调用过的工具名。

    原实现读 tool 消息的 tool_call.function.name——该字段不存在（tool 消息
    只有 tool_call_id/content），恒返回空列表使 expected_tool_hit 形同虚设；
    改读 assistant 消息的 tool_calls 段。
    """
    names: list[str] = []
    for entry in agent.history:
        for call in entry.get("tool_calls") or []:
            name = call.get("function", {}).get("name", "")
            if name:
                names.append(name)
    return names


def _hard_gates(scene: dict, reply: str, tools_used: list[str], agent) -> dict:
    """程序化硬断言（不经模型判断）：必需工具命中 + 引用白名单 + 数字有出处。

    复用 AgentSession 的引用校验原语：以本轮 history 中 tool 消息重建
    工具结果集，citation_warning 为空 = 回复引用的 #ID 全部有据。
    """
    from backend.services.agent import citation_warning, extract_tool_ids

    tool_messages = [
        entry.get("content", "")
        for entry in agent.history
        if entry.get("role") == "tool"
    ]
    citation_ok = not citation_warning(reply, extract_tool_ids(tool_messages))
    expected_hit = len(set(tools_used) & set(scene["expect_tools"])) > 0

    # 数字出处：回复中的关键统计数字（≥2 位数）应出现在工具结果文本里
    tool_corpus = " ".join(tool_messages)
    import re

    numbers = set(re.findall(r"\d{2,}", reply))
    traced = {n for n in numbers if n in tool_corpus}
    numbers_traced = not numbers or len(traced) >= len(numbers) // 2

    hard_pass = expected_hit and citation_ok and numbers_traced
    return {
        "hard_pass": hard_pass,
        "expected_tool_hit": expected_hit,
        "citation_ok": citation_ok,
        "numbers_traced": numbers_traced,
        "untraced_numbers": sorted(numbers - traced),
    }


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
        tools_used = _tools_from_history(agent)
        hard = _hard_gates(scene, reply, tools_used, agent)
        print(f"耗时 {elapsed}s · 工具调用 {tools_used or '无'}")
        print(f"硬断言：{'通过' if hard['hard_pass'] else '未过'} {hard}")
        print(reply[:400])

        score = _judge(settings, scene["prompt"], reply)
        results.append(
            {
                "id": scene["id"],
                "title": scene["title"],
                "latency_s": elapsed,
                "tools_used": tools_used,
                "expected_tool_hit": hard["expected_tool_hit"],
                "hard": hard,
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
        "hard_pass_rate": round(
            sum(1 for r in results if r["hard"]["hard_pass"]) / max(len(results), 1), 2
        ),
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
