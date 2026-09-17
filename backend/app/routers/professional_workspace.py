from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException
from ..db import get_db
from ..deps import require_role
from ..models import User, ProfessionalProfile, Service, Availability, Booking, BookingStatus, Payment
from ..schemas import ProfileIn, ServiceIn, ServiceUpdateIn, AvailabilityIn

router = APIRouter()

async def profile_for(user, db):
    p = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if not p: raise HTTPException(400, "Create your professional profile first")
    return p

def service_dict(s):
    return {"id":str(s.id),"name":s.name,"description":s.description,"service_type":s.service_type.value,"price_ngn":s.price_ngn,"duration_minutes":s.duration_minutes,"is_active":s.is_active}

@router.get("/me")
async def get_me(user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p = await profile_for(user, db)
    return {"id":str(p.id),"name":user.display_name,"headline":p.headline,"bio":p.bio,"years_experience":p.years_experience,"service_area":p.service_area,"verification_status":p.verification_status,"average_rating":float(p.average_rating or 0),"review_count":p.review_count,"completed_jobs":p.completed_jobs,"onboarding_complete":p.onboarding_complete}

@router.put("/me")
async def update_me(data: ProfileIn, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if not p: p=ProfessionalProfile(user_id=user.id); db.add(p)
    p.headline,p.bio,p.years_experience,p.service_area = data.headline,data.bio,data.years_experience,data.service_area
    p.onboarding_complete=True
    await db.commit(); await db.refresh(p)
    return {"id":str(p.id),"onboarding_complete":p.onboarding_complete}

@router.get("/me/services")
async def my_services(user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db)
    rows=(await db.scalars(select(Service).where(Service.professional_id==p.id).order_by(Service.created_at.desc()))).all()
    return [service_dict(s) for s in rows]

@router.post("/me/services", status_code=201)
async def add_service(data: ServiceIn, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db); s=Service(professional_id=p.id,**data.model_dump()); db.add(s); await db.commit(); await db.refresh(s); return service_dict(s)

@router.patch("/me/services/{service_id}")
async def edit_service(service_id: UUID, data: ServiceUpdateIn, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db); s=await db.scalar(select(Service).where(Service.id==service_id,Service.professional_id==p.id))
    if not s: raise HTTPException(404,"Service not found")
    for k,v in data.model_dump(exclude_unset=True).items(): setattr(s,k,v)
    await db.commit(); await db.refresh(s); return service_dict(s)

@router.delete("/me/services/{service_id}")
async def remove_service(service_id: UUID, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db); s=await db.scalar(select(Service).where(Service.id==service_id,Service.professional_id==p.id))
    if not s: raise HTTPException(404,"Service not found")
    s.is_active=False; await db.commit(); return {"id":str(s.id),"is_active":False}

@router.get("/me/availability")
async def my_availability(user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db); rows=(await db.scalars(select(Availability).where(Availability.professional_id==p.id).order_by(Availability.weekday,Availability.start_time))).all()
    return [{"id":str(a.id),"weekday":a.weekday,"start_time":a.start_time,"end_time":a.end_time} for a in rows]

@router.post("/me/availability", status_code=201)
async def add_availability(data: AvailabilityIn, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    if data.end_time <= data.start_time: raise HTTPException(400,"End time must be after start time")
    p=await profile_for(user,db); a=Availability(professional_id=p.id,**data.model_dump()); db.add(a); await db.commit(); await db.refresh(a)
    return {"id":str(a.id),"weekday":a.weekday,"start_time":a.start_time,"end_time":a.end_time}

@router.delete("/me/availability/{availability_id}")
async def remove_availability(availability_id: UUID, user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db); a=await db.scalar(select(Availability).where(Availability.id==availability_id,Availability.professional_id==p.id))
    if not a: raise HTTPException(404,"Availability not found")
    await db.delete(a); await db.commit(); return {"id":str(a.id),"deleted":True}

@router.get("/me/dashboard")
async def dashboard(user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db)
    active=(await db.scalars(select(Booking).where(Booking.professional_id==p.id,Booking.status.in_([BookingStatus.pending,BookingStatus.confirmed,BookingStatus.in_progress])).order_by(Booking.starts_at))).all()
    completed=await db.scalar(select(func.count()).select_from(Booking).where(Booking.professional_id==p.id,Booking.status==BookingStatus.completed)) or 0
    earnings=await db.scalar(select(func.coalesce(func.sum(Payment.professional_payable_ngn),0)).join(Booking,Payment.booking_id==Booking.id).where(Booking.professional_id==p.id,Payment.status.in_(["paid","settled"]))) or 0
    return {"pending_requests":sum(1 for b in active if b.status==BookingStatus.pending),"upcoming_bookings":sum(1 for b in active if b.status==BookingStatus.confirmed),"in_progress":sum(1 for b in active if b.status==BookingStatus.in_progress),"completed_jobs":int(completed),"earnings_ngn":int(earnings),"rating":float(p.average_rating or 0),"review_count":p.review_count}

@router.get("/me/requests")
async def requests(user: User = Depends(require_role("professional")), db: AsyncSession = Depends(get_db)):
    p=await profile_for(user,db); rows=(await db.scalars(select(Booking).where(Booking.professional_id==p.id,Booking.status==BookingStatus.pending).order_by(Booking.starts_at))).all()
    return [{"id":str(b.id),"starts_at":b.starts_at,"ends_at":b.ends_at,"total_ngn":b.total_ngn,"service_id":str(b.service_id),"customer_id":str(b.customer_id),"customer_note":b.customer_note} for b in rows]
