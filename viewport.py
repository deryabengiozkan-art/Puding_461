"""The game camera follows the arrow, holds its landing, then returns to aim.

Offsets are metres in the same world as physics. No Pygame or webcam imports;
this camera changes the scenery only, never the measured hand coordinates.
"""
import math


class WorldCamera:
    AIM = 'AIM'
    FOLLOW = 'FOLLOW'
    IMPACT = 'IMPACT'
    RETURN = 'RETURN'
    FOLLOW_FROM_X = 5.15
    FOLLOW_HEIGHT = 4.5
    IMPACT_SECONDS = 0.8
    RETURN_SECONDS = 0.9

    def __init__(self):
        self.reset()

    def reset(self):
        self.pan_x = self.pan_y = 0.0
        self.phase = self.AIM
        self._seen_impact = None
        self._hold_left = 0.0
        self._return_elapsed = 0.0
        self._return_from = (0.0, 0.0)

    @property
    def can_shoot(self):
        return self.phase == self.AIM

    @staticmethod
    def focus(position):
        return max(0.0, position[0] - WorldCamera.FOLLOW_FROM_X), max(0.0, position[1] - WorldCamera.FOLLOW_HEIGHT)

    def update(self, dt, flight, latest_impact=None):
        if not math.isfinite(dt) or dt < 0:
            return
        if flight is not None:
            self.phase = self.FOLLOW
            desired_x, desired_y = self.focus(flight.position)
            weight = 1 - math.exp(-dt / 0.10)
            self.pan_x += weight * (desired_x - self.pan_x)
            self.pan_y += weight * (desired_y - self.pan_y)
            return

        # The same impact is supplied on every frame; recognize it only once.
        if latest_impact is not None and latest_impact is not self._seen_impact:
            self._seen_impact = latest_impact
            self.pan_x, self.pan_y = self.focus(latest_impact.position)
            self.phase = self.IMPACT
            self._hold_left = self.IMPACT_SECONDS

        if self.phase == self.IMPACT:
            held = min(dt, self._hold_left)
            self._hold_left -= held
            dt -= held
            if self._hold_left > 1e-9:
                return
            self.phase = self.RETURN
            self._return_from = (self.pan_x, self.pan_y)
            self._return_elapsed = 0.0

        if self.phase == self.RETURN:
            self._return_elapsed = min(self.RETURN_SECONDS, self._return_elapsed + dt)
            fraction = self._return_elapsed / self.RETURN_SECONDS
            eased = fraction * fraction * (3 - 2 * fraction)
            self.pan_x = self._return_from[0] * (1 - eased)
            self.pan_y = self._return_from[1] * (1 - eased)
            if fraction >= 1 - 1e-9:
                self.phase = self.AIM
                self.pan_x = self.pan_y = 0.0
