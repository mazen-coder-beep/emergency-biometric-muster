import cv2
import time
import json
import urllib.request
import sys

BACKEND_URL = "http://localhost:8000/api/event"

def send_event_to_backend(event_type, msg, camera, zone, floor, is_hotzone, occupant_name, avatar="👤"):
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
            "role": "ALERT: Face in Restricted Hotzone" if is_hotzone else "Visitor in Public Lobby" if event_type == "visitor" else "Registered Employee",
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
            print(f"[LIVE BROADCAST SUCCESS] -> Dashboard Updated: {msg}")
    except Exception as e:
        print(f"[WS ERROR] Backend server not reachable at {BACKEND_URL}. Ensure server.py is running! Error: {e}")

def get_working_camera():
    for idx in [0, 1, 2]:
        try:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    print(f"[CAMERA FOUND] Connected to Camera Index {idx}")
                    return cap
                cap.release()
        except Exception:
            pass
    return None

def main():
    print("=========================================================")
    print("  LIVE WEBCAM FACE RECOGNITION & EDGE DETECTOR NODE     ")
    print("=========================================================")
    print("Controls while camera window is open:")
    print("  [E] Key -> Scan Face as Registered Employee (Turnstile Check-In)")
    print("  [V] Key -> Scan Face as Visitor in Lobby (Public Zone OK)")
    print("  [I] Key -> Scan Face as UNREGISTERED INTRUDER (Hotzone Alert!)")
    print("  [Q] Key -> Quit Webcam")
    print("---------------------------------------------------------")

    # Safe Cascade Classifier Loading
    face_cascade = None
    try:
        if hasattr(cv2, 'CascadeClassifier') and hasattr(cv2, 'data'):
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            face_cascade = cv2.CascadeClassifier(cascade_path)
            if face_cascade.empty():
                face_cascade = None
    except Exception:
        face_cascade = None

    cap = get_working_camera()

    if cap is None:
        print("\n⚠️ COULD NOT ACCESS ANY MAC WEBCAM (Index 0, 1, 2).")
        print("macOS Security Checklist:")
        print("1. Go to System Settings -> Privacy & Security -> Camera")
        print("2. Make sure 'Terminal' (or VS Code) has Camera Access toggled ON.")
        print("3. Ensure FaceTime, Zoom, or Photo Booth are closed.")
        sys.exit(1)

    print("[CAMERA RUNNING] Camera window active on desktop...")

    current_mode = "REGISTERED"

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to grab frame from webcam.")
            break

        frame = cv2.flip(frame, 1)
        h_img, w_img, _ = frame.shape

        faces = []
        if face_cascade is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(60, 60)
                )
            except Exception:
                faces = []

        # Fallback bounding box in frame center if cascade is uninitialized
        if len(faces) == 0:
            box_w, box_h = 220, 260
            center_x, center_y = w_img // 2, h_img // 2
            faces = [(center_x - box_w // 2, center_y - box_h // 2, box_w, box_h)]

        for (x, y, w, h) in faces:
            if current_mode == "REGISTERED":
                color = (0, 255, 0) # Green
                label = "MATCH: REGISTERED EMPLOYEE"
            elif current_mode == "VISITOR":
                color = (255, 191, 0) # Blue
                label = "VISITOR: PUBLIC LOBBY (OK)"
            else:
                color = (147, 20, 255) # Purple/Red
                label = "WARNING: UNREGISTERED INTRUDER"

            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
            cv2.rectangle(frame, (x, y - 30), (x + w, y), color, cv2.FILLED)
            cv2.putText(frame, label, (x + 5, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        # On-screen HUD Overlays
        cv2.putText(frame, "LIVE EDGE CAMERA SCANNER", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"Mode: {current_mode}", (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cv2.putText(frame, "Press: [E] Employee | [V] Visitor | [I] Hotzone Intruder | [Q] Quit", (15, h_img - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        cv2.imshow("Emergency Muster Edge Camera - Live Face ID Node", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q') or key == ord('Q'):
            print("[SHUTDOWN] Closing camera window.")
            break
        elif key == ord('e') or key == ord('E'):
            current_mode = "REGISTERED"
            send_event_to_backend(
                event_type="entry",
                msg="[WEBCAM FACE ID] Employee Face Matched -> Logged IN_BUILDING at Turnstile.",
                camera="WEBCAM-CAM-01",
                zone="Main Entrance Turnstile",
                floor=1,
                is_hotzone=False,
                occupant_name="Webcam Verified Employee",
                avatar="👨‍💻"
            )
        elif key == ord('v') or key == ord('V'):
            current_mode = "VISITOR"
            send_event_to_backend(
                event_type="visitor",
                msg="🌐 [WEBCAM FACE ID] Unregistered Visitor in Lobby & Reception -> ALLOWED.",
                camera="WEBCAM-CAM-01",
                zone="Lobby & Reception",
                floor=1,
                is_hotzone=False,
                occupant_name="Webcam Guest Visitor",
                avatar="👤"
            )
        elif key == ord('i') or key == ord('I'):
            current_mode = "INTRUDER"
            send_event_to_backend(
                event_type="hotzone",
                msg="🔥 [WEBCAM FACE ID] UNREGISTERED FACE DETECTED IN SERVER ROOM B!",
                camera="WEBCAM-CAM-02",
                zone="Server Room B",
                floor=2,
                is_hotzone=True,
                occupant_name="WEBCAM INTRUDER SUSPECT",
                avatar="🕵️‍♂️"
            )

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
