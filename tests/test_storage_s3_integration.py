"""S3 后端离线集成测试：moto 拦截层 + 真实 boto3 client 构建路径。

与 tests/test_storage.py 的区别：那里注入 FakeS3Client 桩，只验证后端逻辑；
这里经 moto 走真实 botocore 请求（签名/参数校验/HTTP 语义），是 MinIO 上线
前无需 Docker 的最强离线验证。moto 未安装时跳过（可选依赖）。

注意：@mock_aws 必须直接贴在测试函数上——moto 上下文退出后请求会漏到
真实 AWS；且 S3_ENDPOINT 环境变量需清空，否则 boto3 直连自定义端点绕过拦截。
"""
from __future__ import annotations

import pytest

pytest.importorskip("boto3")
pytest.importorskip("moto")

from moto import mock_aws  # noqa: E402

from backend.services.storage import S3Storage, get_storage, reset_storage  # noqa: E402


@mock_aws
def test_s3_real_boto3_roundtrip(tmp_path):
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="mathtutor")
    backend = S3Storage(
        "mathtutor",
        access_key="testing",
        secret_key="testing",
        region="us-east-1",
    )
    backend._tmp_dir = tmp_path / "objcache"

    assert backend.exists("images/u1/a.jpg") is False
    backend.save("images/u1/a.jpg", b"jpeg-real", content_type="image/jpeg")
    assert backend.exists("images/u1/a.jpg") is True
    assert backend.load("images/u1/a.jpg") == b"jpeg-real"

    # 展示来源是预签名 URL（含对象 key）
    url = backend.display_source("images/u1/a.jpg")
    assert url is not None and "images/u1/a.jpg" in url
    assert backend.display_source("images/u1/none.jpg") is None

    # materialize 落地本地缓存，内容一致
    mat = backend.materialize("images/u1/a.jpg")
    assert mat is not None and mat.parent == tmp_path / "objcache"
    assert mat.read_bytes() == b"jpeg-real"
    assert backend.materialize("images/u1/none.jpg") is None


@mock_aws
def test_get_storage_selects_s3_by_env(monkeypatch):
    """STORAGE_BACKEND=s3 时单例按配置选 S3 后端（moto 拦截真实构建）。"""
    import boto3

    from backend.config import get_settings

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="mathtutor")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "mathtutor")
    monkeypatch.setenv("S3_ACCESS_KEY", "testing")
    monkeypatch.setenv("S3_SECRET_KEY", "testing")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("S3_ENDPOINT", "")  # 空端点=默认 AWS，moto 才能拦截
    get_settings.cache_clear()
    reset_storage()
    try:
        backend = get_storage()
        assert isinstance(backend, S3Storage)
        backend.save("k.jpg", b"v")
        assert backend.exists("k.jpg") is True
        assert backend.load("k.jpg") == b"v"
    finally:
        get_settings.cache_clear()
        reset_storage()
