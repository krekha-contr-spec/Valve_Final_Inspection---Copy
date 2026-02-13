import cv2
import time
import os
from camera_manager import start_camera_service, capture_frame
start_camera_service()
time.sleep(5)
SAVE_FOLDER = "captured_images"
os.makedirs(SAVE_FOLDER, exist_ok=True)

print("Camera started. Press 'q' to quit...")

try:
    while True:

        frame = capture_frame()
        if frame is not None:
            cv2.imshow("LIVE CAMERA", frame)
            timestamp = int(time.time())
            filename = os.path.join(SAVE_FOLDER, f"capture_{timestamp}.jpg")
            cv2.imwrite(filename, frame)
            print(f"Captured image saved as {filename}")
        else:
            print("No frame captured")
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Exiting...")
            break
        time.sleep(3)

finally:
    cv2.destroyAllWindows()
