from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..models import AuthIdentity, User, RefreshSession, Role
from ..deps import current_user
from ..schemas import AppleAuthIn, RegisterIn, LoginIn, TokenOut
from ..apple_auth import AppleAuthError, verify_apple_identity
from ..security import hash_password, verify_password, access_token, refresh_token, decode_token, token_hash
from ..config import settings

router = APIRouter()

class RefreshIn(BaseModel):
    refresh_token: str

def issue_tokens(user: User, db: AsyncSession):
    at = access_token(str(user.id)); rt = refresh_token(str(user.id))
    db.add(RefreshSession(user_id=user.id, token_hash=token_hash(rt), expires_at=datetime.now(timezone.utc)+timedelta(days=settings.refresh_token_days)))
    return TokenOut(access_token=at, refresh_token=rt)

@router.post("/register", response_model=TokenOut, status_code=201)
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing: raise HTTPException(409, "Email already registered")
    user = User(email=data.email, password_hash=hash_password(data.password), display_name=data.display_name, role=data.role)
    db.add(user); await db.flush()
    result = issue_tokens(user, db); await db.commit()
    return result

@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == data.email))
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    result = issue_tokens(user, db); await db.commit(); return result


@router.post("/apple", response_model=TokenOut)
async def apple_login(data: AppleAuthIn, db: AsyncSession = Depends(get_db)):
    """Authenticate an Apple identity and link it to a Dopenexa account."""
    try:
        claims = await verify_apple_identity(data.identity_token, data.nonce)
    except AppleAuthError as exc:
        raise HTTPException(401, str(exc)) from exc

    subject = claims["sub"]
    identity = await db.scalar(select(AuthIdentity).where(
        AuthIdentity.provider == "apple", AuthIdentity.provider_subject == subject
    ))
    if identity:
        user = await db.scalar(select(User).where(User.id == identity.user_id, User.is_active.is_(True)))
        if not user:
            raise HTTPException(401, "Apple account is inactive")
        email = claims.get("email")
        if user.email is None and email:
            conflict = await db.scalar(select(User).where(User.email == email, User.id != user.id))
            if conflict:
                raise HTTPException(409, "Apple email is already linked to another account")
            user.email = email
        result = issue_tokens(user, db)
        await db.commit()
        return result

    if data.role not in {Role.customer, Role.professional}:
        raise HTTPException(422, "role is required for a new Apple account")

    email = claims.get("email")
    if email and await db.scalar(select(User).where(User.email == email)):
        # Never link an Apple identity to an account based on email alone.
        raise HTTPException(409, "Email already belongs to an account; sign in with that account first")
    display_name = claims.get("name") or (email.split("@", 1)[0] if email else "Dopenexa member")
    user = User(email=email, password_hash=None, display_name=display_name[:120], role=data.role)
    db.add(user)
    await db.flush()
    db.add(AuthIdentity(user_id=user.id, provider="apple", provider_subject=subject))
    try:
        result = issue_tokens(user, db)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        identity = await db.scalar(select(AuthIdentity).where(
            AuthIdentity.provider == "apple", AuthIdentity.provider_subject == subject
        ))
        if not identity:
            raise HTTPException(409, "Apple identity could not be linked")
        user = await db.scalar(select(User).where(User.id == identity.user_id, User.is_active.is_(True)))
        if not user:
            raise HTTPException(401, "Apple account is inactive")
        result = issue_tokens(user, db)
        await db.commit()
    return result

@router.post("/refresh", response_model=TokenOut)
async def refresh(data: RefreshIn, db: AsyncSession = Depends(get_db)):
    user_id = decode_token(data.refresh_token, "refresh")
    session = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash(data.refresh_token), RefreshSession.revoked_at.is_(None), RefreshSession.expires_at > datetime.now(timezone.utc)))
    if not session or str(session.user_id) != user_id: raise HTTPException(401, "Refresh session is invalid or revoked")
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user: raise HTTPException(401, "User not found")
    session.revoked_at = datetime.now(timezone.utc)
    result = issue_tokens(user, db); await db.commit(); return result

@router.post("/logout")
async def logout(data: RefreshIn, db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash(data.refresh_token), RefreshSession.revoked_at.is_(None)))
    if session: session.revoked_at = datetime.now(timezone.utc); await db.commit()
    return {"signed_out": True}

@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name, "role": user.role.value}
