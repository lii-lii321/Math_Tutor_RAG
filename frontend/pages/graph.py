"""知识图谱页：错题标签共现的力导向图，洞察知识点关联结构。"""
from __future__ import annotations

from itertools import combinations

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from frontend.common import get_question_service, page_header

_PALETTE = [
    "#2563eb", "#0d9488", "#d97706", "#dc2626", "#7c3aed",
    "#059669", "#db2777", "#0891b2", "#65a30d", "#c2410c",
]


def render_graph_page(user: dict) -> None:
    service = get_question_service()
    page_header("知识图谱", "标签共现网络 · 节点大小=错题数，连线的粗细=两种知识点同时出现的频率")

    questions = service.list_questions(user["id"], include_others=user["role"] == "teacher")
    if not questions:
        st.info("还没有错题，先去「AI 录题」上传几张错题照片，图谱会随错题积累自动生长。")
        return

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
            color=_PALETTE[i % len(_PALETTE)],
        )
        for i, tag in enumerate(top_tags)
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
