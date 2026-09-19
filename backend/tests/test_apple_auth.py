import hashlib
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from jose import jwt

from app.apple_auth import AppleAuthError, AppleJWKSCache, verify_apple_identity
from app.models import AuthIdentity, Role, User
from app.routers.auth import apple_login
from app.schemas import AppleAuthIn


class AppleVerifierTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from jose.utils import base64url_encode

        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public = cls.private_key.public_key().public_numbers()
        cls.jwk = {
            "kty": "RSA", "kid": "test-key", "use": "sig", "alg": "RS256",
            "n": base64url_encode(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")).decode(),
            "e": base64url_encode(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big")).decode(),
        }

    def token(self, **changes):
        nonce = "client-generated-nonce"
        claims = {
            "iss": "https://appleid.apple.com", "aud": "com.dopenexa.app",
            "sub": "apple-subject-1", "exp": 4102444800, "iat": 1700000000,
            "nonce": hashlib.sha256(nonce.encode()).hexdigest(), "email": "apple@example.com",
        }
        claims.update(changes)
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "test-key"}), nonce

    async def verify(self, token, nonce):
        with patch("app.apple_auth.settings.apple_client_id", "com.dopenexa.app"), \
             patch("app.apple_auth.settings.apple_issuer", "https://appleid.apple.com"):
            return await verify_apple_identity(token, nonce, jwks_fetcher=AsyncMock(return_value={"test-key": self.jwk}))

    async def test_valid_token_and_security_claims(self):
        token, nonce = self.token()
        claims = await self.verify(token, nonce)
        self.assertEqual(claims["sub"], "apple-subject-1")
        for changes in (
            {"iss": "https://evil.example"}, {"aud": "other.app"},
            {"exp": 1}, {"nonce": "wrong"},
        ):
            with self.subTest(changes=changes), self.assertRaises(AppleAuthError):
                await self.verify(*self.token(**changes))

    async def test_invalid_signature_and_unknown_key(self):
        token, nonce = self.token()
        from cryptography.hazmat.primitives.asymmetric import rsa
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        invalid = jwt.encode(jwt.get_unverified_claims(token), other, algorithm="RS256", headers={"kid": "test-key"})
        with self.assertRaises(AppleAuthError):
            await self.verify(invalid, nonce)
        with patch("app.apple_auth.settings.apple_client_id", "com.dopenexa.app"), self.assertRaises(AppleAuthError):
            await verify_apple_identity(token, nonce, jwks_fetcher=AsyncMock(return_value={}))


class FakeSession:
    def __init__(self, scalar_values):
        self.scalar_values = list(scalar_values)
        self.added = []
        self.commits = 0

    async def scalar(self, _query):
        return self.scalar_values.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, User) and value.id is None:
                value.id = uuid.uuid4()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


class AppleEndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.claims = {"sub": "stable-sub", "email": "stable@example.com"}
        self.data = AppleAuthIn(identity_token="a" * 32, nonce="n" * 16, role=Role.customer)

    async def test_new_customer_and_professional_roles(self):
        for role in (Role.customer, Role.professional):
            with self.subTest(role=role), patch("app.routers.auth.verify_apple_identity", new=AsyncMock(return_value=self.claims)):
                db = FakeSession([None, None])
                result = await apple_login(self.data.model_copy(update={"role": role}), db)
                user = next(item for item in db.added if isinstance(item, User))
                identity = next(item for item in db.added if isinstance(item, AuthIdentity))
                self.assertEqual(user.role, role)
                self.assertEqual(identity.provider_subject, "stable-sub")
                self.assertTrue(result.access_token)

    async def test_existing_identity_ignores_role_change(self):
        user = User(id=uuid.uuid4(), email="old@example.com", password_hash=None, display_name="Old", role=Role.customer)
        identity = AuthIdentity(user_id=user.id, provider="apple", provider_subject="stable-sub")
        with patch("app.routers.auth.verify_apple_identity", new=AsyncMock(return_value=self.claims)):
            result = await apple_login(self.data.model_copy(update={"role": Role.professional}), FakeSession([identity, user]))
        self.assertTrue(result.access_token)
        self.assertEqual(user.role, Role.customer)

    def test_migration_has_unique_provider_subject(self):
        from scripts import verify_staging
        table = verify_staging.load_schema().tables["auth_identities"]
        self.assertTrue(any(name == "auth_identities_provider_subject_key" for name, _ in table.constraints))


if __name__ == "__main__":
    unittest.main()
