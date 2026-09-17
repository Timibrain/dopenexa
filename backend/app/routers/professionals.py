from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user, require_role
from ..models import User, ProfessionalProfile, Service, SavedProfessional, SearchEvent
from ..schemas import ProfileIn

router = APIRouter()

@router.get("")
async def search(q: str | None = None, verified: bool = False, min_rating: float = 0, max_price_ngn: int | None = None, service_type: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(ProfessionalProfile, User).join(User, User.id == ProfessionalProfile.user_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(ProfessionalProfile.headline.ilike(like), ProfessionalProfile.bio.ilike(like), User.display_name.ilike(like), ProfessionalProfile.service_area.ilike(like)))
    if verified:
        stmt = stmt.where(ProfessionalProfile.verification_status == "verified")
    if min_rating > 0:
        stmt = stmt.where(ProfessionalProfile.average_rating >= min_rating)
    if max_price_ngn is not None:
        stmt = stmt.join(Service, Service.professional_id == ProfessionalProfile.id).where(Service.is_active.is_(True), Service.price_ngn <= max_price_ngn).distinct()
    if service_type:
        stmt = stmt.join(Service, Service.professional_id == ProfessionalProfile.id).where(Service.is_active.is_(True), Service.service_type == service_type).distinct()
    rows = (await db.execute(stmt)).all()
    results = [{
        "id": str(p.id), "name": u.display_name, "headline": p.headline,
        "bio": p.bio, "rating": float(p.average_rating or 0),
        "reviews": p.review_count, "verified": p.verification_status == "verified",
        "completed_jobs": p.completed_jobs
    } for p,u in rows]
    if db and q is not None:
        db.add(SearchEvent(user_id=None, query=q, result_count=len(results)))
        await db.commit()
    return results

@router.get("/{professional_id}")
async def get_professional(professional_id: UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(ProfessionalProfile, User).join(User, User.id == ProfessionalProfile.user_id)
        .where(ProfessionalProfile.id == professional_id)
    )).first()
    if not row:
        raise HTTPException(404, "Professional not found")
    p,u = row
    services = (await db.scalars(select(Service).where(Service.professional_id == p.id, Service.is_active.is_(True)))).all()
    return {
        "id": str(p.id), "name": u.display_name, "headline": p.headline, "bio": p.bio,
        "years_experience": p.years_experience, "rating": float(p.average_rating or 0),
        "reviews": p.review_count, "verified": p.verification_status == "verified",
        "services": [{"id": str(s.id), "name": s.name, "description": s.description,
                      "service_type": s.service_type.value, "price_ngn": s.price_ngn,
                      "duration_minutes": s.duration_minutes} for s in services]
    }

@router.post("/me", status_code=201)
async def create_profile(
    data: ProfileIn,
    user: User = Depends(require_role("professional")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(select(ProfessionalProfile).where(ProfessionalProfile.user_id == user.id))
    if existing:
        existing.headline, existing.bio, existing.years_experience = data.headline, data.bio, data.years_experience
        await db.commit()
        return {"id": str(existing.id)}
    p = ProfessionalProfile(user_id=user.id, headline=data.headline, bio=data.bio, years_experience=data.years_experience)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": str(p.id)}
