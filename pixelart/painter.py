"""Screen-space helpers shared by the duel and practice renderers.

Positions and rectangles are in *screen* pixels; artwork is generated natively
and scaled by ``SCALE`` so it lines up with the 3x pixel grid.
"""
import pygame
from . import ui, font
from .kit import SCALE, INK, WHITE, big, rgba, shade

# Text sizes used by the old Arial UI map onto whole pixel-font scales.
def text_scale(size):
    if size >= 50:
        return 5
    if size >= 32:
        return 4
    if size >= 22:
        return 3
    return 2


class Painter:
    def __init__(self, screen):
        self.screen = screen
        self.buttons = {}
        self._big = {}

    # ------------------------------------------------------------------ basics
    def scaled(self, native, scale=SCALE, key=None):
        """Scale a native surface; cached when ``key`` is given."""
        if key is None:
            return big(native, scale)
        hit = self._big.get((key, scale))
        if hit is None:
            hit = big(native, scale)
            if pygame.display.get_init() and pygame.display.get_surface():
                hit = hit.convert_alpha()
            if len(self._big) > 400:
                self._big.clear()
            self._big[(key, scale)] = hit
        return hit

    def put(self, native, pos, scale=SCALE, anchor='topleft', key=None):
        img = self.scaled(native, scale, key)
        rect = img.get_rect(**{anchor: (round(pos[0]), round(pos[1]))})
        self.screen.blit(img, rect)
        return rect

    def text(self, words, pos, size=18, color=WHITE, center=False, bold=None, anchor=None,
             outline=INK, shadow=1, max_width=None):
        scale = text_scale(size)
        bold = size >= 18 if bold is None else bold
        surf = font.text(words, scale, fill=color, bold=bold, outline=outline, shadow=shadow)
        if max_width and surf.get_width() > max_width:
            surf = font.text(words, scale, fill=color, bold=False, outline=outline, shadow=shadow)
            if surf.get_width() > max_width and scale > 2:
                surf = font.text(words, scale - 1, fill=color, bold=False, outline=outline, shadow=shadow)
        rect = surf.get_rect(**{anchor or ('center' if center else 'topleft'): (round(pos[0]), round(pos[1]))})
        self.screen.blit(surf, rect)
        return rect

    def paragraph(self, words, pos, max_width, size=16, color=WHITE, center=False, gap=4):
        scale = text_scale(size)
        bold = size >= 18
        lines = font.wrap(words, max_width // scale - 4, bold)
        x, y = pos
        for line in lines:
            r = self.text(line, (x, y), size, color, False, bold, anchor='midtop' if center else 'topleft')
            y = r.bottom + gap
        return y

    # ------------------------------------------------------------------ widgets
    def button(self, name, label, rect, color='green', icon=None, enabled=True, selected=False):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        pressed = hover and pygame.mouse.get_pressed()[0]
        state = ('disabled' if not enabled else 'pressed' if pressed else 'selected' if selected
                 else 'hover' if hover else 'normal')
        native = ui.button(max(12, rect.w // SCALE - 2), max(10, rect.h // SCALE - 2), str(label),
                           color, state, icon)
        self.put(native, rect.topleft, key=('btn', str(label), rect.size, color, state, icon))
        self.buttons[name] = rect
        return rect

    def icon_button(self, name, icon, center, color='orange', size=20):
        native_hover = pygame.Rect(0, 0, (size + 2) * SCALE, (size + 2) * SCALE)
        native_hover.center = center
        hover = native_hover.collidepoint(pygame.mouse.get_pos())
        pressed = hover and pygame.mouse.get_pressed()[0]
        state = 'pressed' if pressed else 'hover' if hover else 'normal'
        rect = self.put(ui.icon_button(icon, color, state, size), center, anchor='center',
                        key=('ibtn', icon, color, state, size))
        self.buttons[name] = rect
        return rect

    def panel(self, rect, color=ui.PANEL, inset=False):
        rect = pygame.Rect(rect)
        native = ui.panel(rect.w // SCALE, rect.h // SCALE, color, None, inset)
        self.put(native, rect.topleft, key=('panel', rect.size, color, inset))
        return rect

    def ribbon(self, words, center, color='red', width=None):
        return self.put(ui.ribbon(str(words), color, width), center, anchor='center',
                        key=('ribbon', str(words), color, width))

    def shade_screen(self, alpha=170, color=(20, 16, 34)):
        veil = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        veil.fill(color + (alpha,))
        self.screen.blit(veil, (0, 0))
