"""Verification of Sign in with Apple identity tokens.

The raw Apple identity token is only handled in memory and is never logged or
stored. Apple publishes rotating RSA keys, so the verifier caches JWKS briefly
and refreshes immediately when a previously unknown key id is encountered.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections.abc import Awaitable, Callable

import httpx
from jose import JWTError, jwk, jwt

from .config import settings


class AppleAuthError(ValueError):
    """A safe, client-facing Apple authentication failure."""


class AppleJWKSCache:
    def __init__(self, ttl_seconds: int = 21600):
        self.ttl_seconds = ttl_seconds
        self._keys: dict[str, dict] = {}
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def _fetch(self) -> dict[str, dict]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.apple_jwks_url)
            response.raise_for_status()
            payload = response.json()
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list) or not keys:
            raise AppleAuthError("Apple signing keys are unavailable")
        parsed = {item.get("kid"): item for item in keys if isinstance(item, dict) and item.get("kid")}
        if not parsed:
            raise AppleAuthError("Apple signing keys are unavailable")
        self._keys = parsed
        self._fetched_at = time.monotonic()
        return parsed

    async def keys(self, force_refresh: bool = False) -> dict[str, dict]:
        async with self._lock:
            if force_refresh or not self._keys or time.monotonic() - self._fetched_at >= self.ttl_seconds:
                return await self._fetch()
            return self._keys


_jwks_cache = AppleJWKSCache()


async def verify_apple_identity(
    identity_token: str,
    raw_nonce: str,
    *,
    key_cache: AppleJWKSCache | None = None,
    jwks_fetcher: Callable[[], Awaitable[dict[str, dict]]] | None = None,
) -> dict:
    if not settings.apple_client_id:
        raise AppleAuthError("Apple sign-in is not configured")
    if not identity_token or not raw_nonce:
        raise AppleAuthError("Apple identity token and nonce are required")
    try:
        header = jwt.get_unverified_header(identity_token)
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise AppleAuthError("Apple identity token is invalid")
        cache = key_cache or _jwks_cache
        keys = await jwks_fetcher() if jwks_fetcher else await cache.keys()
        key_data = keys.get(header["kid"])
        if key_data is None and not jwks_fetcher:
            keys = await cache.keys(force_refresh=True)
            key_data = keys.get(header["kid"])
        if key_data is None:
            raise AppleAuthError("Apple signing key is unavailable")
        signing_key = jwk.construct(key_data, algorithm="RS256")
        claims = jwt.decode(
            identity_token,
            signing_key,
            algorithms=["RS256"],
            audience=settings.apple_client_id,
            issuer=settings.apple_issuer,
            options={"require_sub": True, "require_exp": True, "require_iat": True, "require_aud": True, "require_iss": True},
        )
        token_nonce = claims.get("nonce")
        expected_nonce = hashlib.sha256(raw_nonce.encode("utf-8")).hexdigest()
        if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, expected_nonce):
            raise AppleAuthError("Apple nonce is invalid")
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise AppleAuthError("Apple subject is invalid")
        if "email" in claims and claims["email"] is not None and not isinstance(claims["email"], str):
            raise AppleAuthError("Apple email claim is invalid")
        if "name" in claims and claims["name"] is not None and not isinstance(claims["name"], str):
            raise AppleAuthError("Apple name claim is invalid")
        return claims
    except AppleAuthError:
        raise
    except (JWTError, KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
        raise AppleAuthError("Apple identity token is invalid") from exc
