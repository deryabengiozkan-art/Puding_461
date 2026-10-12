"""Round state only: three arrows, flight, impact and total score.

No window, camera or drawing starts when this module is imported.
The old separate menu loop is preserved in legacy/game_mechanics.py.
"""
from dataclasses import dataclass, field
import math
from physics import Shot, clamp_elevation, score_height, strength_to_speed

STATE_MENU = "MENU"
STATE_PLAY = "PLAY"
STATE_CALIBRATE = "CALIBRATE"
STATE_FINISH = "FINISH"
MAX_SHOTS = 3
# At maximum speed these samples are less than 0.3 metres apart. A shot's
# path is computed only once, then reused for its live trail and shot history.
PATH_SAMPLE_SECONDS = 0.0125


@dataclass
class Flight:
    shot: Shot
    elapsed: float = 0.0
    strength: float = 0.0
    path: tuple = field(init=False)

    def __post_init__(self):
        self.path = tuple(self.shot.preview(PATH_SAMPLE_SECONDS))

    @property
    def position(self):
        return self.shot.position(self.elapsed)

    @property
    def velocity(self):
        return self.shot.velocity(self.elapsed)

    @property
    def trail(self):
        """The flown part of the cached path, ending at the live arrow tip."""
        count = min(int(self.elapsed / PATH_SAMPLE_SECONDS) + 1, len(self.path))
        points = self.path[:count]
        position = self.position
        return points if points[-1] == position else points + (position,)


@dataclass(frozen=True)
class Impact:
    position: tuple
    velocity: tuple
    points: int
    on_target: bool


@dataclass(frozen=True)
class CompletedShot:
    """Immutable shot details kept until the player restarts the round."""
    number: int
    strength: float
    shot: Shot
    path: tuple
    impact: Impact


class GameRound:
    def __init__(self):
        self.reset()

    def reset(self):
        self.score = self.shots = 0
        self.arrow = None
        self.impacts = []
        self.history = []
        self.message = "Three arrows. The distant target is beyond your view."

    @property
    def last_shot(self):
        return self.history[-1] if self.history else None

    @property
    def finished(self):
        # Wait for the third arrow to land before showing the final score.
        return self.shots >= MAX_SHOTS and self.arrow is None

    def shoot(self, strength, angle):
        if self.arrow is not None or self.shots >= MAX_SHOTS:
            return False
        if not math.isfinite(strength) or not math.isfinite(angle) or strength < 0.08:
            return False
        strength = min(1.0, strength)
        shot = self.prediction(strength, angle)
        self.arrow = Flight(shot, strength=strength)
        self.shots += 1
        self.message = "Arrow in flight..."
        return True

    def update(self, dt):
        if self.arrow is None or not math.isfinite(dt) or dt <= 0:
            return
        flight = self.arrow
        flight.elapsed = min(flight.elapsed + dt, flight.shot.end_time)
        if flight.elapsed < flight.shot.end_time:
            return
        position = flight.position
        on_target = flight.shot.reaches_target
        points = score_height(position[1]) if on_target else 0
        impact = Impact(position, flight.velocity, points, on_target)
        self.impacts.append(impact)
        self.history.append(CompletedShot(self.shots, flight.strength, flight.shot,
                                          flight.path, impact))
        self.score += points
        self.arrow = None
        if points == 50:
            self.message = "Bullseye! +50 points"
        elif points:
            self.message = f"Hit! +{points} points"
        elif on_target:
            self.message = "Miss. Adjust your aim or pull."
        else:
            self.message = "Landed short. Try more pull or aim higher."

    def prediction(self, strength, angle):
        return Shot(strength_to_speed(strength), clamp_elevation(angle))
