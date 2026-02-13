import os
import cv2
from PIL import Image
import logging

def get_all_images_from_subfolders(trained_folder):
    file_paths = []
    if not os.path.exists(trained_folder):
        logging.warning(f"Training folder {trained_folder} does not exist")
        return file_paths
    
    for root, dirs, files in os.walk(trained_folder):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.jfif', '.tiff', '.tif', '.bmp')):
                file_paths.append(os.path.join(root, file))
    
    logging.info(f"Found {len(file_paths)} reference images in {trained_folder}")
    return file_paths

def mat_to_image(mat):
    return Image.fromarray(cv2.cvtColor(mat, cv2.COLOR_BGR2RGB))

def ensure_dir_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)
        logging.info(f"Created directory: {directory}")
        
def get_file_size_mb(filepath):
    return os.path.getsize(filepath) / (1024 * 1024)

def is_valid_image(filepath):
    try:
        img = cv2.imread(filepath)
        return img is not None
    except Exception:
        return False