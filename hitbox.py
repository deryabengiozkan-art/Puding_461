"""Arrow hits that match the drawn pixel-art archers.

The arena is not drawn to one scale: one metre is 65 px vertically but only
WIDTH / BASE_VIEW (about 29 px) horizontally, and the big-headed characters are
pixel art. The old physics box (1 m wide, 2.4 m tall) therefore covered a thin
strip of each drawing, so arrows visibly flew through heads and bodies. Hits now
use each character's own body silhouette (head, torso and legs; the bow, string
and nocked arrow do not count), converted to metres with the arena's scales.
Arrows likewise launch from the drawn arrow tip on the bow.
"""
import math
from functools import lru_cache

import numpy as np

from pixelart import sprites
from pixelart.kit import SCALE

PX_PER_M_X = 1280 / 44          # duel_renderer: WIDTH / BASE_VIEW (checked by tests)
PX_PER_M_Y = 65                 # duel_renderer.world_project
M_PER_ART_X = SCALE / PX_PER_M_X
M_PER_ART_Y = SCALE / PX_PER_M_Y
TIP_PX = 100                    # characters.CharacterArtist.arrow_tip: shoulder -> tip


@lru_cache(maxsize=None)
def silhouette(character_id):
    """Boolean [x, y] mask of the drawn body in native art pixels, 1 px padded."""
    import pygame
    surface = sprites.build_body(character_id, 'aim')
    alpha = pygame.surfarray.array_alpha(surface) > 0
    padded = alpha.copy()
    # One art pixel of tolerance for the arrow's own thickness.
    padded[1:, :] |= alpha[:-1, :]
    padded[:-1, :] |= alpha[1:, :]
    padded[:, 1:] |= alpha[:, :-1]
    padded[:, :-1] |= alpha[:, 1:]
    return padded


def contains(character_id, feet_x, facing, x, y):
    """Whether world point (x, y) in metres is on a character standing at feet_x."""
    mask = silhouette(character_id)
    u = math.floor(sprites.FX + (x - feet_x) * (1 if facing >= 0 else -1) / M_PER_ART_X + .5)
    v = math.floor(sprites.GY - y / M_PER_ART_Y + .5)
    return 0 <= u < mask.shape[0] and 0 <= v < mask.shape[1] and bool(mask[u, v])


def first_hit(character_id, facing, a, b, feet_a, feet_b):
    """Fraction 0..1 along segment a->b where it first touches the body, or None.

    The target moves from feet_a to feet_b over the same interval, so a fast
    arrow or a dodging player cannot pass through between two samples (samples
    are at most half an art pixel apart on screen).
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    moved = (feet_b - feet_a)
    steps = max(1, math.ceil(max(abs(dx - moved) / (M_PER_ART_X / 2), abs(dy) / (M_PER_ART_Y / 2))))
    for k in range(steps + 1):
        t = k / steps
        if contains(character_id, feet_a + moved * t, facing, a[0] + dx * t, a[1] + dy * t):
            return t
    return None


def shoulder_offset():
    """Bow shoulder relative to the feet, in metres (x forward, y up)."""
    return ((sprites.SHOULDER[0] - sprites.FX) * M_PER_ART_X,
            (sprites.GY - sprites.SHOULDER[1] - sprites.TOP) * M_PER_ART_Y)


def tip_offset(angle):
    """Drawn arrow tip relative to the feet, in metres, for a world aim angle."""
    radians = math.radians(angle)
    # The renderer draws the bow at the on-screen angle of the world direction.
    visible = math.atan2(PX_PER_M_Y * math.sin(radians), PX_PER_M_X * math.cos(radians))
    sx, sy = shoulder_offset()
    return (sx + TIP_PX * math.cos(visible) / PX_PER_M_X,
            sy + TIP_PX * math.sin(visible) / PX_PER_M_Y)
