"""Original big-head pixel-art archers (see ``pixelart/sprites.py`` for the art).

``CHARACTERS`` is an ordered tuple of selection-card dictionaries. ``draw``
anchors the character between its feet; facing +1 shoots right, -1 shoots left,
and positive angles aim upward. Sprites are drawn at native resolution and
scaled with nearest-neighbour (3x by default), so pixels stay crisp. The aim
rig (arms, bow, string, arrow) is redrawn natively for every angle and pull, so
aiming never needs blurry sprite rotation. No image files are required.
"""
from collections import OrderedDict
import math

import pygame

from pixelart import sprites
from pixelart.kit import big


CHARACTERS = (
    {'id': 'ranger', 'name': 'FERN', 'title': 'THE FOREST RANGER',
     'tagline': 'Quick wit. Steady aim.', 'color': (110, 225, 140),
     'description': 'A feather-capped woodland archer with a ginger beard.'},
    {'id': 'storm', 'name': 'FLINT', 'title': 'THE STORM VIKING',
     'tagline': 'Big heart. Thunderous shots.', 'color': (255, 184, 84),
     'description': 'A horned-helmet viking in blue armor and a red cape.'},
    {'id': 'torque', 'name': 'PROF. TORQUE', 'title': 'THE MAD ENGINEER',
     'tagline': 'Compound bow. Compound interest.', 'color': (255, 150, 60),
     'description': 'A goggled mechanical-engineering professor with a compound bow.'},
    {'id': 'bolt', 'name': 'BOLT-9', 'title': 'THE SCRAP ROBOT',
     'tagline': 'Calculating trajectory...', 'color': (90, 235, 220),
     'description': 'A boxy lab robot with a neon bow.'},
    {'id': 'akinci', 'name': 'AKINCI', 'title': 'THE STEPPE ARCHER',
     'tagline': 'A thousand years of archery.', 'color': (240, 90, 90),
     'description': 'A Turkish horse archer with a felt hat and a recurve bow.'},
    {'id': 'gourd', 'name': 'GOURD', 'title': 'THE FIELD SPOOK',
     'tagline': 'Hollow head. Sharp arrows.', 'color': (255, 170, 70),
     'description': 'A pumpkin-headed scarecrow in patched overalls.'},
)
CHARACTER_IDS = tuple(item['id'] for item in CHARACTERS)
PIXEL = 3


class CharacterArtist:
    """Reusable renderer with a bounded cache of animated pixel poses."""

    SIZE = (300, 400)
    FEET = pygame.Vector2(126, 270)
    OFFSET = FEET - pygame.Vector2(sprites.FX, sprites.GY) * PIXEL
    SHOULDER = OFFSET + pygame.Vector2(sprites.SHOULDER[0], sprites.SHOULDER[1] + sprites.TOP) * PIXEL
    CACHE_LIMIT = 96

    def __init__(self):
        self._cache = OrderedDict()        # full 300x400 poses (3x)
        self._native = OrderedDict()       # native sprites keyed by pose
        self._parts = OrderedDict()        # bodies and rigs
        self._screen = OrderedDict()       # scaled / mirrored sprites ready to blit

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def metadata(character_id):
        for item in CHARACTERS:
            if item['id'] == character_id:
                return item
        raise ValueError(f'Unknown character {character_id!r}; choose {CHARACTER_IDS}.')

    @staticmethod
    def _angle(angle):
        value = float(angle)
        return max(-90, min(90, value)) if math.isfinite(value) else 20.0

    @classmethod
    def arrow_tip(cls, feet, facing=1, angle=20, scale=1.,
                  walk_phase=0., walk_amount=0., move_direction=1):
        """Screen-space tip of the held arrow, usable as a projectile origin."""
        radians = math.radians(cls._angle(angle))
        direction = pygame.Vector2(math.cos(radians), -math.sin(radians))
        offset = (cls.SHOULDER + 100 * direction - cls.FEET
                  + cls._walk_offset(walk_phase, walk_amount,
                                     move_direction * (1 if facing >= 0 else -1)))
        return pygame.Vector2(feet) + pygame.Vector2(offset.x * (1 if facing >= 0 else -1), offset.y) * scale

    @staticmethod
    def _walk_state(walk_phase=0., walk_amount=0., move_direction=1):
        """Quantize a distance-driven gait; stationary poses ignore walk phase."""
        amount = float(walk_amount)
        amount = round(max(0., min(1., amount)) * 16) / 16 if math.isfinite(amount) else 0.
        phase = float(walk_phase)
        frame = round((phase % math.tau) / math.tau * 32) % 32 if math.isfinite(phase) else 0
        return (frame if amount else 0, amount, (1 if move_direction >= 0 else -1) if amount else 1)

    @classmethod
    def _gait(cls, walk_phase=0., walk_amount=0., move_direction=1):
        """Integer leg swing/lift (native pixels) and body bob for the pixel walk cycle."""
        frame, amount, direction = cls._walk_state(walk_phase, walk_amount, move_direction)
        if not amount:
            return (0, 0, 0, 0), 0
        phase = frame / 32 * math.tau
        swing = math.sin(phase) * 3.4 * amount * direction
        back = (round(swing), round(max(0., math.cos(phase)) * 3 * amount))
        front = (round(-swing), round(max(0., -math.cos(phase)) * 3 * amount))
        bob = -round(abs(math.sin(phase)) * 1.4 * amount)
        return back + front, bob

    @classmethod
    def _walk_offset(cls, walk_phase=0., walk_amount=0., move_direction=1):
        _, bob = cls._gait(walk_phase, walk_amount, move_direction)
        return pygame.Vector2(0, bob * PIXEL)

    def _remember(self, cache, key, value, limit):
        cache[key] = value
        if len(cache) > limit:
            cache.popitem(last=False)
        return value

    # ---------------------------------------------------------------- poses
    def _key(self, character_id, angle, strength, firing, time,
             walk_phase=0., walk_amount=0., move_direction=1, pose='aim'):
        self.metadata(character_id)
        angle = round(self._angle(angle) / 2) * 2
        strength = float(strength)
        strength = round(max(0., min(1., strength)) * 20) / 20 if math.isfinite(strength) else 0.
        try:
            t = float(time)
        except (TypeError, ValueError):
            t = 0.
        gait, bob = self._gait(walk_phase, walk_amount, move_direction)
        if not any(gait) and math.isfinite(t):
            bob = -1 if int(t * 1.6) % 2 else 0        # gentle idle breathing
        if firing:
            strength = 0.
        return character_id, pose, angle, strength, bool(firing), gait, bob

    def native(self, character_id, angle=20, strength=.6, firing=False, time=0,
               walk_phase=0., walk_amount=0., move_direction=1, pose='aim'):
        """Native-resolution (1x) sprite, feet at ``(sprites.FX, sprites.GY)``."""
        key = self._key(character_id, angle, strength, firing, time,
                        walk_phase, walk_amount, move_direction, pose)
        if key in self._native:
            self._native.move_to_end(key)
            return self._native[key]
        cid, pose, angle, strength, firing, gait, bob = key
        bkey = ('body', cid, pose, gait, bob)
        body = self._parts.get(bkey) or self._remember(
            self._parts, bkey, sprites.build_body(cid, pose, gait, bob), 160)
        rkey = ('rig', cid, pose, angle, strength, firing, bob)
        rig = self._parts.get(rkey) or self._remember(
            self._parts, rkey, sprites.build_rig(cid, angle, strength, not firing, pose, bob), 160)
        image = body.copy()
        image.blit(rig, (0, 0))
        return self._remember(self._native, key, image, self.CACHE_LIMIT)

    def _pose(self, character_id, angle, strength, firing, time,
              walk_phase=0., walk_amount=0., move_direction=1):
        """Full 300x400 transparent pose at 3x, feet at ``FEET``."""
        key = self._key(character_id, angle, strength, firing, time,
                        walk_phase, walk_amount, move_direction)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        image = self.native(character_id, angle, strength, firing, time,
                            walk_phase, walk_amount, move_direction)
        canvas = pygame.Surface(self.SIZE, pygame.SRCALPHA)
        canvas.blit(big(image, PIXEL), (round(self.OFFSET.x), round(self.OFFSET.y)))
        return self._remember(self._cache, key, canvas, self.CACHE_LIMIT)

    def draw(self, screen, character_id, feet=(0, 0), facing=1, angle=20,
             strength=.6, scale=1., firing=False, time=0,
             walk_phase=0., walk_amount=0., move_direction=1, pose='aim'):
        """Blit a pose; gait phase is radians from travel, amount is speed 0..1.

        ``move_direction`` is world left/right, independent of aiming ``facing``.
        ``scale`` 1 means 3x pixels; it is rounded to whole art pixels.
        """
        scale = float(scale)
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError('Character scale must be positive and finite.')
        pixel = max(1, round(PIXEL * scale))
        direction = move_direction * (1 if facing >= 0 else -1)
        key = (self._key(character_id, angle, strength, firing, time, walk_phase, walk_amount,
                         direction, pose), facing >= 0, pixel)
        fx = sprites.FX if facing >= 0 else sprites.W - 1 - sprites.FX
        image = self._screen.get(key)
        if image is None:
            image = self.native(character_id, angle, strength, firing, time, walk_phase, walk_amount,
                                direction, pose)
            if facing < 0:
                image = pygame.transform.flip(image, True, False)
            image = big(image, pixel)
            if pygame.display.get_init() and pygame.display.get_surface():
                image = image.convert_alpha()
            self._remember(self._screen, key, image, self.CACHE_LIMIT)
        else:
            self._screen.move_to_end(key)
        return screen.blit(image, (round(feet[0] - fx * pixel), round(feet[1] - sprites.GY * pixel)))

    def surface(self, character_id, size=(240, 280), facing=1, pose='idle', angle=12):
        """Full-body transparent selection portrait, with 12px safe padding."""
        width, height = (int(size[0]), int(size[1]))
        if width <= 0 or height <= 0:
            raise ValueError('Portrait size must be positive.')
        image = self.native(character_id, angle, .72, False, 0, pose=pose)
        cropped = image.subsurface(image.get_bounding_rect()).copy()
        if facing < 0:
            cropped = pygame.transform.flip(cropped, True, False)
        factor = max(1, int(min(max(1, width - 24) / cropped.get_width(),
                                max(1, height - 24) / cropped.get_height())))
        fitted = big(cropped, factor)
        portrait = pygame.Surface((width, height), pygame.SRCALPHA)
        portrait.blit(fitted, fitted.get_rect(center=(width // 2, height // 2)))
        return portrait
