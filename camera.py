"""Small process bridge: keep OpenCV's SDL library out of the Pygame process.

Only RGB frames and immutable tracker snapshots cross this boundary. Gesture
logic and the round still run together in the main process, once per result.
"""
import multiprocessing
import queue
from types import SimpleNamespace
import numpy as np
from tracking_clock import monotonic_seconds


def _worker(output, stop, camera_index):
    # Import vision dependencies only after entering the spawned child process.
    from camera_worker import run_camera
    run_camera(output, stop, camera_index)


class CameraSession:
    STARTUP_TIMEOUT_MS = 20000
    FRAME_TIMEOUT_MS = 3000

    def __init__(self, controller, camera_index=0):
        self.controller = controller
        self.rgb = np.zeros((480, 640, 3), dtype=np.uint8)
        self.received_frame = False
        self.closed = False
        # These hold only immutable snapshots, never MediaPipe detector objects.
        self.pose_tracker = SimpleNamespace(pose_sample=(None, 0))
        self.hand_tracker = SimpleNamespace(game_sample=(0, {}, False, {}))
        controller.pose_tracker = self.pose_tracker
        controller.hand_tracker = self.hand_tracker
        self.started_at = int(monotonic_seconds() * 1000)
        self.last_frame_stamp = None
        self.started = False
        # Spawn avoids inheriting the GUI's loaded native libraries on macOS.
        context = multiprocessing.get_context('spawn')
        self.output = context.Queue(maxsize=2)
        self.stop = context.Event()
        self.process = context.Process(target=_worker, args=(self.output, self.stop, camera_index),
                                       name='Archidon camera', daemon=True)
        try:
            self.process.start()
            self.started = True
        except Exception:
            self.close()
            raise

    def read(self):
        if getattr(self, 'closed', False):
            raise RuntimeError('Camera session is closed. Start camera play again.')
        timestamp = int(monotonic_seconds() * 1000)
        # Accommodate controller-owned snapshots in standalone integrations.
        if not hasattr(self, 'pose_tracker'):
            self.pose_tracker = self.controller.pose_tracker
            self.hand_tracker = self.controller.hand_tracker
        while True:
            try:
                packet = self.output.get_nowait()
            except queue.Empty:
                break
            except (EOFError, OSError) as exc:
                raise RuntimeError('Lost the camera connection. Start camera play again.') from exc
            if packet['type'] == 'error':
                raise RuntimeError(packet['message'])
            self.rgb = packet['rgb']
            self.pose_tracker.pose_sample = packet['pose']
            self.hand_tracker.game_sample = packet['hands']
            self.received_frame = True
            self.last_frame_stamp = packet.get('stamp', timestamp)
        if not self.process.is_alive():
            raise RuntimeError('Camera worker stopped unexpectedly. Try reconnecting the webcam.')
        if self.received_frame:
            if timestamp - self.last_frame_stamp > self.FRAME_TIMEOUT_MS:
                raise RuntimeError('Camera frames stopped arriving. Reconnect the webcam and start camera play again.')
        elif timestamp - getattr(self, 'started_at', timestamp) > self.STARTUP_TIMEOUT_MS:
            raise RuntimeError('Camera startup timed out. Check webcam permission and restart camera play.')
        sample, message = self.controller.read_measurement(
            self.rgb, timestamp, self.pose_tracker, self.hand_tracker
        )
        if not self.received_frame:
            message = 'Starting the camera and loading tracking models...'
        return self.rgb, sample, message, timestamp

    def preview(self, frame):
        # Already mirrored, annotated and converted to RGB by the camera worker.
        return frame

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop.set()
        if getattr(self, 'started', True):
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.terminate()  # A blocked camera read must not keep the app open.
                self.process.join(timeout=1)
            if not self.process.is_alive():
                self.process.close()
        self.output.cancel_join_thread()
        self.output.close()
