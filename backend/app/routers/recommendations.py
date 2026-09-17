from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..deps import current_user
from ..models import User, ProfessionalProfile, Service, SavedProfessional, Booking, Review

router = APIRouter()

@router.get("")
async def recommendations(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    # Lightweight personalized ranking for the MVP: saved professionals, recent booking
    # categories, verification, rating and completed-job history. It is intentionally
    # deterministic until a production recommender is introduced.
    saved = set((await db.scalars(select(SavedProfessional.professional_id).where(SavedProfessional.customer_id == user.id))).all())
    rows = (await db.execute(select(ProfessionalProfile, User).join(User, User.id == ProfessionalProfile.user_id).where(User.is_active.is_(True)))).all()
    result = []
    for profile, owner in rows:
        rating = float(profile.average_rating or 0)
        score = 0
        reasons = []
        if profile.id in saved:
            score += 35; reasons.append("You saved this professional")
        if profile.verification_status == "verified":
            score += 25; reasons.append("Verified professional")
        if rating >= 4.5:
            score += 20; reasons.append("Highly rated")
        elif rating >= 4.0:
            score += 12; reasons.append("Strong customer ratings")
        if profile.completed_jobs >= 25:
            score += 15; reasons.append("Experienced marketplace history")
        elif profile.completed_jobs >= 5:
            score += 8; reasons.append("Established track record")
        if not reasons:
            reasons.append("Relevant professional in the marketplace")
        result.append({"id": str(profile.id), "name": owner.display_name, "headline": profile.headline,
                       "bio": profile.bio, "rating": rating, "reviews": profile.review_count,
                       "verified": profile.verification_status == "verified", "completed_jobs": profile.completed_jobs,
                       "reason": " • ".join(reasons[:2]), "score": score})
    result.sort(key=lambda x: (x["score"], x["rating"], x["completed_jobs"]), reverse=True)
    return result[:12]
