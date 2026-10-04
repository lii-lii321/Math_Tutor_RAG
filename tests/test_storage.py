"""对象存储抽象测试：本地后端往返 + s3 后端（注入桩 client）+ 单例选择。"""
from __future__ import annotations

import io

import pytest

from backend.services.storage import (
    LocalStorage,
    S3Storage,
    StorageError,
    get_storage,
    reset_storage,
)


class FakeS3Client:
    """最小 S3 客户端桩：内存 dict 存对象，presign 返回固定格式 URL。"""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: ANN001
        self.objects[Key] = (bytes(Body), ContentType)

    def head_object(self, Bucket, Key):  # noqa: ANN001
        if Key not in self.objects:
            raise RuntimeError("404")

    def get_object(self, Bucket, Key):  # noqa: ANN001
        if Key not in self.objects:
            raise RuntimeError("404")
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def generate_presigned_url(self, ClientMethod, Params, ExpiresIn):  # noqa: ANN001
        return f"https://fake-s3/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


def test_local_roundtrip(tmp_path):
    backend = LocalStorage(tmp_path)
    backend.save("images/u1/a.jpg", b"jpeg-bytes")
    assert backend.exists("images/u1/a.jpg")
    assert backend.exists("images/u1/missing.jpg") is False
    assert backend.load("images/u1/a.jpg") == b"jpeg-bytes"
    src = backend.display_source("images/u1/a.jpg")
    assert src is not None and src.endswith("a.jpg")
    assert backend.display_source("images/u1/missing.jpg") is None
    mat = backend.materialize("images/u1/a.jpg")
    assert mat is not None and mat.read_bytes() == b"jpeg-bytes"
    assert backend.materialize("images/u1/missing.jpg") is None


def test_local_supports_legacy_absolute_paths(tmp_path):
    legacy = tmp_path / "legacy.jpg"
    legacy.write_bytes(b"old")
    backend = LocalStorage(tmp_path)
    assert backend.display_source(str(legacy)) == str(legacy)


def test_s3_roundtrip_with_injected_client(tmp_path):
    fake = FakeS3Client()
    backend = S3Storage("mathtutor", client=fake)
    # materialize 的缓存目录来自 settings.data_dir；指向 tmp 避免污染仓库
    backend._tmp_dir = tmp_path / "objcache"

    backend.save("images/u2/b.jpg", b"jpg2", content_type="image/jpeg")
    assert fake.objects["images/u2/b.jpg"] == (b"jpg2", "image/jpeg")
    assert backend.exists("images/u2/b.jpg") is True
    assert backend.exists("images/u2/none.jpg") is False
    assert backend.load("images/u2/b.jpg") == b"jpg2"

    url = backend.display_source("images/u2/b.jpg")
    assert url is not None and "images/u2/b.jpg" in url
    assert backend.display_source("images/u2/none.jpg") is None

    mat = backend.materialize("images/u2/b.jpg")
    assert mat is not None and mat.parent == tmp_path / "objcache"
    assert mat.read_bytes() == b"jpg2"
    assert backend.materialize("images/u2/none.jpg") is None


def test_s3_requires_bucket():
    with pytest.raises(StorageError):
        S3Storage("", client=FakeS3Client())


def test_get_storage_defaults_to_local():
    reset_storage()
    backend = get_storage()
    assert isinstance(backend, LocalStorage)


def test_get_storage_s3_mode_propagates_config_error(monkeypatch):
    """STORAGE_BACKEND=s3 且后端不可构建（如未装 boto3）时，报错清晰可读。"""
    from backend.config import get_settings

    def _boom(**_kw):
        raise StorageError("STORAGE_BACKEND=s3 需要 boto3：pip install boto3")

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "mathtutor")
    monkeypatch.setattr(S3Storage, "_build_client", staticmethod(_boom))
    get_settings.cache_clear()
    reset_storage()
    try:
        with pytest.raises(StorageError, match="boto3"):
            get_storage()
    finally:
        get_settings.cache_clear()
        reset_storage()
