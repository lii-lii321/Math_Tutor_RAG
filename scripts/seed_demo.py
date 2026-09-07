"""开发辅助：向本地数据库写入一条演示错题（仅用于本地验证）。"""
import io
import os
import sys

os.environ.setdefault("AI_PROVIDER", "mock")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from backend.database import init_db
from backend.services.question_service import QuestionService


def main(user_id: int = 2) -> None:
    init_db()
    service = QuestionService()
    image = Image.new("RGB", (60, 40), (210, 220, 240))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    question, analysis = service.analyze_and_save(user_id, buf.getvalue(), user_tags=["演示数据"])
    print(f"SEEDED question id={question.id} tags={question.tags} points={analysis.knowledge_points}")


if __name__ == "__main__":
    main()
