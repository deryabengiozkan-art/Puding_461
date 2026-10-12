"""Campaign checks: level data, flight against wind/terrain/obstacles, moving
and relocating boards, arrow budget and required score, saved progress, and
the menu -> level select -> briefing -> play -> result flow.

Run: ../.venv/bin/python -m unittest discover -s . -p 'test_campaign.py' -v
"""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import json
import math
import tempfile
import unittest
from pathlib import Path

import pygame

from campaign import (CampaignRound, CampaignShot, CampaignProgress, Layout, terrain_height,
                      stars_for, obstacle_boxes)
from campaign_solver import gold_shots
from game_mechanics import STATE_PLAY, STATE_FINISH, STATE_MENU
from levels import LEVELS, Level, Hill, Obstacle
from main import Archidon, load_ui, CAMPAIGN_SELECT
from physics import ARCHER_HEIGHT


def flat_level(**kw):
    base = dict(number=1, name='T', tagline='', arrows=3, required=50, distance=(30, 30), radius=0.5,
                max_speed=30, bow='B')
    base.update(kw)
    return Level(**base)


def layout(level, x=30.0, y=1.0, wind=0.0):
    return Layout(level, x, y, wind)


class LevelDesignTests(unittest.TestCase):
    def test_ten_levels_numbered_with_rising_challenge(self):
        self.assertEqual([lv.number for lv in LEVELS], list(range(1, 11)))
        far = [lv.distance[1] for lv in LEVELS]
        power = [lv.max_speed for lv in LEVELS]
        self.assertEqual(far, sorted(far))
        self.assertEqual(power, sorted(power))
        self.assertGreater(LEVELS[-1].max_speed, 24)            # stronger than practice bow
        self.assertLessEqual(LEVELS[-1].radius, LEVELS[0].radius)
        self.assertGreaterEqual(LEVELS[-1].arrows, LEVELS[0].arrows)
        for lv in LEVELS:
            self.assertLess(lv.required, lv.max_score)
            self.assertGreater(lv.distance[1], lv.distance[0])
            self.assertTrue(0 < lv.preview <= 1)

    def test_every_level_has_a_gold_shot_on_many_random_layouts(self):
        for lv in LEVELS:
            for seed in range(6):
                game = CampaignRound(lv, seed)
                clocks = [0.0]
                if lv.target_motion[0]:
                    clocks = [i * lv.target_motion[1] / 6 for i in range(6)]
                found = any(next(gold_shots(game, c), None) for c in clocks)
                self.assertTrue(found, f'level {lv.number} seed {seed} has no gold shot')

    def test_targets_never_sit_inside_obstacles_and_stay_in_range(self):
        for lv in LEVELS:
            for seed in range(30):
                game = CampaignRound(lv, seed)
                x, y = game.layout.target_x, game.layout.target_y
                self.assertTrue(lv.distance[0] - .1 <= x <= lv.distance[1] + .1)
                self.assertGreater(y - terrain_height(x, lv.hills), .5)
                for obstacle in lv.obstacles:
                    for x0, _, x1, _ in obstacle_boxes(obstacle, 0):
                        self.assertFalse(x0 - 1 <= x <= x1 + 1)

    def test_obstacles_block_a_real_share_of_arcs_in_later_levels(self):
        game = CampaignRound(LEVELS[3], 0)        # castle wall
        blocked = sum(CampaignShot(game.speed(s / 10), 10, game.layout).outcome == 'obstacle'
                      for s in range(3, 11))
        self.assertGreater(blocked, 0)


class FlightTests(unittest.TestCase):
    def test_flat_shot_matches_practice_equations(self):
        lv = flat_level()
        shot = CampaignShot(25, 10, layout(lv, x=200))   # board out of reach
        t = shot.end_time
        x, y = shot.position(t)
        self.assertAlmostEqual(y, 0, places=3)
        self.assertEqual(shot.outcome, 'ground')
        self.assertAlmostEqual(x, 25 * math.cos(math.radians(10)) * t, places=6)

    def test_centre_hit_scores_fifty_and_rings(self):
        lv = flat_level()
        lay = layout(lv)
        game = CampaignRound(lv, 0)
        game.layout = lay
        strength, angle = next(gold_shots(game))
        shot = game.prediction(strength, angle)
        self.assertEqual((shot.outcome, shot.points), ('target', 50))
        for offset, points in ((0.3, 25), (0.45, 15), (0.6, 0)):
            lay.target_y = 1.0 + offset
            self.assertEqual(game.prediction(strength, angle).points, points)

    def test_arrow_through_the_drawn_disc_counts_even_off_the_centre_line(self):
        # A steep arrow passes through the near edge of the disc before it
        # would reach the board's centre line below the rings.
        lv = flat_level(radius=0.8)
        lay = layout(lv, x=30, y=1.2)
        hits = [CampaignShot(s / 10, 65, lay) for s in range(150, 260)]
        off_line = [h for h in hits if h.outcome == 'target' and abs(h.offset[0]) > 0.3]
        self.assertTrue(off_line)
        for h in off_line:
            self.assertLessEqual(math.hypot(*h.offset), lv.radius + 0.07)

    def test_ring_follows_closest_approach_to_centre(self):
        from campaign import HIT_MARGIN
        lv = flat_level(radius=0.8)
        game = CampaignRound(lv, 0)
        game.layout = layout(lv)
        for strength, angle in list(gold_shots(game))[::15]:
            for y in (1.0, 1.25, 1.5, 1.75, 1.95):
                game.layout.target_y = y
                shot = game.prediction(strength, angle)
                if shot.outcome != 'target':
                    continue
                d = math.hypot(*shot.offset)
                expected = 50 if d <= .32 else 25 if d <= .64 else 15
                self.assertEqual(shot.points, expected)
                self.assertLessEqual(d, .8 + HIT_MARGIN + 1e-6)

    def test_clear_miss_outside_disc_scores_nothing(self):
        lv = flat_level(radius=0.6)
        game = CampaignRound(lv, 0)
        game.layout = layout(lv)
        strength, angle = next(gold_shots(game))
        game.layout.target_y = 1.0 + 0.6 / math.cos(math.radians(abs(angle))) + 0.5
        self.assertEqual(game.prediction(strength, angle).points, 0)

    def test_wall_stops_the_arrow(self):
        lv = flat_level(obstacles=(Obstacle('wall', 10, 0, 1, 20),))
        shot = CampaignShot(30, 20, layout(lv))
        self.assertEqual(shot.outcome, 'obstacle')
        self.assertAlmostEqual(shot.position(shot.end_time)[0], 10, places=3)

    def test_hill_stops_low_arrow(self):
        lv = flat_level(hills=(Hill(15, 5, 6),))
        shot = CampaignShot(30, 0, layout(lv))
        x, y = shot.position(shot.end_time)
        self.assertEqual(shot.outcome, 'ground')
        self.assertLess(x, 15)
        self.assertAlmostEqual(y, terrain_height(x, lv.hills), places=3)

    def test_tailwind_carries_further_than_headwind(self):
        lv = flat_level()
        tail = CampaignShot(25, 30, layout(lv, x=500, wind=1.5))
        head = CampaignShot(25, 30, layout(lv, x=500, wind=-1.5))
        calm = CampaignShot(25, 30, layout(lv, x=500))
        lands = [s.position(s.end_time)[0] for s in (head, calm, tail)]
        self.assertEqual(lands, sorted(lands))
        self.assertGreater(lands[2] - lands[0], 10)

    def test_moving_board_scores_depend_on_release_time(self):
        lv = flat_level(target_motion=(1.5, 3.0))
        lay = layout(lv, y=2.5)
        game = CampaignRound(lv, 0)
        game.layout = lay
        strength, angle = next(gold_shots(game, 0.0))
        self.assertEqual(game.prediction(strength, angle).points, 50)
        game.clock = 0.75                      # board a quarter cycle higher
        self.assertEqual(game.prediction(strength, angle).points, 0)

    def test_floating_crate_bobs(self):
        crate = Obstacle('crate', 20, 5, 2, 2, move_amp=2, move_period=4)
        self.assertNotEqual(obstacle_boxes(crate, 0)[0][1], obstacle_boxes(crate, 1)[0][1])

    def test_vertical_shot_is_valid(self):
        shot = CampaignShot(30, 90, layout(flat_level()))
        self.assertAlmostEqual(shot.position(shot.end_time)[0], 0, places=6)
        self.assertEqual(shot.points, 0)


class RoundTests(unittest.TestCase):
    def fly(self, game, strength, angle):
        self.assertTrue(game.shoot(strength, angle))
        while game.arrow is not None:
            game.update(1 / 60)
        game.settle()

    def test_arrow_budget_required_score_and_stars(self):
        lv = LEVELS[0]
        game = CampaignRound(lv, 3)
        gold = next(gold_shots(game))
        needed = math.ceil(lv.required / 50)
        for _ in range(needed):
            self.fly(game, *gold)
        self.assertFalse(game.finished)
        self.assertTrue(game.passed)
        for _ in range(lv.arrows - needed):
            self.fly(game, *gold)
        self.assertTrue(game.finished)
        self.assertFalse(game.shoot(*gold))       # out of arrows
        self.assertEqual((game.score, game.stars), (lv.max_score, 3))

    def test_round_ends_early_when_required_score_is_unreachable(self):
        lv = LEVELS[9]
        game = CampaignRound(lv, 1)
        misses = lv.arrows - math.ceil(lv.required / 50) + 1
        for _ in range(misses):
            self.fly(game, 0.1, -20)              # into the ground
        self.assertTrue(game.hopeless)
        self.assertTrue(game.finished)
        self.assertEqual(game.shots, misses)
        self.assertLess(game.shots, lv.arrows)
        self.assertFalse(game.passed)

    def test_star_thresholds(self):
        lv = LEVELS[0]
        self.assertEqual(stars_for(lv, lv.required - 1), 0)
        self.assertEqual(stars_for(lv, lv.required), 1)
        self.assertEqual(stars_for(lv, lv.max_score), 3)

    def test_relocating_board_moves_only_after_settle(self):
        lv = LEVELS[6]
        game = CampaignRound(lv, 2)
        before = (game.layout.target_x, game.layout.target_id)
        self.assertTrue(game.shoot(*next(gold_shots(game))))
        while game.arrow is not None:
            game.update(1 / 60)
        self.assertEqual((game.layout.target_x, game.layout.target_id), before)
        self.assertEqual(game.history[-1].impact.points, 50)
        game.settle()
        self.assertEqual(game.layout.target_id, before[1] + 1)
        x = game.layout.target_x
        self.assertTrue(lv.distance[0] - .1 <= x <= lv.distance[1] + .1)

    def test_random_layouts_differ_between_attempts(self):
        game = CampaignRound(LEVELS[4], 11)
        seen = set()
        for _ in range(6):
            game.reset()
            seen.add((game.layout.target_x, game.layout.wind))
        self.assertGreater(len(seen), 3)
        self.assertTrue(any(w < 0 for _, w in seen) or any(w > 0 for _, w in seen))


class ProgressTests(unittest.TestCase):
    def test_clearing_unlocks_next_and_persists(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'p.json'
            progress = CampaignProgress(path)
            self.assertTrue(progress.is_unlocked(1))
            self.assertFalse(progress.is_unlocked(2))
            game = CampaignRound(LEVELS[0], 0)
            game.score = LEVELS[0].required - 1
            progress.record(game)
            self.assertFalse(progress.is_unlocked(2))
            game.score = 200
            progress.record(game)
            again = CampaignProgress(path)
            self.assertTrue(again.is_unlocked(2))
            self.assertEqual(again.best[1], 200)
            self.assertEqual(again.stars[1], stars_for(LEVELS[0], 200))

    def test_unlock_all_is_not_saved_and_bad_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'p.json'
            path.write_text('{not json')
            progress = CampaignProgress(path)
            self.assertEqual(progress.unlocked, 1)
            progress.unlock_all = True
            self.assertTrue(progress.is_unlocked(10))
            progress.save()
            self.assertEqual(json.loads(path.read_text())['unlocked'], 1)


class CampaignFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_ui()
        pygame.display.init()
        pygame.font.init()
        cls.screen = pygame.display.set_mode((1280, 800))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        pygame.event.clear()
        self.dir = tempfile.TemporaryDirectory()
        self.app = Archidon(self.screen, progress_path=Path(self.dir.name) / 'p.json')

    def tearDown(self):
        self.app.close_camera()
        self.dir.cleanup()

    def click(self, name, view):
        self.app.draw()
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=view.buttons[name].center))
        self.app.events()

    def key(self, key, unicode=''):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode, mod=0))
        self.app.events()

    def play_out(self, shot):
        for _ in range(self.app.game.level.arrows):
            if self.app.state != STATE_PLAY:
                break
            self.assertTrue(self.app.shoot(*shot))
            for _ in range(900):
                self.app.update(1 / 60)
                self.app.draw()
                if self.app.state == STATE_FINISH or (self.app.game.arrow is None and self.app.world_camera.can_shoot):
                    break

    def test_menu_to_level_select_to_cleared_level(self):
        self.click('campaign_mouse', self.app.duel_renderer)
        self.assertEqual(self.app.state, CAMPAIGN_SELECT)
        self.assertNotIn('level_2', self.app.campaign_renderer.buttons)
        self.click('level_1', self.app.campaign_renderer)
        self.assertEqual(self.app.state, STATE_PLAY)
        self.assertTrue(self.app.briefing)
        gold = next(gold_shots(self.app.game))
        self.assertFalse(self.app.shoot(*gold))           # blocked by briefing
        self.key(pygame.K_SPACE)
        self.assertFalse(self.app.briefing)
        self.play_out(gold)
        self.assertEqual(self.app.state, STATE_FINISH)
        self.assertTrue(self.app.game.passed)
        self.assertTrue(self.app.progress.is_unlocked(2))
        self.click('next_level', self.app.campaign_renderer)
        self.assertEqual(self.app.game.level.number, 2)
        self.assertTrue(self.app.briefing)

    def test_failed_level_offers_retry_but_not_next(self):
        self.app.open_campaign('mouse')
        self.assertTrue(self.app.start_level(1))
        self.app.begin_level()
        self.play_out((0.1, -30))
        self.assertEqual(self.app.state, STATE_FINISH)
        self.assertFalse(self.app.game.passed)
        self.app.draw()
        self.assertNotIn('next_level', self.app.campaign_renderer.buttons)
        self.assertFalse(self.app.progress.is_unlocked(2))
        self.key(pygame.K_r)
        self.assertEqual((self.app.state, self.app.game.shots), (STATE_PLAY, 0))

    def test_locked_levels_cannot_start_and_number_keys_work(self):
        self.app.open_campaign('mouse')
        self.assertFalse(self.app.start_level(5))
        self.key(pygame.K_5, '5')
        self.assertEqual(self.app.state, CAMPAIGN_SELECT)
        self.key(pygame.K_1, '1')
        self.assertEqual((self.app.state, self.app.game.level.number), (STATE_PLAY, 1))
        self.key(pygame.K_ESCAPE)
        self.assertEqual(self.app.state, STATE_MENU)
        self.assertFalse(self.app.campaign)

    def test_camera_gesture_starts_level_from_briefing(self):
        self.app.open_campaign('mouse')
        self.app.start_level(1)
        self.app.mode = 'camera'                  # gesture path without a webcam
        self.assertFalse(self.app.shoot(.5, 20))
        self.assertFalse(self.app.briefing)
        self.assertEqual(self.app.game.shots, 0)

    def test_mouse_arrow_keys_fine_tune(self):
        self.app.open_campaign('mouse')
        self.app.start_level(1)
        self.app.begin_level()
        angle, strength = self.app.angle, self.app.strength
        self.key(pygame.K_UP)
        self.key(pygame.K_RIGHT)
        self.assertAlmostEqual(self.app.angle, angle + .1)
        self.assertAlmostEqual(self.app.strength, strength + .002)

    def test_every_level_renders_all_screens(self):
        self.app.progress.unlock_all = True
        self.app.open_campaign('mouse')
        self.app.draw()
        for lv in LEVELS:
            self.assertTrue(self.app.start_level(lv.number, seed=lv.number))
            self.app.draw()
            self.app.begin_level()
            self.app.draw()
            self.app.shoot(.8, 40)
            for _ in range(30):
                self.app.update(1 / 30)
                self.app.draw()
            self.app.state = STATE_FINISH
            self.app.draw()


class AdminTests(unittest.TestCase):
    def setUp(self):
        from admin import Admin
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / 'admin.json'
        self.admin = Admin(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def test_default_password_then_change_is_hashed_and_persisted(self):
        from admin import Admin, DEFAULT_PASSWORD
        self.assertFalse(self.admin.login('nope')[0])
        self.assertTrue(self.admin.login(DEFAULT_PASSWORD)[0])
        self.assertTrue(self.admin.set_password('bullseye42')[0])
        self.assertNotIn('bullseye42', self.path.read_text())
        again = Admin(self.path)
        self.assertFalse(again.login(DEFAULT_PASSWORD)[0])
        self.assertTrue(again.login('bullseye42')[0])

    def test_lockout_after_repeated_wrong_passwords(self):
        from admin import DEFAULT_PASSWORD, MAX_ATTEMPTS
        for _ in range(MAX_ATTEMPTS):
            self.admin.login('wrong')
        self.assertGreater(self.admin.lockout_left, 0)
        self.assertFalse(self.admin.login(DEFAULT_PASSWORD)[0])   # even the right one waits

    def test_options_change_levels_only_when_enabled(self):
        from admin import DEFAULT_PASSWORD
        lv = LEVELS[9]
        self.admin.toggle('infinite_arrows')        # ignored while locked
        self.assertFalse(self.admin.options.infinite_arrows)
        self.admin.login(DEFAULT_PASSWORD)
        for name in ('infinite_arrows', 'full_preview', 'no_wind', 'still_target', 'target_scale'):
            self.admin.toggle(name)
        played = self.admin.options.apply(lv)
        self.assertEqual((played.arrows, played.preview, played.wind), (99, 1.0, (0.0, 0.0)))
        self.assertEqual((played.target_motion, played.relocate), ((0.0, 0.0), False))
        self.assertAlmostEqual(played.radius, lv.radius * 1.5)
        self.assertEqual(played.number, lv.number)
        self.admin.logout()
        self.assertFalse(self.admin.active)
        self.assertFalse(self.admin.options.infinite_arrows)


class AdminFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_ui()
        pygame.display.init()
        pygame.font.init()
        cls.screen = pygame.display.set_mode((1280, 800))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        pygame.event.clear()
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name)
        self.app = Archidon(self.screen, progress_path=d / 'p.json', admin_path=d / 'a.json')

    def tearDown(self):
        self.app.close_camera()
        self.dir.cleanup()

    def click(self, name, view):
        self.app.draw()
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=view.buttons[name].center))
        self.app.events()

    def type(self, text):
        for ch in text:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=ch, mod=0))
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode='\r', mod=0))
        self.app.events()

    def test_gear_password_panel_unlocks_levels_and_results_are_not_saved(self):
        from admin import DEFAULT_PASSWORD
        from main import ADMIN_LOGIN, ADMIN_PANEL
        self.click('admin', self.app.duel_renderer)
        self.assertEqual(self.app.state, ADMIN_LOGIN)
        self.type('wrong')
        self.assertEqual(self.app.state, ADMIN_LOGIN)
        self.app.draw()
        self.type(DEFAULT_PASSWORD)                 # typing must not trigger game shortcuts
        self.assertTrue(self.app.running)
        self.assertEqual(self.app.state, ADMIN_PANEL)
        self.assertTrue(self.app.progress.is_unlocked(10))
        self.click('adm_toggle_infinite_arrows', self.app.campaign_renderer)
        self.click('adm_toggle_show_hitboxes', self.app.campaign_renderer)
        self.click('adm_levels', self.app.campaign_renderer)
        self.assertEqual(self.app.state, CAMPAIGN_SELECT)
        self.click('level_10', self.app.campaign_renderer)
        self.assertEqual(self.app.game.level.arrows, 99)
        self.app.begin_level()
        self.app.draw()                              # hitbox overlay renders
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_f, unicode='f', mod=0))
        self.app.events()
        for _ in range(5):
            self.app.update(1 / 60)
        self.assertEqual(self.app.state, STATE_FINISH)
        self.app.draw()
        self.assertEqual(self.app.progress.best, {})        # admin results are not saved
        self.assertFalse(Path(self.dir.name, 'p.json').exists())

    def test_change_password_and_lock(self):
        from admin import DEFAULT_PASSWORD
        from main import ADMIN_PANEL
        self.app.open_admin()
        self.type(DEFAULT_PASSWORD)
        self.click('adm_password', self.app.campaign_renderer)
        self.type('ab')                               # too short
        self.type('newpass1')
        self.type('newpass2')                         # mismatch -> start again
        self.type('newpass1')
        self.type('newpass1')
        self.assertEqual(self.app.state, ADMIN_PANEL)
        self.click('adm_lock', self.app.campaign_renderer)
        self.assertEqual(self.app.state, STATE_MENU)
        self.assertFalse(self.app.admin.active)
        self.assertFalse(self.app.progress.is_unlocked(2))
        self.app.open_admin()
        self.type(DEFAULT_PASSWORD)
        self.assertFalse(self.app.admin.active)
        self.type('newpass1')
        self.assertTrue(self.app.admin.active)

    def test_reset_progress_needs_two_presses(self):
        from admin import DEFAULT_PASSWORD
        self.app.progress.unlocked, self.app.progress.best = 4, {1: 200}
        self.app.open_admin()
        self.type(DEFAULT_PASSWORD)
        self.click('adm_reset', self.app.campaign_renderer)
        self.assertEqual(self.app.progress.unlocked, 4)
        self.click('adm_reset', self.app.campaign_renderer)
        self.assertEqual((self.app.progress.unlocked, self.app.progress.best), (1, {}))


if __name__ == '__main__':
    unittest.main()
