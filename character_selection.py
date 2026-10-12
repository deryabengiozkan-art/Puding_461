"""Two independent character choices, shared by camera and keyboard duels."""
import pygame

from characters import CHARACTERS, CHARACTER_IDS


class CharacterSelection:
    def __init__(self):
        self.ready = [False, False]

    def reset(self):
        self.ready[:] = [False, False]

    def choose(self, selected, player, character):
        if player not in (0, 1) or character not in CHARACTER_IDS:
            return
        if selected[player] != character:
            selected[player] = character
            self.ready[player] = False

    def key(self, key, selected):
        """Return True only when both players have confirmed and press Space."""
        for player, previous, following, confirm in (
                (0, pygame.K_a, pygame.K_d, pygame.K_f),
                (1, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_RETURN)):
            if key in (previous, following):
                index = CHARACTER_IDS.index(selected[player])
                self.choose(selected, player,
                            CHARACTER_IDS[(index + (1 if key == following else -1)) % len(CHARACTER_IDS)])
            elif key == confirm:
                self.ready[player] = not self.ready[player]
        return key == pygame.K_SPACE and all(self.ready)

    def draw(self, ui, selected, mode):
        ui.draw_selection(selected, self.ready, mode)

    @staticmethod
    def draw_reopen(ui):
        ui.icon_button('duel_characters', 'users', (ui.screen.get_width() // 2 - 36, 160), 'purple')
