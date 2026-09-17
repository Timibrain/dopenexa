from typing import Protocol
import httpx
from .config import settings

class AIProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...
    async def extract_intent(self, text: str) -> dict: ...

class ConfiguredAIProvider:
    async def _post(self, path: str, payload: dict) -> dict:
        if not settings.ai_api_key: raise RuntimeError("AI_API_KEY is not configured")
        headers={"Authorization":f"Bearer {settings.ai_api_key}","Content-Type":"application/json"}
        async with httpx.AsyncClient(timeout=20) as client:
            r=await client.post(settings.ai_base_url.rstrip("/")+path,headers=headers,json=payload)
            r.raise_for_status(); return r.json()
    async def embed(self,text:str)->list[float]:
        data=await self._post("/embeddings",{"model":settings.ai_embedding_model,"input":text})
        return data["data"][0]["embedding"]
    async def extract_intent(self,text:str)->dict:
        system=("Extract marketplace intent as JSON with keys category, budget_ngn, constraints. "
                "category should be a short service category; budget_ngn is integer or null; "
                "constraints is an object of concise strings.")
        data=await self._post("/chat/completions",{"model":settings.ai_chat_model,"temperature":0,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":system},{"role":"user","content":text}]})
        import json
        return json.loads(data["choices"][0]["message"]["content"])
