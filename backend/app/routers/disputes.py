from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, Booking, BookingStatus, Dispute, ProfessionalProfile, Notification

router=APIRouter()
class DisputeIn(BaseModel):
    reason:str=Field(min_length=5,max_length=500)
    details:str=Field(min_length=5,max_length=5000)

async def owned(booking_id,user,db):
    b=await db.scalar(select(Booking).where(Booking.id==booking_id)); p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not b or (b.customer_id!=user.id and (not p or b.professional_id!=p.id)): raise HTTPException(404,"Booking not found")
    return b

@router.post("/{booking_id}",status_code=201)
async def open_dispute(booking_id:UUID,data:DisputeIn,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    b=await owned(booking_id,user,db)
    if b.status in [BookingStatus.cancelled,BookingStatus.refunded]: raise HTTPException(400,"Booking is closed")
    existing=await db.scalar(select(Dispute).where(Dispute.booking_id==b.id,Dispute.status.in_(["open","reviewing"])))
    if existing: raise HTTPException(409,"An active dispute already exists")
    d=Dispute(id=uuid4(),booking_id=b.id,opened_by=user.id,reason=data.reason,details=data.details,status="open")
    db.add(d); b.status=BookingStatus.disputed
    other=b.customer_id if user.id!=b.customer_id else None
    if other: db.add(Notification(user_id=other,booking_id=b.id,type="dispute",title="Booking disputed",body="A dispute was opened on this booking."))
    await db.commit(); await db.refresh(d)
    return {"id":str(d.id),"status":d.status}

@router.get("/{booking_id}")
async def get_dispute(booking_id:UUID,user:User=Depends(current_user),db:AsyncSession=Depends(get_db)):
    b=await owned(booking_id,user,db); d=await db.scalar(select(Dispute).where(Dispute.booking_id==b.id).order_by(Dispute.created_at.desc()))
    if not d: raise HTTPException(404,"No dispute found")
    return {"id":str(d.id),"status":d.status,"reason":d.reason,"details":d.details,"resolution":d.resolution,"created_at":d.created_at}
