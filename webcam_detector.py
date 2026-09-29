"""
webcam_detector.py  (v2 – JWT auth + no false-positive fallback)
─────────────────────────────────────────────────────────────────
Live webcam face detection node.

Changes vs v1
─────────────
1. Fetches a JWT from /auth/token on startup.
2. Attaches Authorization: Bearer <token> to every /api/event POST.
3. Refreshes the token automatically when a 401 is returned.
4. Removed the misleading center-box fallback — key presses that
   trigger an event now only fire when an actual face is detected.
   If no face is in frame, the HUD shows "NO FACE DETECTED" and
   the keypress is ignored.
"""

import cv2
import json
import os
import sys
import time
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL          = os.getenv("BACKEND_HTTP", "http://localhost:8000")
TOKEN_URL            = f"{BACKEND_URL}/auth/token"
EVENT_URL            = f"{BACKEND_URL}/api/event"

CAMERA_CLIENT_ID     = os.getenv("CAMERA_CLIENT_ID", "camera_node_01")
CAMERA_CLIENT_SECRET = os.getenv("CAMERA_CLIENT_SECRET", "replace_me_camera_secret")


# ── Auth ──────────────────────────────────────────────────────────────────────

def fetch_token() -> str:
    payload = json.dumps({
        "client_id": CAMERA_CLIENT_ID,
        "client_secret": CAMERA_CLIENT_SECRET,
    }).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            print(f"[Auth] Token obtained (expires in {data['expires_in']}s).")
            return data["access_token"]
    except Exception as e:
        print(f"[Auth ERROR] Could not obtain token: {e}")
        print("Ensure server.py is running. Starting in offline mode (events will not be sent).")
        return ""          # empty string → events skipped, camera still runs


# ── Event sender ──────────────────────────────────────────────────────────────

_current_token: str = ""

def send_event_to_backend(
    event_type: str,
    msg: str,
    camera: str,
    zone: str,
    floor: int,
    is_hotzone: bool,
    occupant_name: str,
    avatar: str = "👤",
) -> None:
    global _current_token

    if not _current_token:
        print("[Event] Skipped – no auth token (server offline?).")
        return

    payload = json.dumps({
        "eventType": event_type,
        "msg": msg,
        "camera": camera,
        "zone": zone,
        "floor": floor,
        "isHotzone": is_hotzone,
        "occupant": {
            "id": int(time.time() * 1000),
            "name": occupant_name,
            "type": (
                "UNREGISTERED_HOTZONE" if is_hotzone
                else "VISITOR_LOBBY" if event_type == "visitor"
                else "REGISTERED"
            ),
            "role": (
                "ALERT: Face in Restricted Hotzone" if is_hotzone
                else "Visitor in Public Lobby" if event_type == "visitor"
                else "Registered Employee"
            ),
            "status": (
                "HOTZONE_BREACH" if is_hotzone
                else "VISITOR_ALLOWED" if event_type == "visitor"
                else "MISSING"
            ),
            "floor": floor,
            "zone": zone,
            "isHotzone": is_hotzone,
            "camera": camera,
            "entryTime": time.strftime("%I:%M:%S %p"),
            "avatar": avatar,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        EVENT_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_current_token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"[Event OK] Broadcasted → {result['broadcasted_to_clients']} client(s) | {msg}")
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("[Auth] Token expired – refreshing…")
            _current_token = fetch_token()
            # Retry once with the new token
            send_event_to_backend(event_type, msg, camera, zone, floor,
                                   is_hotzone, occupant_name, avatar)
        else:
            print(f"[HTTP ERROR] {e.code}: {e.read().decode()}")
    except Exception as e:
        print(f"[Network ERROR] {e}")


# ── Camera helpers ────────────────────────────────────────────────────────────

def get_working_camera():
    for idx in [0, 1, 2]:
        try:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    print(f"[Camera] Connected to index {idx}.")
                    return cap
                cap.release()
        except Exception:
            pass
    return None


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    global _current_token

    print("=" * 57)
    print("  LIVE WEBCAM FACE RECOGNITION & EDGE DETECTOR NODE v2  ")
    print("=" * 57)
    print("Controls (only fire when a face IS detected):")
    print("  [E]  Employee face scan  → turnstile check-in")
    print("  [V]  Visitor face scan   → public lobby log")
    print("  [I]  Intruder face scan  → HOTZONE ALERT")
    print("  [Q]  Quit")
    print("-" * 57)

    _current_token = fetch_token()

    # Cascade classifier
    face_cascade = None
    try:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            face_cascade = None
            print("[Warning] Haar cascade unavailable – face detection disabled.")
    except Exception:
        print("[Warning] cv2.data not found – face detection disabled.")

    cap = get_working_camera()
    if cap is None:
        print("\n⚠️  No camera found.")
        print("macOS: System Settings → Privacy & Security → Camera → allow Terminal.")
        sys.exit(1)

    current_mode = "REGISTERED"
    face_detected = False   # tracks whether the CURRENT frame has a face

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Error] Failed to grab frame.")
            break

        frame = cv2.flip(frame, 1)
        h_img, w_img, _ = frame.shape

        # ── Face detection ────────────────────────────────────────────────────
        faces = []
        if face_cascade is not None:
            try:
                gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
                )
            except Exception:
                faces = []

        face_detected = len(faces) > 0

        # ── Draw bounding boxes only when faces are present ───────────────────
        for (x, y, w, h) in faces:
            if current_mode == "REGISTERED":
                color, label = (0, 255, 0),     "MATCH: REGISTERED EMPLOYEE"
            elif current_mode == "VISITOR":
                color, label = (255, 191, 0),   "VISITOR: PUBLIC LOBBY (OK)"
            else:
                color, label = (147, 20, 255),  "WARNING: UNREGISTERED INTRUDER"

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.rectangle(frame, (x, y - 30), (x + w, y), color, cv2.FILLED)
            cv2.putText(frame, label, (x + 5, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        # ── HUD overlays ──────────────────────────────────────────────────────
        cv2.putText(frame, "LIVE EDGE CAMERA SCANNER v2",
                    (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Mode: {current_mode}",
                    (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # Face status indicator
        if face_detected:
            cv2.putText(frame, f"FACE DETECTED ({len(faces)})",
                        (15, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        else:
            cv2.putText(frame, "NO FACE DETECTED — key presses ignored",
                        (15, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 100, 255), 1)

        auth_label = "AUTH: ONLINE" if _current_token else "AUTH: OFFLINE"
        auth_color = (0, 255, 128) if _current_token else (0, 60, 255)
        cv2.putText(frame, auth_label,
                    (w_img - 160, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, auth_color, 1)

        cv2.putText(frame, "Press: [E] Employee | [V] Visitor | [I] Hotzone | [Q] Quit",
                    (15, h_img - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        cv2.imshow("Emergency Muster Edge Camera – Live Face ID Node v2", frame)

        # ── Key handling ──────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), ord("Q")):
            print("[Shutdown] Camera closed.")
            break

        # Guard: only fire events when a face is actually in frame
        if not face_detected:
            continue

        if key in (ord("e"), ord("E")):
            current_mode = "REGISTERED"
            send_event_to_backend(
                event_type="entry",
                msg="[WEBCAM FACE ID] Employee face matched → logged IN_BUILDING at turnstile.",
                camera="WEBCAM-CAM-01",
                zone="Main Entrance Turnstile",
                floor=1,
                is_hotzone=False,
                occupant_name="Webcam Verified Employee",
                avatar="👨‍💻",
            )

        elif key in (ord("v"), ord("V")):
            current_mode = "VISITOR"
            send_event_to_backend(
                event_type="visitor",
                msg="🌐 [WEBCAM FACE ID] Unregistered visitor in Lobby & Reception → ALLOWED.",
                camera="WEBCAM-CAM-01",
                zone="Lobby & Reception",
                floor=1,
                is_hotzone=False,
                occupant_name="Webcam Guest Visitor",
                avatar="👤",
            )

        elif key in (ord("i"), ord("I")):
            current_mode = "INTRUDER"
            send_event_to_backend(
                event_type="hotzone",
                msg="🔥 [WEBCAM FACE ID] UNREGISTERED FACE DETECTED IN SERVER ROOM B!",
                camera="WEBCAM-CAM-02",
                zone="Server Room B",
                floor=2,
                is_hotzone=True,
                occupant_name="WEBCAM INTRUDER SUSPECT",
                avatar="🕵️‍♂️",
            )

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
