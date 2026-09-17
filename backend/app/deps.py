from uuid import UUID
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .db import get_db
from .models import User
from .security import decode_token

async def current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    user_id = UUID(decode_token(authorization.removeprefix("Bearer ").strip()))
    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(401, "User not found")
    return user

def require_role(*roles: str):
    async def checker(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Insufficient role")
        return user
    return checker
