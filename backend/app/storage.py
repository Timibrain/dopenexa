import asyncio
import re
from pathlib import Path
from typing import Protocol
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from .config import settings

class StorageError(RuntimeError): pass

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$")

def validate_object_key(key: str) -> str:
    if not isinstance(key, str) or not _KEY_PATTERN.fullmatch(key) or key.startswith("/") or ".." in key.split("/"):
        raise StorageError("Invalid object key")
    return key

class StorageProvider(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def delete(self, key: str) -> None: ...
    def download_path(self, key: str) -> Path | None: ...
    async def download_url(self, key: str, expires_seconds: int = 300) -> str | None: ...

class LocalStorage:
    def __init__(self):
        self.root = Path(settings.upload_dir); self.root.mkdir(parents=True, exist_ok=True)
    async def put(self, key, data, content_type):
        key = validate_object_key(key); path = self.root / key; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); return key
    async def delete(self, key):
        path = self.root / key
        if path.exists(): path.unlink()
    def download_path(self, key): return self.root / key
    async def download_url(self, key, expires_seconds=300): return None

class ExternalObjectStorage:
    """S3-compatible storage adapter for Cloudflare R2 and compatible providers."""
    def __init__(self, client=None):
        required = (settings.object_storage_bucket, settings.object_storage_endpoint,
                    settings.object_storage_access_key, settings.object_storage_secret_key)
        if not all(required): raise StorageError("External object storage is not configured")
        self.bucket = settings.object_storage_bucket
        self.client = client or boto3.client("s3", endpoint_url=settings.object_storage_endpoint,
            aws_access_key_id=settings.object_storage_access_key,
            aws_secret_access_key=settings.object_storage_secret_key,
            region_name=settings.object_storage_region or "auto",
            config=Config(signature_version="s3v4"))
    async def put(self, key, data, content_type):
        key = validate_object_key(key)
        try:
            await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
            return key
        except (BotoCoreError, ClientError) as exc: raise StorageError("Object upload failed") from exc
    async def delete(self, key):
        key = validate_object_key(key)
        try: await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc: raise StorageError("Object deletion failed") from exc
    def download_path(self, key): return None
    async def download_url(self, key, expires_seconds=300):
        key = validate_object_key(key)
        if not 1 <= expires_seconds <= 3600: raise StorageError("Invalid download URL expiry")
        try:
            return await asyncio.to_thread(self.client.generate_presigned_url, "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_seconds)
        except (BotoCoreError, ClientError) as exc: raise StorageError("Download URL generation failed") from exc

def configured_storage() -> StorageProvider:
    return LocalStorage() if settings.storage_backend == "local" else ExternalObjectStorage()
