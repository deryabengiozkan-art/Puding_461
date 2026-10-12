"""Shared projectile physics in metres, seconds and degrees.

Positive x travels toward the target (left on screen); positive y is up.
The original trajectory/scoring API and 50 / 25 / 15 scoring are retained.
Both the prediction dots and animated flight evaluate the same equations.
"""
from dataclasses import dataclass
import math

FIRST_CIRCLE_PTS = 50
SECOND_CIRCLE_PTS = 25
THIRD_CIRCLE_PTS = 15
ARCHER_HEIGHT = 1.4
TARGET_DISTANCE = 35.0
TARGET_HEIGHT = 1.0
TARGET_RADIUS = 0.5
GRAVITY = 9.81
MIN_GAME_SPEED = 12.0
MAX_GAME_SPEED = 24.0
MAX_ELEVATION = 90.0

# Preserve the names used in the original course files and notebooks.
First_Circle_Pts = FIRST_CIRCLE_PTS
Second_Circle_Pts = SECOND_CIRCLE_PTS
Third_Circle_Pts = THIRD_CIRCLE_PTS
Archer_Height = ARCHER_HEIGHT
Target_Distance = TARGET_DISTANCE
Target_Height = TARGET_HEIGHT


def strength_to_speed(strength):
    """Map calibrated pull [0, 1] to a useful speed for the distant target."""
    if not math.isfinite(strength):
        raise ValueError("Pull strength must be finite.")
    return MIN_GAME_SPEED + (MAX_GAME_SPEED - MIN_GAME_SPEED) * max(0.0, min(1.0, strength))


def clamp_elevation(angle):
    """Apply the same playable aim limit to both prediction and release."""
    if not math.isfinite(angle):
        raise ValueError("Aim elevation must be finite.")
    return max(-MAX_ELEVATION, min(MAX_ELEVATION, angle))


def _validate_shot(speed, angle):
    """Time-based flight also supports straight up and straight down shots."""
    if (not math.isfinite(speed) or not math.isfinite(angle)
            or speed <= 0 or not -90 <= angle <= 90):
        raise ValueError("A shot needs finite positive speed and elevation within -90 to 90 degrees.")


def _trajectory(speed, angle):
    """Return a, b, c for y(x); an exactly vertical path has no such function."""
    _validate_shot(speed, angle)
    if abs(angle) == 90:
        raise ValueError("A vertical trajectory cannot be expressed as y(x); use Shot.position(time).")
    vx = speed * math.cos(math.radians(angle))
    return -GRAVITY / (2 * vx * vx), math.tan(math.radians(angle)), ARCHER_HEIGHT


def score_height(height):
    """Inclusive boundaries: gold <= .2 m, red <= .4 m, blue <= .5 m."""
    if not math.isfinite(height):
        return 0
    error = abs(height - TARGET_HEIGHT)
    if error <= 0.2 + 1e-9:
        return FIRST_CIRCLE_PTS
    if error <= 0.4 + 1e-9:
        return SECOND_CIRCLE_PTS
    if error <= TARGET_RADIUS + 1e-9:
        return THIRD_CIRCLE_PTS
    return 0


@dataclass(frozen=True)
class Shot:
    speed: float
    angle: float

    def __post_init__(self):
        _validate_shot(self.speed, self.angle)  # Validate once when launching.

    @property
    def vx(self):
        # cos(90°) has a tiny floating-point residual. Exact vertical shots
        # have no horizontal travel, including their final ground position.
        if abs(self.angle) == 90:
            return 0.0
        return self.speed * math.cos(math.radians(self.angle))

    @property
    def vy(self):
        return self.speed * math.sin(math.radians(self.angle))

    @property
    def ground_time(self):
        vy = self.vy
        root = math.hypot(vy, math.sqrt(2 * GRAVITY * ARCHER_HEIGHT))
        if vy < 0:
            # Rationalizing the root avoids cancellation for steep down shots.
            return (2 * ARCHER_HEIGHT / root) / (1 - vy / root)
        return vy / GRAVITY + root / GRAVITY

    @property
    def target_time(self):
        return TARGET_DISTANCE / self.vx if self.vx > 0 else math.inf

    @property
    def end_time(self):
        return min(self.target_time, self.ground_time)

    @property
    def reaches_target(self):
        return self.target_time <= self.ground_time

    def position(self, seconds):
        return (self.vx * seconds,
                ARCHER_HEIGHT + self.vy * seconds - 0.5 * GRAVITY * seconds ** 2)

    def velocity(self, seconds):
        return self.vx, self.vy - GRAVITY * seconds

    def preview(self, spacing=0.025):
        """Sample the exact path, terminating at the same impact as live flight."""
        if not math.isfinite(spacing) or spacing <= 0:
            raise ValueError("Preview spacing must be finite and positive.")
        count = math.ceil(self.end_time / spacing)
        return [self.position(i * spacing) for i in range(count)] + [self.position(self.end_time)]


def Trajectory(speed, angle):
    """Original classroom API, backed by the same equations as animated flight."""
    return _trajectory(speed, angle)


def Score_Calculator(speed, angle):
    """Original scoring API; invalid or short shots earn zero points."""
    try:
        shot = Shot(speed, angle)
    except (TypeError, ValueError, OverflowError):
        return 0
    return score_height(shot.position(shot.end_time)[1]) if shot.reaches_target else 0
