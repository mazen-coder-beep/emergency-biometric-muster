"""
server.py  (v2 – auth + persistence)
─────────────────────────────────────
FastAPI WebSocket event broker with:
  • JWT authentication on every endpoint
  • PostgreSQL persistence via async SQLAlchemy
  • State snapshot replay for new WebSocket connections
  • Server-side police-brief export endpoint
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, List

from fastapi import (
    Depends, FastAPI, HTTPException, WebSocket,
    WebSocketDisconnect, status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, require_role, router as auth_router, ws_token_auth
from database import AsyncSessionLocal, Event, Occupant, create_tables, get_db


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    print("[DB] Tables verified / created.")
    yield
    print("[Server] Shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Emergency Muster & Police Forensics API Engine",
    description=(
        "Real-time WebSocket event broker for biometric turnstile check-ins "
        "and spatial zone breach detection. All endpoints require a JWT."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten to your dashboard origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class OccupantIn(BaseModel):
    id: int
    name: str
    type: str
    role: str
    status: str
    floor: int
    zone: str
    isHotzone: bool
    camera: str
    entryTime: str
    avatar: str = "👤"


class DetectionEvent(BaseModel):
    eventType: str       # entry | visitor | hotzone | safe
    msg: str
    camera: str
    zone: str
    floor: int
    isHotzone: bool
    occupant: OccupantIn | None = None


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        print(f"[WS] Client connected. Total: {len(self._connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket) if hasattr(self._connections, "discard") \
            else self._connections.remove(websocket) if websocket in self._connections else None
        print(f"[WS] Client disconnected. Remaining: {len(self._connections)}")

    async def broadcast(self, message: dict) -> None:
        dead: List[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(json.dumps(message))
            except Exception as exc:
                print(f"[WS] Dead client detected: {exc}")
                dead.append(ws)
        for ws in dead:
            if ws in self._connections:
                self._connections.remove(ws)

    async def send_personal(self, websocket: WebSocket, message: dict) -> None:
        await websocket.send_text(json.dumps(message))


manager = ConnectionManager()


# ── DB helpers ────────────────────────────────────────────────────────────────

def _occupant_to_dict(o: Occupant) -> dict:
    return {
        "id": o.occupant_id,
        "name": o.name,
        "type": o.type,
        "role": o.role,
        "status": o.status,
        "floor": o.floor,
        "zone": o.zone,
        "isHotzone": o.is_hotzone,
        "camera": o.camera,
        "entryTime": o.entry_time,
        "avatar": o.avatar,
    }


async def _upsert_occupant(session: AsyncSession, occupant: OccupantIn) -> None:
    """
    INSERT … ON CONFLICT (occupant_id) DO UPDATE
    Keeps the occupants table as the live state of the building.
    """
    stmt = (
        pg_insert(Occupant)
        .values(
            occupant_id=occupant.id,
            name=occupant.name,
            type=occupant.type,
            role=occupant.role,
            status=occupant.status,
            floor=occupant.floor,
            zone=occupant.zone,
            is_hotzone=occupant.isHotzone,
            camera=occupant.camera,
            entry_time=occupant.entryTime,
            avatar=occupant.avatar,
            last_updated=datetime.now(timezone.utc),
        )
        .on_conflict_do_update(
            constraint="uq_occupants_occupant_id",
            set_={
                "name": occupant.name,
                "type": occupant.type,
                "role": occupant.role,
                "status": occupant.status,
                "floor": occupant.floor,
                "zone": occupant.zone,
                "is_hotzone": occupant.isHotzone,
                "camera": occupant.camera,
                "entry_time": occupant.entryTime,
                "avatar": occupant.avatar,
                "last_updated": datetime.now(timezone.utc),
            },
        )
    )
    await session.execute(stmt)


async def _log_event(
    session: AsyncSession,
    event: DetectionEvent,
    posted_by: str,
) -> None:
    """Write one row to the append-only events table."""
    row = Event(
        event_type=event.eventType,
        msg=event.msg,
        camera=event.camera,
        zone=event.zone,
        floor=event.floor,
        is_hotzone=event.isHotzone,
        occupant_id=event.occupant.id if event.occupant else None,
        occupant_name=event.occupant.name if event.occupant else None,
        occupant_type=event.occupant.type if event.occupant else None,
        occupant_status=event.occupant.status if event.occupant else None,
        occupant_avatar=event.occupant.avatar if event.occupant else None,
        posted_by=posted_by,
    )
    session.add(row)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/status", tags=["system"])
async def get_status():
    """Public health-check – no auth required."""
    return {
        "status": "ONLINE",
        "system": "Emergency Muster & Life Safety Engine v2",
        "ws_clients_connected": len(manager._connections),
    }


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token_data: Annotated[TokenData, Depends(ws_token_auth)],
    db: AsyncSession = Depends(get_db),
):
    """
    Requires ?token=<jwt> query param with role 'dashboard'.
    On connect, sends a STATE_SNAPSHOT of all current occupants from the DB
    so the dashboard doesn't start blank, then streams live events.
    """
    if token_data.role != "dashboard":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)

    # ── Replay state snapshot ────────────────────────────────────────────────
    result = await db.execute(select(Occupant).order_by(Occupant.last_updated.desc()))
    all_occupants = result.scalars().all()
    await manager.send_personal(websocket, {
        "type": "STATE_SNAPSHOT",
        "occupants": [_occupant_to_dict(o) for o in all_occupants],
    })

    try:
        while True:
            # Keep-alive: accept pings but ignore content
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post(
    "/api/event",
    tags=["events"],
    dependencies=[Depends(require_role("camera_node"))],
)
async def receive_camera_event(
    event: DetectionEvent,
    token_data: Annotated[TokenData, Depends(require_role("camera_node"))],
    db: AsyncSession = Depends(get_db),
):
    """
    Edge cameras POST events here.
    Requires a JWT with role **camera_node**.

    1. Persists event to `events` table.
    2. Upserts occupant state in `occupants` table.
    3. Broadcasts to all connected dashboard WebSocket clients.
    """
    # Persist
    await _log_event(db, event, posted_by=token_data.sub)
    if event.occupant:
        await _upsert_occupant(db, event.occupant)

    # Broadcast
    payload = {
        "type": "EVENT",
        "eventType": event.eventType,
        "msg": event.msg,
        "camera": event.camera,
        "zone": event.zone,
        "floor": event.floor,
        "isHotzone": event.isHotzone,
        "occupant": event.occupant.model_dump() if event.occupant else None,
    }
    await manager.broadcast(payload)

    return {
        "status": "SUCCESS",
        "persisted": True,
        "broadcasted_to_clients": len(manager._connections),
    }


@app.get(
    "/api/export/police-brief",
    tags=["export"],
    dependencies=[Depends(require_role("dashboard", "camera_node"))],
)
async def export_police_brief(db: AsyncSession = Depends(get_db)):
    """
    Server-side police forensic brief.
    Requires a valid JWT (any role).
    Returns structured JSON; the dashboard formats it for download.
    """
    missing_result = await db.execute(
        select(Occupant).where(Occupant.status == "MISSING")
    )
    missing = missing_result.scalars().all()

    hotzone_result = await db.execute(
        select(Occupant).where(Occupant.type == "UNREGISTERED_HOTZONE")
    )
    hotzones = hotzone_result.scalars().all()

    visitor_result = await db.execute(
        select(Occupant).where(Occupant.type == "VISITOR_LOBBY")
    )
    visitors = visitor_result.scalars().all()

    # Last 50 events for the log section
    events_result = await db.execute(
        select(Event).order_by(Event.created_at.desc()).limit(50)
    )
    recent_events = events_result.scalars().all()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "facility": "HQ Building 4",
        "summary": {
            "hotzone_breaches": len(hotzones),
            "missing_employees": len(missing),
            "lobby_visitors": len(visitors),
        },
        "hotzone_breaches": [_occupant_to_dict(o) for o in hotzones],
        "missing_employees": [_occupant_to_dict(o) for o in missing],
        "lobby_visitors": [_occupant_to_dict(o) for o in visitors],
        "recent_event_log": [
            {
                "id": e.id,
                "timestamp": e.created_at.isoformat(),
                "event_type": e.event_type,
                "msg": e.msg,
                "camera": e.camera,
                "zone": e.zone,
                "floor": e.floor,
                "is_hotzone": e.is_hotzone,
                "occupant_name": e.occupant_name,
                "posted_by": e.posted_by,
            }
            for e in recent_events
        ],
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
