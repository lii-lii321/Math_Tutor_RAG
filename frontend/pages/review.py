"""间隔重复复习页：闪卡式复习，SM-2 调度；支持「今日计划」自适应队列模式。"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from backend.services.review import GRADE_ORDER, format_interval
from backend.utils.paths import resolve_image_path
from frontend.common import (
    edit_question_form,
    get_question_service,
    go_to,
    keyboard_shortcuts,
    page_header,
    pop_params,
)
from frontend.components import GRADE_LABELS, safe_call


def render_review_page(user: dict) -> None:
    service = get_question_service()
    incoming = pop_params("mode", "question_id")
    # 计划模式标记入会话态：评分后的 rerun 不会丢模式（pop 的一次性参数会消失）
    if incoming.get("mode") == "plan":
        st.session_state["review_plan_mode"] = True
    elif incoming.get("mode") == "due":
        st.session_state.pop("review_plan_mode", None)
        st.session_state.pop("review_cursor", None)
    plan_mode = st.session_state.get("review_plan_mode", False)

    # 队列驻留会话态：评分后不再重新拉取——「忘了」的题当轮重现、撤销能还原队列
    queue_key = "review_queue"
    reasons_key = "review_reasons"
    rebuild = (
        incoming.get("mode") in ("plan", "due")
        or queue_key not in st.session_state
    )
    if rebuild:
        if plan_mode:
            ok, plan = safe_call(
                service.today_plan, user["id"], size=12,
                error_title="今日计划生成失败",
            )
            if not ok:
                st.stop()
            st.session_state[queue_key] = [item.question for item in plan]
            st.session_state[reasons_key] = {item.question.id: item.reason for item in plan}
        else:
            ok, due_list = safe_call(
                service.due_questions, user["id"],
                error_title="复习队列加载失败",
            )
            if not ok:
                st.stop()
            st.session_state[queue_key] = due_list
            st.session_state[reasons_key] = {}
    due = st.session_state.get(queue_key, [])
    reasons = st.session_state.get(reasons_key, {})

    if not due:
        st.session_state.pop(queue_key, None)
        st.session_state.pop(reasons_key, None)
        summary = st.session_state.pop("review_session", None)
        if summary and summary.get("graded"):
            grades = summary.get("grades", {})
            strong = grades.get("good", 0) + grades.get("easy", 0)
            rate = round(strong / summary["graded"] * 100) if summary["graded"] else 0
            st.balloons()
            st.success(
                f"🎉 本轮复习完成！共评分 {summary['graded']} 题，"
                f"记得/秒懂占 {rate}%。错题已按 SM-2 重新排期，明天见。"
            )
            if st.button("返回学情看板", type="primary"):
                go_to("dashboard")
        elif plan_mode:
            st.session_state.pop("review_plan_mode", None)
            st.success("🎉 今日计划已全部处理完，去「能力画像」看看掌握度变化。")
            if st.button("查看能力画像", type="primary"):
                go_to("mastery")
        else:
            st.success("🎉 今日复习任务已清空，错题本处于健康状态。")
        return

    idx_key = "review_cursor"
    if idx_key not in st.session_state:
        st.session_state[idx_key] = 0
    # 计划项「复习」按钮直达：把游标跳到指定题目（在队列中时）
    jump_id = incoming.get("question_id")
    if jump_id is not None:
        ids = [q.id for q in due]
        if jump_id in ids:
            st.session_state[idx_key] = ids.index(jump_id)
    st.session_state[idx_key] = min(st.session_state[idx_key], len(due) - 1)
    session_key = "review_session"  # 本轮复习统计：{"graded": n, "grades": {...}}
    if session_key not in st.session_state:
        st.session_state[session_key] = {"graded": 0, "grades": {}}

    if plan_mode:
        page_header(
            "今日复习 · 计划模式",
            "按掌握度引擎生成的今日计划复习：到期题优先，其余为薄弱知识点加固",
        )
    else:
        page_header("今日复习", "SM-2 间隔重复调度 · 按记忆掌握程度评分，自动安排下次复习时间")

    # 撤销上一评（恢复 SM-2 状态并把题插回当前队列位置）
    undo_state = st.session_state.get("review_undo")
    if undo_state:
        undo_col, _ = st.columns([1, 2])
        with undo_col:
            if st.button("↩️ 撤销上一评", width="stretch"):
                restored = service.restore_review_state(
                    undo_state["question_id"], user["id"], undo_state["snapshot"]
                )
                if restored:
                    q_list = st.session_state.get(queue_key, [])
                    q_list.insert(
                        min(st.session_state[idx_key], len(q_list)),
                        undo_state["question"],
                    )
                    stats = st.session_state[session_key]
                    stats["graded"] = max(0, stats["graded"] - 1)
                    stats["grades"][undo_state["grade"]] = max(
                        0, stats["grades"].get(undo_state["grade"], 1) - 1
                    )
                    st.session_state[queue_key] = q_list
                    st.session_state.pop("review_undo", None)
                st.rerun()

    st.markdown(
        f"""
        <div class="mm-stat mm-stat--accent" style="margin-bottom:0.8rem">
          <div class="mm-stat__value">{len(due)}</div>
          <div class="mm-stat__label">道错题待复习 · 当前进度 {st.session_state[idx_key] + 1} / {len(due)} · 本轮已评 {st.session_state[session_key]["graded"]} 题</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # 进度按已完成数计算：首题即为 1/N，消除"进度 0% 但显示 1/N"的自相矛盾
    done = st.session_state[session_key]["graded"]
    st.progress(min(done / len(due), 1.0), text=None)

    cursor = st.session_state[idx_key]
    question = due[cursor]

    st.markdown(
        f"""<div style="margin-bottom:0.6rem">
        <span class="mm-badge mm-badge--blue">{question.difficulty}</span>
        {''.join(f'<span class="mm-badge">{t}</span>' for t in question.tags)}
        </div>""",
        unsafe_allow_html=True,
    )
    if question.id in reasons:
        st.markdown(
            f'<span class="mm-badge mm-badge--warn">🎯 {reasons[question.id]}</span>',
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        reveal_key = f"reveal_{question.id}"  # 按题隔离，避免上一题状态泄漏
        if question.last_reviewed_at:
            last = question.last_reviewed_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=dt.timezone.utc)
            days_ago = (dt.datetime.now(dt.timezone.utc) - last).days
            st.caption(f"上次复习：{days_ago} 天前 · 已连续记牢 {question.reps} 次")
        stored = question.image_path
        image_abs = resolve_image_path(stored)
        if image_abs and image_abs.exists():
            st.image(str(image_abs), width="stretch")
        elif stored:
            st.markdown(question.content_markdown[:220], unsafe_allow_html=True)
            st.caption("⚠️ 原图文件缺失（可能已迁移目录），请参考解析文字")
        else:
            st.markdown(question.content_markdown[:220], unsafe_allow_html=True)
            st.caption("（手动录入题，请先回忆解法）")

        if st.button("显示解析", type="secondary"):
            st.session_state[reveal_key] = True

        if st.session_state.get(reveal_key):
            st.divider()
            st.markdown(question.content_markdown, unsafe_allow_html=True)
            st.markdown(f"**答案**：{question.answer}")
            st.markdown("##### 这道题你掌握得如何？")
            grade_cols = st.columns(4)
            for col, grade in zip(grade_cols, GRADE_ORDER, strict=False):
                with col:
                    preview = service.scheduler.next_schedule(
                        grade=grade,
                        reps=question.reps,
                        ease=question.ease,
                        interval_days=question.interval_days,
                    )
                    if st.button(GRADE_LABELS[grade], key=f"grade_{grade}", width="stretch"):
                        snapshot = service.snapshot_review_state(question.id, user["id"])
                        updated = service.grade_review(question.id, user["id"], grade)
                        st.session_state[reveal_key] = False
                        session_stats = st.session_state[session_key]
                        session_stats["graded"] += 1
                        session_stats["grades"][grade] = session_stats["grades"].get(grade, 0) + 1
                        if updated is not None:
                            when = format_interval(updated.interval_days)
                            msg = f"下次复习：{when}"
                            if updated.mastered:
                                msg += " · 🎉 已掌握归档，移出复习池"
                            st.toast(msg, icon="⏰")
                        if grade == "again":
                            # 忘了：当轮重现——本题移到队尾，本轮还会再见到它
                            q_list = st.session_state.get(queue_key, [])
                            q_list.append(q_list.pop(cursor))
                        else:
                            q_list = st.session_state.get(queue_key, [])
                            q_list.pop(cursor)
                        if snapshot is not None:
                            st.session_state["review_undo"] = {
                                "question_id": question.id,
                                "question": question,
                                "snapshot": snapshot,
                                "grade": grade,
                            }
                        st.session_state[idx_key] = min(cursor, max(len(q_list) - 1, 0))
                        st.rerun()
                    st.caption(format_interval(preview.next_interval))  # 评分后该题按队列逻辑处理，游标指向下一题
        else:
            skip_col, _ = st.columns([1, 2])
            with skip_col:
                if st.button("⏭️ 先跳过这道", width="stretch"):
                    st.session_state[idx_key] = (cursor + 1) % len(due)
                    st.rerun()

    with st.expander("✏️ 这道题解析有误？直接修改"):
        edit_question_form(service, question, user)

    keyboard_shortcuts()

    st.divider()
    with st.expander("复习历史（最近 20 次）"):
        history = service.recent_reviews(user["id"], limit=20)
        if not history:
            st.caption("还没有复习记录。")
        else:
            rows = [
                {
                    "时间": h["reviewed_at"].astimezone().strftime("%m-%d %H:%M")
                    if h["reviewed_at"] else "",
                    "评分": GRADE_LABELS.get(h["grade"], h["grade"]),
                    "下次间隔": f"{h['interval_days']:.0f} 天",
                    "题目": h["snippet"],
                }
                for h in history
            ]
            st.dataframe(rows, width="stretch", hide_index=True)

    with st.expander("SM-2 评分说明"):
        st.markdown(
            "| 评分 | SM-2 质量 q | 效果 |\n|---|---|---|\n"
            "| 😵 忘了 | 0 | 重置进度，10 分钟后重现 |\n"
            "| 😅 勉强 | 3 | 间隔按 1 天重新计算 |\n"
            "| 🙂 记得 | 4 | 间隔 × ease 正常拉长 |\n"
            "| 😎 秒懂 | 5 | 间隔拉长更快，ease 略增 |"
        )
