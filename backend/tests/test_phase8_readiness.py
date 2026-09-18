import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.apns import send_notification
from app.storage import ExternalObjectStorage, LocalStorage, StorageError, validate_object_key
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

    async def test_s3_upload_delete_and_presigned_download(self):
        class FakeS3:
            def __init__(self): self.calls=[]
            def put_object(self, **kwargs): self.calls.append(("put", kwargs)); return {}
            def delete_object(self, **kwargs): self.calls.append(("delete", kwargs)); return {}
            def generate_presigned_url(self, *args, **kwargs): self.calls.append(("sign", args, kwargs)); return "https://objects.example/signed"
        with patch.multiple("app.storage.settings", object_storage_bucket="bucket", object_storage_endpoint="https://r2.example", object_storage_access_key="access", object_storage_secret_key="secret"):
            fake=FakeS3(); storage=ExternalObjectStorage(client=fake)
            self.assertEqual(await storage.put("attachments/file.pdf", b"data", "application/pdf"), "attachments/file.pdf")
            self.assertEqual(await storage.download_url("attachments/file.pdf"), "https://objects.example/signed")
            await storage.delete("attachments/file.pdf")
            self.assertEqual(fake.calls[0][1]["ContentType"], "application/pdf")
            self.assertEqual([call[0] for call in fake.calls], ["put", "sign", "delete"])

    def test_s3_keys_reject_traversal(self):
        with self.assertRaises(StorageError): validate_object_key("../private.txt")

    def test_postgresql_url_is_normalized_for_asyncpg(self):
        plain = Settings(database_url="postgresql://user:pass@example.test:5432/db?sslmode=require")
        asyncpg = Settings(database_url="postgresql+asyncpg://user:pass@example.test:5432/db?sslmode=require")
        self.assertEqual(plain.database_url, "postgresql+asyncpg://user:pass@example.test:5432/db?sslmode=require")
        self.assertEqual(asyncpg.database_url, "postgresql+asyncpg://user:pass@example.test:5432/db?sslmode=require")


if __name__ == "__main__": unittest.main()
