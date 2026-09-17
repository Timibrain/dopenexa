from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, Notification

router = APIRouter()

@router.get("")
async def list_notifications(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50))).all()
    return [{"id":str(n.id),"title":n.title,"body":n.body,"type":n.type,"is_read":n.is_read,"created_at":n.created_at,"booking_id":str(n.booking_id) if n.booking_id else None} for n in rows]

@router.post("/{notification_id}/read")
async def mark_read(notification_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    n = await db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if not n: raise HTTPException(404, "Notification not found")
    n.is_read = True; await db.commit(); return {"id":str(n.id),"is_read":True}
