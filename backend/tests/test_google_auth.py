import unittest
import uuid
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from jose import jwt
from app.google_auth import GoogleAuthError, verify_google_identity
from app.models import AuthIdentity, Role, User
from app.routers.auth import GoogleAuthIn, google_login
import test_apple_auth as fixtures


class GoogleVerifierTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.AppleVerifierTests.setUpClass()
        cls.key = fixtures.AppleVerifierTests.private_key
        cls.jwk = fixtures.AppleVerifierTests.jwk

    async def verify(self, changes=None, consumed='nonce'):
        claims = {'iss': 'https://accounts.google.com', 'aud': 'web-client', 'sub': 'google-sub',
            'iat': 1700000000, 'exp': 4102444800, 'nonce': 'nonce', 'email': 'member@gmail.com', 'email_verified': True}
        claims.update(changes or {})
        token = jwt.encode(claims, self.key, algorithm='RS256', headers={'kid': 'test-key'})
        redis = AsyncMock()
        redis.__aenter__.return_value = redis
        redis.get.return_value = 'nonce'
        redis.getdel.return_value = consumed
        cache = AsyncMock()
        cache.keys.return_value = {'test-key': self.jwk}
        with patch('app.google_auth.settings.google_client_id', 'web-client'), patch('app.google_auth.redis.from_url', return_value=redis):
            return await verify_google_identity(token, 'c' * 43, key_cache=cache)

    async def test_valid_and_alternate_issuer(self):
        self.assertEqual((await self.verify())['sub'], 'google-sub')
        await self.verify({'iss': 'accounts.google.com'})

    async def test_reject_invalid_claims(self):
        for change in ({'aud': 'evil'}, {'iss': 'evil'}, {'exp': 1}, {'nonce': 'wrong'},
            {'azp': 'evil'}, {'iat': 4102444800}, {'email_verified': False}, {'email': 'invalid'}, {'sub': ''}):
            with self.subTest(change=change), self.assertRaises(GoogleAuthError):
                await self.verify(change)

    async def test_replay_rejected(self):
        with self.assertRaises(GoogleAuthError):
            await self.verify(consumed=None)


class GoogleEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, values, role="customer"):
        self.db = fixtures.FakeSession(values)
        with patch('app.routers.auth.verify_google_identity', new=AsyncMock(return_value={'sub': 'google-sub', 'email': 'member@gmail.com', 'name': 'Member'})):
            return await google_login(GoogleAuthIn(credential='credential', challenge='c' * 43, role=role), self.db)

    async def test_new_account_is_customer(self):
        result = await self.call([None, None])
        user = next(x for x in self.db.added if isinstance(x, User))
        self.assertEqual(user.role, Role.customer)
        self.assertIsNone(user.password_hash)
        self.assertTrue(result.access_token)
        self.assertTrue(any(isinstance(x, AuthIdentity) and x.provider == 'google' for x in self.db.added))

    async def test_professional_and_explicit_choice(self):
        await self.call([None, None], role="professional")
        user = next(x for x in self.db.added if isinstance(x, User))
        self.assertEqual(user.role, Role.professional)
        with self.assertRaises(HTTPException) as caught:
            await self.call([None, None], role=None)
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.db.commits, 0)

    async def test_preserves_professional_role(self):
        user = User(id=uuid.uuid4(), role=Role.professional)
        await self.call([AuthIdentity(user_id=user.id), user])
        self.assertEqual(user.role, Role.professional)

    async def test_inactive_and_email_collision(self):
        for values, status in (([AuthIdentity(user_id=uuid.uuid4()), None], 401), ([None, User()], 409)):
            with self.subTest(status=status), self.assertRaises(HTTPException) as caught:
                await self.call(values)
            self.assertEqual(caught.exception.status_code, status)
            self.assertEqual(self.db.commits, 0)
