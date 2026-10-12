"""Find a gold shot for a layout (used by tests and for balancing levels).

For each elevation, bisect the bow speed so the arrow crosses the board plane
at the board's centre, then simulate that shot against terrain and obstacles.
"""
import math
from campaign import CampaignShot
from physics import ARCHER_HEIGHT, GRAVITY


def _height_at_board(speed, angle, layout):
    shot = CampaignShot.__new__(CampaignShot)
    shot.layout, shot.wind = layout, layout.wind
    r = math.radians(angle)
    shot.vx, shot.vy = speed * math.cos(r), speed * math.sin(r)
    t = CampaignShot._target_time(shot)
    if not math.isfinite(t):
        return -math.inf
    return ARCHER_HEIGHT + shot.vy * t - 0.5 * GRAVITY * t * t


def gold_shots(game, clock=0.0, angles=None):
    """Yield (strength, angle) pairs that score 50 from the current layout."""
    layout = game.layout
    lo_s, hi_s = game.speed(0.08), game.speed(1.0)
    angles = angles if angles is not None else [a * 0.5 for a in range(-10, 170)]
    goal = layout.target_center(clock)
    for angle in angles:
        f_lo = _height_at_board(lo_s, angle, layout) - goal
        f_hi = _height_at_board(hi_s, angle, layout) - goal
        if f_lo > 0 or f_hi < 0:
            continue
        a, b = lo_s, hi_s
        for _ in range(40):
            m = (a + b) / 2
            if _height_at_board(m, angle, layout) < goal:
                a = m
            else:
                b = m
        speed = (a + b) / 2
        shot = CampaignShot(speed, angle, layout, clock)
        if shot.points == 50:
            lv = game.level
            yield (speed - lv.min_speed) / (lv.max_speed - lv.min_speed), angle
