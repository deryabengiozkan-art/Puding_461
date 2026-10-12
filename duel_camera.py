"""Nonblocking Pygame-side camera bridge for a two-person duel.

DuelSession(camera_index=0).read() returns
    (mirrored_rgb_preview, [P1_observation_or_None, P2_observation_or_None],
     readable_status, current_shared_clock_ms)
Observations contain their source `stamp`; reading repeats the latest packet.
DuelMatch consumes each source timestamp once and rejects stale measurements.
Only NumPy/snapshots cross the spawned worker boundary. No OpenCV or MediaPipe
is imported into the Pygame process. close() is idempotent.
"""
import multiprocessing
import queue
import numpy as np
from tracking_clock import monotonic_seconds


def _worker(output, stop, camera_index):
    from duel_camera_worker import run_camera
    run_camera(output, stop, camera_index)


class DuelSession:
    STARTUP_TIMEOUT_MS = 25000
    FRAME_TIMEOUT_MS = 3000

    def __init__(self, camera_index=0):
        self.rgb = np.zeros((240, 320, 3), dtype=np.uint8)
        self.observations = [None, None]
        self.status = 'Starting one camera and loading two-player tracking...'
        self.closed = False
        self.started = False
        self.started_at = int(monotonic_seconds() * 1000)
        self.last_stamp = None
        context = multiprocessing.get_context('spawn')
        self.output = context.Queue(maxsize=2)
        self.stop = context.Event()
        self.process = context.Process(target=_worker, args=(self.output, self.stop, camera_index),
                                       name='Archidon duel camera', daemon=True)
        try:
            self.process.start()
            self.started = True
        except Exception:
            self.close()
            raise

    def read(self):
        if self.closed:
            raise RuntimeError('Camera duel is closed. Start it again.')
        timestamp = int(monotonic_seconds() * 1000)
        while True:
            try:
                packet = self.output.get_nowait()
            except queue.Empty:
                break
            except (EOFError, OSError) as exc:
                raise RuntimeError('Camera connection lost. Restart camera duel.') from exc
            if packet['type'] == 'error':
                raise RuntimeError(packet['message'])
            self.rgb = packet['rgb']
            self.observations = packet['observations']
            self.status = packet['status']
            self.last_stamp = packet['stamp']
        if not self.process.is_alive():
            raise RuntimeError('Camera worker stopped. Restart the game or choose keyboard duel.')
        if self.last_stamp is None:
            if timestamp - self.started_at > self.STARTUP_TIMEOUT_MS:
                raise RuntimeError('Camera startup timed out. Check webcam permission and models.')
        elif timestamp - self.last_stamp > self.FRAME_TIMEOUT_MS:
            raise RuntimeError('Camera frames stopped. Reconnect the webcam, or choose keyboard duel.')
        if self.last_stamp is not None and timestamp - self.last_stamp > 350:
            return self.rgb, [None, None], 'Waiting for fresh tracking — draws cancelled.', timestamp
        return self.rgb, self.observations, self.status, timestamp

    def preview(self, frame):
        return frame

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stop.set()
        if self.started:
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=1)
            if not self.process.is_alive():
                self.process.close()
        self.output.cancel_join_thread()
        self.output.close()
