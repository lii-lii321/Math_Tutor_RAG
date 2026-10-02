"""知识图谱页：错题标签共现的力导向图，洞察知识点关联结构。"""
from __future__ import annotations

from itertools import combinations

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from backend.services.mastery import mastery_status
from frontend.common import get_question_service, go_to, page_header
from frontend.components import safe_call

_MASTERY_NODE_COLORS = {
    "weak": "#dc2626",  # 薄弱
    "shaky": "#d97706",  # 不稳固
    "solid": "#2563eb",  # 已掌握
    "unknown": "#94a3b8",  # 无复习数据
}


def _mastery_level(mastery: float | None) -> str:
    """颜色档位与后端掌握度引擎同源。"""
    if mastery is None:
        return "unknown"
    return mastery_status(mastery)


def render_graph_page(user: dict) -> None:
    service = get_question_service()
    page_header(
        "知识图谱",
        "标签共现网络 · 节点大小=错题数，颜色=掌握度（🔴薄弱 🟡不稳固 🔵已掌握 ⚪无数据）",
    )

    ok, questions = safe_call(
        service.list_questions,
        user["id"],
        include_others=user["role"] == "teacher",
        error_title="错题数据加载失败",
    )
    if not ok:
        st.stop()
    if not questions:
        st.info("还没有错题，先去「AI 录题」上传几张错题照片，图谱会随错题积累自动生长。")
        return

    ok, stats = safe_call(service.dashboard_stats, user["id"], error_title="掌握度数据加载失败")
    tag_mastery: dict[str, float] = (
        {s.tag: s.mastery for s in stats["tag_stats"]} if ok and stats else {}
    )

    tag_count: dict[str, int] = {}
    edge_count: dict[tuple[str, str], int] = {}
    for q in questions:
        tags = sorted({t for t in (q.tags or []) if t})
        for tag in tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1
        for a, b in combinations(tags, 2):
            edge_count[(a, b)] = edge_count.get((a, b), 0) + 1

    top_tags = sorted(tag_count, key=tag_count.get, reverse=True)[:15]
    top_set = set(top_tags)

    max_count = max(tag_count[t] for t in top_tags)
    nodes = [
        Node(
            id=tag,
            label=f"{tag} ({tag_count[tag]})",
            size=18 + 26 * tag_count[tag] / max_count,
            color=_MASTERY_NODE_COLORS[_mastery_level(tag_mastery.get(tag))],
        )
        for tag in top_tags
    ]
    edges = [
        Edge(source=a, target=b, width=1 + 3 * weight)
        for (a, b), weight in edge_count.items()
        if a in top_set and b in top_set
    ]

    if not edges:
        st.warning("错题数量还太少，标签之间尚未形成共现关系。多积累几道错题后再来看图谱。")
        return

    config = Config(
        width=1080,
        height=560,
        directed=False,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#2563eb",
        collapsible=False,
        node={"labelProperty": "label"},
        link={"labelProperty": "weight", "renderLabel": False},
    )

    c_graph, c_insight = st.columns([3, 1])
    with c_graph:
        agraph(nodes=nodes, edges=edges, config=config)
        st.caption("红色节点是需要优先加固的知识群；点击「📝」可在错题本中集中处理。")
    with c_insight:
        st.markdown("#### 关联最强的知识点对")
        strongest = sorted(edge_count.items(), key=lambda kv: kv[1], reverse=True)[:8]
        for (a, b), weight in strongest:
            st.markdown(
                f"<span class='mm-badge'>{a}</span>"
                f"<span class='mm-muted'> × </span>"
                f"<span class='mm-badge'>{b}</span>"
                f"<span class='mm-badge mm-badge--blue'>{weight} 次</span>",
                unsafe_allow_html=True,
            )
        st.caption("同时出现在同一道错题中的知识点，往往需要一起复习。")

        weak_tags = sorted(
            (t for t in top_tags if _mastery_level(tag_mastery.get(t)) == "weak"),
            key=tag_count.get,
            reverse=True,
        )
        if weak_tags:
            st.markdown("#### 🔴 薄弱知识群")
            for tag in weak_tags[:5]:
                if st.button(f"📝 {tag}", key=f"graph_go_{tag}", width="stretch"):
                    go_to("notebook", tag=tag)
