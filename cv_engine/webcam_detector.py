import time
import json
import urllib.request
import sys

BACKEND_URL = "http://localhost:8000/api/event"

def send_event(event_type, msg, camera, zone, floor, is_hotzone, occupant_name="Unknown", avatar="👤"):
    payload = {
        "eventType": event_type,
        "msg": msg,
        "camera": camera,
        "zone": zone,
        "floor": floor,
        "isHotzone": is_hotzone,
        "occupant": {
            "id": int(time.time() * 1000),
            "name": occupant_name,
            "type": "UNREGISTERED_HOTZONE" if is_hotzone else "VISITOR_LOBBY" if event_type == "visitor" else "REGISTERED",
            "role": "ALERT: Face in Restricted Hotzone" if is_hotzone else "Guest Visitor",
            "status": "HOTZONE_BREACH" if is_hotzone else "VISITOR_ALLOWED" if event_type == "visitor" else "MISSING",
            "floor": floor,
            "zone": zone,
            "isHotzone": is_hotzone,
            "camera": camera,
            "entryTime": time.strftime("%I:%M:%S %p"),
            "avatar": avatar
        }
    }
    
    req = urllib.request.Request(
        BACKEND_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            print(f"[SUCCESS] Event Broadcasted -> Dashboard: {res}")
    except Exception as e:
        print(f"[ERROR] Could not connect to backend server at {BACKEND_URL}. Make sure server.py is running! Error: {e}")

def main():
    print("=========================================================")
    print("  CAMERA FACE DETECTION SIMULATOR (CV ENGINE NODE)      ")
    print("=========================================================")
    print("1. Simulate Turnstile Entry Scan (Employee Face Match)")
    print("2. Simulate Visitor in Public Lobby (No Alert)")
    print("3. Simulate Unregistered Intruder in Server Room B (HOTZONE ALERT!)")
    print("4. Exit")
    print("---------------------------------------------------------")

    while True:
        try:
            choice = input("\nSelect camera event to trigger [1-4]: ").strip()
            if choice == "1":
                send_event(
                    event_type="entry",
                    msg="[FACE ID TURNSTILE 01] Face Vector Match: Alex Mercer -> Logged IN_BUILDING.",
                    camera="CAM-101",
                    zone="Main Entrance",
                    floor=1,
                    is_hotzone=False,
                    occupant_name="Alex Mercer",
                    avatar="👨‍💼"
                )
            elif choice == "2":
                send_event(
                    event_type="visitor",
                    msg="🌐 [PUBLIC ZONE LOG] CAM-101 detected Unregistered Visitor in Lobby & Reception -> ALLOWED.",
                    camera="CAM-101",
                    zone="Lobby & Reception",
                    floor=1,
                    is_hotzone=False,
                    occupant_name="Lobby Guest #12",
                    avatar="👤"
                )
            elif choice == "3":
                send_event(
                    event_type="hotzone",
                    msg="🔥 [HOTZONE BREACH ALERT] CAM-204 detected UNREGISTERED FACE in Server Room B!",
                    camera="CAM-204",
                    zone="Server Room B",
                    floor=2,
                    is_hotzone=True,
                    occupant_name="HOTZONE INTRUDER SUSPECT #8",
                    avatar="🕵️‍♂️"
                )
            elif choice == "4":
                print("Exiting CV Simulator.")
                break
            else:
                print("Invalid choice. Please select 1, 2, 3, or 4.")
        except KeyboardInterrupt:
            print("\nExiting.")
            break

if __name__ == "__main__":
    main()
