"""The ten single-player campaign levels as plain data.

Distances are metres from the archer (world x grows toward the target),
heights are metres above flat ground. Every level is checked for
solvability over many random layouts in test_campaign.py.

Edit this file to rebalance the campaign: target ranges, target size, arrow
budget, required score, bow power, wind, hills and obstacles.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Hill:
    """A smooth cosine bump: ``height`` at ``center``, flat ground at +/- ``half_width``."""
    center: float
    half_width: float
    height: float


@dataclass(frozen=True)
class Obstacle:
    """A solid block that stops arrows.

    ``x`` is the near edge (closest to the archer) and ``y`` the bottom edge.
    Floating blocks (``y`` > 0) may bob vertically with ``move_amp`` metres
    over ``move_period`` seconds. ``kind`` only changes the artwork, except
    trees, whose trunk and canopy are separate collision boxes.
    """
    kind: str            # 'hedge' | 'wall' | 'tree' | 'crate' | 'rock'
    x: float
    y: float
    w: float
    h: float
    move_amp: float = 0.0
    move_period: float = 0.0


@dataclass(frozen=True)
class Level:
    number: int
    name: str
    tagline: str
    arrows: int                       # shots given
    required: int                     # score needed to clear
    distance: tuple                   # (min, max) random target distance
    radius: float                     # outer ring radius (m)
    max_speed: float                  # bow power at full pull (m/s)
    bow: str
    height: tuple = (1.0, 1.0)        # target centre above the terrain (min, max)
    wind: tuple = (0.0, 0.0)          # |horizontal wind accel| range m/s^2; sign is random
    hills: tuple = ()
    obstacles: tuple = ()
    target_motion: tuple = (0.0, 0.0)  # (vertical amplitude m, period s)
    relocate: bool = False            # target moves to a new random spot after every arrow
    preview: float = 1.0              # share of the predicted flight drawn as dots
    min_speed: float = 12.0
    features: tuple = field(default=())

    @property
    def max_score(self):
        return self.arrows * 50


LEVELS = (
    Level(1, 'TRAINING FIELD', 'Find the range. The board moves every attempt.',
          arrows=6, required=60, distance=(24, 32), radius=0.9, max_speed=26, bow='TRAINING BOW', min_speed=12,
          preview=1.0, features=('Random target distance', 'Extra-large board', 'Full aim preview')),
    Level(2, 'THE HEDGE', 'A hedge row guards the low line.',
          arrows=6, required=70, distance=(30, 40), radius=0.85, max_speed=28, bow='TRAINING BOW', min_speed=13,
          obstacles=(Obstacle('hedge', 26, 0, 1.8, 4.6),), preview=0.95,
          features=('Hedge blocks flat shots', 'Shorter preview')),
    Level(3, 'ROLLING HILLS', 'Two hills hide the target behind them.',
          arrows=6, required=75, distance=(40, 50), radius=0.8, max_speed=30, bow='HUNTING BOW', min_speed=14,
          hills=(Hill(15, 6, 3.4), Hill(30, 7, 6.0)), preview=0.85,
          features=('Hills block low arcs', 'Longer range')),
    Level(4, 'CASTLE WALL', 'Lob it over the battlements.',
          arrows=6, required=80, distance=(42, 54), radius=0.8, max_speed=31, bow='HUNTING BOW', min_speed=15,
          obstacles=(Obstacle('wall', 27, 0, 1.6, 9.0),), height=(1.0, 2.2), preview=0.8,
          features=('9 m wall: high arcs only', 'Random target height')),
    Level(5, 'CROSSWIND MEADOW', 'Feel the wind before you let go.',
          arrows=7, required=90, distance=(48, 60), radius=0.75, max_speed=32, bow='RECURVE BOW', min_speed=16,
          wind=(0.4, 0.9), obstacles=(Obstacle('tree', 30, 0, 4.0, 9.0),), preview=0.75,
          features=('Wind changes every attempt', 'Oak tree in the way')),
    Level(6, 'CRATE CANYON', 'Thread the gaps between floating crates.',
          arrows=7, required=95, distance=(55, 66), radius=0.75, max_speed=33, bow='RECURVE BOW', min_speed=17,
          obstacles=(Obstacle('crate', 24, 4.0, 2.4, 2.4), Obstacle('crate', 34, 10.5, 2.8, 2.8),
                     Obstacle('rock', 44, 0, 2.6, 4.2)), height=(1.0, 2.5), preview=0.7,
          features=('Floating crates', 'Over, under or between')),
    Level(7, 'HILLTOP', 'The target hops along the ridge after every arrow.',
          arrows=7, required=100, distance=(60, 74), radius=0.7, max_speed=34, bow='LONGBOW', min_speed=18,
          hills=(Hill(36, 8, 9.5), Hill(67, 14, 6.0)), relocate=True, preview=0.65,
          features=('Target relocates after each arrow', 'Raised ridge')),
    Level(8, 'SWINGING TARGET', 'Time your release: the board never stops.',
          arrows=7, required=100, distance=(64, 76), radius=0.75, max_speed=35, bow='LONGBOW', min_speed=19,
          height=(2.4, 2.8), target_motion=(1.0, 4.0), wind=(0.3, 0.7),
          obstacles=(Obstacle('tree', 40, 0, 4.2, 10.0),), preview=0.6,
          features=('Moving target', 'Light wind', 'Tree')),
    Level(9, 'THE GAUNTLET', 'Hill, wall, a drifting crate and wind.',
          arrows=8, required=110, distance=(74, 86), radius=0.7, max_speed=36, bow='WAR BOW', min_speed=20,
          hills=(Hill(20, 8, 3.0),), wind=(0.4, 1.0), relocate=True,
          obstacles=(Obstacle('wall', 42, 0, 1.6, 11.0),
                     Obstacle('crate', 58, 14.0, 3.0, 3.0, move_amp=3.0, move_period=2.6)),
          preview=0.55, features=('Moving crate', 'Wall + hill', 'Wind', 'Target relocates')),
    Level(10, "CHAMPION'S RANGE", 'Everything at once. Make every arrow count.',
          arrows=8, required=120, distance=(86, 98), radius=0.65, max_speed=38, bow='WAR BOW', min_speed=21,
          hills=(Hill(25, 9, 3.5), Hill(92, 12, 3.0)), wind=(0.5, 1.1), relocate=True,
          height=(1.6, 2.0), target_motion=(0.8, 3.6),
          obstacles=(Obstacle('wall', 46, 0, 1.8, 8.0),
                     Obstacle('crate', 66, 7.0, 2.6, 2.6, move_amp=2.0, move_period=3.2)),
          preview=0.5, features=('Moving target', 'Wind', 'Wall + moving crate')),
)


def level(number):
    return LEVELS[number - 1]
