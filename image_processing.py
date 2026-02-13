import cv2
import numpy as np
import os
import logging
from config import TRAINED_IMAGES_FOLDER
from utils import get_all_images_from_subfolders

IMAGE_SIZE = (256, 256)
CANNY_LOW = 50
CANNY_HIGH = 150
EDGE_MATCH_THRESHOLD = float(os.environ.get('EDGE_THRESHOLD', '0.90'))


def ensure_dir_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)


def detect_edges(image):
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    gray = cv2.resize(gray, IMAGE_SIZE)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    edges = cv2.Canny(blurred, CANNY_LOW, CANNY_HIGH)

    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    edges = cv2.erode(edges, kernel, iterations=1)

    return edges


def extract_edge_features(edges):
    contours, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    largest_contour = max(contours, key=cv2.contourArea)

    area = cv2.contourArea(largest_contour)
    perimeter = cv2.arcLength(largest_contour, True)

    hull = cv2.convexHull(largest_contour)
    hull_area = cv2.contourArea(hull)
    solidity = area / hull_area if hull_area > 0 else 0

    x, y, w, h = cv2.boundingRect(largest_contour)
    aspect_ratio = float(w) / h if h > 0 else 0
    extent = area / (w * h) if w * h > 0 else 0

    moments = cv2.moments(largest_contour)
    hu_moments = cv2.HuMoments(moments).flatten()

    return {
        'area': area,
        'perimeter': perimeter,
        'solidity': solidity,
        'aspect_ratio': aspect_ratio,
        'extent': extent,
        'hu_moments': hu_moments.tolist()
    }


def compare_edge_features(test_features, ref_features):
    if not test_features or not ref_features:
        return 0.0

    area_ratio = min(test_features['area'], ref_features['area']) / \
                 max(test_features['area'], ref_features['area']) if max(test_features['area'], ref_features['area']) > 0 else 0

    perimeter_ratio = min(test_features['perimeter'], ref_features['perimeter']) / \
                      max(test_features['perimeter'], ref_features['perimeter']) if max(test_features['perimeter'], ref_features['perimeter']) > 0 else 0

    solidity_diff = 1 - abs(test_features['solidity'] - ref_features['solidity'])
    aspect_diff = 1 - min(abs(test_features['aspect_ratio'] - ref_features['aspect_ratio']), 1.0)
    extent_diff = 1 - abs(test_features['extent'] - ref_features['extent'])

    test_hu = np.array(test_features['hu_moments'])
    ref_hu = np.array(ref_features['hu_moments'])

    test_hu_log = np.sign(test_hu) * np.log10(np.abs(test_hu) + 1e-10)
    ref_hu_log = np.sign(ref_hu) * np.log10(np.abs(ref_hu) + 1e-10)

    hu_distance = np.sum(np.abs(test_hu_log - ref_hu_log))
    hu_score = max(0, 1 - hu_distance / 10)

    score = (
        0.20 * area_ratio +
        0.15 * perimeter_ratio +
        0.15 * solidity_diff +
        0.15 * aspect_diff +
        0.10 * extent_diff +
        0.25 * hu_score
    )

    return score


def detect_defect_from_edges(test_features, ref_features):
    if not test_features:
        return "Unknown"

    if not ref_features:
        return "No_Reference"

    area_ratio = test_features['area'] / ref_features['area'] if ref_features['area'] > 0 else 1

    if area_ratio < 0.7:
        return "Undersized"
    elif area_ratio > 1.3:
        return "Oversized"

    aspect_diff = abs(test_features['aspect_ratio'] - ref_features['aspect_ratio'])
    if aspect_diff > 0.3:
        return "Shape_Deformation"

    if test_features['solidity'] < ref_features['solidity'] * 0.85:
        return "Surface_Defect"

    perimeter_ratio = test_features['perimeter'] / ref_features['perimeter'] if ref_features['perimeter'] > 0 else 1
    if abs(perimeter_ratio - 1) > 0.25:
        return "Edge_Damage"

    return "Edge_Mismatch"


def process_image_web(frame, filename):
    try:
        resized_frame = cv2.resize(frame, IMAGE_SIZE)

        # Extract features for test image
        test_edges = detect_edges(resized_frame)
        test_features = extract_edge_features(test_edges)

        if not test_features:
            return "Error", 0.0, None, "No edges detected", "Unknown", "Unknown", "Unknown"

        ref_images = get_all_images_from_subfolders(TRAINED_IMAGES_FOLDER)

        if not ref_images:
            return "Error", 0.0, None, "No reference images", "Unknown", "Unknown", "Unknown"

        best_score = 0.0
        best_match = None
        best_subfolder = None
        best_ref_features = None

        for ref_path in ref_images:
            ref_img = cv2.imread(ref_path)
            if ref_img is None:
                continue

            ref_edges = detect_edges(ref_img)
            ref_features = extract_edge_features(ref_edges)

            if not ref_features:
                continue

            score = compare_edge_features(test_features, ref_features)

            if score > best_score:
                best_score = score
                best_match = os.path.splitext(os.path.basename(ref_path))[0]
                best_subfolder = os.path.basename(os.path.dirname(ref_path))
                best_ref_features = ref_features

        best_score = round(float(best_score), 4)

        if best_score >= EDGE_MATCH_THRESHOLD:
            result = "Accepted"
            defect_type = "OK"
        else:
            result = "Rejected"
            defect_type = detect_defect_from_edges(test_features, best_ref_features)

        # ✅ Save ONLY real captured image (NO drawing, NO overlay)
        result_img_path = os.path.join("static/uploads", filename)
        ensure_dir_exists(os.path.dirname(result_img_path))
        cv2.imwrite(result_img_path, frame)

        if best_subfolder:
            part_number = best_subfolder
            part_name = best_subfolder
        elif best_match:
            part_number = ''.join([c for c in best_match if c.isalnum() or c in ['_', '-']])
            part_name = best_match
        else:
            part_number = "Unknown"
            part_name = "Unknown"

        logging.info(
            f"Inspection {filename}: {result} ({defect_type}) "
            f"(Score: {best_score}) Part Number: {part_number}, Part Name: {part_name}"
        )

        return result, best_score, result_img_path, best_match, defect_type, part_number, part_name

    except Exception as e:
        logging.error(f"Image processing error: {str(e)}")
        return "Error", 0.0, None, "Unknown", "Unknown", "Unknown", "Unknown"


def pixels_to_mm(pixels, scale=0.05):
    try:
        return pixels * scale
    except Exception:
        return 0
