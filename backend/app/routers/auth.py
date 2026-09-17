from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..models import User, RefreshSession
from ..deps import current_user
from ..schemas import RegisterIn, LoginIn, TokenOut
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
    if not user or not verify_password(data.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    result = issue_tokens(user, db); await db.commit(); return result

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
