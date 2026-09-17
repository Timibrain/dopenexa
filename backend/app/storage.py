from pathlib import Path
from typing import Protocol
from uuid import UUID
from .config import settings

class StorageError(RuntimeError): pass

class StorageProvider(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def delete(self, key: str) -> None: ...
    def download_path(self, key: str) -> Path | None: ...

class LocalStorage:
    def __init__(self):
        self.root = Path(settings.upload_dir); self.root.mkdir(parents=True, exist_ok=True)
    async def put(self, key, data, content_type):
        path = self.root / key; path.write_bytes(data); return key
    async def delete(self, key):
        path = self.root / key
        if path.exists(): path.unlink()
    def download_path(self, key): return self.root / key

class ExternalObjectStorage:
    """Provider-neutral boundary; production adapters can implement S3-compatible PUT/GET signing."""
    def __init__(self):
        if not (settings.object_storage_bucket and settings.object_storage_endpoint):
            raise StorageError("External object storage is not configured")
    async def put(self, key, data, content_type):
        raise StorageError("External storage adapter requires deployment integration")
    async def delete(self, key): raise StorageError("External storage adapter requires deployment integration")
    def download_path(self, key): return None

def configured_storage() -> StorageProvider:
    return LocalStorage() if settings.storage_backend == "local" else ExternalObjectStorage()
