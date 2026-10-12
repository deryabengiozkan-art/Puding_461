"""Pygame presentation for solo practice; screen coordinates exist only here.

Drawn with the shared pixel-art kit: the endless parallax campus, a pixel
archer (Player 1's chosen character), pixel arrows, target, panels and font.
"""
import math
import pygame
from characters import CharacterArtist
from physics import ARCHER_HEIGHT, TARGET_DISTANCE, TARGET_HEIGHT, TARGET_RADIUS
from pixelart import ui as pui, scenery as pscenery
from pixelart.kit import Layer, INK as PINK, WHITE as PWHITE, big
from pixelart.painter import Painter

WIDTH, HEIGHT = 1280, 800
PIXELS_PER_METRE = 70
GROUND_Y = 650
LAUNCH_X = 1000
INK = (31, 24, 44)
PANEL = pui.PANEL
PAPER = (255, 245, 220)
MUTED = (200, 196, 230)
GOLD = (255, 210, 64)
GREEN = (92, 214, 120)
HISTORY_COLORS = ((98, 212, 235), (246, 150, 101), (197, 167, 244))
FIELD = pygame.Rect(28, 116, 1224, 564)
SCENERY_PER_PIXEL = 1 / 3          # parallax camera units per screen pixel of pan


def world_to_screen(point, pan_x=0.0, pan_y=0.0):
    # World x is distance toward the target, so drawing subtracts it from x.
    return pygame.Vector2(LAUNCH_X - (point[0]-pan_x) * PIXELS_PER_METRE,
                          GROUND_Y - (point[1]-pan_y) * PIXELS_PER_METRE)


def point(vector):
    return round(vector[0]), round(vector[1])


def _target_sprite():
    """Native target board on a wooden stand; rings follow the scoring radii."""
    s = PIXELS_PER_METRE / 3
    r = round(TARGET_RADIUS * s)
    L = Layer(2 * r + 30, 2 * r + 40)
    c = (r + 15, r + 8)
    for sx in (-1, 1):
        L.thick((c[0] + sx * 3, c[1] + 4), (c[0] + sx * 12, c[1] + r + 26), 2, (150, 96, 60))
    L.outline()
    B = Layer(L.w, L.h)
    B.ell(c[0] - r - 1, c[1] - r - 1, 2 * r + 3, 2 * r + 3, (250, 244, 228))
    for metres, color in ((.5, (90, 196, 216)), (.4, (239, 101, 93)), (.2, GOLD)):
        rr = round(metres * s)
        B.ell(c[0] - rr, c[1] - rr, 2 * rr + 1, 2 * rr + 1, color)
    B.px(c[0], c[1], INK)
    B.outline()
    L.paste(B)
    return L.surf, c


class Renderer(Painter):
    def __init__(self, screen, background='pixelMakinaG.jpeg', scenery_mode='day'):
        super().__init__(screen)
        self.pan_x = self.pan_y = 0.0
        self.artist = CharacterArtist()
        self.character = 'ranger'
        self.scenery_mode = scenery_mode if scenery_mode in ('day', 'night') else 'day'
        self._prediction_shot = None
        self._prediction_path = ()
        self._camera_rgb = self._camera_surface = None
        self._target = None

    # ------------------------------------------------------------------ widgets
    def panel(self, rect, color=PANEL, radius=16):
        rect = pygame.Rect(rect)
        if rect.h < 30 or rect.w < 30:
            # Thin bars stay flat, with a crisp ink frame.
            pygame.draw.rect(self.screen, INK, rect.inflate(6, 6))
            pygame.draw.rect(self.screen, color, rect)
            return rect
        return Painter.panel(self, rect, color)

    def button(self, name, label, rect, primary=False):
        return Painter.button(self, name, label, rect, 'green' if primary else 'blue')

    def arrow(self, tip, direction, color=GOLD, length=46):
        direction = pygame.Vector2(direction)
        # An exactly vertical arrow is momentarily stationary at its apex.
        # Keep its upward orientation for that instant instead of normalizing zero.
        direction = (direction.normalize() if direction.length_squared() > 1e-12
                     else pygame.Vector2(0, -1))
        angle = round(math.degrees(math.atan2(-direction.y, direction.x)) / 5) * 5
        color = tuple(color[:3])
        img = self.scaled(pui.arrow_sprite(angle, color), key=('arrow', angle, color))
        r = math.radians(angle)
        centre = (tip[0] - math.cos(r) * 14 * 3, tip[1] + math.sin(r) * 14 * 3)
        self.screen.blit(img, img.get_rect(center=point(centre)))

    def target(self):
        center = self.project((TARGET_DISTANCE, TARGET_HEIGHT))
        radius = round(TARGET_RADIUS * PIXELS_PER_METRE)
        # Hide the whole board and its label until they enter the world view.
        if not FIELD.inflate(90, 180).collidepoint(point(center)):
            return
        if self._target is None:
            native, c = _target_sprite()
            self._target = big(native), pygame.Vector2(c) * 3
        img, offset = self._target
        self.screen.blit(img, point(center - offset))
        label = pygame.Rect(round(center.x-96), round(center.y-radius-84), 192, 66)
        self.panel(label, PANEL)
        self.text('50 / 25 / 15', (label.centerx, label.y+20), 20, GOLD, True)
        self.text('GOLD / RED / BLUE', (label.centerx, label.y+44), 14, MUTED, True)

    def project(self, position):
        return world_to_screen(position, self.pan_x, self.pan_y)

    def archer(self, angle, strength, in_flight):
        tip = self.project((0, ARCHER_HEIGHT))
        if FIELD.inflate(250, 200).collidepoint(point(tip)):
            feet = (tip.x + 12, tip.y + ARCHER_HEIGHT * PIXELS_PER_METRE)
            self.artist.draw(self.screen, self.character, feet, -1, angle, strength, scale=4/3,
                             firing=in_flight, time=pygame.time.get_ticks()/1000)

    def draw_path(self, path, color, spacing=22, solid=False):
        if not path:
            return
        locations = [self.project(position) for position in path]
        if solid and len(locations) > 1:
            for a in locations[::2]:
                if FIELD.collidepoint(point(a)):
                    pygame.draw.rect(self.screen, color, (round(a.x)-2, round(a.y)-2, 4, 4))
        else:
            previous = None
            accumulated = 0.0
            for location in locations:
                if previous is not None:
                    accumulated += (location-previous).length()
                if previous is None or accumulated >= spacing:
                    if FIELD.collidepoint(point(location)):
                        x, y = point(location)
                        pygame.draw.rect(self.screen, INK, (x-4, y-4, 9, 9))
                        pygame.draw.rect(self.screen, color, (x-2, y-2, 5, 5))
                    accumulated = 0
                previous = location
        end = locations[-1]
        if FIELD.collidepoint(point(end)):
            x, y = point(end)
            pygame.draw.rect(self.screen, INK, (x-8, y-8, 17, 17), 3)
            pygame.draw.rect(self.screen, color, (x-6, y-6, 13, 13), 3)

    def trajectory(self, shot):
        if shot != self._prediction_shot:
            self._prediction_shot = shot
            self._prediction_path = tuple(shot.preview(.025))
        self.draw_path(self._prediction_path, PAPER)

    def scenery(self):
        self.buttons = {}
        parallax = pscenery.get(self.scenery_mode)
        ground = round(GROUND_Y + self.pan_y * PIXELS_PER_METRE)
        bottom = ground + (pscenery.H - pscenery.GROUND_Y - 2) * 3
        cam = -self.pan_x * PIXELS_PER_METRE * SCENERY_PER_PIXEL
        parallax.draw(self.screen, cam, bottom, 'back', pygame.time.get_ticks()/1000)
        if bottom < HEIGHT:
            grass = pscenery.PALETTES[self.scenery_mode]['grass']
            self.screen.fill(grass[:3], (0, bottom, WIDTH, HEIGHT - bottom))
        if ground < FIELD.bottom:
            for metres in range(0, int(TARGET_DISTANCE)+6, 5):
                x = round(self.project((metres, 0)).x)
                if FIELD.left < x < FIELD.right:
                    pygame.draw.rect(self.screen, INK, (x-2, ground+6, 4, 12))
                    self.text(f'{metres} M', (x, ground+30), 14, PAPER, True)

    def shot_history(self, game):
        if not game.history:
            return
        # Move the diagram up during flight so it cannot hide the distant board.
        shift_y = 0 if getattr(self, '_phase', 'AIM') == 'AIM' else -230
        rect = pygame.Rect(54, 420+shift_y, 438, 222)
        self.panel(rect, PANEL)
        self.text('PREVIOUS SHOT PATHS', (72, 436+shift_y), 14, MUTED)
        last = game.last_shot
        self.text(f'LAST: {last.strength:.0%} PULL  {last.shot.angle:+.1f}°  {last.impact.points} PTS',
                  (72, 460+shift_y), 16, PAPER)
        plot = pygame.Rect(73, 490+shift_y, 395, 96)
        high = max(ARCHER_HEIGHT, *(p[1] for record in game.history for p in record.path)) + .3
        def miniature(position):
            return (plot.right-position[0]/TARGET_DISTANCE*plot.width,
                    plot.bottom-max(0, position[1])/high*plot.height)
        pygame.draw.line(self.screen, MUTED, plot.bottomleft, plot.bottomright, 3)
        self.text(f'{TARGET_DISTANCE:.0f} M', (plot.left, plot.bottom+6), 14, MUTED)
        self.text('LAUNCH', (plot.right-60, plot.bottom+6), 14, MUTED)
        for record in game.history:
            color = HISTORY_COLORS[(record.number-1) % len(HISTORY_COLORS)]
            vertices = [point(miniature(p)) for p in record.path]
            pygame.draw.lines(self.screen, color, False, vertices, 3)
            pygame.draw.rect(self.screen, color, (vertices[-1][0]-3, vertices[-1][1]-3, 7, 7))
            self.text(f'{record.number}: {record.strength:.0%} / {record.shot.angle:+.0f}°',
                      (72+(record.number-1)*138, 620+shift_y), 14, color, bold=False)

    def scene(self, game, strength, angle, preview=True, world_camera=None):
        self.pan_x = world_camera.pan_x if world_camera else 0.0
        self.pan_y = world_camera.pan_y if world_camera else 0.0
        self.scenery()
        self.target()
        for record in game.history:
            color = HISTORY_COLORS[(record.number-1) % len(HISTORY_COLORS)]
            self.draw_path(record.path, color, spacing=20)
        if preview and game.arrow is None and not game.finished:
            self.trajectory(game.prediction(strength, angle))
        for record in game.history:
            impact = record.impact
            position = self.project(impact.position)
            if FIELD.collidepoint(point(position)):
                self.arrow(position, (-impact.velocity[0], -impact.velocity[1]), HISTORY_COLORS[record.number-1], 35)
        if game.arrow is not None:
            flight = game.arrow
            self.draw_path(flight.trail, GOLD, solid=True)
            self.arrow(self.project(flight.position), (-flight.velocity[0], -flight.velocity[1]))
        self.archer(angle, strength, game.arrow is not None)
        ground = round(GROUND_Y + self.pan_y * PIXELS_PER_METRE)
        pscenery.get(self.scenery_mode).draw(self.screen, -self.pan_x * PIXELS_PER_METRE * SCENERY_PER_PIXEL,
                                             ground + (pscenery.H - pscenery.GROUND_Y - 2) * 3, 'front')
        # Top HUD
        self.text('ARCHIDON', (28, 18), 40, GOLD)
        self.text('ME461 / DISTANT TARGET', (30, 70), 14, PAPER, bold=False)
        self.panel((740, 18, 234, 84))
        self.text('ROUND SCORE', (762, 34), 14, MUTED)
        self.text(f'{game.score:03d} / 150', (762, 56), 26, GOLD)
        self.panel((986, 18, 268, 84))
        self.text('ARROWS', (1008, 34), 14, MUTED)
        for i in range(3):
            color = GOLD if i >= game.shots else (90, 84, 110)
            self.arrow((1060+i*62, 74), (-1, 0), color, 27)
        self.panel((1040, 252, 204, 90), PANEL)
        self.text(f'{strength:.0%} POWER', (1060, 270), 20, PAPER)
        self.text(f'{angle:+.0f}° ANGLE', (1060, 304), 20, PAPER)
        phase = world_camera.phase if world_camera else 'AIM'
        self._phase = phase
        caption = {'AIM': 'TARGET BEYOND VIEW', 'FOLLOW': 'FOLLOWING ARROW',
                   'IMPACT': 'SHOT LANDED', 'RETURN': 'RETURNING TO ARCHER'}[phase]
        words = f'{TARGET_DISTANCE:.0f} M RANGE · {caption}'
        self.put(pui.ribbon(words, 'purple'), (22, 108), key=('ribbon', words))
        self.shot_history(game)

    def hud(self, game, strength, angle, status, mode, drawing_hand='Right'):
        self.panel((28, 690, 350, 84))
        self.text('PULL STRENGTH', (48, 706), 14, MUTED)
        self.text(f'{strength:.0%}', (356, 704), 20, GOLD, anchor='topright')
        self.put(pui.pull_meter(100, strength), (46, 736))
        self.panel((392, 690, 860, 84))
        self.text(game.message, (414, 704), 20, GOLD, max_width=820)
        self.text(status, (414, 738), 16, PAPER, bold=False, max_width=820)
        footer = ('Drag left mouse to pull; move vertically to aim; release to shoot.' if mode == 'mouse'
                  else f'{drawing_hand} draws: close hand, pull and aim, then open to release. SPACE also shoots.')
        self.text(footer + '  |  R restart · C calibrate · Esc menu', (WIDTH//2, 794), 14, PAPER,
                  anchor='midbottom', bold=False, max_width=1240)

    def camera(self, rgb, drawing_hand, hand_state):
        self.panel((986, 122, 254, 240), pui.PANEL_DARK)
        self.text(f'CAMERA / {drawing_hand.upper()} DRAWS', (1004, 136), 14, MUTED, bold=False)
        if rgb is not None:
            if rgb is not self._camera_rgb:
                self._camera_rgb = rgb
                h, w = rgb.shape[:2]
                surface = pygame.image.frombuffer(rgb.tobytes(), (w, h), 'RGB')
                factor = min(222 / w, 155 / h)
                self._camera_surface = pygame.transform.smoothscale(surface, (round(w*factor), round(h*factor)))
            surface = self._camera_surface
            self.screen.blit(surface, (1002 + (222-surface.get_width())//2, 162))
        self.text(f'HAND: {hand_state.upper()} · H SWAP', (1004, 328), 14, GOLD, bold=False)

    def overlay(self, rect):
        self.shade_screen(140)
        self.panel(rect, PANEL)

    def menu(self, error=''):
        self.overlay((316, 178, 648, 433))
        self.ribbon('TAKE YOUR SHOT', (640, 182), 'orange')
        self.text('Three arrows. A hidden target. Learn from each flight.', (640, 250), 16, MUTED, True)
        self.button('camera', 'PLAY WITH CAMERA', (398, 290, 484, 66), True)
        self.button('mouse', 'MOUSE PRACTICE', (398, 368, 484, 66))
        self.button('quit', 'QUIT', (398, 446, 484, 60))
        self.text('Right hand draws. Left hand holds the bow.', (640, 540), 16, PAPER, True)
        self.text('Camera play begins with three short calibration steps.', (640, 570), 14, MUTED, True)
        if error:
            self.panel((45, 116, 916, 54), (150, 50, 60))
            self.text(error, (64, 134), 16, PAPER, max_width=880)

    def calibration(self, calibration, message):
        self.overlay((95, 185, 900, 410))
        title, instruction = calibration.instructions[calibration.step]
        self.ribbon(title, (545, 190), 'orange')
        y = self.paragraph(instruction, (130, 240), 830, 18, PAPER)
        y = self.paragraph('Keep facing the camera; let it see both shoulders and hands.', (130, y+6), 830, 16, MUTED)
        y = self.paragraph(message, (130, y+12), 830, 16, PAPER)
        capture_message = calibration.message
        if capture_message == message:
            capture_message = 'Waiting for fresh tracking to record this position.'
        self.paragraph(capture_message, (130, y+8), 830, 18, GOLD)
        for i in range(3):
            self.panel((130 + i * 68, 470, 48, 9), GREEN if i < calibration.step else (90, 84, 110))
        self.button('capture', 'SPACE / RECORD POSITION', (130, 500, 420, 66), True)
        self.button('menu', 'BACK TO MENU', (570, 500, 380, 66))

    def finish(self, game):
        self.overlay((342, 201, 596, 400))
        self.ribbon('ROUND COMPLETE', (640, 206), 'green')
        self.text(f'{game.score} / 150', (640, 320), 64, GOLD, True)
        results = '  /  '.join(f'SHOT {i+1}: {hit.points}' for i, hit in enumerate(game.impacts))
        self.text(results, (640, 400), 16, MUTED, True)
        self.button('again', 'PLAY AGAIN', (386, 450, 242, 66), True)
        self.button('menu', 'MENU', (652, 450, 242, 66))
        self.text('R to restart with the same calibration', (640, 560), 14, MUTED, True)
