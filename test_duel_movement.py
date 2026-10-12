"""Relative movement has no fixed arena boundaries or separation cap."""
import math
import unittest
import hitbox

from duel import DuelMatch
from test_duel import camera_match, pair, aim_at_opponent


class DuelMovementTests(unittest.TestCase):
    def settle(self, match, centers, scale=.16, start=1100):
        for stamp in range(start, start + 2500, 100):
            observations = pair(stamp)
            for observation, center in zip(observations, centers):
                observation['center'][0] = center
                observation['scale'] = scale
            match.apply_tracking(observations, stamp)

    def test_calibrated_positions_stay_at_their_original_starts(self):
        match = camera_match()
        match.body_baselines[0]['center'][0] = .32
        match.body_baselines[1]['center'][0] = .67
        self.settle(match, (.32, .67))
        self.assertEqual([p.x for p in match.players], [9., 31.])

    def test_visible_camera_motion_can_exceed_previous_world_boundaries(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        self.settle(match, (.12, .88), .08)
        self.assertLess(match.players[0].x, 0)
        self.assertGreater(match.players[1].x, 40)
        self.assertGreater(match.separation, 40)

    def test_players_can_cross_then_turn_to_face_their_opponent(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        self.settle(match, (.88, .12))
        self.assertGreater(match.players[0].x, match.players[1].x)
        self.assertEqual([p.facing for p in match.players], [-1, 1])

    def test_simultaneous_crossing_and_release_uses_both_current_positions(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        match.apply_tracking(pair(1100, state='Open'), 1100)
        observations = pair(1210, state='Open')
        observations[0]['center'][0] = .9
        observations[1]['center'][0] = .1
        match.apply_tracking(observations, 1210)
        self.assertGreater(match.players[0].x, match.players[1].x)
        self.assertEqual([p.shots for p in match.players], [1, 1])
        self.assertLess(match.arrows[0].vx, 0)
        self.assertGreater(match.arrows[1].vx, 0)
        for arrow in match.arrows:
            player = match.players[arrow.owner]
            angle = math.degrees(math.atan2(arrow.vy, abs(arrow.vx)))
            self.assertAlmostEqual(arrow.x, player.x + hitbox.tip_offset(angle)[0] * player.facing)

    def test_depth_still_changes_separation_near_calibrated_positions(self):
        match = camera_match()
        self.settle(match, (.25, .75), .12)
        self.assertGreater(match.separation, 22)
        self.settle(match, (.25, .75), .24, start=4000)
        self.assertLess(match.separation, 22)

    def test_missing_hands_allow_body_movement(self):
        match = camera_match()
        match.apply_tracking(pair(1000), 1000)
        observations = pair(1100)
        for observation in observations:
            observation['center'][0] += .1
            observation['hands_clear'] = False
        match.apply_tracking(observations, 1100)
        self.assertGreater(match.players[0].x, 9)
        self.assertGreater(match.players[1].x, 31)
        self.assertFalse(match.arrows)

    def test_stale_duplicate_missing_and_ambiguous_samples_do_not_move_players(self):
        for failure in ('stale', 'duplicate', 'missing', 'ambiguous', 'old'):
            with self.subTest(failure=failure):
                match = camera_match()
                match.apply_tracking(pair(1000), 1000)
                observations = pair(1100)
                for observation in observations:
                    observation['center'][0] = .9
                    if failure == 'stale':
                        observation['stamp'] = 500
                    elif failure == 'duplicate':
                        observation['stamp'] = 1000
                    elif failure == 'old':
                        observation['stamp'] = 950
                    elif failure == 'ambiguous':
                        observation['identity_clear'] = False
                if failure == 'missing':
                    observations = [None, None]
                match.apply_tracking(observations, 1100)
                match.update(.1)
                self.assertEqual([p.x for p in match.players], [9., 31.])

    def test_reacquisition_and_normal_tracking_smooth_position_changes(self):
        for stamp in (1100, 5000):
            with self.subTest(stamp=stamp):
                match = camera_match()
                match.apply_tracking(pair(1000), 1000)
                observations = pair(stamp)
                observations[0]['center'][0] = .9
                match.apply_tracking(observations, stamp)
                self.assertGreater(match.players[0].x, 9)
                self.assertLess(match.players[0].x, 41.5)

    def test_keyboard_players_can_continue_beyond_previous_boundaries(self):
        match = DuelMatch(keyboard=True)
        for player_id in range(2):
            match.keyboard(player_id, move=-1, dt=10)
            self.assertLess(match.players[player_id].x, 0)
            match.keyboard(player_id, move=1, dt=20)
            self.assertGreater(match.players[player_id].x, 40)

    def test_projectiles_hit_opponents_outside_the_previous_arena(self):
        match = DuelMatch(keyboard=True)
        match.players[0].x, match.players[1].x = 120, 142
        match.update(.01)
        match.shoot(0, 1, aim_at_opponent(match, 0))
        match.update(3)
        self.assertEqual(match.players[1].health, 60)

    def test_view_keeps_both_players_visible_at_large_separation(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
        import pygame
        from duel_renderer import DuelRenderer, ARENA
        pygame.display.init()
        pygame.font.init()
        renderer = DuelRenderer(pygame.display.set_mode((1280, 800)))
        match = DuelMatch(keyboard=True)
        match.players[0].x, match.players[1].x = -130, 210
        match.update(.01)
        renderer.arena(match)
        self.assertGreater(renderer.view_width, match.separation)
        for player in match.players:
            x, _ = renderer.project(player.x, 0)
            self.assertGreater(x, ARENA.left+75)
            self.assertLess(x, ARENA.right-75)

    def test_camera_zoom_follows_distance_smoothly(self):
        import os
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
        import pygame
        from duel_renderer import DuelRenderer, camera_zoom
        pygame.display.init()
        pygame.font.init()
        renderer = DuelRenderer(pygame.display.set_mode((1280, 800)))
        self.assertAlmostEqual(camera_zoom(22), 1.0)
        self.assertGreater(camera_zoom(6), camera_zoom(22))
        self.assertLess(camera_zoom(60), camera_zoom(22))
        match = DuelMatch(keyboard=True)
        match.update(.01)
        renderer.arena(match)
        start = renderer.zoom
        match.players[0].x, match.players[1].x = 18, 24
        match.update(1/60)
        renderer.arena(match)
        # One frame later the camera has only begun to move...
        self.assertGreater(renderer.zoom, start)
        self.assertLess(renderer.zoom - start, .05)
        for _ in range(300):
            match.update(1/60)
            renderer.arena(match)
        # ...and after a few seconds it has settled on the closer framing.
        self.assertAlmostEqual(renderer.zoom, camera_zoom(6), places=2)
        match.players[0].x, match.players[1].x = -20, 45
        for _ in range(300):
            match.update(1/60)
            renderer.arena(match)
        self.assertLess(renderer.zoom, start)
        for player in match.players:
            x, _ = renderer.project(player.x, 0)
            self.assertGreater(x, 75)
            self.assertLess(x, 1205)


if __name__ == '__main__':
    unittest.main()
