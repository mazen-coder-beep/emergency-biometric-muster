"""
simulate_camera.py  (v2 – JWT auth)
─────────────────────────────────────
CLI simulator for camera edge events.
Now authenticates as a camera_node before posting events.
"""

import json
import time
import urllib.request
import urllib.error
import sys
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL       = os.getenv("BACKEND_HTTP", "http://localhost:8000")
TOKEN_URL         = f"{BACKEND_URL}/auth/token"
EVENT_URL         = f"{BACKEND_URL}/api/event"

CAMERA_CLIENT_ID     = os.getenv("CAMERA_CLIENT_ID", "camera_node_01")
CAMERA_CLIENT_SECRET = os.getenv("CAMERA_CLIENT_SECRET", "replace_me_camera_secret")

# ── Auth ──────────────────────────────────────────────────────────────────────

def fetch_token() -> str:
    """
    POST to /auth/token and return a JWT access token.
    Exits the process if auth fails — no point running without a token.
    """
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
            token = data["access_token"]
            print(f"[Auth] Token obtained (expires in {data['expires_in']}s).")
            return token
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[Auth ERROR] HTTP {e.code}: {body}")
        sys.exit(1)
    except Exception as e:
        print(f"[Auth ERROR] Could not reach {TOKEN_URL}: {e}")
        print("Make sure server.py is running and your .env credentials are correct.")
        sys.exit(1)


# ── Event sender ──────────────────────────────────────────────────────────────

def send_event(
    token: str,
    event_type: str,
    msg: str,
    camera: str,
    zone: str,
    floor: int,
    is_hotzone: bool,
    occupant_name: str = "Unknown",
    avatar: str = "👤",
) -> None:
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
                else "Guest Visitor" if event_type == "visitor"
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
            "Authorization": f"Bearer {token}",   # ← JWT attached here
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"[OK] Broadcasted to {result['broadcasted_to_clients']} client(s) | persisted={result['persisted']}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 401:
            print(f"[Auth ERROR] Token rejected (401). Re-run to fetch a fresh token.")
        elif e.code == 403:
            print(f"[Auth ERROR] Forbidden (403) – this client_id may not have camera_node role.")
        else:
            print(f"[HTTP ERROR] {e.code}: {body}")
    except Exception as e:
        print(f"[Network ERROR] Could not reach {EVENT_URL}: {e}")
        print("Is server.py running?")


# ── CLI menu ──────────────────────────────────────────────────────────────────

MENU = """
=========================================================
  CAMERA FACE DETECTION SIMULATOR (CV ENGINE NODE) v2
=========================================================
  1  Turnstile Entry Scan       (Employee Face Match)
  2  Visitor in Public Lobby    (No Alert)
  3  Intruder in Server Room B  (HOTZONE ALERT)
  4  Intruder in Research Lab   (HOTZONE ALERT)
  5  Intruder in Exec Suite     (HOTZONE ALERT)
  r  Refresh JWT token          (if current token expired)
  q  Quit
---------------------------------------------------------"""

def main() -> None:
    print(MENU)
    token = fetch_token()

    while True:
        try:
            choice = input("\nSelect event [1-5 / r / q]: ").strip().lower()
        except KeyboardInterrupt:
            print("\n[Quit]")
            break

        if choice == "q":
            print("[Quit]")
            break

        elif choice == "r":
            token = fetch_token()

        elif choice == "1":
            send_event(
                token,
                event_type="entry",
                msg="[FACE ID TURNSTILE 01] Face Vector Match: Alex Mercer -> Logged IN_BUILDING.",
                camera="CAM-101",
                zone="Main Entrance",
                floor=1,
                is_hotzone=False,
                occupant_name="Alex Mercer",
                avatar="👨‍💼",
            )

        elif choice == "2":
            send_event(
                token,
                event_type="visitor",
                msg="🌐 [PUBLIC ZONE LOG] CAM-101 detected Unregistered Visitor in Lobby & Reception -> ALLOWED.",
                camera="CAM-101",
                zone="Lobby & Reception",
                floor=1,
                is_hotzone=False,
                occupant_name="Lobby Guest",
                avatar="👤",
            )

        elif choice == "3":
            send_event(
                token,
                event_type="hotzone",
                msg="🔥 [HOTZONE BREACH] CAM-204 detected UNREGISTERED FACE in Server Room B!",
                camera="CAM-204",
                zone="Server Room B",
                floor=2,
                is_hotzone=True,
                occupant_name="HOTZONE INTRUDER SUSPECT",
                avatar="🕵️‍♂️",
            )

        elif choice == "4":
            send_event(
                token,
                event_type="hotzone",
                msg="🔥 [HOTZONE BREACH] CAM-209 detected UNREGISTERED FACE in Research Lab 2B!",
                camera="CAM-209",
                zone="Research Lab 2B",
                floor=2,
                is_hotzone=True,
                occupant_name="HOTZONE INTRUDER SUSPECT",
                avatar="🕵️‍♂️",
            )

        elif choice == "5":
            send_event(
                token,
                event_type="hotzone",
                msg="🔥 [HOTZONE BREACH] CAM-301 detected UNREGISTERED FACE in Executive Suite 301!",
                camera="CAM-301",
                zone="Executive Suite 301",
                floor=3,
                is_hotzone=True,
                occupant_name="HOTZONE INTRUDER SUSPECT",
                avatar="🕵️‍♂️",
            )

        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
