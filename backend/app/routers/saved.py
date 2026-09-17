from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import require_role
from ..models import User, SavedProfessional, ProfessionalProfile, Service

router = APIRouter()

@router.get("")
async def saved(user: User = Depends(require_role("customer")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(ProfessionalProfile, User).join(User, User.id == ProfessionalProfile.user_id).join(SavedProfessional, SavedProfessional.professional_id == ProfessionalProfile.id).where(SavedProfessional.customer_id == user.id).order_by(SavedProfessional.created_at.desc()))).all()
    return [{"id": str(p.id), "name": u.display_name, "headline": p.headline, "bio": p.bio, "rating": float(p.average_rating or 0), "reviews": p.review_count, "verified": p.verification_status == "verified", "completed_jobs": p.completed_jobs} for p,u in rows]

@router.post("/{professional_id}")
async def save(professional_id: UUID, user: User = Depends(require_role("customer")), db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(select(SavedProfessional).where(SavedProfessional.customer_id == user.id, SavedProfessional.professional_id == professional_id))
    if not exists:
        db.add(SavedProfessional(customer_id=user.id, professional_id=professional_id)); await db.commit()
    return {"saved": True}

@router.delete("/{professional_id}")
async def unsave(professional_id: UUID, user: User = Depends(require_role("customer")), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SavedProfessional).where(SavedProfessional.customer_id == user.id, SavedProfessional.professional_id == professional_id)); await db.commit()
    return {"saved": False}
