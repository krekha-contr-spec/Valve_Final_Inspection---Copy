import os
import cv2
import time
from datetime import datetime
from camera_manager import capture_frame
from database_manager import DatabaseManager

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

db = DatabaseManager()
def run_inspection(part_number: str = "UNKNOWN"):
   
    frame = capture_frame()

    if frame is None:
        print("No frame available")
        return False
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
    timestamp = int(time.time())
    filename = f"inspect_{part_number}_{timestamp}"
    image_path = os.path.join(UPLOAD_DIR, f"{filename}.jpg")
    master = load_master_contour(part_number)
    processed_frame, status_text = process_frame(frame, master)
    result = "PASS" if "PASS" in status_text else "FAIL"
    try:
        success = cv2.imwrite(image_path, processed_frame)
        if not success:
            print(f"Failed to save image to {image_path}")
            return False
        print(f"Image saved to {image_path}")
    except Exception as e:
        print(f"Error saving image: {e}")
        return False
    defect_type = "None" if result == "PASS" else "Geometric Mismatch"
    try:
        db_result = db.insert_inspection(
            data={
                "part_number": part_number,
                "image_name": filename + ".jpg", 
                "result": result,
                "defect_type": defect_type,
                "timestamp": datetime.now(),
                "ssim_score": None,
                "best_match": None,
                "location": "Station_1",
                "shifts": "Day"
            }
        )
        if db_result:
            print(f"Inspection stored in database (ID: {db_result})")
            return True
        else:
            print("Failed to store inspection in database")
            return False
    except Exception as e:
        print(f"Database error: {e}")
        return False
