"""教学数据模拟器：生成带时间线的模拟学生与干预记录，让工作台/画像/趋势
在无真实使用数据时也能完整展示（演示/截图/开发验证用）。

红线：
- 与学生W（student_w_1027）真实教学记录完全隔离——模拟数据只进
  「sim_」前缀的模拟学生账号与「模拟」标记班级，绝不触碰真实档案；
- 所有模拟学生名带「模拟」字样，界面上一眼可辨；
- 幂等：按用户名判定，已存在则跳过创建（--reset 先清模拟班重建）。

生成的三种学生画像（工作台三种状态）：
- sim_jiayi（模拟·甲）：进步生——干预已复测通过，掌握度上移，少量待复习；
- sim_yier（模拟·乙）：挣扎生——干预复测已排期未做，大量拖期；
- sim_san（模拟·丙）：新学员——刚录题，无复习，无干预。

运行：
    .venv/Scripts/python.exe scripts/simulate_teaching_data.py           # 幂等生成
    .venv/Scripts/python.exe scripts/simulate_teaching_data.py --reset   # 清模拟班重建
"""
from __future__ import annotations

import datetime as dt
import os
import sys

os.environ.setdefault("AI_PROVIDER", "mock")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models.orm import Question, ReviewLog, TeachingIntervention, User
from backend.services.auth import AuthService, RegisterInput
from backend.services.class_service import ClassService
from backend.services.question_service import QuestionService
from backend.services.teaching import TeachingService
from backend.utils.logging import get_logger

logger = get_logger("simulate")

CLASS_NAME = "模拟班（演示数据）"
TEACHER_USERNAME = "admin"  # 挂在 admin 名下，用户登录 admin 即可在工作台看到
SIM_KPS = ["一元二次方程", "二次函数的图象", "全等三角形判定", "有理数混合运算"]

QUESTION_BANK = [
    ("解方程：x² - 5x + 6 = 0", "(x-2)(x-3)=0，x₁=2，x₂=3", "一元二次方程"),
    ("求抛物线 y = x² - 4x + 3 的顶点坐标与对称轴", "顶点 (2, -1)，对称轴 x = 2", "二次函数的图象"),
    ("如图，AB=AC，BD=CD，求证 △ABD ≌ △ACD", "SSS：AB=AC，BD=CD，AD 公共边", "全等三角形判定"),
    ("计算 (-2)³ + 4 × (-3) - (-15)", "-8 - 12 + 15 = -5", "有理数混合运算"),
    ("已知关于 x 的方程 x² - 2mx + m² = 0 有两个相等实数根", "Δ = 4m² - 4m² = 0 恒成立，m 为任意值", "一元二次方程"),
    ("二次函数 y = ax² + bx + c 图象过点 (0,1)、(1,0)、(-1,4)，求解析式", "a=1, b=-2, c=1，y = x² - 2x + 1", "二次函数的图象"),
    ("两个三角形全等的判定方法有哪些", "SSS、SAS、ASA、AAS、HL（直角三角形）", "全等三角形判定"),
    ("计算 (-1) × (-4) ÷ 2 + (-3) × 2", "4 ÷ 2 - 6 = 2 - 6 = -4", "有理数混合运算"),
]


def _days_ago(days: int, hour: int = 19) -> dt.datetime:
    day = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    return day.replace(hour=hour, minute=hash(str(days)) % 60, second=0, microsecond=0)


def _get_or_create_teacher() -> int:
    with SessionLocal() as session:
        teacher = session.query(User).filter_by(username=TEACHER_USERNAME).one_or_none()
        return teacher.id if teacher else 0


def _get_or_create_student(username: str, password: str) -> int:
    with SessionLocal() as session:
        existing = session.query(User).filter_by(username=username).one_or_none()
        if existing is not None:
            return existing.id
    auth_session = SessionLocal()
    try:
        result = AuthService(auth_session).register(
            RegisterInput(username=username, password=password, role="student")
        )
        auth_session.commit()  # register 只写不提交，调用方收口
        return result.user_id
    finally:
        auth_session.close()


def _backdate_question(qid: int, created_at: dt.datetime) -> None:
    with SessionLocal() as session:
        row = session.get(Question, qid)
        row.created_at = created_at
        session.commit()


def _add_log(qid: int, user_id: int, grade: str, reviewed_at: dt.datetime, interval: float) -> None:
    with SessionLocal() as session:
        session.add(
            ReviewLog(
                question_id=qid,
                user_id=user_id,
                grade=grade,
                quality={"again": 0, "hard": 3, "good": 4, "easy": 5}[grade],
                prev_interval=0,
                next_interval=interval,
                ease_after=2.5,
                reviewed_at=reviewed_at,
            )
        )
        session.commit()


def _set_question_state(qid: int, *, reps: int, interval: float, due_at=None,
                        retest_verified: dt.datetime | None = None) -> None:
    with SessionLocal() as session:
        row = session.get(Question, qid)
        row.reps = reps
        row.interval_days = interval
        row.due_at = due_at
        row.last_reviewed_at = due_at
        if retest_verified is not None:
            row.retest_verified_at = retest_verified
        session.commit()


def _grade_label_from(quality: int) -> str:
    return {0: "again", 3: "hard", 4: "good", 5: "easy"}[quality]


def simulate() -> None:
    teacher_id = _get_or_create_teacher()
    if not teacher_id:
        print("admin 教师不存在——先运行应用完成初始化")
        return

    class_service = ClassService()
    existing = [c for c in class_service.list_for_teacher(teacher_id) if c["name"] == CLASS_NAME]
    if existing:
        print(f"模拟班已存在（id={existing[0]['id']}）——幂等跳过创建；如需重建用 --reset")
        class_id = existing[0]["id"]
    else:
        class_id = class_service.create_class(teacher_id, CLASS_NAME)["id"]
        print(f"创建模拟班 id={class_id}")

    service = QuestionService(session_factory=SessionLocal)
    teaching = TeachingService(session_factory=SessionLocal)
    now = dt.datetime.now(dt.timezone.utc)

    students = [
        ("sim_jiayi", "模拟·甲（进步生）", "sim_jiayi"),
        ("sim_yier", "模拟·乙（挣扎生）", "sim_yier"),
        ("sim_san", "模拟·丙（新学员）", "sim_san"),
    ]
    student_ids: dict[str, int] = {}
    for username, _, password in students:
        student_ids[username] = _get_or_create_student(username, password)
        class_service.add_student(teacher_id, class_id, student_ids[username])

    # ---------- 模拟·甲（进步生）：3 周前录题 → 干预 → 复测通过 → 少量待复习 ----------
    jiayi = student_ids["sim_jiayi"]
    jiayi_qids: list[int] = []
    for offset, (stem, answer, kp) in enumerate(QUESTION_BANK[:4]):
        q = service.create_manual_question(
            jiayi, content_markdown=stem, answer=answer, knowledge_points=[kp],
            tags=["模拟数据"], source="word",
        )
        _backdate_question(q.id, _days_ago(21 - offset))
        jiayi_qids.append(q.id)

    # 干预：16 天前诊断（掌握度差）→ 练习 → 10 天前复测通过 → 掌握归档两题
    diag = teaching.start_intervention(jiayi, SIM_KPS[0])
    with SessionLocal() as session:
        record = session.get(TeachingIntervention, diag["intervention_id"])
        record.created_at = _days_ago(16)
        record.updated_at = _days_ago(16)
        session.commit()
    teaching.record_practice(diag["intervention_id"], jiayi, jiayi_qids[:2])
    teaching.record_outcome(diag["intervention_id"], jiayi, passed=True)

    # 复习时间线：18 天前差评（again/hard）→ 干预后 8-3 天前好评 → 上移
    _add_log(jiayi_qids[0], jiayi, "again", _days_ago(18), 0)
    _add_log(jiayi_qids[1], jiayi, "hard", _days_ago(17), 0)
    _add_log(jiayi_qids[0], jiayi, "good", _days_ago(9), 1)
    _add_log(jiayi_qids[1], jiayi, "easy", _days_ago(6), 21)
    _set_question_state(jiayi_qids[0], reps=2, interval=6,
                        due_at=now - dt.timedelta(days=1),  # 已到期
                        retest_verified=_days_ago(9))
    _set_question_state(jiayi_qids[1], reps=2, interval=21,
                        due_at=now + dt.timedelta(days=15),
                        retest_verified=_days_ago(6))
    # 复测通过登记：干预标记 retest_passed（直接落库，保证时间线自洽）
    with SessionLocal() as session:
        record = session.get(TeachingIntervention, diag["intervention_id"])
        record.outcome = "retest_passed"
        record.retest_due_at = _days_ago(9)
        session.commit()
    print(f"模拟·甲：{len(jiayi_qids)} 题，干预 retest_passed，1 题待复习")

    # ---------- 模拟·乙（挣扎生）：3 周前录题 → 干预复测排期临期未做 → 大量拖期 ----------
    yier = student_ids["sim_yier"]
    yier_qids: list[int] = []
    for offset, (stem, answer, kp) in enumerate(QUESTION_BANK[2:6]):
        q = service.create_manual_question(
            yier, content_markdown=stem, answer=answer, knowledge_points=[kp],
            tags=["模拟数据"], source="word",
        )
        _backdate_question(q.id, _days_ago(18 - offset))
        yier_qids.append(q.id)
    diag2 = teaching.start_intervention(yier, SIM_KPS[2])
    with SessionLocal() as session:
        record = session.get(TeachingIntervention, diag2["intervention_id"])
        record.created_at = _days_ago(12)
        record.updated_at = _days_ago(12)
        session.commit()
    teaching.record_practice(diag2["intervention_id"], yier, yier_qids[:2])
    teaching.record_outcome(diag2["intervention_id"], yier, passed=True)
    with SessionLocal() as session:
        record = session.get(TeachingIntervention, diag2["intervention_id"])
        # 复测约定 2 天前——逾期未做（挣扎生画像）
        record.retest_due_at = now - dt.timedelta(days=2)
        session.commit()
    _add_log(yier_qids[0], yier, "again", _days_ago(11), 0)
    _set_question_state(yier_qids[0], reps=1, interval=0, due_at=now - dt.timedelta(days=6))
    for qid in yier_qids[1:]:
        _set_question_state(qid, reps=0, interval=0, due_at=now - dt.timedelta(days=4))
    print(f"模拟·乙：{len(yier_qids)} 题，复测排期逾期 2 天，全部拖期")

    # ---------- 模拟·丙（新学员）：昨天录 2 题，无复习无干预 ----------
    san = student_ids["sim_san"]
    for offset, (stem, answer, kp) in enumerate(QUESTION_BANK[6:8]):
        q = service.create_manual_question(
            san, content_markdown=stem, answer=answer, knowledge_points=[kp],
            tags=["模拟数据"], source="word",
        )
        _backdate_question(q.id, _days_ago(1 - offset))
        _set_question_state(q.id, reps=0, interval=0, due_at=None)
    print("模拟·丙：2 题新录入，无复习无干预")

    print("\n完成。admin 登录工作台即可看到三种学生状态；"
          "student 视角可登录 sim_jiayi / sim_yier / sim_san（口令 sim_pass）体验学生视图。")


def reset() -> None:
    """清掉全部模拟数据（用户、班级、题目级联、干预级联），重建。"""
    class_service = ClassService()
    teacher_id = _get_or_create_teacher()
    for klass in class_service.list_for_teacher(teacher_id):
        if klass["name"] == CLASS_NAME:
            class_service.delete_class(teacher_id, klass["id"])
    with SessionLocal() as session:
        removed = 0
        for username in ("sim_jiayi", "sim_yier", "sim_san"):
            user = session.query(User).filter_by(username=username).one_or_none()
            if user is not None:
                session.delete(user)  # 级联清题目/日志/干预/对话
                removed += 1
        session.commit()
    print(f"已清模拟数据：{removed} 个模拟学生（级联题目/日志/干预），重建模拟班")
    simulate()


if __name__ == "__main__":
    from backend.database import init_db

    init_db(seed_users=True)
    if "--reset" in sys.argv:
        reset()
    else:
        simulate()
