import unittest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.main import HealthcheckHostMiddleware
from app.config import settings


class HealthcheckHostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        settings.trusted_hosts = "staging.example.com"
        self.app = FastAPI()
        @self.app.get("/health")
        async def health(): return {"status": "ok"}
        @self.app.get("/ready")
        async def ready(): return {"status": "ready"}
        @self.app.get("/private")
        async def private(): return {"private": True}
        self.app.add_middleware(TrustedHostMiddleware, allowed_hosts=["staging.example.com"])
        self.app.add_middleware(HealthcheckHostMiddleware)

    async def test_health_and_ready_allow_internal_host(self):
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test") as client:
            self.assertEqual((await client.get("/health", headers={"host": "railway.internal"})).status_code, 200)
            self.assertEqual((await client.get("/ready", headers={"host": "railway.internal"})).status_code, 200)

    async def test_normal_route_rejects_untrusted_host(self):
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url="http://test") as client:
            self.assertEqual((await client.get("/private", headers={"host": "railway.internal"})).status_code, 400)


if __name__ == "__main__": unittest.main()
