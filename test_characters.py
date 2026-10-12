"""Headless asset checks: transparency, pose range and mirrored world anchors."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import unittest
import math

import pygame
from characters import CharacterArtist, CHARACTER_IDS


class CharacterAssetTests(unittest.TestCase):
    def setUp(self):
        self.artist = CharacterArtist()

    def test_selection_portraits_are_distinct_and_transparent(self):
        images = [self.artist.surface(cid) for cid in CHARACTER_IDS]
        for image in images:
            self.assertEqual(image.get_size(), (240, 280))
            self.assertEqual(image.get_at((0, 0)).a, 0)
            self.assertGreater(image.get_bounding_rect().height, 160)
        blobs = [pygame.image.tobytes(image, 'RGBA') for image in images]
        self.assertEqual(len(set(blobs)), len(blobs))

    def test_extreme_aims_and_pull_levels_fit_the_asset_canvas(self):
        for cid in CHARACTER_IDS:
            for angle in (-90, -40, 0, 40, 90):
                for strength in (0, .5, 1):
                    for firing in (False, True):
                        image = self.artist._pose(cid, angle, strength, firing, 1)
                        rect = image.get_bounding_rect()
                        self.assertGreater(rect.left, 0)
                        self.assertGreater(rect.top, 0)
                        self.assertLess(rect.right, image.get_width())
                        self.assertLess(rect.bottom, image.get_height())

    def test_facing_mirrors_held_arrow_tip_around_feet(self):
        for angle in (-90, 0, 35, 90):
            right = self.artist.arrow_tip((400, 500), 1, angle, .8)
            left = self.artist.arrow_tip((400, 500), -1, angle, .8)
            self.assertAlmostEqual(right.x + left.x, 800)
            self.assertAlmostEqual(right.y, left.y)
            if angle > -90:   # the shorter pixel archers aim a straight-down arrow at the ground
                self.assertLess(right.y, 500)

    def test_vertical_aim_remains_vertical(self):
        for angle in (-90, 90):
            self.assertEqual(self.artist._angle(angle), angle)
            tip = self.artist.arrow_tip(self.artist.FEET, angle=angle)
            self.assertAlmostEqual(tip.x, self.artist.SHOULDER.x)
            self.assertAlmostEqual(abs(tip.y-self.artist.SHOULDER.y), 100)

    def test_walking_changes_legs_and_returns_to_idle(self):
        for cid in CHARACTER_IDS:
            idle = self.artist._pose(cid, 20, .7, False, 0)
            stopped = self.artist._pose(cid, 20, .7, False, 0,
                                        walk_phase=2.3, walk_amount=0, move_direction=-1)
            self.assertIs(idle, stopped)
            step_a = self.artist._pose(cid, 20, .7, False, 0,
                                      walk_phase=0, walk_amount=1)
            step_b = self.artist._pose(cid, 20, .7, False, 0,
                                      walk_phase=math.pi, walk_amount=1)
            legs = pygame.Rect(60, 217, 135, 59)
            self.assertNotEqual(pygame.image.tobytes(step_a.subsurface(legs), 'RGBA'),
                                pygame.image.tobytes(step_b.subsurface(legs), 'RGBA'))
            self.assertNotEqual(pygame.image.tobytes(idle, 'RGBA'),
                                pygame.image.tobytes(step_a, 'RGBA'))

    def test_walking_extremes_fit_the_asset_canvas(self):
        for cid in CHARACTER_IDS:
            for angle in (-90, 90):
                for direction in (-1, 1):
                    for frame in range(8):
                        pose = self.artist._pose(cid, angle, 1, False, 0,
                                                frame/8*math.tau, 1, direction)
                        rect = pose.get_bounding_rect()
                        self.assertGreater(rect.left, 0)
                        self.assertGreater(rect.top, 0)
                        self.assertLess(rect.right, pose.get_width())
                        self.assertLess(rect.bottom, pose.get_height())

    def test_walk_cache_quantizes_motion(self):
        a = self.artist._pose('ranger', 20, .7, False, 0, .1, .7)
        b = self.artist._pose('ranger', 20, .7, False, 0, .11, .71)
        self.assertIs(a, b)
        for frame in range(150):
            self.artist._pose('storm', 20, .7, False, 0, frame*.123, frame/150)
        self.assertLessEqual(len(self.artist._cache), self.artist.CACHE_LIMIT)

    def test_animation_cache_stays_bounded(self):
        for angle in range(-80, 80):
            self.artist._pose('ranger', angle, .8, False, angle/10)
        self.assertLessEqual(len(self.artist._cache), self.artist.CACHE_LIMIT)

    def test_invalid_character_and_scale_fail_clearly(self):
        with self.assertRaises(ValueError):
            self.artist.surface('missing')
        canvas = pygame.Surface((500, 500), pygame.SRCALPHA)
        for scale in (0, -1, float('nan')):
            with self.assertRaises(ValueError):
                self.artist.draw(canvas, 'ranger', scale=scale)


if __name__ == '__main__':
    unittest.main()
