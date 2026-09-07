"""开发辅助：向本地数据库写入演示错题（仅用于本地验证 / 截图）。"""
import io
import os
import sys

os.environ.setdefault("AI_PROVIDER", "mock")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from backend.database import init_db
from backend.services.question_service import QuestionService

_EXTRA = [
    ((255, 210, 210), ["几何", "三角形"]),
    ((210, 255, 220), ["函数", "二次函数"]),
    ((210, 225, 255), ["概率", "统计"]),
    ((255, 240, 200), ["几何", "圆"]),
    ((230, 210, 255), ["代数", "因式分解"]),
    ((220, 255, 255), ["应用题", "行程问题"]),
]


def main(user_id: int = 2, extra: bool = False) -> None:
    init_db()
    service = QuestionService()
    batches = _EXTRA if extra else [((210, 220, 240), ["演示数据"])]
    for color, tags in batches:
        image = Image.new("RGB", (80, 50), color)
        buf = io.BytesIO()
        image.save(buf, format="JPEG")
        question, analysis = service.analyze_and_save(user_id, buf.getvalue(), user_tags=tags)
        print(f"SEEDED question id={question.id} tags={question.tags} points={analysis.knowledge_points}")


if __name__ == "__main__":
    extra = "--extra" in sys.argv
    main(extra=extra)
