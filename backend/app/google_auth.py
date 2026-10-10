"""Google credentials bound to a short-lived, single-use server challenge."""
import hmac
import secrets
import time

import httpx
import redis.asyncio as redis
from jose import JWTError, jwk, jwt
from pydantic import EmailStr, TypeAdapter

from .apple_auth import AppleJWKSCache
from .config import settings


class GoogleAuthError(ValueError):
    pass


class GoogleKeys(AppleJWKSCache):
    async def _fetch(self):
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get('https://www.googleapis.com/oauth2/v3/certs')
            response.raise_for_status()
        payload = response.json()
        keys = {item['kid']: item for item in payload.get('keys', []) if isinstance(item, dict) and item.get('kid')}
        if not keys:
            raise GoogleAuthError('Google signing keys are unavailable')
        self._keys, self._fetched_at = keys, time.monotonic()
        return keys


_keys = GoogleKeys(ttl_seconds=3600)


async def create_google_challenge():
    if not settings.google_client_id:
        raise GoogleAuthError('Google sign-in is not configured')
    challenge, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    async with redis.from_url(settings.redis_url, decode_responses=True) as client:
        await client.set('dpx:google:' + challenge, nonce, ex=300, nx=True)
    return {'challenge': challenge, 'nonce': nonce, 'client_id': settings.google_client_id, 'expires_in': 300}


async def verify_google_identity(credential: str, challenge: str, *, key_cache=None):
    if not settings.google_client_id:
        raise GoogleAuthError('Google sign-in is not configured')
    try:
        async with redis.from_url(settings.redis_url, decode_responses=True) as client:
            nonce = await client.get('dpx:google:' + challenge)
        if not nonce:
            raise GoogleAuthError('Google sign-in expired. Please try again.')
        header = jwt.get_unverified_header(credential)
        if header.get('alg') != 'RS256' or not header.get('kid'):
            raise GoogleAuthError('Google credential is invalid')
        cache = key_cache or _keys
        keys = await cache.keys()
        if header['kid'] not in keys:
            keys = await cache.keys(force_refresh=True)
        claims = jwt.decode(credential, jwk.construct(keys[header['kid']], algorithm='RS256'),
            algorithms=['RS256'], audience=settings.google_client_id,
            issuer=['https://accounts.google.com', 'accounts.google.com'],
            options={'require_sub': True, 'require_exp': True, 'require_iat': True, 'require_aud': True, 'require_iss': True})
        if claims.get('azp', settings.google_client_id) != settings.google_client_id or claims['iat'] > time.time() + 60:
            raise GoogleAuthError('Google credential is invalid')
        if not isinstance(claims.get('nonce'), str) or not hmac.compare_digest(claims['nonce'], nonce):
            raise GoogleAuthError('Google sign-in challenge is invalid')
        if claims.get('email_verified') is not True:
            raise GoogleAuthError('Google email must be verified')
        if not isinstance(claims.get('sub'), str) or not 0 < len(claims['sub']) <= 255:
            raise GoogleAuthError('Google account is invalid')
        claims['email'] = str(TypeAdapter(EmailStr).validate_python(claims.get('email')))
        if claims.get('name') is not None and not isinstance(claims['name'], str):
            raise GoogleAuthError('Google account name is invalid')
        # Atomic consumption prevents simultaneous requests replaying a credential.
        async with redis.from_url(settings.redis_url, decode_responses=True) as client:
            consumed = await client.getdel('dpx:google:' + challenge)
        if consumed != nonce:
            raise GoogleAuthError('Google sign-in expired. Please try again.')
        return claims
    except GoogleAuthError:
        raise
    except (JWTError, KeyError, TypeError, ValueError, httpx.HTTPError) as exc:
        raise GoogleAuthError('Google credential is invalid') from exc
