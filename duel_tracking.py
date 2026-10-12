"""Pure tracking logic for two people sharing one camera (no GUI/vision imports).

Identities are assigned once, by mirrored screen position, then matched globally
using predicted body position, shoulder size and torso colour. Ambiguous matches
are withheld instead of silently swapping players. Hand ownership is a separate
one-to-one assignment to each pose's anatomical wrists; handedness labels alone
cannot identify a player. Monocular shoulder size is a relative depth proxy.
"""
from itertools import product
import math
import numpy as np


def _distance(a, b):
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b)))


def _assign(costs, missing_cost, margin=0):
    """Global injective assignment, allowing unmatched slots; reject ambiguity."""
    rows, columns = costs.shape
    choices = range(-1, columns)
    ranked = []
    for assignment in product(choices, repeat=rows):
        used = [j for j in assignment if j >= 0]
        if len(used) != len(set(used)):
            continue
        cost = sum(missing_cost if j < 0 else costs[i, j] for i, j in enumerate(assignment))
        ranked.append((cost, assignment))
    ranked.sort(key=lambda item: item[0])
    best_cost, best = ranked[0]
    result = list(best)
    # A competing near-equal mapping makes only its changed slots ambiguous.
    for cost, alternative in ranked[1:]:
        if cost - best_cost >= margin:
            break
        for i in range(rows):
            if alternative[i] != best[i]:
                result[i] = -1
    return result


class IdentityTracker:
    MAX_GAP_MS = 300

    def __init__(self):
        self.tracks = [None, None]
        self.last_stamp = -1

    def update(self, observations, stamp):
        if stamp <= self.last_stamp:
            return [None, None]
        self.last_stamp = stamp
        observations = [o for o in observations if o is not None and
                        np.isfinite(o['center']).all() and .012 < o['scale'] < .65]
        if all(t is None for t in self.tracks):
            if len(observations) != 2 or abs(observations[0]['center'][0] - observations[1]['center'][0]) < .12:
                return [None, None]
            observations.sort(key=lambda o: o['center'][0])
            indices = [0, 1]
        else:
            costs = np.full((2, len(observations)), 100.0)
            for i, track in enumerate(self.tracks):
                if track is None:
                    continue
                elapsed = max(0, (stamp - track['stamp']) / 1000)
                prediction = track['center'] + track['velocity'] * min(elapsed, .5)
                for j, observation in enumerate(observations):
                    distance = _distance(prediction, observation['center'])
                    scale = abs(math.log(observation['scale'] / track['scale']))
                    colour = _distance(observation.get('colour', [0, 0, 0]), track['colour'])
                    if distance > min(.40, .10 + elapsed * .8) or scale > .9:
                        continue
                    # Clothing is only a soft identity cue: lighting changes too.
                    costs[i, j] = distance + .11 * scale + .18 * colour
            indices = _assign(costs, .40, margin=.035)
        output = [None, None]
        for i, j in enumerate(indices):
            if j < 0:
                continue
            observation = dict(observations[j])
            center = np.asarray(observation['center'], dtype=float)
            previous = self.tracks[i]
            gap = self.MAX_GAP_MS + 1 if previous is None else stamp - previous['stamp']
            velocity = np.zeros(2)
            if previous is not None and gap <= self.MAX_GAP_MS:
                instantaneous = (center - previous['center']) / max(gap / 1000, .001)
                velocity = .45 * previous['velocity'] + .55 * instantaneous
                velocity = np.clip(velocity, -.8, .8)
            generation = (0 if previous is None else previous['generation']) + int(gap > self.MAX_GAP_MS)
            self.tracks[i] = {'center': center, 'velocity': velocity, 'stamp': stamp,
                              'scale': observation['scale'],
                              'colour': np.asarray(observation.get('colour', [0, 0, 0])),
                              'generation': generation}
            observation.update(stamp=stamp, player_id=i, generation=generation, identity_clear=True)
            output[i] = observation
        return output


def associate_hands(observations, hands, aspect=4 / 3):
    """Attach up to four hand detections by globally matching pose wrists."""
    slots = []
    for player_id, observation in enumerate(observations):
        if observation is None:
            continue
        observation['hands_clear'] = False
        observation['state'] = 'Unknown'
        observation['wrists'] = {}
        pose = np.asarray(observation['pose'])
        for side, index in (('Left', 15), ('Right', 16)):
            if np.isfinite(pose[index, :2]).all():
                slots.append((player_id, side, pose[index, :2], observation['scale']))
    costs = np.full((len(slots), len(hands)), 100.0)
    for i, (player, side, wrist, scale) in enumerate(slots):
        for j, hand in enumerate(hands):
            delta = (np.asarray(hand['wrist']) - wrist) * [1, 1 / aspect]
            distance = float(np.linalg.norm(delta))
            if distance <= min(.15, max(.055, scale * .70)):
                costs[i, j] = distance
    if slots:
        assignment = _assign(costs, .16, margin=.018)
        for (player, side, wrist, scale), j in zip(slots, assignment):
            if j >= 0:
                observations[player]['wrists'][side] = np.asarray(hands[j]['wrist'])
                if side == 'Right':
                    observations[player]['state'] = hands[j]['state']
    for observation in observations:
        if observation is not None and len(observation['wrists']) == 2:
            _hand_geometry(observation, aspect)
    return observations


def _hand_geometry(observation, aspect, toward=None):
    """Draw gap (in shoulder widths) and aim angle from the two wrists.

    toward is +1 when the opponent is to the right in the mirrored preview and
    -1 when to the left. Aim follows the line through both hands, read from the
    opponent's side: raising the hand nearer the opponent aims up. The bow is in
    the left hand, which the mirrored preview shows on the left, so for the
    archer on the right this is the bow hand and for the archer on the left it
    is the drawing hand. (Always reading the bow hand made aiming feel reversed
    for the left player, whose bow arm points away from the opponent.)
    """
    if toward is None:
        toward = 1 if observation.get('player_id', 0) == 0 else -1
    draw, bow = [observation['wrists'][side] * [aspect, 1] for side in ('Right', 'Left')]
    delta = bow - draw
    observation['gap'] = float(np.linalg.norm(delta) / (observation['scale'] * aspect))
    observation['angle'] = math.degrees(math.atan2(toward * delta[1], -delta[0]))
    observation['hands_clear'] = observation['gap'] >= .10 and observation['state'] != 'Unknown'


# --- Far-player hand tracking -------------------------------------------------
# A full-frame palm detector sees a hand only a few pixels wide once players
# stand back. Pose wrists survive much further, so the hand model runs only on
# an upscaled crop around each player's drawing (right) wrist. The bow hand
# needs a position, never a gesture, so it comes straight from the pose.

HAND_CROP_SIZE = 256


def hand_crop_box(pose, scale, width, height):
    """Square pixel box (cx, cy, side) around a player's right hand, or None."""
    pose = np.asarray(pose, dtype=float)
    if pose.ndim != 2 or pose.shape[0] < 23 or not np.isfinite(pose[16, :2]).all():
        return None
    if not (math.isfinite(scale) and scale > 0):
        return None
    size = np.array([width, height], dtype=float)
    wrist = pose[16, :2] * size
    fingers = [pose[i, :2] * size for i in (18, 20, 22) if np.isfinite(pose[i, :2]).all()]
    if fingers:
        centre = wrist + .6 * (np.mean(fingers, axis=0) - wrist)
    elif np.isfinite(pose[14, :2]).all():
        centre = wrist + .35 * (wrist - pose[14, :2] * size)
    else:
        centre = wrist
    # A hand is about half a shoulder width long; the margin absorbs pose error.
    side = max(1.3 * scale * width, 64.)
    return float(centre[0]), float(centre[1]), float(side)


def crop_affine(box, size=HAND_CROP_SIZE):
    """2x3 matrix mapping frame pixels into the square crop (for warpAffine)."""
    cx, cy, side = box
    s = size / side
    return np.array([[s, 0, size / 2 - cx * s], [0, s, size / 2 - cy * s]], dtype=float)


def pick_crop_hand(candidates, box, wrist, scale, width, height):
    """Choose the crop's hand that belongs to the pose wrist; reject ambiguity.

    candidates are (21, 3) landmarks normalized to the square crop. Returns
    {'wrist': frame-normalized xy, 'state': Open/Closed/Unknown} or None.
    """
    cx, cy, side = box
    wrist = np.asarray(wrist, dtype=float)
    if not np.isfinite(wrist).all():
        return None
    matches = []
    for points in candidates:
        points = np.asarray(points, dtype=float)
        if points.shape != (21, 3) or not np.isfinite(points).all():
            continue
        frame_wrist = np.array([(cx + (points[0, 0] - .5) * side) / width,
                                (cy + (points[0, 1] - .5) * side) / height])
        distance = float(np.linalg.norm((frame_wrist - wrist) * [1, height / width]))
        if distance <= .6 * scale:
            matches.append((distance, frame_wrist, points))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0])
    # Both of one player's hands (or a neighbour's) can share the crop.
    if len(matches) > 1 and matches[1][0] - matches[0][0] < .2 * scale:
        return None
    # The crop is square, so finger angles are measured without distortion.
    points = matches[0][2]
    frame_points = np.column_stack([(cx + (points[:, 0] - .5) * side) / width,
                                    (cy + (points[:, 1] - .5) * side) / height])
    return {'wrist': matches[0][1], 'state': classify_hand(points), 'points': frame_points}


class HandStateHold:
    """Bridge brief detector dropouts with the last confident hand state.

    Far away, a single missed frame used to cancel a draw. Releasing still
    needs a fresh Open reading, confirmed over time by the controller.
    """
    HOLD_MS = 250

    def __init__(self):
        self.last = [None, None]

    def update(self, player_id, generation, state, stamp):
        if state in ('Open', 'Closed'):
            self.last[player_id] = (state, stamp, generation)
            return state
        last = self.last[player_id]
        if last is not None and last[2] == generation and 0 <= stamp - last[1] <= self.HOLD_MS:
            return last[0]
        return 'Unknown'


def measure_hands(observations, draw_states, aspect=4 / 3):
    """Wrists from each player's own pose; gesture from their right-hand crop.

    Pose wrists already belong to one tracked body, so no cross-player hand
    matching is needed and a hand is never given to the wrong archer.
    """
    for player_id, observation in enumerate(observations):
        if observation is None:
            continue
        toward = 1 if player_id == 0 else -1
        other = observations[1 - player_id] if len(observations) == 2 else None
        if other is not None and abs(other['center'][0] - observation['center'][0]) > .03:
            toward = 1 if other['center'][0] > observation['center'][0] else -1
        observation['hands_clear'] = False
        observation['state'] = draw_states[player_id] or 'Unknown'
        observation['wrists'] = {}
        pose = np.asarray(observation['pose'], dtype=float)
        for side, index in (('Left', 15), ('Right', 16)):
            if np.isfinite(pose[index, :2]).all():
                observation['wrists'][side] = pose[index, :2].copy()
        if len(observation['wrists']) == 2:
            _hand_geometry(observation, aspect, toward)
    return observations


def classify_hand(points):
    """Finger joint geometry; no hand label or player-specific state assumed."""
    points = np.asarray(points, dtype=float)
    if points.shape != (21, 3) or not np.isfinite(points).all():
        return 'Unknown'
    straight = curled = 0
    for base, joint, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)):
        first, second = points[base] - points[joint], points[tip] - points[joint]
        lengths = np.linalg.norm(first) * np.linalg.norm(second)
        if lengths < 1e-9:
            continue
        angle = math.degrees(math.acos(float(np.clip(np.dot(first, second) / lengths, -1, 1))))
        straight += angle > 140
        curled += angle < 125
    return 'Open' if straight >= 3 else 'Closed' if curled >= 3 and straight == 0 else 'Unknown'
