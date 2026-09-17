import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.apns import send_notification
from app.storage import ExternalObjectStorage, LocalStorage, StorageError
from app.config import Settings


class Phase8ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_storage_provider_round_trip(self):
        with tempfile.TemporaryDirectory() as directory, patch("app.storage.settings.upload_dir", directory):
            storage = LocalStorage()
            await storage.put("test.bin", b"data", "application/octet-stream")
            self.assertEqual(storage.download_path("test.bin").read_bytes(), b"data")

    async def test_apns_disabled_is_safe_noop(self):
        with patch("app.apns.settings.apns_enabled", False):
            await send_notification("token", "Title", "Body")

    def test_external_storage_requires_configuration(self):
        with patch("app.storage.settings.object_storage_bucket", ""), patch("app.storage.settings.object_storage_endpoint", ""):
            with self.assertRaises(StorageError): ExternalObjectStorage()

    def test_postgresql_url_is_normalized_for_asyncpg(self):
        plain = Settings(database_url="postgresql://user:pass@example.test:5432/db?sslmode=require")
        asyncpg = Settings(database_url="postgresql+asyncpg://user:pass@example.test:5432/db?sslmode=require")
        self.assertEqual(plain.database_url, "postgresql+asyncpg://user:pass@example.test:5432/db?sslmode=require")
        self.assertEqual(asyncpg.database_url, "postgresql+asyncpg://user:pass@example.test:5432/db?sslmode=require")


if __name__ == "__main__": unittest.main()
