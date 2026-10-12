"""Single-player campaign: level layouts, flight with wind/terrain/obstacles,
the arrow-budget round, and saved progress.

No window or camera starts on import. ``CampaignRound`` exposes the same
interface as ``game_mechanics.GameRound`` (shoot / update / arrow / impacts /
history / finished / prediction), so main.py's shared release gate, the game
camera and the webcam controls work unchanged.
"""
from dataclasses import dataclass
import json
import math
import random
from pathlib import Path

import numpy as np

from game_mechanics import Flight, CompletedShot
from levels import LEVELS, Level
from physics import ARCHER_HEIGHT, GRAVITY, clamp_elevation

STEP = 0.004            # collision sampling (s); < 0.16 m at 38 m/s
MAX_FLIGHT = 12.0       # s
REFINE = 28             # bisection iterations (sub-millimetre)
RINGS = ((0.4, 50), (0.8, 25), (1.0, 15))   # fraction of radius -> points
# The board is drawn as a disc, so it is hit wherever the arrow's path passes
# over that disc (not only where it crosses the centre line). The arrow sticks
# at its closest approach to the centre, and that distance sets the ring. A
# small margin for the arrow head keeps edge hits that look like hits.
HIT_MARGIN = 0.06
PROGRESS_FILE = Path(__file__).resolve().with_name('campaign_progress.json')


# --------------------------------------------------------------------------- layout
def terrain_height(x, hills):
    """Ground height (m) at world x; works on floats and numpy arrays."""
    x = np.asarray(x, dtype=float)
    h = np.zeros_like(x)
    for hill in hills:
        u = np.clip((x - hill.center) / hill.half_width, -1.0, 1.0)
        h = np.maximum(h, hill.height * 0.5 * (1 + np.cos(np.pi * u)))
    return h if h.ndim else float(h)


def obstacle_boxes(obstacle, clock):
    """Collision rectangles (x0, y0, x1, y1) of one obstacle at a level time."""
    dy = 0.0
    if obstacle.move_amp and obstacle.move_period:
        dy = obstacle.move_amp * math.sin(2 * math.pi * clock / obstacle.move_period)
    x, y, w, h = obstacle.x, obstacle.y + dy, obstacle.w, obstacle.h
    if obstacle.kind == 'tree':
        trunk = (x + w * 0.38, y, x + w * 0.62, y + h * 0.45)
        canopy = (x, y + h * 0.35, x + w, y + h)
        return trunk, canopy
    return ((x, y, x + w, y + h),)


@dataclass
class Layout:
    """One attempt's random state: target position and wind."""
    level: Level
    target_x: float
    target_y: float          # centre height at rest
    wind: float              # +: tailwind (toward target), -: headwind
    target_id: int = 0

    def target_center(self, clock):
        amp, period = self.level.target_motion
        if amp and period:
            return self.target_y + amp * math.sin(2 * math.pi * clock / period)
        return self.target_y

    @property
    def hills(self):
        return self.level.hills


def random_target(level, rng):
    x = rng.uniform(*level.distance)
    # Keep the whole board above the ground, whatever its size or motion.
    lowest = level.radius + 0.25 + level.target_motion[0]
    y = terrain_height(x, level.hills) + max(lowest, rng.uniform(*level.height))
    return round(x, 1), round(y, 2)


def make_layout(level, rng):
    x, y = random_target(level, rng)
    lo, hi = level.wind
    wind = rng.uniform(lo, hi) * rng.choice((-1, 1)) if hi > 0 else 0.0
    return Layout(level, x, y, round(wind, 2))


# --------------------------------------------------------------------------- flight
class CampaignShot:
    """Exact projectile with constant horizontal wind acceleration.

    Ends at the first of: board crossing inside the rings, an obstacle, the
    terrain, or MAX_FLIGHT. An arrow that misses the board keeps flying.
    """

    def __init__(self, speed, angle, layout, launch_clock=0.0):
        if not (math.isfinite(speed) and math.isfinite(angle)) or speed <= 0 or not -90 <= angle <= 90:
            raise ValueError('A shot needs finite positive speed and elevation within -90 to 90 degrees.')
        self.speed, self.angle = speed, angle
        self.layout, self.launch_clock = layout, launch_clock
        self.wind = layout.wind
        r = math.radians(angle)
        self.vx = 0.0 if abs(angle) == 90 else speed * math.cos(r)
        self.vy = speed * math.sin(r)
        self.outcome, self.end_time, self.points, self.offset = self._solve()

    # Shot-compatible API -------------------------------------------------
    def position(self, t):
        return (self.vx * t + 0.5 * self.wind * t * t,
                ARCHER_HEIGHT + self.vy * t - 0.5 * GRAVITY * t * t)

    def velocity(self, t):
        return self.vx + self.wind * t, self.vy - GRAVITY * t

    @property
    def reaches_target(self):
        return self.outcome == 'target'

    def preview(self, spacing=0.025):
        if not math.isfinite(spacing) or spacing <= 0:
            raise ValueError('Preview spacing must be finite and positive.')
        count = math.ceil(self.end_time / spacing)
        return [self.position(i * spacing) for i in range(count)] + [self.position(self.end_time)]

    # Collision -------------------------------------------------------------
    def _blocked(self, t):
        """Vectorised: True where the arrow is inside terrain or an obstacle."""
        t = np.asarray(t, dtype=float)
        x = self.vx * t + 0.5 * self.wind * t * t
        y = ARCHER_HEIGHT + self.vy * t - 0.5 * GRAVITY * t * t
        hit = y <= terrain_height(x, self.layout.hills)
        for obstacle in self.layout.level.obstacles:
            amp, period = obstacle.move_amp, obstacle.move_period
            dy = amp * np.sin(2 * np.pi * (self.launch_clock + t) / period) if amp and period else 0.0
            for x0, y0, x1, y1 in obstacle_boxes(obstacle, 0.0):
                hit |= (x >= x0) & (x <= x1) & (y >= y0 + dy) & (y <= y1 + dy)
        return hit

    def _target_time(self):
        """First time the arrow reaches the board's plane, or inf."""
        tx, a, b = self.layout.target_x, 0.5 * self.wind, self.vx
        if abs(a) < 1e-12:
            return tx / b if b > 0 else math.inf
        disc = b * b + 4 * a * tx
        if disc < 0:
            return math.inf
        roots = [(-b + s * math.sqrt(disc)) / (2 * a) for s in (1, -1)]
        roots = [r for r in roots if r > 0]
        return min(roots) if roots else math.inf

    def _solve(self):
        times = np.arange(STEP, MAX_FLIGHT + STEP, STEP)
        blocked = self._blocked(times)
        index = int(np.argmax(blocked)) if blocked.any() else None
        stop = MAX_FLIGHT
        if index is not None:
            lo = times[index - 1] if index else 0.0
            hi = times[index]
            for _ in range(REFINE):
                mid = (lo + hi) / 2
                if self._blocked(mid):
                    hi = mid
                else:
                    lo = mid
            stop = hi
        hit = self._board_hit(times, stop)
        if hit is not None:
            return hit
        if index is None:
            return 'timeout', stop, 0, (0.0, 0.0)
        x, y = self.position(stop)
        ground = terrain_height(x, self.layout.hills)
        return ('ground' if y <= ground + 0.02 else 'obstacle'), stop, 0, (0.0, 0.0)

    def _distance(self, t):
        """Vectorised distance from the arrow tip to the (possibly moving) board centre."""
        t = np.asarray(t, dtype=float)
        x = self.vx * t + 0.5 * self.wind * t * t
        y = ARCHER_HEIGHT + self.vy * t - 0.5 * GRAVITY * t * t
        layout = self.layout
        amp, period = layout.level.target_motion
        cy = layout.target_y + (amp * np.sin(2 * np.pi * (self.launch_clock + t) / period)
                                if amp and period else 0.0)
        return np.hypot(x - layout.target_x, y - cy)

    def _board_hit(self, times, stop):
        radius = self.layout.level.radius
        reach = radius + HIT_MARGIN
        times = np.concatenate(([0.0], times[times < stop], [stop]))
        d = self._distance(times)
        inside = d <= reach
        if not inside.any():
            # A fast arrow can cross a small board between samples: check the
            # closest sample pair around the minimum more finely.
            k = int(np.argmin(d))
            fine = np.linspace(times[max(0, k - 1)], times[min(len(times) - 1, k + 1)], 64)
            if self._distance(fine).min() > reach:
                return None
            times, d = fine, self._distance(fine)
            inside = d <= reach
        first = int(np.argmax(inside))
        leave = np.argmax(~inside[first:])
        end = first + (int(leave) if leave else len(inside) - first)
        k = first + int(np.argmin(d[first:end]))
        # Golden-section search for the exact closest approach near sample k.
        lo, hi = times[max(0, k - 1)], times[min(len(times) - 1, k + 1)]
        g = (math.sqrt(5) - 1) / 2
        for _ in range(40):
            a, b = hi - g * (hi - lo), lo + g * (hi - lo)
            if self._distance(a) < self._distance(b):
                hi = b
            else:
                lo = a
        t_hit = min(stop, (lo + hi) / 2)
        distance = float(self._distance(t_hit))
        if distance > reach:
            return None
        x, y = self.position(t_hit)
        offset = (float(x - self.layout.target_x), float(y - self.layout.target_center(self.launch_clock + t_hit)))
        for fraction, points in RINGS:
            limit = fraction * radius + (HIT_MARGIN if fraction == 1.0 else 0.0)
            if distance <= limit + 1e-9:
                return 'target', t_hit, points, offset
        return None


# --------------------------------------------------------------------------- round
@dataclass(frozen=True)
class CampaignImpact:
    position: tuple
    velocity: tuple
    points: int
    on_target: bool
    outcome: str
    target_id: int
    offset: tuple      # (dx, dy) from the board centre for arrows stuck in it


def stars_for(level, score):
    if score < level.required:
        return 0
    span = level.max_score - level.required
    if score >= level.required + 0.65 * span:
        return 3
    if score >= level.required + 0.35 * span:
        return 2
    return 1


class CampaignRound:
    """One attempt at one level; GameRound-compatible for main.py."""

    def __init__(self, level, seed=None):
        self.level = level if isinstance(level, Level) else LEVELS[level - 1]
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.layout = make_layout(self.level, self.rng)
        self.score = self.shots = 0
        self.clock = 0.0
        self.arrow = None
        self.pending_relocate = False
        self.impacts = []
        self.history = []
        self.message = f'{self.level.arrows} arrows. Score {self.level.required} to clear.'

    # GameRound-compatible properties --------------------------------------
    @property
    def max_shots(self):
        return self.level.arrows

    @property
    def last_shot(self):
        return self.history[-1] if self.history else None

    @property
    def arrows_left(self):
        return self.level.arrows - self.shots

    @property
    def passed(self):
        return self.score >= self.level.required

    @property
    def hopeless(self):
        """Even straight gold with every remaining arrow cannot clear the level."""
        return self.score + 50 * self.arrows_left < self.level.required

    @property
    def finished(self):
        return self.arrow is None and (self.shots >= self.level.arrows or self.hopeless)

    @property
    def stars(self):
        return stars_for(self.level, self.score)

    def speed(self, strength):
        lv = self.level
        return lv.min_speed + (lv.max_speed - lv.min_speed) * max(0.0, min(1.0, strength))

    def prediction(self, strength, angle):
        return CampaignShot(self.speed(strength), clamp_elevation(angle), self.layout, self.clock)

    def shoot(self, strength, angle):
        self.settle()
        if self.arrow is not None or self.finished:
            return False
        if not math.isfinite(strength) or not math.isfinite(angle) or strength < 0.08:
            return False
        strength = min(1.0, strength)
        self.arrow = Flight(self.prediction(strength, angle), strength=strength)
        self.shots += 1
        self.message = 'Arrow in flight...'
        return True

    def update(self, dt):
        if not math.isfinite(dt) or dt <= 0:
            return
        self.clock += dt
        if self.arrow is None:
            return
        flight = self.arrow
        flight.elapsed = min(flight.elapsed + dt, flight.shot.end_time)
        if flight.elapsed < flight.shot.end_time:
            return
        shot = flight.shot
        impact = CampaignImpact(flight.position, flight.velocity, shot.points, shot.reaches_target,
                                shot.outcome, self.layout.target_id, shot.offset)
        self.impacts.append(impact)
        self.history.append(CompletedShot(self.shots, flight.strength, shot, flight.path, impact))
        self.score += shot.points
        self.arrow = None
        self.message = self._describe(impact)
        # Relocate only after the player has seen the landing (see settle()).
        self.pending_relocate = self.level.relocate and not self.finished

    def force_finish(self):
        """Admin: end the level now with the current score."""
        if self.arrow is None:
            self.shots = self.level.arrows
            self.pending_relocate = False

    def settle(self):
        """Called once the game camera is back at the archer."""
        if self.pending_relocate and self.arrow is None:
            self.pending_relocate = False
            self.relocate()

    def relocate(self):
        x, y = random_target(self.level, self.rng)
        self.layout.target_x, self.layout.target_y = x, y
        self.layout.target_id += 1
        self.message += f'  Board moved to {x:.0f} m.'

    def _describe(self, impact):
        need = max(0, self.level.required - self.score)
        tail = f' Need {need} more.' if need else ' Required score reached!'
        if impact.points == 50:
            return 'Bullseye! +50.' + tail
        if impact.points:
            return f'Hit! +{impact.points}.' + tail
        if impact.outcome == 'obstacle':
            return 'Blocked by an obstacle. Change your arc.' + tail
        x = impact.position[0]
        if x < self.layout.target_x:
            return f'Short by {self.layout.target_x - x:.1f} m. More pull or higher.' + tail
        return 'Missed the board. Adjust your aim.' + tail


# --------------------------------------------------------------------------- progress
class CampaignProgress:
    """Unlocked levels, best scores and stars; saved as JSON beside the game."""

    def __init__(self, path=PROGRESS_FILE):
        self.path = Path(path) if path else None
        self.unlocked = 1
        self.best = {}
        self.stars = {}
        self.unlock_all = False      # --unlock-all: this run only, never saved
        self.load()

    def load(self):
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            self.unlocked = max(1, min(len(LEVELS), int(data.get('unlocked', 1))))
            self.best = {int(k): int(v) for k, v in data.get('best', {}).items()}
            self.stars = {int(k): int(v) for k, v in data.get('stars', {}).items()}
        except (OSError, ValueError, TypeError, AttributeError):
            self.unlocked, self.best, self.stars = 1, {}, {}

    def save(self):
        if not self.path:
            return
        try:
            self.path.write_text(json.dumps({'unlocked': self.unlocked, 'best': self.best,
                                             'stars': self.stars}, indent=1))
        except OSError:
            pass

    def record(self, game):
        number = game.level.number
        self.best[number] = max(self.best.get(number, 0), game.score)
        self.stars[number] = max(self.stars.get(number, 0), game.stars)
        if game.passed:
            self.unlocked = max(self.unlocked, min(len(LEVELS), number + 1))
        self.save()

    def is_unlocked(self, number):
        return self.unlock_all or number <= self.unlocked

    @property
    def total_stars(self):
        return sum(self.stars.values())
