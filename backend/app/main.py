from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import redis.asyncio as redis
from uuid import uuid4
import logging
from .config import settings
from .routers import auth, professionals, services, availability, bookings, payments, messaging, reviews, professional_workspace, ai, projects, notifications, disputes, attachments, devices, trust, payouts, saved, recommendations, realtime, reconciliation

app = FastAPI(title="Dopenexa API", version="0.1.0")
logging.basicConfig(level=getattr(logging, settings.logging_level.upper(), logging.INFO), format="%(message)s")
logger = logging.getLogger("dopenexa")

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed request_id=%s path=%s", request_id, request.url.path)
            raise
        response.headers["X-Request-ID"] = request_id
        return response

class HealthcheckHostMiddleware(BaseHTTPMiddleware):
    """Allow infrastructure health probes before strict host validation.

    Only the health endpoints are normalized; application routes still pass
    through TrustedHostMiddleware unchanged.
    """
    paths = {"/health", "/ready"}
    async def dispatch(self, request, call_next):
        if request.url.path in self.paths and settings.trusted_host_list:
            headers = [(key, value) for key, value in request.scope["headers"] if key != b"host"]
            headers.append((b"host", settings.trusted_host_list[0].encode("ascii")))
            request.scope["headers"] = headers
        return await call_next(request)

app.add_middleware(RequestContextMiddleware)

class RateLimitMiddleware(BaseHTTPMiddleware):
    protected = ("/auth/login", "/auth/register", "/payments/create", "/payments/refund", "/payouts", "/admin/reconciliation", "/attachments")
    async def dispatch(self, request, call_next):
        if not settings.rate_limit_enabled or not any(request.url.path.startswith(path) for path in self.protected):
            return await call_next(request)
        key = f"dpx:rate:{request.client.host if request.client else 'unknown'}:{request.url.path}"
        try:
            client = redis.from_url(settings.redis_url, decode_responses=True)
            count = await client.incr(key)
            if count == 1: await client.expire(key, 60)
            await client.close()
            if count > settings.rate_limit_per_minute:
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        except Exception:
            logger.exception("rate_limit_backend_unavailable")
        return await call_next(request)

app.add_middleware(RateLimitMiddleware)
if settings.environment != "development":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    app.add_middleware(HealthcheckHostMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(professionals.router, prefix="/professionals", tags=["professionals"])
app.include_router(services.router, prefix="/services", tags=["services"])
app.include_router(availability.router, prefix="/availability", tags=["availability"])
app.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(messaging.router, prefix="/conversations", tags=["messaging"])
app.include_router(reviews.router, prefix="/reviews", tags=["reviews"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "dopenexa-api"}

@app.get("/ready")
async def ready():
    return {"status": "ready", "environment": settings.environment}

app.include_router(professional_workspace.router, prefix="/professional", tags=["professional workspace"])
app.include_router(ai.router, prefix="/ai", tags=["ai matching"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
app.include_router(disputes.router, prefix="/disputes", tags=["disputes"])
app.include_router(attachments.router, prefix="/attachments", tags=["attachments"])

app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(trust.router, prefix="/trust", tags=["trust"])
app.include_router(payouts.router, prefix="/payouts", tags=["payouts"])
app.include_router(reconciliation.router, prefix="/admin/reconciliation", tags=["reconciliation"])
app.include_router(saved.router, prefix="/saved", tags=["saved professionals"])
app.include_router(recommendations.router, prefix="/recommendations", tags=["recommendations"])

app.include_router(realtime.router, prefix="/realtime", tags=["realtime"])
