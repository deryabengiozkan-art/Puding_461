"""Production SDL event flow for selection, simultaneous input and cleanup."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
from collections import defaultdict
import unittest
from unittest.mock import Mock, patch
import pygame
from main import (Archidon, STATE_MENU, DUEL_SELECT, DUEL_CALIBRATE,
                  DUEL_PLAY, DUEL_FINISH)


class DuelUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.font.init()
        cls.screen = pygame.display.set_mode((1280, 800))

    def setUp(self):
        pygame.event.clear()
        self.app = Archidon(self.screen)

    def tearDown(self):
        self.app.close_camera()
        pygame.event.clear()

    def event(self, kind, **attributes):
        pygame.event.post(pygame.event.Event(kind, attributes))
        self.app.events()

    def click(self, action):
        self.app.draw()
        self.event(pygame.MOUSEBUTTONDOWN, button=1,
                   pos=self.app.duel_renderer.buttons[action].center)

    def keyboard_match(self):
        self.click('duel_keyboard')
        self.click('begin_duel')
        self.assertEqual(self.app.state, DUEL_PLAY)

    def test_menu_selection_both_characters_and_start(self):
        self.click('duel_keyboard')
        self.assertEqual(self.app.state, DUEL_SELECT)
        self.click('pick_0_storm')
        self.click('pick_1_ranger')
        self.click('begin_duel')
        self.assertEqual([p.character for p in self.app.duel.players], ['storm', 'ranger'])
        self.app.draw()

    def test_both_held_keys_then_same_frame_releases_fire(self):
        self.keyboard_match()
        keys = defaultdict(int, {pygame.K_f: 1, pygame.K_RETURN: 1,
                                 pygame.K_d: 1, pygame.K_LEFT: 1})
        with patch('pygame.key.get_pressed', return_value=keys):
            self.app.update(.5)
        self.assertLess(self.app.duel.separation, 22)
        # The production loop updates before consuming the key-up events.
        with patch('pygame.key.get_pressed', return_value=defaultdict(int)):
            self.app.update(.01)
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_f))
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_RETURN))
        self.app.events()
        self.assertEqual(len(self.app.duel.arrows), 2)
        self.assertEqual([p.shots for p in self.app.duel.players], [1, 1])
        self.app.draw()

    def test_focus_loss_cancels_both_held_draws(self):
        self.keyboard_match()
        for i in range(2):
            self.app.duel.keyboard(i, draw=True, dt=.5)
        self.event(pygame.WINDOWFOCUSLOST)
        self.event(pygame.KEYUP, key=pygame.K_f)
        self.event(pygame.KEYUP, key=pygame.K_RETURN)
        self.assertEqual(self.app.duel.arrows, [])

    def test_camera_selection_capture_failure_and_cleanup(self):
        session = Mock()
        session.read.return_value = (None, [None, None], 'Both players needed', 1000)
        with patch('duel_camera.DuelSession', return_value=session):
            self.click('duel_camera')
            self.click('begin_duel')
        self.assertEqual(self.app.state, DUEL_CALIBRATE)
        self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
        self.assertTrue(self.app.duel.capturing)
        self.app.update(.01)
        self.app.draw()
        session.read.side_effect = RuntimeError('Camera frames stopped')
        self.app.update(.01)
        self.assertEqual(self.app.state, STATE_MENU)
        self.assertIn('Camera frames stopped', self.app.error)
        session.close.assert_called_once()
        self.app.draw()
        self.assertIn('duel_keyboard', self.app.duel_renderer.buttons)

    def test_knockout_finish_rematch_and_menu(self):
        self.keyboard_match()
        self.app.duel.players[1].health = 0
        self.app.update(.02)
        self.assertEqual(self.app.state, DUEL_FINISH)
        self.click('duel_again')
        self.assertEqual(self.app.state, DUEL_PLAY)
        self.assertEqual([p.health for p in self.app.duel.players], [100, 100])
        self.event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        self.assertEqual(self.app.state, STATE_MENU)

    def test_camera_calibration_to_simultaneous_gesture_release(self):
        session = Mock()
        with patch('duel_camera.DuelSession', return_value=session):
            self.app.select_duel('camera')
            self.app.begin_duel()
        stamp = 1000

        def camera_frame(gap, state='Closed', x_shift=0):
            nonlocal stamp
            stamp += 100
            observations = [dict(stamp=stamp, center=(x+x_shift, .4), scale=.16,
                                 gap=gap, angle=12., state=state, generation=1,
                                 hands_clear=True, identity_clear=True)
                            for x in (.25, .75)]
            session.read.return_value = (None, observations, 'Both players tracked', stamp)
            self.app.update(.01)

        for gap in (.4, .4, 1.4):
            self.event(pygame.KEYDOWN, key=pygame.K_SPACE)
            for _ in range(12):
                camera_frame(gap)
            self.app.draw()
        self.assertEqual(self.app.state, DUEL_PLAY)
        camera_frame(1.4, 'Closed', .1)
        camera_frame(1.4, 'Closed', .1)
        camera_frame(1.4, 'Open', .1)
        camera_frame(1.4, 'Open', .1)
        self.assertEqual([p.shots for p in self.app.duel.players], [1, 1])
        self.assertEqual(len(self.app.duel.arrows), 2)
        self.assertGreater(self.app.duel.players[0].x, 9)
        self.app.draw()


if __name__ == '__main__':
    unittest.main()
