import asyncio
import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Emergency Muster & Police Forensics API Engine",
    description="Real-time WebSocket event broker for biometric turnstile check-ins and spatial zone breach detection.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DetectionEvent(BaseModel):
    eventType: str  # 'entry', 'visitor', 'hotzone', 'safe'
    msg: str
    camera: str
    zone: str
    floor: int
    isHotzone: bool
    occupant: dict = None

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WS] Client disconnected. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                print(f"[WS Error] Failed to send to client: {e}")

manager = ConnectionManager()

@app.get("/api/status")
def get_status():
    return {
        "status": "ONLINE",
        "system": "Emergency Muster & Life Safety Engine",
        "ws_clients_connected": len(manager.active_connections)
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for client ping/messages
            data = await websocket.receive_text()
            print(f"[WS Received]: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/event")
async def receive_camera_event(event: DetectionEvent):
    """
    Endpoint for Edge Cameras or Computer Vision detectors to post real-time face matches or intruder alerts.
    """
    payload = {
        "type": "EVENT",
        "eventType": event.eventType,
        "msg": event.msg,
        "camera": event.camera,
        "zone": event.zone,
        "floor": event.floor,
        "isHotzone": event.isHotzone,
        "occupant": event.occupant
    }
    await manager.broadcast(payload)
    return {"status": "SUCCESS", "broadcasted_to_clients": len(manager.active_connections)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
