"""仓储层：封装全部数据库访问，服务层不直接触碰 ORM 查询细节。"""
from backend.repositories.questions import QuestionRepository
from backend.repositories.users import UserRepository

__all__ = ["QuestionRepository", "UserRepository"]
