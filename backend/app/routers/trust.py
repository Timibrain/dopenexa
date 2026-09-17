from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user, require_role
from ..models import User, ProfessionalProfile, VerificationSubmission, Notification

router=APIRouter()
class VerificationIn(BaseModel):
    document_type:str=Field(min_length=2,max_length=60)
    document_reference:str=Field(min_length=2,max_length=255)
class ReviewIn(BaseModel):
    status:str
    note:str|None=None

@router.post("/verification",status_code=201)
async def submit(data:VerificationIn,user:User=Depends(require_role("professional")),db:AsyncSession=Depends(get_db)):
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    if not p: raise HTTPException(400,"Create a professional profile first")
    active=await db.scalar(select(VerificationSubmission).where(VerificationSubmission.professional_id==p.id,VerificationSubmission.status=="pending"))
    if active: raise HTTPException(409,"A verification submission is already pending")
    item=VerificationSubmission(id=uuid4(),professional_id=p.id,document_type=data.document_type,document_reference=data.document_reference)
    db.add(item); await db.commit(); await db.refresh(item)
    return {"id":str(item.id),"status":item.status}

@router.get("/verification/me")
async def my_verification(user:User=Depends(require_role("professional")),db:AsyncSession=Depends(get_db)):
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id==user.id))
    rows=(await db.scalars(select(VerificationSubmission).where(VerificationSubmission.professional_id==p.id).order_by(VerificationSubmission.created_at.desc()))).all() if p else []
    return [{"id":str(x.id),"document_type":x.document_type,"status":x.status,"reviewer_note":x.reviewer_note,"created_at":x.created_at,"reviewed_at":x.reviewed_at} for x in rows]

@router.get("/admin/verification")
async def queue(user:User=Depends(require_role("admin")),db:AsyncSession=Depends(get_db)):
    rows=(await db.scalars(select(VerificationSubmission).where(VerificationSubmission.status=="pending").order_by(VerificationSubmission.created_at))).all()
    return [{"id":str(x.id),"professional_id":str(x.professional_id),"document_type":x.document_type,"created_at":x.created_at} for x in rows]

@router.post("/admin/verification/{submission_id}")
async def review(submission_id:UUID,data:ReviewIn,user:User=Depends(require_role("admin")),db:AsyncSession=Depends(get_db)):
    if data.status not in {"verified","rejected"}: raise HTTPException(400,"Status must be verified or rejected")
    item=await db.scalar(select(VerificationSubmission).where(VerificationSubmission.id==submission_id))
    if not item: raise HTTPException(404,"Submission not found")
    item.status=data.status; item.reviewer_id=user.id; item.reviewer_note=data.note; item.reviewed_at=datetime.now(timezone.utc)
    p=await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.id==item.professional_id))
    if p: p.verification_status="verified" if data.status=="verified" else "unverified"
    if p:
        owner=await db.scalar(select(User).where(User.id==p.user_id))
        if owner: db.add(Notification(user_id=owner.id,type="trust",title="Verification updated",body=f"Your verification submission was {data.status}."))
    await db.commit(); return {"id":str(item.id),"status":item.status}
