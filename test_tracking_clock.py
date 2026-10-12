"""Regression for starting camera play after waiting in the menu on macOS 3.9.

Use a real spawned worker and the real camera bridge; no models or webcam.
"""
import multiprocessing
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from camera import CameraSession
from controls import InputController
from tracking_clock import monotonic_seconds


def publish_camera_fixture(output, stop, camera_index):
    pose = np.full((33, 2), .5)
    pose[11], pose[12] = [.35, .35], [.65, .35]
    wrists = {'Left': np.array([.35, .5]), 'Right': np.array([.65, .5])}
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    for _ in range(4):
        stamp = int(monotonic_seconds() * 1000)
        output.put({'type': 'frame', 'rgb': rgb, 'pose': (pose, stamp),
                    'hands': (stamp, wrists, True, {'Right': 'Closed'})})
        if stop.wait(.36):
            return
    stop.wait(5)


class CrossProcessClockTests(unittest.TestCase):
    def test_menu_wait_does_not_make_fresh_worker_results_look_old(self):
        time.monotonic()  # Start the process-local Python 3.9 clock too.
        time.sleep(1.1)   # Reproduce menu time before a new child is launched.
        context = multiprocessing.get_context('spawn')
        substitute = SimpleNamespace(Queue=context.Queue, Event=context.Event,
            Process=lambda **kwargs: context.Process(**dict(kwargs, target=publish_camera_fixture)))
        controls = InputController(lambda strength, angle: False)
        controls.calibration.start_capture()
        with patch('camera.multiprocessing.get_context', return_value=substitute):
            session = CameraSession(controls)
        try:
            deadline = monotonic_seconds() + 5
            while monotonic_seconds() < deadline and controls.calibration.step == 0:
                rgb, sample, message, stamp = session.read()
                controls.calibration.update(sample, stamp, message)
                time.sleep(.01)
            self.assertEqual(controls.calibration.step, 1, message)
            self.assertLess(stamp - session.pose_tracker.pose_sample[1], 250)
            # The stricter gameplay age/synchronization checks must work too.
            controls.calibration.step = 3
            sample, message = controls.read_measurement(rgb, stamp, session.pose_tracker, session.hand_tracker)
            self.assertIsNotNone(sample, message)
        finally:
            session.close()
        self.assertTrue(session.closed)
        self.assertNotIn(session.process, multiprocessing.active_children())


if __name__ == '__main__':
    unittest.main()
