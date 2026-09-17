from uuid import UUID, uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, Booking, BookingStatus, ProfessionalProfile
from pydantic import BaseModel, Field

router = APIRouter()

class UpdateIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=5000)
    status: str = "update"

async def get_owned_booking(booking_id: UUID, user: User, db: AsyncSession):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id))
    if not b: raise HTTPException(404, "Booking not found")
    p = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if b.customer_id != user.id and (not p or b.professional_id != p.id): raise HTTPException(403, "Not allowed")
    return b

@router.get("/{booking_id}")
async def get_project(booking_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    b = await get_owned_booking(booking_id, user, db)
    updates = db.execute
    from ..models import ProjectUpdate
    rows = (await db.scalars(select(ProjectUpdate).where(ProjectUpdate.booking_id == b.id).order_by(ProjectUpdate.created_at))).all()
    return {"booking_id": str(b.id), "status": b.status.value, "title": f"Project {str(b.id)[:8]}",
            "starts_at": b.starts_at, "ends_at": b.ends_at,
            "updates": [{"id":str(x.id),"title":x.title,"body":x.body,"status":x.status,"created_at":x.created_at} for x in rows]}

@router.post("/{booking_id}/updates", status_code=201)
async def add_update(booking_id: UUID, data: UpdateIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    b = await get_owned_booking(booking_id, user, db)
    if b.status in [BookingStatus.cancelled, BookingStatus.refunded]: raise HTTPException(400, "Project is closed")
    from ..models import ProjectUpdate
    item = ProjectUpdate(id=uuid4(), booking_id=b.id, author_id=user.id, title=data.title, body=data.body, status=data.status)
    db.add(item); await db.commit(); await db.refresh(item)
    return {"id":str(item.id),"title":item.title,"body":item.body,"status":item.status,"created_at":item.created_at}
