import cv2
import numpy as np
import os

DATASET_PATH = r"D:\C102641-Data\copy_folder\Valve_Final_Inspection - Copy\dataset"
MIN_DEFECT_AREA = 150


class DefectDetector:
    def __init__(self):
        self.reference_mask = self._build_reference_mask()

    def _build_reference_mask(self):
        acc = None
        count = 0

        for file in os.listdir(DATASET_PATH):
            if not file.lower().endswith((".jpg", ".png", ".bmp")):
                continue

            img = cv2.imread(os.path.join(DATASET_PATH, file), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue

            _, binary = cv2.threshold(
                img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            body = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            defect = cv2.subtract(binary, body)

            if acc is None:
                acc = defect.astype(np.float32)
            else:
                acc += defect

            count += 1

        if count == 0:
            raise RuntimeError("No defect images found in dataset folder")

        return (acc / count).astype(np.uint8)

    def inspect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        defect_mask = cv2.bitwise_and(binary, self.reference_mask)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        defect_mask = cv2.morphologyEx(defect_mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(
            defect_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        defect_found = False

        for cnt in contours:
            if cv2.contourArea(cnt) > MIN_DEFECT_AREA:
                x, y, w, h = cv2.boundingRect(cnt)
                cv2.rectangle(frame, (x, y), (x + w, y + h),
                              (0, 0, 255), 2)
                defect_found = True

        result = "Rejected" if defect_found else "Accepted"
        defect_type = "Surface Defect" if defect_found else "OK"

        return result, defect_type, frame
