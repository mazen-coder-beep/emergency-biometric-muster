import cv2
import sys

print("Checking available camera devices on macOS...")

found_cam = False

for index in [0, 1, 2]:
    print(f"Testing Camera Index {index}...")
    cap = cv2.VideoCapture(index)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret and frame is not None:
            print(f"✅ SUCCESS: Camera Index {index} is working! Resolution: {frame.shape[1]}x{frame.shape[0]}")
            found_cam = True
            
            # Show test frame
            cv2.imshow(f"Mac Camera Test (Index {index}) - Press ANY KEY to Close", frame)
            print(f"Displaying camera window for Index {index}. Click on the window and press ANY KEY to continue.")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            cap.release()
            break
        else:
            print(f"❌ Camera Index {index} opened but could not read frame.")
    else:
        print(f"❌ Camera Index {index} could not be opened.")
    cap.release()

if not found_cam:
    print("\n⚠️ NO WORKING CAMERA FOUND.")
    print("Troubleshooting Steps for macOS:")
    print("1. Go to System Settings -> Privacy & Security -> Camera")
    print("2. Ensure 'Terminal' (or your IDE) is toggled ON to allow Camera Access.")
    print("3. Make sure no other application (Zoom, FaceTime, Photo Booth, Teams) is using the webcam.")
