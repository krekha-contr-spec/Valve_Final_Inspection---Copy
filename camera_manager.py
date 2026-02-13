import cv2
import threading
import numpy as np
import time
import logging
from typing import Optional
import ctypes

from hik_cam.MvCameraControl_class import (
    MvCamera,
    MV_CC_DEVICE_INFO_LIST,
    MV_CC_DEVICE_INFO,
    MV_GIGE_DEVICE,
    MV_USB_DEVICE,
    MV_ACCESS_Exclusive,
    MV_FRAME_OUT,
    MV_EXPOSURE_AUTO_MODE_OFF,
    MV_GAIN_MODE_OFF,
    MV_TRIGGER_MODE_ON,
    MV_TRIGGER_MODE_OFF,
    MV_TRIGGER_SOURCE_SOFTWARE,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("camera_manager")

_camera: Optional["BaseCamera"] = None
_camera_type: str = "hikrobot"
_device_id: int = 0
_camera_thread: Optional[threading.Thread] = None
_running: bool = False
_lock = threading.Lock()
_last_frame: Optional[np.ndarray] = None

class BaseCamera:
    def read(self):
        raise NotImplementedError

    def release(self):
        raise NotImplementedError

    def set_exposure(self, value: float):
        pass

    def set_gain(self, value: float):
        pass

    def set_trigger(self, enable: bool):
        pass

    def software_trigger(self):
        pass

class WebcamCamera(BaseCamera):
    def __init__(self, device_id: int = 0):
        self.cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError("Webcam not opened")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        logger.info("Webcam opened")

    def read(self):
        return self.cap.read()

    def release(self):
        self.cap.release()
        logger.info("Webcam released")

class MockCamera(BaseCamera):
    def read(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            "MOCK CAMERA",
            (140, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
        )
        return True, frame

    def release(self):
        logger.info("Mock camera released")

class HikrobotCamera(BaseCamera):
    def __init__(self):
        self.cam = MvCamera()

        device_list = MV_CC_DEVICE_INFO_LIST()
        ret = MvCamera.MV_CC_EnumDevices(
            MV_GIGE_DEVICE | MV_USB_DEVICE, device_list
        )
        if device_list.nDeviceNum == 0:
            raise RuntimeError("No Hikrobot camera detected")

        device = ctypes.cast(
            device_list.pDeviceInfo[0],
            ctypes.POINTER(MV_CC_DEVICE_INFO)
        ).contents

        self.cam.MV_CC_CreateHandle(device)
        self.cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)

        self.cam.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_OFF)
        self.cam.MV_CC_SetEnumValue("GainAuto", MV_GAIN_MODE_OFF)
        self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)

        self.cam.MV_CC_StartGrabbing()
        logger.info("Hikrobot camera opened")

    def read(self):
        frame_out = MV_FRAME_OUT()
        ret = self.cam.MV_CC_GetImageBuffer(frame_out, 1000)
        if ret != 0:
            return False, None

        w = frame_out.stFrameInfo.nWidth
        h = frame_out.stFrameInfo.nHeight

        buf = ctypes.cast(
            frame_out.pBufAddr,
            ctypes.POINTER(ctypes.c_ubyte * (w * h))
        ).contents

        frame = np.frombuffer(buf, dtype=np.uint8).reshape(h, w)
        self.cam.MV_CC_FreeImageBuffer(frame_out)
        return True, frame

    def set_exposure(self, value: float):
        self.cam.MV_CC_SetEnumValue("ExposureAuto", MV_EXPOSURE_AUTO_MODE_OFF)
        self.cam.MV_CC_SetFloatValue("ExposureTime", float(value))

    def set_gain(self, value: float):
        self.cam.MV_CC_SetEnumValue("GainAuto", MV_GAIN_MODE_OFF)
        self.cam.MV_CC_SetFloatValue("Gain", float(value))

    def set_trigger(self, enable: bool):
        if enable:
            self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
            self.cam.MV_CC_SetEnumValue(
                "TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE
            )
        else:
            self.cam.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_OFF)

    def software_trigger(self):
        self.cam.MV_CC_SetCommandValue("TriggerSoftware")

    def release(self):
        try:
            self.cam.MV_CC_StopGrabbing()
            self.cam.MV_CC_CloseDevice()
            self.cam.MV_CC_DestroyHandle()
        except Exception:
            pass
        logger.info("Hikrobot camera released")

def _open_camera():
    global _camera_type

    if _camera_type == "auto":
        try:
            logger.info("Trying Hikrobot camera")
            cam = HikrobotCamera()
            _camera_type = "hikrobot"
            return cam
        except Exception as e:
            logger.warning(f"Hikrobot not available: {e}")
        try:
            logger.info("Trying Webcam")
            cam = WebcamCamera(_device_id)
            _camera_type = "webcam"
            return cam
        except Exception as e:
            logger.warning(f"Webcam not available: {e}")
        raise RuntimeError("No camera detected")

    if _camera_type == "hikrobot":
        return HikrobotCamera()

    if _camera_type == "webcam":
        return WebcamCamera(_device_id)

    if _camera_type == "mock":
        return MockCamera()

    raise ValueError("Invalid camera type")

def _camera_loop():
    global _camera, _last_frame, _camera_type
    logger.info("Camera service started")
    while _running:
        try:
            if _camera is None:
                _camera = _open_camera()
                time.sleep(0.2)

            ret, frame = _camera.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue
            with _lock:
                _last_frame = frame
        except Exception as e:
            logger.error(f"Camera error: {e}")
            try:
                if _camera:
                    _camera.release()
            except Exception:
                pass

            _camera = None
            time.sleep(1)
    if _camera:
        _camera.release()
        _camera = None


def start_camera_service(camera_type="hikrobot", device_id=0):
    global _camera_thread, _running, _camera_type, _device_id

    if _running:
        return

    _camera_type = camera_type
    _device_id = device_id
    _running = True

    _camera_thread = threading.Thread(
        target=_camera_loop, daemon=True
    )
    _camera_thread.start()


def stop_camera_service():
    global _running
    _running = False


def get_latest_frame() -> Optional[np.ndarray]:
    with _lock:
        return None if _last_frame is None else _last_frame.copy()


def capture_frame() -> Optional[np.ndarray]:
    return get_latest_frame()


def set_exposure(value: float):
    if _camera:
        _camera.set_exposure(value)


def set_gain(value: float):
    if _camera:
        _camera.set_gain(value)


def set_trigger(enable: bool):
    if _camera:
        _camera.set_trigger(enable)


def software_trigger():
    if _camera:
        _camera.software_trigger()
