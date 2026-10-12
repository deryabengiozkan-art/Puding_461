"""Duel aiming keeps both vertical endpoints after level-aim calibration."""
import numpy as np

from controls import Calibration, InputController
from physics import MAX_ELEVATION, Shot, clamp_elevation, strength_to_speed


class DuelCalibration(Calibration):
    def normalize(self, measurement):
        strength = float(np.clip(
            (measurement['gap'] - self.rest_gap) / (self.full_gap - self.rest_gap), 0, 1))
        angle = clamp_elevation(measurement['angle'])
        # The tracker itself is bounded at ±90°. Scale each side separately:
        # a nonlevel neutral must not consume one end of the aiming range.
        # Keep a minimal span if a player records a nearly vertical neutral.
        neutral = float(np.clip(self.neutral_angle, -MAX_ELEVATION + 1, MAX_ELEVATION - 1))
        span = MAX_ELEVATION - neutral if angle >= neutral else MAX_ELEVATION + neutral
        return strength, (angle - neutral) / span


class DuelInputController(InputController):
    def __init__(self, on_shot):
        super().__init__(on_shot)
        self.calibration = DuelCalibration()

    def reset(self, recalibrate=False):
        if recalibrate:
            self.calibration = DuelCalibration()
        super().reset(recalibrate=False)


def launch_velocity(strength, angle, facing):
    """Use identical clamping and exact vertical velocity for preview and fire."""
    shot = Shot(strength_to_speed(strength), clamp_elevation(angle))
    return facing * shot.vx, shot.vy
