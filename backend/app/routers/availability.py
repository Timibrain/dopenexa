from datetime import datetime, date, time, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import require_role
from ..models import User, ProfessionalProfile, Availability, Booking, BookingStatus
from ..schemas import AvailabilityIn

router = APIRouter()

@router.post("/me", status_code=201)
async def create_availability(data: AvailabilityIn, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if not profile:
        return {"error": "Create your professional profile first"}
    row = Availability(professional_id=profile.id, weekday=data.weekday, start_time=data.start_time, end_time=data.end_time)
    db.add(row); await db.commit(); await db.refresh(row)
    return {"id": str(row.id)}

@router.post("/check")
async def check_slot(professional_id: UUID, starts_at: datetime, ends_at: datetime, db: AsyncSession = Depends(get_db)):
    weekday = starts_at.weekday()
    rows = (await db.scalars(select(Availability).where(Availability.professional_id == professional_id, Availability.weekday == weekday))).all()
    inside = any(r.start_time <= starts_at.timetz().replace(tzinfo=None) and r.end_time >= ends_at.timetz().replace(tzinfo=None) for r in rows)
    if not inside: return {"available": False, "reason": "Outside working hours"}
    conflict = await db.scalar(select(Booking).where(
        Booking.professional_id == professional_id,
        Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed, BookingStatus.in_progress]),
        Booking.starts_at < ends_at, Booking.ends_at > starts_at
    ))
    return {"available": conflict is None, "reason": None if conflict is None else "Already booked"}

@router.get("/slots")
async def slots(professional_id: UUID, date: date, duration_minutes: int = 60, db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Availability).where(Availability.professional_id == professional_id, Availability.weekday == date.weekday()))).all()
    bookings = (await db.scalars(select(Booking).where(
        Booking.professional_id == professional_id,
        Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed, BookingStatus.in_progress]),
        Booking.starts_at < datetime.combine(date, time.max, tzinfo=timezone.utc),
        or_(Booking.ends_at.is_(None), Booking.ends_at > datetime.combine(date, time.min, tzinfo=timezone.utc))
    ))).all()
    result=[]
    for window in rows:
        cursor=datetime.combine(date, window.start_time, tzinfo=timezone.utc)
        finish=datetime.combine(date, window.end_time, tzinfo=timezone.utc)
        while cursor + timedelta(minutes=duration_minutes) <= finish:
            end=cursor+timedelta(minutes=duration_minutes)
            conflict=any(b.starts_at < end and b.ends_at and b.ends_at > cursor for b in bookings)
            if not conflict and cursor > datetime.now(timezone.utc): result.append({"starts_at":cursor.isoformat(),"ends_at":end.isoformat()})
            cursor += timedelta(minutes=30)
    return result
