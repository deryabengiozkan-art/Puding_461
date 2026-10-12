"""Two independent archers in one shared, moving-target ballistic duel.

Public integration:
    match = DuelMatch(('ranger', 'storm'), keyboard=False)
    match.request_capture()              # Space during each calibration step
    match.apply_tracking(observations, shared_clock_ms)
    match.keyboard(0, move=-1, aim=1, draw=True, dt=frame_seconds)
    match.keyboard(0, release=True)       # F / Enter key-up
    match.update(frame_seconds)

Camera observations come from DuelSession.read(). Three synchronized one-second
captures record body positions, relaxed gaps, then full pulls and neutral aim.
Tracking never shoots on stale, ambiguous, missing or reacquired samples.
"""
from dataclasses import dataclass, field
import math
import numpy as np
from controls import InputController
from duel_aim import DuelInputController, launch_velocity
from physics import GRAVITY, clamp_elevation
import hitbox

PLAYER_STARTS = (9.0, 31.0)
CAMERA_METRES_PER_SHOULDER = 8.0
MAX_HEALTH = 100


def _camera_position(player_id, observation, baseline):
    """Calibrated relative movement without world-position or distance clamps.

    Shoulder width normalizes lateral travel as camera distance changes. Depth
    is a monocular gameplay proxy; neither value measures physical metres.
    """
    lateral = ((observation['center'][0] - baseline['center'][0])
               / observation['scale'] * CAMERA_METRES_PER_SHOULDER)
    depth = (baseline['scale'] / observation['scale'] - 1) * 6
    return float(PLAYER_STARTS[player_id] + lateral + depth * (-1 if player_id == 0 else 1))


@dataclass
class DuelPlayer:
    id: int
    character: str
    x: float
    health: int = MAX_HEALTH
    strength: float = .0
    angle: float = 15.0
    drawing: bool = False
    facing: int = 1
    tracking: bool = False
    status: str = 'Ready'
    shots: int = 0
    hits: int = 0
    cooldown: float = 0.0


@dataclass
class DuelArrow:
    owner: int
    x: float
    y: float
    vx: float
    vy: float
    strength: float
    age: float = 0.0
    trail: list = field(default_factory=list)

    @property
    def position(self):
        return self.x, self.y

    @property
    def velocity(self):
        return self.vx, self.vy


class DuelMatch:
    calibration_instructions = [
        ('1 / 3  BOTH PLAYERS IN FRAME', 'P1 starts on the preview left, P2 on the right. Face the camera and hold still.'),
        ('2 / 3  RELAXED HANDS', 'Both players bring their hands close, leaving a small visible gap.'),
        ('3 / 3  FULL PULL', 'Both players pull comfortably apart. Hold your normal level aim.'),
    ]
    FRESH_MS = 350
    CAPTURE_MS = 1000
    MIN_CAPTURE_SAMPLES = 6

    def __init__(self, character_ids=('ranger', 'storm'), keyboard=False):
        self.character_ids = tuple(character_ids)
        self.keyboard_mode = keyboard
        self.controllers = [DuelInputController(lambda strength, angle, i=i: self.shoot(i, strength, angle))
                            for i in range(2)]
        self.calibration_step = 3 if keyboard else 0
        self.calibration_message = 'Press SPACE when both players are ready.'
        self.capturing = False
        self.capture_samples = []
        self.body_baselines = [None, None]
        self.reset()

    @property
    def ready(self):
        return self.calibration_step == 3

    @property
    def finished(self):
        return self.winner is not None

    @property
    def separation(self):
        return abs(self.players[1].x - self.players[0].x)

    @property
    def status(self):
        if self.winner == 'draw':
            return 'Double knockout — draw!'
        if self.winner is not None:
            return f'Player {self.winner + 1} wins!'
        if min(p.health for p in self.players) == 0:
            return 'Final arrows in flight...'
        return 'Move, aim, pull and release. First knockout wins.'

    def reset(self, recalibrate=False):
        if recalibrate and not self.keyboard_mode:
            self.calibration_step = 0
            self.body_baselines = [None, None]
        self.players = [DuelPlayer(i, self.character_ids[i], x, facing=1 if i == 0 else -1)
                        for i, x in enumerate((9., 31.))]
        self.arrows = []
        self.impacts = []
        self.winner = None
        self.time = 0.0
        self.capturing = False
        self.capture_samples = []
        self._last_stamp = [-1, -1]
        self._generation = [None, None]
        self._physics_x = [p.x for p in self.players]
        for controller in self.controllers:
            controller.reset(recalibrate=recalibrate)
        if self.keyboard_mode:
            for player in self.players:
                player.strength = .65
                player.tracking = True
                player.status = 'Hold draw key; release to fire.'

    def request_capture(self):
        if not self.ready and not self.capturing:
            self.capturing = True
            self.capture_samples = []
            self.calibration_message = 'Hold still while both players are measured...'

    def _fresh(self, observation, timestamp):
        if observation is None:
            return False
        values = [*observation.get('center', (math.nan, math.nan)), observation.get('scale', math.nan)]
        return (observation.get('identity_clear', False) and all(math.isfinite(v) for v in values)
                and .012 < observation['scale'] < .65
                and -50 <= timestamp - observation['stamp'] <= self.FRESH_MS)

    def _capture(self, observations, timestamp):
        if not self.capturing:
            return
        valid = len(observations) == 2 and all(self._fresh(o, timestamp) for o in observations)
        if valid and self.calibration_step > 0:
            valid = all(o.get('hands_clear', False) and math.isfinite(o.get('gap', math.nan))
                        and math.isfinite(o.get('angle', math.nan)) for o in observations)
        if not valid:
            self.capture_samples = []
            self.calibration_message = 'Show both players clearly; keep both wrists visible.'
            return
        if self.calibration_step == 1 and any(o['gap'] > .8 for o in observations):
            self.capture_samples = []
            self.calibration_message = 'Both players: bring hands closer without overlapping them.'
            return
        if self.calibration_step == 2 and any(o['gap'] < c.calibration.rest_gap + .4
                                             for o, c in zip(observations, self.controllers)):
            self.capture_samples = []
            self.calibration_message = 'Both players: pull farther apart for a useful power range.'
            return
        stamp = min(o['stamp'] for o in observations)
        generations = tuple(o.get('generation', 0) for o in observations)
        if self.capture_samples:
            if stamp <= self.capture_samples[-1][0]:
                return
            if stamp - self.capture_samples[-1][0] > self.FRESH_MS or generations != self.capture_samples[-1][2]:
                self.capture_samples = []
        self.capture_samples.append((stamp, [dict(o) for o in observations], generations))
        self.capture_samples = [s for s in self.capture_samples if stamp - s[0] <= 4000]
        elapsed = stamp - self.capture_samples[0][0]
        self.calibration_message = f'Both hold steady: {min(1, elapsed / self.CAPTURE_MS):.0%}'
        if elapsed < self.CAPTURE_MS or len(self.capture_samples) < self.MIN_CAPTURE_SAMPLES:
            return
        for player_id in range(2):
            samples = [sample[1][player_id] for sample in self.capture_samples]
            def spread(key):
                lo, hi = np.percentile([s[key] for s in samples], (10, 90), axis=0)
                return float(np.max(hi - lo))
            if spread('scale') > .035 or spread('center') > .035 or (self.calibration_step > 0 and spread('gap') > .25) or (self.calibration_step == 2 and spread('angle') > 12):
                self.calibration_message = 'Hold a little steadier; both players are still being measured.'
                return
        for player_id, controller in enumerate(self.controllers):
            samples = [sample[1][player_id] for sample in self.capture_samples]
            median = lambda key: np.median([s[key] for s in samples], axis=0)
            if self.calibration_step == 0:
                self.body_baselines[player_id] = {'center': median('center'), 'scale': float(median('scale'))}
                controller.calibration.camera_scale = float(median('scale'))
            elif self.calibration_step == 1:
                controller.calibration.rest_gap = float(median('gap'))
            else:
                controller.calibration.full_gap = float(median('gap'))
                controller.calibration.neutral_angle = float(median('angle'))
            controller.calibration.step = self.calibration_step + 1
        self.calibration_step += 1
        self.capturing = False
        self.capture_samples = []
        self.calibration_message = ('Calibration complete. Close each right hand to draw; open it to release.'
                                    if self.ready else 'Step recorded. Press SPACE for the next position.')
        self.cancel_draws()

    def apply_tracking(self, observations, timestamp):
        if self.finished:
            return
        observations = list(observations or [None, None])
        if len(observations) != 2:
            observations = [None, None]
        if not self.ready:
            self._capture(observations, timestamp)
            for player, observation in zip(self.players, observations):
                player.tracking = self._fresh(observation, timestamp)
            return
        control_samples = []
        for i, (player, controller, observation) in enumerate(zip(self.players, self.controllers, observations)):
            if not self._fresh(observation, timestamp):
                player.tracking = False
                player.status = 'Tracking paused — show your shoulders and hands.'
                controller.cancel_draw()
                controller.release_since = None
                player.drawing = False
                continue
            player.tracking = True
            stamp = observation['stamp']
            gap = stamp - self._last_stamp[i]
            generation = observation.get('generation', 0)
            reacquired = (self._generation[i] != generation or gap > self.FRESH_MS)
            if reacquired:
                controller.cancel_draw()
                controller.last_control_stamp = None
                controller.filter_stamp = None
            self._generation[i] = generation
            if stamp > self._last_stamp[i]:
                baseline = self.body_baselines[i]
                if baseline is not None:
                    x = _camera_position(i, observation, baseline)
                    # Long gaps cannot turn reacquisition into an abrupt jump.
                    weight = 1 if self._last_stamp[i] < 0 else 1 - math.exp(-min(max(gap, 0), 100) / 90)
                    player.x += weight * (x - player.x)
                self._last_stamp[i] = stamp
            control_samples.append((player, controller, observation, reacquired))
        # Both bodies belong to the same camera frame. Resolve their positions
        # before either release callback can choose a facing and launch point.
        self._face_opponent()
        for player, controller, observation, reacquired in control_samples:
            stamp = observation['stamp']
            if (not observation.get('hands_clear', False)
                    or timestamp - stamp > InputController.HAND_MAX_AGE_MS):
                controller.cancel_draw()
                player.drawing = False
                player.status = 'Show both hands clearly; right hand closes to draw.'
                continue
            # An open hand upon reacquisition cannot release an old closed draw.
            if reacquired and observation.get('state') != 'Closed':
                player.drawing = False
                player.status = 'Close your right hand to begin a fresh draw.'
                continue
            if min(p.health for p in self.players) <= 0:
                controller.cancel_draw()
                player.drawing = False
                continue
            controller.update_controls(observation, timestamp)
            player.strength, player.angle = controller.strength, controller.aim_degrees
            player.drawing, player.status = controller.drawing, controller.status

    def _face_opponent(self):
        if abs(self.players[1].x - self.players[0].x) > .05:
            self.players[0].facing = 1 if self.players[1].x > self.players[0].x else -1
            self.players[1].facing = -self.players[0].facing

    def cancel_draws(self):
        for controller, player in zip(self.controllers, self.players):
            controller.cancel_draw()
            player.drawing = False

    def keyboard(self, player_id, move=0, aim=0, draw=False, release=False, dt=0):
        if not self.ready or self.finished or not self.keyboard_mode:
            return False
        if not math.isfinite(dt) or dt < 0:
            raise ValueError('Frame time must be finite and nonnegative.')
        player = self.players[player_id]
        player.x += float(np.clip(move, -1, 1)) * 7 * dt
        player.angle = clamp_elevation(player.angle + float(np.clip(aim, -1, 1)) * 50 * dt)
        self._face_opponent()
        if draw and min(p.health for p in self.players) > 0:
            if not player.drawing:
                player.strength = .15
            player.drawing = True
            player.strength = min(1, player.strength + .75 * dt)
            player.status = 'Keep holding to pull; release to fire.'
        if release and player.drawing:
            player.drawing = False
            return self.shoot(player_id, player.strength, player.angle)
        return False

    def shoot(self, player_id, strength, angle):
        if (not self.ready or self.finished or min(p.health for p in self.players) <= 0
                or not math.isfinite(strength) or not math.isfinite(angle) or strength < .12):
            return False
        player = self.players[player_id]
        if player.cooldown > 0:
            player.status = 'Reloading...'
            return False
        self._face_opponent()
        strength, angle = float(np.clip(strength, 0, 1)), clamp_elevation(angle)
        vx, vy = launch_velocity(strength, angle, player.facing)
        x, y = self.launch_point(player_id, angle)
        arrow = DuelArrow(player_id, x, y, vx, vy, strength)
        arrow.trail.append(arrow.position)
        player.shots += 1
        # Arrows start at the drawn bow tip; an opponent standing between the
        # archer's shoulder and that tip is hit at once.
        target = 1 - player_id
        sx, sy = hitbox.shoulder_offset()
        shoulder = (player.x + sx * player.facing, sy)
        hit = hitbox.first_hit(self.players[target].character, self.players[target].facing,
                               shoulder, (x, y), self.players[target].x, self.players[target].x)
        if hit is not None:
            self._register_hit(arrow, target, tuple(a + hit * (b - a) for a, b in zip(shoulder, (x, y))),
                               apply_damage=True)
        else:
            self.arrows.append(arrow)
        player.cooldown = .65
        player.drawing = False
        player.status = 'Arrow released!'
        return True

    def launch_point(self, player_id, angle=None):
        """Drawn arrow tip on the bow, in world metres."""
        player = self.players[player_id]
        tx, ty = hitbox.tip_offset(clamp_elevation(player.angle if angle is None else angle))
        return player.x + tx * player.facing, ty

    def prediction(self, player_id, duration=3.0, spacing=.08):
        player = self.players[player_id]
        vx, vy = launch_velocity(player.strength, player.angle, player.facing)
        x0, y0 = self.launch_point(player_id)
        points = []
        for t in np.arange(0, duration, spacing):
            y = y0 + vy * t - .5 * GRAVITY * t * t
            if y < 0:
                break
            points.append((x0 + vx * t, y))
        return points

    def _register_hit(self, arrow, target, point, apply_damage=False):
        amount = round(20 + arrow.strength * 20)
        self.players[arrow.owner].hits += 1
        self.impacts.append({'position': point, 'target': target, 'owner': arrow.owner,
                             'damage': amount, 'time': self.time})
        if apply_damage:
            player = self.players[target]
            player.health = max(0, player.health - amount)
            player.status = f'Hit! −{amount} HP'
        return amount

    def update(self, dt):
        if not math.isfinite(dt) or dt < 0:
            raise ValueError('Frame time must be finite and nonnegative.')
        if self.finished or dt == 0:
            return
        old_x = list(self._physics_x)
        steps = max(1, math.ceil(dt / .01))
        interval = dt / steps
        for step in range(steps):
            self.time += interval
            for player in self.players:
                player.cooldown = max(0, player.cooldown - interval)
            damage = [0, 0]
            survivors = []
            for arrow in self.arrows:
                before = arrow.position
                after = (arrow.x + arrow.vx * interval,
                         arrow.y + arrow.vy * interval - .5 * GRAVITY * interval * interval)
                target = 1 - arrow.owner
                start_x = old_x[target] + (self.players[target].x - old_x[target]) * step / steps
                end_x = old_x[target] + (self.players[target].x - old_x[target]) * (step + 1) / steps
                hit = hitbox.first_hit(self.players[target].character, self.players[target].facing,
                                       before, after, start_x, end_x)
                arrow.age += interval
                arrow.x, arrow.y = after
                arrow.vy -= GRAVITY * interval
                if hit is not None:
                    point = tuple(a + hit * (b - a) for a, b in zip(before, after))
                    damage[target] += self._register_hit(arrow, target, point)
                elif arrow.y >= 0 and arrow.age < 8:
                    if not arrow.trail or _trail_far(arrow.trail[-1], after):
                        arrow.trail.append(after)
                    survivors.append(arrow)
                else:
                    self.impacts.append({'position': (arrow.x, max(0, arrow.y)), 'target': None,
                                         'owner': arrow.owner, 'damage': 0, 'time': self.time})
            self.arrows = survivors
            for player, amount in zip(self.players, damage):
                player.health = max(0, player.health - amount)
                if amount:
                    player.status = f'Hit! −{amount} HP'
            # Let already-launched retaliation finish, enabling a fair double KO.
            if min(p.health for p in self.players) <= 0 and not self.arrows:
                self.winner = ('draw' if all(p.health == 0 for p in self.players)
                               else 0 if self.players[1].health == 0 else 1)
                self.cancel_draws()
                break
        self._physics_x = [p.x for p in self.players]
        self.impacts = [impact for impact in self.impacts if self.time - impact['time'] < 2]


def _trail_far(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1]) > .22
