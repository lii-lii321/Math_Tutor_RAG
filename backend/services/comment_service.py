"""批注服务：错题下的留言（教师批注 / 学生自注）。"""
from __future__ import annotations

from sqlalchemy import select

from backend.database import SessionLocal
from backend.models.orm import Comment, Question, User
from backend.utils.logging import get_logger

logger = get_logger("comments")


class CommentService:
    def list_for_question(self, question_id: int) -> list[dict]:
        with SessionLocal() as session:
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

    def add(self, question_id: int, author_id: int, content: str) -> dict:
        content = (content or "").strip()
        if not content:
            raise ValueError("批注内容不能为空")
        with SessionLocal() as session:
            question = session.get(Question, question_id)
            if question is None:
                raise ValueError("错题不存在")
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
        """删除批注：作者本人或教师可删。"""
        with SessionLocal() as session:
            comment = session.get(Comment, comment_id)
            if comment is None:
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
        with SessionLocal() as session:
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
