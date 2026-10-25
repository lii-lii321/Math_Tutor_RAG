"""班级服务（Batch 10 多租户）：教师的可见范围由其班级决定。

边界收口（2026-10-25，外审 P1）：教师可见范围 = 自己 + 所教班级学生。
未建班或班级无成员时**不再回退全量学生**——学生错题/画像属教育数据，
默认扩大可见面必须显式建班授权，而不是靠「还没建班」的兼容回退。
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.models.orm import ClassMember, SchoolClass, User
from backend.utils.logging import get_logger

logger = get_logger(__name__)


class ClassService:
    def __init__(
        self,
        session_factory: sessionmaker | Callable[[], Iterator[Session]] | None = None,
    ):
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        from backend.database import session_scope

        with session_scope(self._session_factory) as session:
            yield session

    def _get_owned(self, session: Session, class_id: int, teacher_id: int) -> SchoolClass | None:
        return (
            session.execute(
                select(SchoolClass).where(
                    SchoolClass.id == class_id, SchoolClass.teacher_id == teacher_id
                )
            )
            .scalar_one_or_none()
        )

    def create_class(self, teacher_id: int, name: str) -> dict:
        if not name or not name.strip():
            raise ValueError("班级名称不能为空")
        with self._session() as session:
            klass = SchoolClass(name=name.strip()[:64], teacher_id=teacher_id)
            session.add(klass)
            session.flush()
            return self._to_dict(klass, member_count=0)

    def list_for_teacher(self, teacher_id: int) -> list[dict]:
        with self._session() as session:
            klasses = (
                session.execute(
                    select(SchoolClass)
                    .where(SchoolClass.teacher_id == teacher_id)
                    .order_by(SchoolClass.created_at.desc())
                )
                .scalars()
                .all()
            )
            counts = (
                dict(
                    session.execute(
                        select(ClassMember.class_id, func.count())
                        .where(ClassMember.class_id.in_([k.id for k in klasses]))
                        .group_by(ClassMember.class_id)
                    ).all()
                )
                if klasses
                else {}
            )
            return [self._to_dict(k, counts.get(k.id, 0)) for k in klasses]

    def add_student(self, teacher_id: int, class_id: int, student_id: int) -> None:
        with self._session() as session:
            klass = self._get_owned(session, class_id, teacher_id)
            if klass is None:
                raise ValueError("班级不存在或无权操作")
            student = session.get(User, student_id)
            if student is None or student.role != "student":
                raise ValueError("目标用户不存在或不是学生")
            exists = session.execute(
                select(ClassMember).where(
                    ClassMember.class_id == class_id,
                    ClassMember.student_id == student_id,
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(ClassMember(class_id=class_id, student_id=student_id))

    def remove_student(self, teacher_id: int, class_id: int, student_id: int) -> bool:
        with self._session() as session:
            klass = self._get_owned(session, class_id, teacher_id)
            if klass is None:
                raise ValueError("班级不存在或无权操作")
            member = session.execute(
                select(ClassMember).where(
                    ClassMember.class_id == class_id,
                    ClassMember.student_id == student_id,
                )
            ).scalar_one_or_none()
            if member is None:
                return False
            session.delete(member)
            return True

    def delete_class(self, teacher_id: int, class_id: int) -> bool:
        with self._session() as session:
            klass = self._get_owned(session, class_id, teacher_id)
            if klass is None:
                return False
            session.delete(klass)
            return True

    def has_classes(self, teacher_id: int) -> bool:
        """教师是否创建过班级——范围收紧策略的分界判定。

        区分「未建班」与「建班但暂无成员」：后者可见范围同样是
        自己 + 班级成员（可能为空），不回退全量。
        """
        with self._session() as session:
            count = session.execute(
                select(func.count()).select_from(SchoolClass).where(
                    SchoolClass.teacher_id == teacher_id
                )
            ).scalar_one()
        return count > 0

    def student_ids_for_teacher(self, teacher_id: int) -> list[int]:
        """教师可见的学生 ID 集：自己班级的成员（未建班返回空列表）。"""
        with self._session() as session:
            rows = session.execute(
                select(ClassMember.student_id)
                .join(SchoolClass, SchoolClass.id == ClassMember.class_id)
                .where(SchoolClass.teacher_id == teacher_id)
            ).all()
        return sorted({row[0] for row in rows})

    def class_student_ids(self, teacher_id: int, class_id: int) -> list[int]:
        """单个班级的学生 ID 集（校验班级归属，非本人班级返回空）。"""
        with self._session() as session:
            klass = self._get_owned(session, class_id, teacher_id)
            if klass is None:
                return []
            rows = session.execute(
                select(ClassMember.student_id).where(ClassMember.class_id == class_id)
            ).all()
        return sorted({row[0] for row in rows})

    @staticmethod
    def _to_dict(klass: SchoolClass, member_count: int) -> dict:
        return {
            "id": klass.id,
            "name": klass.name,
            "teacher_id": klass.teacher_id,
            "member_count": member_count,
        }
