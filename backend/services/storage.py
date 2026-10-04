"""对象存储抽象：本地磁盘（默认）或 S3 兼容对象存储（MinIO / OSS / COS）。

库存 image_path 字段统一存 key（如 ``images/u1/20260101_090000_ab12.jpg``）：

- ``local`` 后端：key 即 data_dir 相对路径，与既有数据零迁移兼容；
- ``s3`` 后端：key 即桶内对象名，展示走预签名 URL，导出/OCR 临时落地到本地。

切换只需 .env：``STORAGE_BACKEND=s3`` 加 S3_ENDPOINT / S3_BUCKET /
S3_ACCESS_KEY / S3_SECRET_KEY。boto3 为可选依赖，仅 s3 模式需要。
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Protocol

from backend.config import get_settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """存储后端不可用或配置不完整。"""


class StorageBackend(Protocol):
    """图片对象的最小接口；key 与库存 image_path 字段一一对应。"""

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None: ...

    def exists(self, key: str) -> bool: ...

    def load(self, key: str) -> bytes: ...

    def display_source(self, key: str) -> str | None:
        """展示用来源：本地绝对路径字符串或预签名 URL；对象不存在返回 None。"""

    def materialize(self, key: str) -> Path | None:
        """确保对象以本地文件存在（导出 / OCR / 分享卡用）；缺失返回 None。"""


class LocalStorage:
    """data_dir 本地磁盘后端（默认，开箱即用）。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        p = Path(key)
        if p.is_absolute():
            return p  # 历史数据：早期版本存过机器相关绝对路径
        return self._root / p

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def load(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"对象不存在: {key}")
        return path.read_bytes()

    def display_source(self, key: str) -> str | None:
        path = self._path(key)
        return str(path) if path.is_file() else None

    def materialize(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None


class S3Storage:
    """S3 兼容对象存储后端（MinIO / 阿里云 OSS / 腾讯云 COS / AWS S3）。

    boto3 惰性导入：仅 s3 模式需要；client 可注入以便测试。
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
        region: str = "",
        presign_expires: int = 3600,
        client=None,  # botocore client；测试注入桩
    ) -> None:
        if not bucket:
            raise StorageError("S3_BUCKET 未配置")
        self._bucket = bucket
        self._presign_expires = presign_expires
        self._client = client
        if self._client is None:
            self._client = self._build_client(
                endpoint_url=endpoint_url,
                access_key=access_key,
                secret_key=secret_key,
                region=region,
            )
        self._tmp_dir = get_settings().data_dir / "objcache"

    @staticmethod
    def _build_client(
        *, endpoint_url: str, access_key: str, secret_key: str, region: str
    ):
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - 环境相关
            raise StorageError(
                "STORAGE_BACKEND=s3 需要 boto3：pip install boto3"
            ) from exc
        kwargs: dict = {
            "service_name": "s3",
            "endpoint_url": endpoint_url or None,
        }
        if access_key:
            kwargs["aws_access_key_id"] = access_key
        if secret_key:
            kwargs["aws_secret_access_key"] = secret_key
        if region:
            kwargs["region_name"] = region
        return boto3.client(**kwargs)

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 - 404/403 等一律视为不可用
            return False

    def load(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def display_source(self, key: str) -> str | None:
        if not self.exists(key):
            return None
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._presign_expires,
        )

    def materialize(self, key: str) -> Path | None:
        """下载到 data_dir/objcache 下的本地缓存文件（按 key 哈希命名）。"""
        try:
            data = self.load(key)
        except Exception:  # noqa: BLE001 - 缺失/网络故障统一视为不可用
            return None
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        suffix = Path(key).suffix or ".bin"
        path = self._tmp_dir / f"{digest}{suffix}"
        path.write_bytes(data)
        return path


_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """进程级单例：按 STORAGE_BACKEND 配置返回后端实例。"""
    global _instance
    if _instance is None:
        s = get_settings()
        if s.storage_backend == "s3":
            _instance = S3Storage(
                s.s3_bucket,
                endpoint_url=s.s3_endpoint,
                access_key=s.s3_access_key,
                secret_key=s.s3_secret_key,
                region=s.s3_region,
                presign_expires=s.s3_presign_expires,
            )
            logger.info("对象存储后端: s3 (%s / %s)", s.s3_endpoint, s.s3_bucket)
        else:
            _instance = LocalStorage(s.data_dir)
            logger.info("对象存储后端: local (%s)", s.data_dir)
    return _instance


def reset_storage() -> None:
    """测试用：清空单例，使下次 get_storage() 重新按当前配置构建。"""
    global _instance
    _instance = None
