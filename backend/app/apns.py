"""Provider-neutral APNs boundary. Credentials remain environment-only."""
import time
import httpx
from jose import jwt
from .config import settings

class APNSError(RuntimeError): pass

async def send_notification(device_token: str, title: str, body: str, *, topic: str | None = None) -> None:
    if not settings.apns_enabled:
        return
    if not all((settings.apns_team_id, settings.apns_key_id, settings.apns_bundle_id, settings.apns_private_key)):
        raise APNSError("APNs is enabled but not configured")
    try:
        token = jwt.encode({"iss": settings.apns_team_id, "iat": int(time.time())}, settings.apns_private_key, algorithm="ES256", headers={"kid": settings.apns_key_id})
        host = "https://api.push.apple.com" if settings.environment == "production" else "https://api.sandbox.push.apple.com"
        async with httpx.AsyncClient(http2=True, timeout=15) as client:
            response = await client.post(f"{host}/3/device/{device_token}", headers={"authorization": f"bearer {token}", "apns-topic": topic or settings.apns_bundle_id, "content-type": "application/json"}, json={"aps": {"alert": {"title": title, "body": body}, "sound": "default"}})
        if response.status_code >= 300: raise APNSError("APNs rejected notification")
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise APNSError("APNs notification failed") from exc
