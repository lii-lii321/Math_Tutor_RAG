"""班级路由（Batch 10 多租户）：教师班级 CRUD、成员管理、班级周报。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps import get_current_user
from backend.models.orm import User
from backend.services.class_service import ClassService
from backend.services.weekly_report import ClassAccessDenied, WeeklyReportService

router = APIRouter(prefix="/classes", tags=["classes"])


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class MemberAdd(BaseModel):
    student_id: int


def _require_teacher(user: User) -> None:
    if user.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "仅教师可管理班级")


@router.post("", status_code=201)
def create_class(
    payload: ClassCreate, user: User = Depends(get_current_user)
) -> dict:
    _require_teacher(user)
    try:
        return ClassService().create_class(user.id, payload.name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def list_classes(user: User = Depends(get_current_user)) -> list[dict]:
    _require_teacher(user)
    return ClassService().list_for_teacher(user.id)


@router.post("/{class_id}/members", status_code=204)
def add_member(
    class_id: int,
    payload: MemberAdd,
    user: User = Depends(get_current_user),
) -> None:
    _require_teacher(user)
    try:
        ClassService().add_student(user.id, class_id, payload.student_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{class_id}/members/{student_id}", status_code=204)
def remove_member(
    class_id: int,
    student_id: int,
    user: User = Depends(get_current_user),
) -> None:
    _require_teacher(user)
    try:
        removed = ClassService().remove_student(user.id, class_id, student_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not removed:
        raise HTTPException(404, "该学生不在班级中")


@router.delete("/{class_id}", status_code=204)
def delete_class(class_id: int, user: User = Depends(get_current_user)) -> None:
    _require_teacher(user)
    if not ClassService().delete_class(user.id, class_id):
        raise HTTPException(404, "班级不存在")


@router.get("/{class_id}/weekly-report")
def class_weekly_report(
    class_id: int,
    days: int = Query(7, ge=1, le=31, description="统计窗口天数（含今天）"),
    user: User = Depends(get_current_user),
) -> dict:
    """班级学情周报：窗口期新增/复习/正确率/待复习 + 薄弱知识点。"""
    _require_teacher(user)
    try:
        return WeeklyReportService().build(user.id, class_id, days=days)
    except ClassAccessDenied as exc:
        # 不存在与非本人班级统一 404，不泄露存在性
        raise HTTPException(404, "班级不存在") from exc
