"""live API 冒烟测试：对运行中的 uvicorn 实例全链路验证（本地开发用）。"""
import io
import json
import sys
import urllib.request

from PIL import Image

BASE = "http://localhost:8000"


def req(method, path, token=None, data=None, files=None):
    url = BASE + path
    headers = {}
    body = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if files:
        boundary = "X-BOUNDARY"
        parts = []
        for name, (filename, content, ctype) in files.items():
            parts.append(
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'
                ).encode()
                + content
                + b"\r\n"
            )
        parts.append(
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"tags\"\r\n\r\nlive-test\r\n").encode()
        )
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r) as resp:
        return resp.status, json.loads(resp.read().decode())


def main() -> None:
    img = Image.new("RGB", (16, 16), (10, 120, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    s, login = req("POST", "/api/auth/login", data={"username": "demo", "password": "demo123"})
    print("login", s)
    tok = login["access_token"]

    s, exp = req("GET", "/api/questions/export", token=tok)
    print("export", s, "count", exp["count"])

    s, imp = req(
        "POST",
        "/api/questions/import",
        token=tok,
        data={
            "format": "mathmaster-backup",
            "version": 1,
            "questions": [
                {"content_markdown": "live API 导入验证题目", "answer": "ok", "tags": ["live-check"]}
            ],
        },
    )
    print("import", s, imp)

    s, created = req(
        "POST",
        "/api/questions/analyze",
        token=tok,
        files={"image": ("live.jpg", buf.getvalue(), "image/jpeg")},
    )
    print("analyze", s, "qid", created["question"]["id"])

    s, graded = req(
        "POST", f"/api/review/{created['question']['id']}/grade", token=tok, data={"grade": "good"}
    )
    print("grade", s, "reps", graded["reps"])

    s, reply = req(
        "POST",
        f"/api/review/{created['question']['id']}/followup",
        token=tok,
        data={"question": "为什么有两个实数根？", "history": []},
    )
    print("followup", s, "reply_len", len(reply["reply"]) > 10)

    s, dash = req("GET", "/api/stats/dashboard", token=tok)
    print("stats", s, "total", dash["total"], "due", dash["due"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print("SMOKE_FAIL:", exc)
        sys.exit(1)
