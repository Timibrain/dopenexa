from uuid import UUID
from collections import defaultdict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from ..db import SessionLocal
from ..models import User, ConversationMember, Message, Conversation
from ..security import decode_token
from ..config import settings

router = APIRouter()
connections: dict[UUID, set[WebSocket]] = defaultdict(set)

async def broadcast(conversation_id: UUID, payload: dict):
    dead = []
    for socket in list(connections[conversation_id]):
        try:
            await socket.send_json(payload)
        except Exception:
            dead.append(socket)
    for socket in dead:
        connections[conversation_id].discard(socket)

@router.websocket("/conversations/{conversation_id}")
async def conversation_socket(websocket: WebSocket, conversation_id: UUID):
    authorization = websocket.headers.get("authorization")
    token = authorization.removeprefix("Bearer ").strip() if authorization and authorization.startswith("Bearer ") else None
    if not token and settings.environment == "development":
        token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401); return
    try:
        user_id = UUID(decode_token(token))
    except Exception:
        await websocket.close(code=4401); return
    async with SessionLocal() as db:
        member = await db.scalar(select(ConversationMember).where(ConversationMember.conversation_id == conversation_id, ConversationMember.user_id == user_id))
        if not member:
            await websocket.close(code=4403); return
    await websocket.accept()
    connections[conversation_id].add(websocket)
    try:
        while True:
            incoming = await websocket.receive_json()
            body = str(incoming.get("body", "")).strip()
            if not body or len(body) > 5000:
                continue
            async with SessionLocal() as db:
                message = Message(conversation_id=conversation_id, sender_id=user_id, body=body)
                db.add(message); await db.commit(); await db.refresh(message)
                payload = {"type":"message", "id":str(message.id), "sender_id":str(user_id), "body":body, "created_at":message.created_at.isoformat()}
                members = (await db.scalars(select(ConversationMember).where(ConversationMember.conversation_id == conversation_id))).all()
                sender = await db.scalar(select(User).where(User.id == user_id))
                conversation = await db.scalar(select(Conversation).where(Conversation.id == conversation_id))
                from ..models import Notification
                for member in members:
                    if member.user_id != user_id:
                        db.add(Notification(user_id=member.user_id, booking_id=conversation.booking_id if conversation else None, type="message", title="New message", body=f"{sender.display_name if sender else 'A professional'} sent you a new message."))
                await db.commit()
            await broadcast(conversation_id, payload)
    except WebSocketDisconnect:
        connections[conversation_id].discard(websocket)
    except Exception:
        connections[conversation_id].discard(websocket)
