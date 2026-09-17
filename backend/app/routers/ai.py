import re, hashlib, math
from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..db import get_db
from ..models import ProfessionalProfile, User, Service
from ..config import settings
from ..ai_provider import ConfiguredAIProvider

router=APIRouter(); provider=ConfiguredAIProvider()
INTENTS={"design":["logo","brand","branding","graphic","poster","flyer","ui","ux","design","illustration","website design"],"technology":["app","website","software","developer","coding","api","database","tech","automation","ai"],"consulting":["strategy","business","consulting","marketing","finance","accounting","legal","plan","advisor"],"education":["teach","tutor","lesson","course","training","learn","school","exam"],"home-services":["plumb","electric","clean","repair","paint","moving","install","home","carpentry"],"wellness":["fitness","trainer","massage","wellness","nutrition","yoga","therapy","health"]}
def tokenize(v): return set(re.findall(r"[a-z0-9]+",v.lower()))
def infer_intent(v):
    scores={k:sum(1 for term in terms if term in v.lower() or set(term.split())<=tokenize(v)) for k,terms in INTENTS.items()}; best=max(scores,key=scores.get); return (best if scores[best] else None),scores
def embedding(v,dims=64):
    out=[0.0]*dims
    for token in re.findall(r"[a-z0-9]+",v.lower()):
        h=hashlib.sha256(token.encode()).digest()
        for i in range(2): out[int.from_bytes(h[i*2:i*2+2],"big")%dims] += 1 if h[10+i]%2 else -1
    norm=math.sqrt(sum(x*x for x in out)) or 1; return [round(x/norm,7) for x in out]
def vec_literal(v): return "["+",".join(str(x) for x in v)+"]"

@router.post("/intent")
async def extract_intent(payload:dict):
    value=str(payload.get("text","")).strip()
    if settings.ai_provider not in {"openai","configured"}:
        category,_=infer_intent(value); m=re.search(r"(?:₦|ngn\s*)([\d,]+)",value,re.I); budget=int(m.group(1).replace(",","")) if m else None
        return {"text":value,"category":category,"budget_ngn":budget,"constraints":{"raw":value},"confidence":.78 if category else .32,"method":"deterministic-fallback"}
    try:
        result=await provider.extract_intent(value); return {"text":value,"category":result.get("category"),"budget_ngn":result.get("budget_ngn"),"constraints":result.get("constraints") or {},"confidence":.92,"method":"configured-llm"}
    except Exception:
        category,_=infer_intent(value); return {"text":value,"category":category,"budget_ngn":None,"constraints":{"raw":value},"confidence":.45,"method":"deterministic-fallback"}

@router.post("/reindex")
async def reindex(db:AsyncSession=Depends(get_db)):
    rows=(await db.execute(select(ProfessionalProfile,User).join(User,User.id==ProfessionalProfile.user_id).where(ProfessionalProfile.onboarding_complete.is_(True)))).all(); count=0
    if settings.ai_provider in {"openai","configured"} and settings.ai_api_key:
        for p,u in rows:
            services=(await db.scalars(select(Service).where(Service.professional_id==p.id,Service.is_active.is_(True)))).all()
            corpus=" ".join(filter(None,[u.display_name,p.headline,p.bio,p.service_area]+[s.name+" "+(s.description or "") for s in services]))
            try:
                vec=await provider.embed(corpus)
                if len(vec)==1536:
                    await db.execute(text("INSERT INTO professional_ai_embeddings(professional_id,model,dimensions,embedding,source_hash) VALUES (:id,:model,1536,CAST(:v AS vector),:h) ON CONFLICT (professional_id) DO UPDATE SET model=:model,dimensions=1536,embedding=CAST(:v AS vector),source_hash=:h,updated_at=now()"),{"id":str(p.id),"model":settings.ai_embedding_model,"v":vec_literal(vec),"h":hashlib.sha256(corpus.encode()).hexdigest()}); count+=1
            except Exception: continue
        await db.commit()
    return {"indexed":count,"provider":settings.ai_provider,"model":settings.ai_embedding_model if settings.ai_provider in {"openai","configured"} else "deterministic-64"}

@router.post("/match")
async def match_professionals(payload:dict,db:AsyncSession=Depends(get_db)):
    query=str(payload.get("text","")).strip(); category,_=infer_intent(query); results=[]
    rows=(await db.execute(select(ProfessionalProfile,User).join(User,User.id==ProfessionalProfile.user_id).where(ProfessionalProfile.onboarding_complete.is_(True)))).all()
    if settings.ai_provider in {"openai","configured"} and settings.ai_api_key:
        try:
            qv=await provider.embed(query)
            if len(qv)==1536:
                candidates=(await db.execute(text("SELECT p.id, 1-(e.embedding <=> CAST(:q AS vector)) sim FROM professional_profiles p JOIN professional_ai_embeddings e ON e.professional_id=p.id WHERE p.onboarding_complete=true ORDER BY e.embedding <=> CAST(:q AS vector) LIMIT 20"),{"q":vec_literal(qv)})).all()
                byid={str(x.id):float(x.sim) for x in candidates}
                for p,u in rows:
                    if str(p.id) not in byid: continue
                    sim=byid[str(p.id)]; trust=min(float(p.average_rating or 0)/5*.12,.12); ver=.08 if p.verification_status=="verified" else 0; score=max(0,min(.99,.80*sim+trust+ver+.04))
                    results.append({"id":str(p.id),"name":u.display_name,"headline":p.headline,"bio":p.bio,"rating":float(p.average_rating or 0),"reviews":p.review_count,"verified":p.verification_status=="verified","completed_jobs":p.completed_jobs,"match":round(score*100),"match_reason":f"Semantic fit {round(sim*100)}% plus rating and verification signals."})
                results.sort(key=lambda x:x["match"],reverse=True); return {"intent":{"category":category,"text":query},"matches":results[:20],"method":"configured-embedding-v1"}
        except Exception: pass
    qvec=vec_literal(embedding(query))
    for p,u in rows:
        services=(await db.scalars(select(Service).where(Service.professional_id==p.id,Service.is_active.is_(True)))).all(); corpus=" ".join(filter(None,[u.display_name,p.headline,p.bio,p.service_area]+[s.name+" "+(s.description or "") for s in services]))
        await db.execute(text("UPDATE professional_profiles SET embedding=CAST(:v AS vector) WHERE id=:id AND embedding IS NULL"),{"v":vec_literal(embedding(corpus)),"id":str(p.id)})
        sim=float((await db.execute(text("SELECT 1-(embedding <=> CAST(:q AS vector)) FROM professional_profiles WHERE id=:id"),{"q":qvec,"id":str(p.id)})).scalar() or 0); lexical=len(tokenize(query)&tokenize(corpus))/max(1,len(tokenize(query))); score=max(0,min(.99,.62*sim+.20*lexical+min(float(p.average_rating or 0)/5*.12,.12)+(.08 if p.verification_status=="verified" else 0)+.08))
        results.append({"id":str(p.id),"name":u.display_name,"headline":p.headline,"bio":p.bio,"rating":float(p.average_rating or 0),"reviews":p.review_count,"verified":p.verification_status=="verified","completed_jobs":p.completed_jobs,"match":round(score*100),"match_reason":f"Semantic fit {round(sim*100)}% with skill and trust signals."})
    await db.commit(); results.sort(key=lambda x:x["match"],reverse=True); return {"intent":{"category":category,"text":query},"matches":results[:20],"method":"deterministic-pgvector-fallback"}
