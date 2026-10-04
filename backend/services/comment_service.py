"""批注服务：错题下的留言（教师批注 / 学生自注）+ 未读红点。"""
from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from backend.database import session_scope
from backend.models.orm import Comment, CommentReadState, Question, User
from backend.utils.logging import get_logger

logger = get_logger("comments")


class QuestionAccessDenied(LookupError):
    """题目不存在或查看者无权访问。

    「不存在」与「不可见」统一抛出本异常，对外一律按 404 处理，
    避免向无权用户泄露题目存在性（见 docs/ARCHITECTURE.md 边界契约）。
    """


def _visible(question: Question, viewer_id: int, viewer_role: str) -> bool:
    """可见性：题目 owner 本人可见；教师可见（含学生与其他教师的）题。"""
    return question.user_id == viewer_id or viewer_role == "teacher"


class CommentService:
    def list_for_question(
        self,
        question_id: int,
        *,
        viewer_id: int | None = None,
        viewer_role: str = "student",
    ) -> list[dict]:
        """列出题目批注。

        viewer_id/viewer_role 为查看者上下文，API 层必须传入；不传时
        跳过归属校验（仅校验存在性）——frontend/pages/notebook.py 的
        _render_comments（教师浏览学生错题的批注 tab）仍依赖该旧路径，
        调用方迁移（传入查看者）前不可移除，属遗留债务。
        """
        with session_scope() as session:
            self._require_visible(session, question_id, viewer_id, viewer_role)
            rows = session.execute(
                select(Comment, User.username, User.role)
                .join(User, Comment.author_id == User.id)
                .where(Comment.question_id == question_id)
                .order_by(Comment.created_at.asc())
            ).all()
        return [
            {
                "id": comment.id,
                "author": username,
                "role": role,
                "content": comment.content,
                "created_at": comment.created_at,
            }
            for comment, username, role in rows
        ]

    @staticmethod
    def _require_visible(
        session: Session, question_id: int, viewer_id: int | None, viewer_role: str
    ) -> None:
        """校验查看者对题目的可见性，不可见即抛 QuestionAccessDenied。"""
        question = session.get(Question, question_id)
        if viewer_id is None:
            if question is None:
                raise ValueError("错题不存在")
            return
        if question is None or not _visible(question, viewer_id, viewer_role):
            raise QuestionAccessDenied(
                f"题目不可访问 question_id={question_id} viewer_id={viewer_id}"
            )

    def add(
        self,
        question_id: int,
        author_id: int,
        content: str,
        *,
        viewer_role: str | None = None,
    ) -> dict:
        """添加批注。

        查看者即作者本人：viewer_role 传当前作者角色时叠加归属校验
        （题目 owner 或教师）；不传时跳过归属校验——frontend/pages/
        notebook.py 的 _render_comments 批注表单仍依赖该旧路径，
        调用方迁移（传入作者角色）前不可移除，属遗留债务。
        """
        content = (content or "").strip()
        if not content:
            raise ValueError("批注内容不能为空")
        with session_scope() as session:
            self._require_visible(
                session,
                question_id,
                author_id if viewer_role is not None else None,
                viewer_role or "student",
            )
            author = session.get(User, author_id)
            if author is None:
                raise ValueError("用户不存在")
            comment = Comment(
                question_id=question_id, author_id=author_id, content=content
            )
            session.add(comment)
            session.commit()
            out = {"id": comment.id, "created_at": comment.created_at}
        logger.info("批注已添加 question=%s author=%s", question_id, author_id)
        return out

    def delete(self, comment_id: int, user_id: int, is_teacher: bool = False) -> bool:
        """删除批注：作者本人或教师可删，且批注所在题目须对删除者可见。"""
        with session_scope() as session:
            comment = session.get(Comment, comment_id)
            if comment is None:
                return False
            question = session.get(Question, comment.question_id)
            role = "teacher" if is_teacher else "student"
            if question is None or not _visible(question, user_id, role):
                return False
            if comment.author_id != user_id and not is_teacher:
                return False
            session.delete(comment)
            session.commit()
        return True

    def latest_for_questions(self, question_ids: list[int]) -> dict[int, dict]:
        """批量取每题最新一条批注（列表页预览用）。"""
        if not question_ids:
            return {}
        with session_scope() as session:
            rows = session.execute(
                select(Comment)
                .where(Comment.question_id.in_(question_ids))
                .order_by(Comment.created_at.asc())
            ).scalars()
            latest: dict[int, Comment] = {}
            for comment in rows:
                latest[comment.question_id] = comment
        return {
            qid: {"content": c.content, "created_at": c.created_at}
            for qid, c in latest.items()
        }

    def unread_counts(self, user_id: int, question_ids: list[int]) -> dict[int, int]:
        """每题未读教师批注数（未读红点数据源）。

        仅统计教师所发、批注 ID 大于该用户已读水位线的批注；
        无回执视为全部未读。只统计题目归属本人的题——教师浏览
        他人错题不产生红点。
        """
        if not question_ids:
            return {}
        with session_scope() as session:
            rows = session.execute(
                select(Comment.question_id, func.count())
                .join(User, Comment.author_id == User.id)
                .join(Question, Question.id == Comment.question_id)
                .outerjoin(
                    CommentReadState,
                    and_(
                        CommentReadState.question_id == Comment.question_id,
                        CommentReadState.user_id == user_id,
                    ),
                )
                .where(
                    Comment.question_id.in_(question_ids),
                    Question.user_id == user_id,
                    User.role == "teacher",
                    Comment.author_id != user_id,
                    Comment.id > func.coalesce(CommentReadState.last_read_comment_id, 0),
                )
                .group_by(Comment.question_id)
            ).all()
        return {question_id: int(count) for question_id, count in rows}

    def total_unread(self, user_id: int) -> int:
        """该用户全部错题的未读教师批注总数（顶栏提示用）。"""
        with session_scope() as session:
            value = session.execute(
                select(func.count())
                .select_from(Comment)
                .join(User, Comment.author_id == User.id)
                .join(Question, Question.id == Comment.question_id)
                .outerjoin(
                    CommentReadState,
                    and_(
                        CommentReadState.question_id == Comment.question_id,
                        CommentReadState.user_id == user_id,
                    ),
                )
                .where(
                    Question.user_id == user_id,
                    User.role == "teacher",
                    Comment.author_id != user_id,
                    Comment.id > func.coalesce(CommentReadState.last_read_comment_id, 0),
                )
            ).scalar()
        return int(value or 0)

    def mark_read(self, question_id: int, user_id: int) -> None:
        """把已读水位线推进到该题当前最大批注 ID（仅在确有未读时调用）。"""
        with session_scope() as session:
            watermark = session.execute(
                select(func.max(Comment.id)).where(Comment.question_id == question_id)
            ).scalar()
            state = session.execute(
                select(CommentReadState).where(
                    CommentReadState.question_id == question_id,
                    CommentReadState.user_id == user_id,
                )
            ).scalar_one_or_none()
            if state is None:
                session.add(
                    CommentReadState(
                        question_id=question_id,
                        user_id=user_id,
                        last_read_comment_id=int(watermark or 0),
                    )
                )
            else:
                state.last_read_comment_id = int(watermark or 0)
            session.commit()
