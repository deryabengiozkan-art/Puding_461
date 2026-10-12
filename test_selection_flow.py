"""Selection works independently on keys and remains accessible after playing."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import unittest
import pygame

from main import Archidon, DUEL_SELECT, DUEL_PLAY, DUEL_FINISH


class SelectionFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.display.init()
        pygame.font.init()
        cls.screen = pygame.display.set_mode((1280, 800))

    def setUp(self):
        self.app = Archidon(self.screen)
        self.app.select_duel('keyboard')

    def tearDown(self):
        self.app.close_camera()
        pygame.event.clear()

    def key(self, key):
        self.app.duel_event(pygame.event.Event(pygame.KEYDOWN, key=key))

    def click(self, name):
        self.app.draw()
        self.app.duel_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1,
            pos=self.app.duel_renderer.buttons[name].center))

    def test_enter_cannot_skip_other_players_selection(self):
        self.key(pygame.K_RETURN)
        self.key(pygame.K_SPACE)
        self.assertEqual(self.app.state, DUEL_SELECT)
        self.key(pygame.K_d)
        self.key(pygame.K_f)
        self.key(pygame.K_SPACE)
        self.assertEqual(self.app.state, DUEL_PLAY)
        self.assertEqual([p.character for p in self.app.duel.players], ['storm', 'storm'])

    def test_changing_character_requires_new_independent_confirmation(self):
        self.key(pygame.K_f)
        self.key(pygame.K_RETURN)
        self.key(pygame.K_LEFT)
        self.key(pygame.K_SPACE)
        self.assertEqual(self.app.state, DUEL_SELECT)
        self.assertEqual(self.app.character_selection.ready, [True, False])
        self.key(pygame.K_RETURN)
        self.key(pygame.K_SPACE)
        self.assertEqual([p.character for p in self.app.duel.players], ['ranger', 'ranger'])

    def test_character_button_survives_finish_and_changes_next_match(self):
        self.click('begin_duel')
        self.app.duel.players[1].health = 0
        self.app.update(.02)
        self.assertEqual(self.app.state, DUEL_FINISH)
        self.click('duel_characters')
        self.assertEqual(self.app.state, DUEL_SELECT)
        self.click('pick_0_storm')
        self.click('pick_1_ranger')
        self.click('begin_duel')
        self.assertEqual(self.app.state, DUEL_PLAY)
        self.assertEqual([p.character for p in self.app.duel.players], ['storm', 'ranger'])
        self.assertEqual([p.health for p in self.app.duel.players], [100, 100])

    def test_tab_reopens_selection_from_active_match(self):
        self.app.begin_duel()
        self.key(pygame.K_TAB)
        self.assertEqual(self.app.state, DUEL_SELECT)
        self.assertEqual(self.app.duel_mode, 'keyboard')
        self.assertEqual(self.app.character_selection.ready, [False, False])


if __name__ == '__main__':
    unittest.main()
