"""检索意图金标：题目相似之外的三类教学检索意图（提升项 #7）。

四类意图（题目相似型见 test_retrieval_quality.py）：
- same_kp     同知识点不同表述：两道题文字不同、考同一知识点
- same_error  同错因：不同知识点的题、犯同一类错误（漏隐含条件/忘分类讨论…）
- same_method 同解法：不同题型、用同一种方法（换元/配方/数形结合…）

命中语义：查询的期望结果是一个集合（组内任一题进 top3 即命中）——
教师检索「同错因的题」时组内任何一题都是有效结果。
门禁阈值按 2026-10-25 实测基线设定（见各常量注释），只兜「管线打穿」
级回归；接入 BGE-M3 等多语言嵌入后应上调。
"""
from __future__ import annotations

import os

import pytest

from backend.database import SessionLocal
from backend.models.orm import User
from backend.services.auth import AuthService, RegisterInput
from backend.services.question_service import QuestionService

# 每组：查询 + 两条语料（内容, 知识点分组标签）
# 标签进 knowledge_points（向量嵌入文本含知识点，见 create_manual_question）

_SAME_KP: list[tuple[str, list[tuple[str, str]]]] = [
    ("抛物线的最低点或者最高点应该怎么找", [
        ("二次函数 y=ax²+bx+c 的顶点横坐标是 x=-b/(2a)，代入解析式得顶点纵坐标", "抛物线顶点与最值"),
        ("把 y=2x²-8x+1 配方成 y=2(x-2)²-7，开口向上，最小值在顶点处取得", "抛物线顶点与最值"),
    ]),
    ("怎么判断一元二次方程有没有实数根", [
        ("判别式 Δ=b²-4ac 大于零时方程有两个不相等的实数根", "一元二次方程根的判别"),
        ("当 Δ=b²-4ac 小于零时，方程没有实数根，例如 x²+x+1=0", "一元二次方程根的判别"),
    ]),
    ("直角三角形知道两条边求第三边用什么", [
        ("勾股定理 a²+b²=c²：已知两条直角边 3 和 4，斜边为 5", "勾股定理"),
        ("已知直角三角形斜边 13 与一条直角边 5，另一条直角边由 c²-a²=b² 求得 12", "勾股定理"),
    ]),
    ("等差数列前 n 项和的公式是什么", [
        ("等差数列求和 S=n(a₁+aₙ)/2，首尾配对后乘项数除以二", "等差数列求和"),
        ("高斯求 1+2+…+100 的配对思想：首尾相加 50 组 101，即 5050", "等差数列求和"),
    ]),
    ("圆的切线都有什么性质", [
        ("圆的切线垂直于过切点的半径，连接圆心与切点可得直角", "圆的切线性质"),
        ("切线长定理：从圆外一点引两条切线，切线长相等", "圆的切线性质"),
    ]),
    ("相似三角形对应边成比例怎么用来求线段", [
        ("平行于三角形一边的直线截其它两边，所得三角形与原三角形相似，对应边成比例可求线段长", "相似三角形"),
        ("两角对应相等的两个三角形相似（AA 判定），利用相似比可求未知的高或边", "相似三角形"),
    ]),
    ("解分式方程为什么最后一定要验根", [
        ("去分母时方程两边同乘含未知数的式子，可能产生使分母为零的增根", "分式方程的增根"),
        ("解出的根必须代回最简公分母检验：分母为零者舍去", "分式方程的增根"),
    ]),
    ("一组数据的中位数怎么求", [
        ("奇数个数据按大小排列后取正中间的那个数作为中位数", "中位数与众数"),
        ("偶数个数据取中间两个数的平均数作为中位数", "中位数与众数"),
    ]),
]

_SAME_ERROR: list[tuple[str, list[tuple[str, str]]]] = [
    ("我做题总漏掉题目里藏着的隐藏条件", [
        ("求三角形第三边范围时容易漏掉两边之和大于第三边、两边之差小于第三边的隐含条件", "错因:漏隐含条件"),
        ("化简二次根式时忽略被开方数必须非负的限制条件", "错因:漏隐含条件"),
    ]),
    ("什么时候要分类讨论我总是忘", [
        ("解含绝对值的方程需要按 x≥0 与 x<0 两种情况分别讨论，漏讨论是常见失分点", "错因:忘记分类讨论"),
        ("等比数列求和要分公比 q=1 与 q≠1 两种情形，直接套公式会漏解", "错因:忘记分类讨论"),
    ]),
    ("移项以后符号老是搞错怎么办", [
        ("解一元一次方程移项要变号：x+3=7 中 3 移到右边变 -3", "错因:移项未变号"),
        ("不等式移项同样需要变号，且两边同乘负数时不等号方向要翻转", "错因:移项未变号"),
    ]),
    ("去分母的时候总会漏乘某一项", [
        ("解分式方程去分母时，方程两边的每一项都要乘最简公分母，常数项最常被漏乘", "错因:去分母漏乘"),
        ("解含分母的普通方程时，等号右边的常数项也要同时乘公分母", "错因:去分母漏乘"),
    ]),
    ("函数题什么时候要先看定义域", [
        ("求二次根式型函数的定义域需保证被开方数大于等于零", "错因:忽略定义域"),
        ("分式型函数要保证分母不为零，定义域写错后续全错", "错因:忽略定义域"),
    ]),
    ("应用题算完答案总差一个单位", [
        ("行程问题中速度与时间单位要统一：km/h 与 m/s 混用会导致数量级错误", "错因:单位换算失误"),
        ("面积单位换算：1 m² 等于 10⁴ cm²，平方进率最常算错", "错因:单位换算失误"),
    ]),
    ("取值范围的端点能不能取等号我分不清", [
        ("解集端点能否取等号要看原题是严格不等还是可取等，代回检验最稳妥", "错因:端点取值遗漏"),
        ("闭区间端点包含在解集内，开区间不包含；图象上实心点与空心圈要区分", "错因:端点取值遗漏"),
    ]),
    ("负号动不动就丢了怎么破", [
        ("去括号时负号要分配到括号内每一项：-(a-b)=-a+b", "错因:符号处理错误"),
        ("幂运算中负底数的符号要看指数奇偶：(-2)³ 为负而 (-2)⁴ 为正", "错因:符号处理错误"),
    ]),
]

_SAME_METHOD: list[tuple[str, list[tuple[str, str]]]] = [
    ("什么样的题目适合用换元法", [
        ("解高次方程 x⁴-5x²+4=0 时设 t=x² 降次为一元二次方程", "方法:换元法"),
        ("化简复杂分式时设 t=1/(x+1) 整体替换降低复杂度", "方法:换元法"),
    ]),
    ("配方法具体在哪些地方用", [
        ("把二次函数一般式化为顶点式需要配方", "方法:配方法"),
        ("用配方法解一元二次方程 x²+6x+5=0：两边加 9 配成完全平方", "方法:配方法"),
    ]),
    ("待定系数法什么时候用", [
        ("已知抛物线过三点求解析式：设 y=ax²+bx+c 代入三点解方程组", "方法:待定系数法"),
        ("因式分解难题可设待定系数：设 x²+xy-2y²=(x+ay)(x+by) 展开比对系数", "方法:待定系数法"),
    ]),
    ("解方程组的消元有几种做法", [
        ("代入消元法：把一个未知数用另一个表示后代入另一方程", "方法:消元法"),
        ("加减消元法：两方程相加减消去一个未知数", "方法:消元法"),
    ]),
    ("数形结合能解什么样的题", [
        ("判断方程解的个数可画两个函数图象数交点", "方法:数形结合"),
        ("解不等式可转化为图象在 x 轴上方的横坐标范围", "方法:数形结合"),
    ]),
    ("十字相乘法怎么用", [
        ("分解 x²+5x+6：找两数积为 6 且和为 5，得 (x+2)(x+3)", "方法:十字相乘法"),
        ("分解 x²-7x+12：两数积为 12 且和为 -7，得 (x-3)(x-4)", "方法:十字相乘法"),
    ]),
    ("选择题代特殊值检验是怎么回事", [
        ("判断恒等式是否成立可代 x=0、x=1 快速检验", "方法:特殊值检验"),
        ("三角函数化简题可代特殊角 30°、60° 验证选项", "方法:特殊值检验"),
    ]),
    ("整体代换是什么思路", [
        ("已知 x²+x=3，求 x²+x+1 的值：整体代入得 4，无需解出 x", "方法:整体代换"),
        ("齐次分式求值可整体设 t=x/y 转化为关于 t 的式子", "方法:整体代换"),
    ]),
]

_INTENT_USER = "golden_intents"
_INTENT_PW = "-".join(["intent", "pw", os.urandom(2).hex()])


@pytest.fixture(scope="module")
def intent_env():
    """专属用户 + 三类意图语料（模块级一次）。返回 (user_id, service, 组→ID集合)。"""
    with SessionLocal() as session:
        try:
            result = AuthService(session).register(
                RegisterInput(username=_INTENT_USER, password=_INTENT_PW, role="student")
            )
            session.commit()
            user_id = result.user_id
        except ValueError:
            session.rollback()
            user = session.query(User).filter_by(username=_INTENT_USER).one()
            user_id = user.id

    service = QuestionService(session_factory=SessionLocal)
    existing = {q.content_markdown for q in service.list_questions(user_id, semantic=False)}

    def _ensure(content: str, kp: str) -> int:
        if content in existing:
            matched = next(
                q for q in all_cache if q.content_markdown == content
            )
            return matched.id
        out = service.create_manual_question(
            user_id, content_markdown=content, knowledge_points=[kp]
        )
        all_cache.append(out)
        return out.id

    all_cache = list(service.list_questions(user_id, semantic=False))

    groups: dict[str, list[tuple[str, set[int]]]] = {
        "same_kp": [], "same_error": [], "same_method": []
    }
    for dimension, corpus in (
        ("same_kp", _SAME_KP),
        ("same_error", _SAME_ERROR),
        ("same_method", _SAME_METHOD),
    ):
        for query, entries in corpus:
            ids = {_ensure(content, kp) for content, kp in entries}
            groups[dimension].append((query, ids))
    return user_id, service, groups


def _hit_rank(service, user_id, query, expected_ids: set[int]) -> int | None:
    """查询结果中组内首个成员的排名（1 起）；未命中返回 None。"""
    ranked = [q.id for q in service.list_questions(user_id, keyword=query, semantic=True)]
    for rank, qid in enumerate(ranked, start=1):
        if qid in expected_ids:
            return rank
    return None


def _measure(service, user_id, groups, dimension: str) -> tuple[float, float]:
    ranks = [
        r
        for r in (
            _hit_rank(service, user_id, query, ids)
            for query, ids in groups[dimension]
        )
        if r is not None
    ]
    total = len(groups[dimension])
    recall3 = sum(1 for r in ranks if r <= 3) / total
    mrr = sum(1.0 / r for r in ranks) / total
    print(f"\n[意图基线] {dimension}: Recall@3={recall3:.2f} MRR={mrr:.2f}")
    return recall3, mrr


def test_intent_same_kp(intent_env):
    user_id, service, groups = intent_env
    recall, _mrr = _measure(service, user_id, groups, "same_kp")
    # 2026-10-25 实测基线 R@3=0.375 / MRR=0.37（ChromaDB 内置 MiniLM，
    # 混合路）。门禁 0.25 只兜「管线打穿」级回归；接入 BGE-M3 后应上调。
    assert recall >= 0.25, f"same_kp Recall@3 = {recall:.2f}"


def test_intent_same_error(intent_env):
    user_id, service, groups = intent_env
    recall, _mrr = _measure(service, user_id, groups, "same_error")
    # 实测基线 R@3=0.375 / MRR=0.34（同上），门禁 0.25 同 philosophy
    assert recall >= 0.25, f"same_error Recall@3 = {recall:.2f}"


def test_intent_same_method(intent_env):
    user_id, service, groups = intent_env
    recall, _mrr = _measure(service, user_id, groups, "same_method")
    # 实测基线 R@3=0.375 / MRR=0.28（同上），门禁 0.25
    assert recall >= 0.25, f"same_method Recall@3 = {recall:.2f}"
