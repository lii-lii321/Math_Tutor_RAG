"""错题路由：列表 / AI 录题 / 文本录题 / 详情 / 编辑 / 删除 / 相似题。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from api.deps import get_current_user
from backend.models.orm import User
from backend.models.schemas import QuestionAnalysis, QuestionOut
from backend.services.export import generate_word_exam
from backend.services.question_service import QuestionService, sanitize_tags

router = APIRouter(prefix="/questions", tags=["questions"])

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


class QuestionUpdate(BaseModel):
    content_markdown: str | None = None
    answer: str | None = None
    tags: list[str] | None = None


class TextQuestionInput(BaseModel):
    content_markdown: str
    answer: str = ""
    tags: list[str] = Field(default_factory=list, max_length=8)
    knowledge_points: list[str] = Field(default_factory=list, max_length=8)


class AnalyzeResult(BaseModel):
    question: QuestionOut
    analysis: QuestionAnalysis


class ImportResult(BaseModel):
    imported: int


def _service() -> QuestionService:
    return QuestionService()


@router.get("", response_model=list[QuestionOut])
def list_questions(
    tag: str | None = None,
    keyword: str | None = None,
    semantic: bool = True,
    user: User = Depends(get_current_user),
) -> list[QuestionOut]:
    return _service().list_questions(
        user.id,
        include_others=user.role == "teacher",
        tag=tag,
        keyword=keyword,
        semantic=semantic,
    )


@router.post("/analyze", response_model=AnalyzeResult, status_code=status.HTTP_201_CREATED)
async def analyze_question(
    image: UploadFile = File(...),
    tags: str = Form(default=""),
    hint: str = Form(default=""),
    user: User = Depends(get_current_user),
) -> AnalyzeResult:
    """上传错题图片，返回结构化解析并自动归档（含向量索引）。"""
    if image.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"仅支持 {', '.join(sorted(_ALLOWED_MIME))}",
        )
    data = await image.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "图片内容为空")
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "图片不能超过 10MB")

    try:
        saved, analysis = _service().analyze_and_save(
            user.id,
            data,
            mime_type=image.content_type,
            user_tags=sanitize_tags(tags),
            hint=hint,
        )
    except Exception as exc:  # noqa: BLE001 - 统一转为 502
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI 解析失败: {exc}") from exc
    return AnalyzeResult(question=saved, analysis=analysis)


@router.post("/text", response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_text_question(
    payload: TextQuestionInput, user: User = Depends(get_current_user)
) -> QuestionOut:
    """手动录入文本错题（跳过视觉模型，直接归档 + 向量索引）。"""
    if not payload.content_markdown.strip():
        raise HTTPException(422, "题目内容不能为空")
    return _service().create_manual_question(
        user.id,
        content_markdown=payload.content_markdown,
        answer=payload.answer,
        tags=payload.tags,
        knowledge_points=payload.knowledge_points,
    )


@router.post("/import", response_model=ImportResult)
def import_questions(
    payload: dict, user: User = Depends(get_current_user)
) -> ImportResult:
    """从备份 JSON 恢复错题（按手动错题处理）。"""
    try:
        imported = _service().import_user_data(user.id, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return ImportResult(imported=imported)


@router.get("/export")
def export_questions(user: User = Depends(get_current_user)) -> dict:
    """导出当前用户全部错题的 JSON 备份。"""
    return _service().export_user_data(user.id)


@router.get("/export/docx")
def export_word_exam(
    tag: str | None = None,
    keyword: str | None = None,
    user: User = Depends(get_current_user),
) -> Response:
    """按当前筛选（可选 tag/keyword）导出可打印的 Word 复习卷。"""
    questions = _service().list_questions(
        user.id, include_others=user.role == "teacher", tag=tag, keyword=keyword, semantic=False
    )
    if not questions:
        raise HTTPException(404, "没有可导出的错题")
    stream = generate_word_exam(questions, "错题复习卷")
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="mathmaster_exam.docx"'},
    )


@router.get("/{question_id}", response_model=QuestionOut)
def get_question(question_id: int, user: User = Depends(get_current_user)) -> QuestionOut:
    question = _service().get_question(question_id, user.id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
    return question


@router.get("/{question_id}/similar", response_model=list[QuestionOut])
def similar_questions(
    question_id: int, user: User = Depends(get_current_user)
) -> list[QuestionOut]:
    question = _service().get_question(question_id, user.id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
    return _service().similar_questions(question, user_id=user.id)


@router.patch("/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    user: User = Depends(get_current_user),
) -> QuestionOut:
    updated = _service().update_question(
        question_id,
        user.id,
        content_markdown=payload.content_markdown,
        answer=payload.answer,
        tags=payload.tags,
    )
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
    return updated


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question_id: int, user: User = Depends(get_current_user)) -> None:
    deleted = _service().delete_questions([question_id], user.id)
    if deleted == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
