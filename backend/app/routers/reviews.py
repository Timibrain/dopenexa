from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, Booking, BookingStatus, Review, ProfessionalProfile
from ..schemas import ReviewIn

router = APIRouter()

@router.post("", status_code=201)
async def create_review(data: ReviewIn, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    booking = await db.scalar(select(Booking).where(Booking.id == data.booking_id, Booking.customer_id == user.id))
    if not booking or booking.status != BookingStatus.completed:
        raise HTTPException(400, "Only completed bookings can be reviewed")
    existing = await db.scalar(select(Review).where(Review.booking_id == booking.id))
    if existing: raise HTTPException(409, "Booking already reviewed")
    review = Review(booking_id=booking.id, customer_id=user.id, professional_id=booking.professional_id, rating=data.rating, body=data.body)
    db.add(review)
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.id == booking.professional_id))
    if profile:
        count = profile.review_count or 0
        profile.average_rating = ((float(profile.average_rating or 0) * count) + data.rating) / (count + 1)
        profile.review_count = count + 1
    await db.commit(); await db.refresh(review)
    return {"id": str(review.id), "rating": review.rating}

@router.get("/professional/{professional_id}")
async def professional_reviews(professional_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Review).where(Review.professional_id == professional_id).order_by(Review.created_at.desc()))).all()
    return [{"id":str(r.id),"booking_id":str(r.booking_id),"rating":r.rating,"body":r.body,"created_at":r.created_at} for r in rows]
