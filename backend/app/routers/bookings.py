from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user, require_role
from ..models import User, Service, Booking, BookingStatus, Conversation, ConversationMember, ProfessionalProfile, Notification
from ..schemas import BookingIn
from ..payment_transitions import PaymentTransitionError, ensure_booking_payment_paid

router = APIRouter()

@router.post("", status_code=201)
async def create_booking(data: BookingIn, user: User = Depends(require_role("customer")), db: AsyncSession = Depends(get_db)):
    service = await db.scalar(select(Service).where(Service.id == data.service_id, Service.professional_id == data.professional_id, Service.is_active.is_(True)))
    if not service:
        raise HTTPException(404, "Service not found")
    if data.ends_at and data.ends_at <= data.starts_at:
        raise HTTPException(400, "Invalid booking interval")

    # MVP overlap guard. Production should also add a PostgreSQL exclusion constraint.
    if data.ends_at:
        conflict = await db.scalar(select(Booking).where(
            Booking.professional_id == data.professional_id,
            Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed, BookingStatus.in_progress]),
            Booking.starts_at < data.ends_at,
            Booking.ends_at > data.starts_at
        ))
        if conflict:
            raise HTTPException(409, "Time slot is already booked")

    booking = Booking(customer_id=user.id, professional_id=data.professional_id,
                      service_id=data.service_id, starts_at=data.starts_at,
                      ends_at=data.ends_at, total_ngn=service.price_ngn,
                      customer_note=data.customer_note, status=BookingStatus.pending)
    db.add(booking)
    await db.flush()

    conversation = Conversation(booking_id=booking.id)
    db.add(conversation)
    await db.flush()
    db.add_all([
        ConversationMember(conversation_id=conversation.id, user_id=user.id),
    ])
    # Professional user membership is added by looking up the profile owner.
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.id == data.professional_id))
    if profile:
        db.add(ConversationMember(conversation_id=conversation.id, user_id=profile.user_id))
    db.add(Notification(user_id=profile.user_id, booking_id=booking.id, type="booking", title="New booking request", body=f"You received a new booking request for ₦{booking.total_ngn:,}.")) if profile else None
    db.add(Notification(user_id=user.id, booking_id=booking.id, type="booking", title="Booking request sent", body="Your booking request is waiting for the professional to respond."))
    await db.commit()
    return {"id": str(booking.id), "status": booking.status.value, "total_ngn": booking.total_ngn, "conversation_id": str(conversation.id)}

@router.get("")
async def list_bookings(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Booking).where(
        (Booking.customer_id == user.id) | (Booking.professional_id.in_(
            select(ProfessionalProfile.id).where(ProfessionalProfile.user_id == user.id)
        ))
    ).order_by(Booking.created_at.desc()))).all()
    return [{"id": str(b.id), "status": b.status.value, "starts_at": b.starts_at,
             "ends_at": b.ends_at, "total_ngn": b.total_ngn,
             "service_id": str(b.service_id), "professional_id": str(b.professional_id)} for b in rows]

@router.get("/{booking_id}")
async def get_booking(booking_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id))
    if not b:
        raise HTTPException(404, "Booking not found")
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if b.customer_id != user.id and (not profile or b.professional_id != profile.id):
        raise HTTPException(403, "Not allowed to view this booking")
    return {"id": str(b.id), "status": b.status.value, "starts_at": b.starts_at,
            "ends_at": b.ends_at, "total_ngn": b.total_ngn, "customer_note": b.customer_note}

@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: UUID, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id, Booking.customer_id == user.id))
    if not b:
        raise HTTPException(404, "Booking not found")
    if b.status in [BookingStatus.completed, BookingStatus.cancelled]:
        raise HTTPException(400, "Booking cannot be cancelled")
    b.status = BookingStatus.cancelled
    await db.commit()
    return {"id": str(b.id), "status": b.status.value}

@router.post("/{booking_id}/complete")
async def complete_booking(booking_id: UUID, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    b = await db.scalar(select(Booking).where(Booking.id == booking_id))
    profile = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if not b or not profile or b.professional_id != profile.id:
        raise HTTPException(404, "Booking not found")
    b.status = BookingStatus.completed
    db.add(Notification(user_id=b.customer_id, booking_id=b.id, type="booking", title="Project completed", body="Your professional marked the project as completed."))
    await db.commit()
    return {"id": str(b.id), "status": b.status.value}


@router.post("/{booking_id}/confirm")
async def confirm_booking(booking_id: UUID, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    b=await db.scalar(select(Booking).where(Booking.id==booking_id))
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not b or not p or b.professional_id!=p.id: raise HTTPException(404,"Booking not found")
    if b.status!=BookingStatus.pending: raise HTTPException(400,"Booking is not pending")
    b.status=BookingStatus.confirmed; db.add(Notification(user_id=b.customer_id, booking_id=b.id, type="booking", title="Booking confirmed", body="Your professional accepted the booking request.")); await db.commit(); return {"id":str(b.id),"status":b.status.value}

@router.post("/{booking_id}/decline")
async def decline_booking(booking_id: UUID, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    b=await db.scalar(select(Booking).where(Booking.id==booking_id))
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not b or not p or b.professional_id!=p.id: raise HTTPException(404,"Booking not found")
    if b.status not in [BookingStatus.pending,BookingStatus.confirmed]: raise HTTPException(400,"Booking cannot be declined")
    b.status=BookingStatus.cancelled; db.add(Notification(user_id=b.customer_id, booking_id=b.id, type="booking", title="Booking declined", body="The professional declined this booking request.")); await db.commit(); return {"id":str(b.id),"status":b.status.value}

@router.post("/{booking_id}/start")
async def start_booking(booking_id: UUID, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    b=await db.scalar(select(Booking).where(Booking.id==booking_id)); p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not b or not p or b.professional_id!=p.id: raise HTTPException(404,"Booking not found")
    if b.status!=BookingStatus.confirmed: raise HTTPException(400,"Booking must be confirmed")
    try:
        await ensure_booking_payment_paid(db, b.id)
    except PaymentTransitionError as exc:
        raise HTTPException(400, str(exc)) from exc
    b.status=BookingStatus.in_progress; db.add(Notification(user_id=b.customer_id, booking_id=b.id, type="booking", title="Project started", body="Your professional marked the project as in progress.")); await db.commit(); return {"id":str(b.id),"status":b.status.value}
