"""Vision-only child process. Pygame is never imported here.

Reuse the original tracker classes and publish complete camera snapshots.
"""
import queue
import cv2 as cv
import mediapipe as mp
import numpy as np
from controls import InputController
from archer_tracker_test import HandTracker, PoseTracker
from tracking_clock import monotonic_seconds

class GameHandTracker(HandTracker):
    """Reuse HandTracker and publish wrists and gestures from the same result."""

    def __init__(self):
        self.game_sample = (0, {}, False, {})
        super().__init__()

    def on_hand_result(self, result, output_image, timestamp_ms):
        super().on_hand_result(result, output_image, timestamp_ms)
        states = {}
        for hand in self.hand_labels:
            side = hand["label"].replace(" hand", "")
            states[side] = hand["state"]
        stamp, wrists, fresh = self.wrist_sample
        self.game_sample = (stamp, wrists, fresh, states)


class CameraCapture:
    """Own camera/detectors; the Pygame loop owns the window and round timing."""

    def __init__(self, controller, camera_index=0):
        self.controller = controller
        self.camera = None
        self.last_submit = 0.0
        self.last_timestamp = 0
        try:
            controller.pose_tracker = PoseTracker()
            controller.hand_tracker = GameHandTracker()
            self.camera = cv.VideoCapture(camera_index)
            if not self.camera.isOpened():
                raise RuntimeError("Could not open the webcam. Check camera permission or use mouse practice.")
            self.camera.set(cv.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
            self.camera.set(cv.CAP_PROP_FPS, 30)
        except Exception:
            try:
                self.close()
            except Exception:
                pass  # Preserve the original startup error after cleaning up.
            raise

    def read(self):
        ok, frame = self.camera.read()
        if not ok:
            raise RuntimeError("Camera stopped delivering frames. Reconnect it or use mouse practice.")
        frame = self.prepare_frame(frame)
        now = monotonic_seconds()
        timestamp = max(int(now * 1000), self.last_timestamp + 1)
        self.last_timestamp = timestamp
        if now - self.last_submit >= 1 / 30:
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv.cvtColor(frame, cv.COLOR_BGR2RGB))
            self.controller.pose_tracker.detector.detect_async(image, timestamp)
            self.controller.hand_tracker.hand_detector.detect_async(image, timestamp)
            self.last_submit = now
        return frame, timestamp

    def preview(self, frame, pose_sample=None, hand_sample=None):
        """Draw the same shoulder/elbow/wrist links as the original tracker."""
        height, width = frame.shape[:2]
        size = np.array([width, height])
        pose, stamp = (pose_sample if pose_sample is not None else
                       self.controller.pose_tracker.pose_sample)
        hand_sample = (hand_sample if hand_sample is not None else
                       self.controller.hand_tracker.game_sample)
        if pose is not None and self.last_timestamp - stamp <= 400:
            pixels = np.int32(pose * size)
            for a, b in ((11, 13), (12, 14), (11, 12)):
                cv.line(frame, tuple(pixels[a]), tuple(pixels[b]), (80, 230, 120), 2)
            for index in (11, 12, 13, 14):
                cv.circle(frame, tuple(pixels[index]), 5, (230, 160, 40), -1)
            stamp, wrists, fresh, states = hand_sample
            if self.last_timestamp - stamp <= 200:
                for side, elbow in (("Left", 13), ("Right", 14)):
                    if side in wrists:
                        wrist = tuple(np.int32(wrists[side] * size))
                        cv.line(frame, tuple(pixels[elbow]), wrist, (80, 230, 120), 2)
                        cv.circle(frame, wrist, 6, (40, 200, 255), -1)
        frame = cv.flip(frame, 1)
        stamp, wrists, fresh, states = hand_sample
        if self.last_timestamp - stamp <= 200:
            for side, position in wrists.items():
                anchor = (width - 1 - int(position[0] * width), int(position[1] * height))
                cv.putText(frame, side + ': ' + states.get(side, 'Unknown'), anchor,
                           cv.FONT_HERSHEY_SIMPLEX, 0.4, (80, 255, 240), 1, cv.LINE_AA)
        # The HUD inset is small. Sending only its required resolution cuts
        # process traffic by 75%, while models retain the full input resolution.
        factor = min(320 / width, 240 / height, 1.0)
        if factor < 1:
            frame = cv.resize(frame, None, fx=factor, fy=factor, interpolation=cv.INTER_AREA)
        return cv.cvtColor(frame, cv.COLOR_BGR2RGB)

    def close(self):
        # Also handles partially completed startup and repeated close calls.
        errors = []
        if self.camera is not None:
            try:
                self.camera.release()
            except Exception as exc:
                errors.append(exc)
            self.camera = None
        for name, detector_name in (("pose_tracker", "detector"), ("hand_tracker", "hand_detector")):
            tracker = getattr(self.controller, name, None)
            if tracker is not None:
                try:
                    getattr(tracker, detector_name).close()
                except Exception as exc:
                    errors.append(exc)
                setattr(self.controller, name, None)
        if errors:
            raise errors[0]


    def prepare_frame(self, frame):
        """Limit model input size even when the camera ignores the requested resolution."""
        height, width = frame.shape[:2]
        factor = min(640 / width, 480 / height, 1.0)
        if factor < 1:
            frame = cv.resize(frame, None, fx=factor, fy=factor, interpolation=cv.INTER_AREA)
        return frame



def publish(output, packet):
    # Replace queued old data so the UI receives the most recent frame.
    try:
        output.put_nowait(packet)
    except queue.Full:
        try:
            output.get_nowait()
        except queue.Empty:
            pass
        try:
            output.put_nowait(packet)
        except queue.Full:
            pass


def run_camera(output, stop, camera_index):
    controller = InputController(lambda strength, angle: False)
    capture = None
    try:
        capture = CameraCapture(controller, camera_index)
        last_publish = 0
        while not stop.is_set():
            frame, timestamp = capture.read()
            # Millisecond timestamps round a 30 Hz camera's interval to 33/34.
            # Admit both instead of accidentally halving its preview rate.
            if timestamp - last_publish < 33:
                continue
            last_publish = timestamp
            pose_sample = controller.pose_tracker.pose_sample
            hand_sample = controller.hand_tracker.game_sample
            publish(output, {
                'type': 'frame', 'stamp': timestamp,
                'rgb': capture.preview(frame, pose_sample, hand_sample),
                'pose': pose_sample, 'hands': hand_sample,
            })
    except Exception as exc:
        # Wait for the parent to consume the error before leaving the process.
        while not stop.is_set():
            publish(output, {'type': 'error', 'message': str(exc)})
            stop.wait(.1)
    finally:
        try:
            if capture is not None:
                capture.close()
        finally:
            output.cancel_join_thread()
