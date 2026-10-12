"""Controls reused from archery_game.py: calibration, smoothing and release.

This module depends only on NumPy, so it can also run in the Pygame process.
The unchanged tracker algorithms run in the separate camera worker.
"""
import numpy as np
from physics import MAX_ELEVATION
from tracking_clock import monotonic_seconds

class Calibration:
    """Record camera position, relaxed wrist gap, and full pull in three steps."""

    AIM_RANGE = MAX_ELEVATION  # Neutral aim can move through the full ±90° range.
    CAPTURE_MS = 1000
    SAMPLE_WINDOW_MS = 4000
    MAX_SAMPLE_GAP_MS = 1500
    MIN_SAMPLES = 4
    instructions = [
        ("1 / 3  CAMERA POSITION", "Face the camera with both shoulders clearly visible."),
        ("2 / 3  RELAXED GAP", "Bring your hands close, with a small gap between them."),
        ("3 / 3  FULL PULL", "Pull comfortably apart. Hold your normal, level aim."),
    ]

    def __init__(self):
        self.step = 0
        self.capturing = False
        self.samples = []
        self.camera_scale = None
        self.rest_gap = None
        self.full_gap = None
        self.neutral_angle = None
        self.message = "Press SPACE when you are comfortable."

    def ready(self):
        return self.step == 3

    def start_capture(self):
        if self.capturing:
            return  # Holding Space must not keep restarting the timer.
        self.capturing = True
        self.samples = []

    def update(self, measurement, timestamp=None, tracking_message=None):
        if self.ready() or not self.capturing:
            return
        if measurement is None:
            # A short missed detection should not erase an otherwise steady capture.
            if self.samples and timestamp is not None and timestamp - self.samples[-1]["stamp"] > self.MAX_SAMPLE_GAP_MS:
                self.samples = []
            fallback = "Waiting for shoulder tracking." if self.step == 0 else "Tracking briefly paused. Keep your position."
            self.message = tracking_message or fallback
            return

        gap = measurement["gap"]
        if self.step == 1 and gap > 0.8:
            self.samples = []
            self.message = "Bring your hands closer, without overlapping them."
            return
        if self.step == 2 and gap < self.rest_gap + 0.4:
            self.samples = []
            self.message = "Pull farther apart so we can measure a useful range."
            return

        # Count camera results, not repetitions of the same result in the display loop.
        if self.samples and measurement["stamp"] <= self.samples[-1]["stamp"]:
            return
        if self.samples and measurement["stamp"] - self.samples[-1]["stamp"] > self.MAX_SAMPLE_GAP_MS:
            self.samples = []
        self.samples.append(measurement)
        # Keep a short window. An old outlier must not block calibration forever.
        # A frame-count cap can prevent one second ever accumulating at high
        # frame rates. A longer time window also admits slower model callbacks.
        self.samples = [s for s in self.samples if measurement["stamp"] - s["stamp"] <= self.SAMPLE_WINDOW_MS]
        elapsed = measurement["stamp"] - self.samples[0]["stamp"]
        progress = min(elapsed / self.CAPTURE_MS, len(self.samples) / self.MIN_SAMPLES, 1)
        self.message = f"Hold steady: {progress:.0%} ({len(self.samples)} tracking samples)"
        if elapsed < self.CAPTURE_MS or len(self.samples) < self.MIN_SAMPLES:
            return

        # Compare the middle 80% of samples so one bad landmark does not reset progress.
        def spread(name):
            low, high = np.percentile([s[name] for s in self.samples], [10, 90])
            return high - low

        moving = spread("scale") > 0.04
        if self.step > 0:
            moving = moving or spread("gap") > 0.25
        if self.step == 2:
            moving = moving or spread("angle") > 12
        if moving:
            self.message = "Almost there. Keep this position a little steadier."
            return

        # Medians reduce the influence of small landmark errors during calibration.
        if self.step == 0:
            self.camera_scale = float(np.median([s["scale"] for s in self.samples]))
        elif self.step == 1:
            self.rest_gap = float(np.median([s["gap"] for s in self.samples]))
        else:
            self.full_gap = float(np.median([s["gap"] for s in self.samples]))
            self.neutral_angle = float(np.median([s["angle"] for s in self.samples]))
        self.step += 1
        self.capturing = False
        self.samples = []
        self.message = "Press SPACE to record the next position."

    def normalize(self, measurement):
        # Distances are already divided by shoulder width, which reduces scale changes.
        strength = (measurement["gap"] - self.rest_gap) / (self.full_gap - self.rest_gap)
        strength = float(np.clip(strength, 0, 1))

        # Neutral aim is zero; 90 degrees above/below it becomes +1/-1.
        direction = (measurement["angle"] - self.neutral_angle) / self.AIM_RANGE
        direction = float(np.clip(direction, -1, 1))
        return strength, direction


class InputController:
    TRACKING_GRACE_MS = 500
    RELEASE_CONFIRM_MS = 100
    POSE_MAX_AGE_MS = 400
    SETUP_POSE_MAX_AGE_MS = 1000
    HAND_MAX_AGE_MS = 250

    def __init__(self, on_shot):
        self.on_shot = on_shot
        self.pose_tracker = None
        self.hand_tracker = None
        self.drawing_hand = "Right"
        self.calibration = Calibration()
        self.strength = self.direction = self.aim_degrees = 0.0
        self.drawing = False
        self.last_draw = self.last_control_stamp = self.last_closed_stamp = None
        self.release_since = self.filter_stamp = None
        self.controls_clear = False
        self.hand_state = "Unknown"
        self.arrow = None  # The round supplies its current projectile before updating controls.
        self.status = "Calibration required."

    def reset(self, recalibrate=False):
        self.cancel_draw()
        self.last_control_stamp = self.filter_stamp = None
        self.strength = self.direction = self.aim_degrees = 0.0
        self.controls_clear = False
        self.hand_state = "Unknown"
        self.arrow = None
        if recalibrate:
            self.calibration = Calibration()
        self.status = ("Calibration required." if not self.calibration.ready() else
                       "Close your drawing hand to draw; open it to release.")

    def shoot(self, strength, angle):
        self.cancel_draw()
        self.controls_clear = False
        if self.arrow is not None:
            self.status = "Arrow in flight."
            return False
        accepted = self.on_shot(strength, angle)
        if accepted:
            self.status = "Arrow in flight."
        else:
            self.status = "Pull a little farther before shooting."
        return bool(accepted)

    def read_measurement(self, frame, timestamp, pose_tracker=None, hand_tracker=None):
        """Turn fresh tracker results into wrist gap and wrist-line tilt.

        The process bridge supplies immutable snapshots explicitly. Controller
        tracker attributes are also accepted for the original standalone flow.
        """
        pose_tracker = pose_tracker if pose_tracker is not None else self.pose_tracker
        hand_tracker = hand_tracker if hand_tracker is not None else self.hand_tracker
        if pose_tracker is None:
            return None, "Starting shoulder tracking..."
        pose, pose_time = pose_tracker.pose_sample
        if pose is None:
            return None, "No shoulders detected. Face the camera with both shoulders visible."
        # Position setup cannot fire an arrow, so allow the slower initial pose
        # results. Keep the stricter freshness rule for hands and gameplay.
        max_age = self.SETUP_POSE_MAX_AGE_MS if self.calibration.step == 0 else self.POSE_MAX_AGE_MS
        if not -50 <= timestamp - pose_time <= max_age:
            return None, "No fresh shoulder result. Reconnect camera play if tracking stays frozen."
        pose = np.asarray(pose)
        if pose.ndim != 2 or pose.shape[0] < 13 or pose.shape[1] != 2:
            return None, "Waiting for complete shoulder tracking."

        height, width = frame.shape[:2]
        size = np.array([width, height])
        shoulder_points = pose[[11, 12]]
        if not np.isfinite(shoulder_points).all() or np.any(shoulder_points < 0.02) or np.any(shoulder_points > 0.98):
            return None, "Keep both shoulders inside the picture."

        shoulders = np.linalg.norm((pose[11] - pose[12]) * size)
        scale = shoulders / width
        if scale < 0.08:
            return None, "Move closer and face the camera."
        if scale > 0.75:
            return None, "Step back a little."

        # Positioning the camera needs only shoulders, not reliable hand gestures.
        if self.calibration.step == 0:
            return {"stamp": pose_time, "scale": scale, "pose": pose,
                    "wrists": {}, "gap": 0.0, "angle": 0.0, "state": "Unknown"}, "Camera distance looks good."
        if hand_tracker is None:
            return None, "Starting hand tracking..."
        stamp, wrists, fresh, states = hand_tracker.game_sample
        if not fresh or "Left" not in wrists or "Right" not in wrists:
            return None, "Show both hands clearly inside the camera picture."
        if not -50 <= timestamp - stamp <= self.HAND_MAX_AGE_MS or abs(stamp - pose_time) > self.HAND_MAX_AGE_MS:
            return None, "Waiting for fresh hand tracking."
        hand_points = np.array([wrists["Left"], wrists["Right"]])
        if not np.isfinite(hand_points).all() or np.any(hand_points < 0.01) or np.any(hand_points > 0.99):
            return None, "Keep both hands inside the picture."

        bow_hand = "Left" if self.drawing_hand == "Right" else "Right"
        draw = wrists[self.drawing_hand] * size
        bow = wrists[bow_hand] * size
        gap = float(np.linalg.norm(bow - draw) / shoulders)
        if gap < 0.10:
            return None, "Leave a small visible gap between your hands."

        # Raising the bow hand raises aim, for either choice of drawing hand.
        dx, dy = bow - draw
        angle = float(np.degrees(np.arctan2(-dy, abs(dx))))
        return {
            "stamp": stamp, "gap": gap, "angle": angle, "scale": scale,
            "state": states.get(self.drawing_hand, "Unknown"),
            "wrists": wrists, "pose": pose,
        }, "Tracking OK"

    def update_controls(self, measurement, timestamp=None):
        """A fresh closed hand starts at any gap; confirmed opening releases."""
        if timestamp is None:
            timestamp = measurement["stamp"] if measurement is not None else int(monotonic_seconds() * 1000)
        # Flight cannot preserve a draw that later releases as another arrow.
        # Consume its camera stamps too, so the result seen at impact is not
        # replayed as the beginning of a fresh draw.
        if self.arrow is not None:
            self.cancel_draw()
            self.controls_clear = False
            self.hand_state = measurement["state"] if measurement is not None else "Unknown"
            if measurement is not None:
                self.last_control_stamp = max(measurement["stamp"], self.last_control_stamp or -1)
            self.status = "Arrow in flight."
            return
        if not self.calibration.ready():
            self.cancel_draw()
            self.controls_clear = False
            self.status = "Calibration required."
            return
        if measurement is not None and not -50 <= timestamp - measurement["stamp"] <= self.HAND_MAX_AGE_MS:
            measurement = None
        self.controls_clear = measurement is not None
        self.hand_state = measurement["state"] if measurement is not None else "Unknown"

        # Preserve the last aim briefly, but require fresh data to release an arrow.
        if measurement is None or self.hand_state == "Unknown":
            self.release_since = None
            if self.last_closed_stamp is not None and timestamp - self.last_closed_stamp <= self.TRACKING_GRACE_MS:
                self.status = "Tracking paused briefly - holding your draw."
            else:
                self.cancel_draw()
                self.status = "Show your drawing hand clearly; SPACE also fires with wrist tracking."
            if measurement is None:
                return

        # Returning after a long gap cannot release an old draw, even if no intermediate frame ran.
        if self.drawing and timestamp - self.last_closed_stamp > self.TRACKING_GRACE_MS:
            self.cancel_draw()
        if measurement["stamp"] <= (self.last_control_stamp if self.last_control_stamp is not None else -1):
            return
        self.last_control_stamp = measurement["stamp"]

        strength, direction = self.calibration.normalize(measurement)
        # Time-based smoothing behaves the same at different camera frame rates.
        weight = 1.0 if self.filter_stamp is None else 1 - np.exp(-(measurement["stamp"] - self.filter_stamp) / 100)
        self.filter_stamp = measurement["stamp"]
        if self.drawing and self.hand_state != "Closed":
            weight = 0.0  # Opening fingers must not change the shot being released.
        self.strength += weight * (strength - self.strength)
        self.direction += weight * (direction - self.direction)
        # Level is 0 degrees. Positive angles aim up; negative angles aim down.
        self.aim_degrees = self.calibration.AIM_RANGE * self.direction

        if self.hand_state == "Unknown":
            return
        if self.hand_state == "Closed":
            self.release_since = None
            # Calibration defines power only. It is not a physical reset pose:
            # after a shot or tracking loss, close again wherever comfortable.
            self.drawing = True
            self.last_draw = (self.strength, self.aim_degrees)
            self.last_closed_stamp = measurement["stamp"]
            self.status = "Pull and aim. Open your drawing hand to release."
        elif self.drawing and self.last_draw is not None:
            # Confirm Open on multiple results; a single misclassification must not fire.
            if self.release_since is None:
                self.release_since = measurement["stamp"]
            if measurement["stamp"] - self.release_since >= self.RELEASE_CONFIRM_MS:
                self.shoot(*self.last_draw)
            else:
                self.status = "Release detected..."
        else:
            self.status = "Close your drawing hand to draw; open it to release."


    def cancel_draw(self):
        """Forget an unfinished shot after a long interruption or reset."""
        self.drawing = False
        self.last_draw = None
        self.last_closed_stamp = None
        self.release_since = None
