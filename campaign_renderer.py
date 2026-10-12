"""Pixel-art presentation of the 10-level campaign.

Adds to the practice renderer: hills, obstacles, a board that can sit on a
ridge or bob up and down, wind, a whole-level minimap, the level-select
screen, the level briefing and the cleared / failed result.
"""
import math
import pygame

from campaign import obstacle_boxes, terrain_height
from levels import LEVELS
from physics import ARCHER_HEIGHT
from pixelart import ui as pui, scenery as pscenery
from pixelart.kit import Layer, big
from pixelart.painter import Painter
from renderer import (Renderer, FIELD, GROUND_Y, PIXELS_PER_METRE, WIDTH, HEIGHT, INK, PANEL,
                      PAPER, MUTED, GOLD, GREEN, HISTORY_COLORS, SCENERY_PER_PIXEL, point)

RED = (238, 72, 72)
SKY_BLUE = (98, 212, 235)
LOCKED = (90, 84, 110)
WOOD, WOOD_DARK, WOOD_LIGHT = (176, 116, 64), (124, 76, 46), (214, 160, 96)
STONE, STONE_DARK, STONE_LIGHT = (176, 168, 160), (120, 112, 116), (208, 200, 188)
ROCK, ROCK_DARK = (150, 144, 156), (100, 94, 112)


def snap(v):
    return int(round(v / 3.0)) * 3


def board_sprite(radius):
    """Native-resolution board; rings at 40 / 80 / 100 % of the radius."""
    s = PIXELS_PER_METRE / 3
    r = max(4, round(radius * s))
    B = Layer(2 * r + 6, 2 * r + 6)
    c = (r + 3, r + 3)
    B.ell(c[0] - r - 1, c[1] - r - 1, 2 * r + 3, 2 * r + 3, (250, 244, 228))
    for fraction, color in ((1.0, (90, 196, 216)), (.8, (239, 101, 93)), (.4, GOLD)):
        rr = max(1, round(fraction * radius * s))
        B.ell(c[0] - rr, c[1] - rr, 2 * rr + 1, 2 * rr + 1, color)
    B.px(c[0], c[1], INK)
    B.outline()
    return B.surf, c


def star_points(cx, cy, r):
    pts = []
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.45
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((round(cx + radius * math.cos(a)), round(cy + radius * math.sin(a))))
    return pts


class CampaignRenderer(Renderer):
    def __init__(self, screen, background='pixelMakinaG.jpeg', scenery_mode='day'):
        super().__init__(screen, background, scenery_mode)
        self._boards = {}
        self.mode = 'mouse'
        self.admin = None

    def stars(self, count, center, size=10, gap=None):
        gap = gap or size * 2 + 6
        x0 = center[0] - gap
        for i in range(3):
            pts = star_points(x0 + i * gap, center[1], size)
            pygame.draw.polygon(self.screen, INK, star_points(x0 + i * gap, center[1] + 1, size + 3))
            pygame.draw.polygon(self.screen, GOLD if i < count else LOCKED, pts)

    def arrow_pips(self, total, used, x, y):
        for i in range(total):
            px = x + i * 24
            color = GOLD if i >= used else LOCKED
            pygame.draw.rect(self.screen, INK, (px - 3, y - 3, 12, 36))
            pygame.draw.rect(self.screen, (226, 220, 236) if i >= used else LOCKED, (px, y, 6, 9))
            pygame.draw.rect(self.screen, color, (px + 1, y + 9, 4, 15))
            pygame.draw.rect(self.screen, (240, 80, 70) if i >= used else LOCKED, (px - 1, y + 24, 8, 6))

    def button(self, name, label, rect, color='green', icon=None):
        return Painter.button(self, name, label, rect, color, icon)

    # ------------------------------------------------------------------ world
    def ground_y(self):
        return round(GROUND_Y + self.pan_y * PIXELS_PER_METRE)

    def world_x(self, screen_x):
        from renderer import LAUNCH_X
        return self.pan_x + (LAUNCH_X - screen_x) / PIXELS_PER_METRE

    def ruler(self, layout):
        ground = self.ground_y()
        if ground >= FIELD.bottom:
            return
        for metres in range(0, int(layout.target_x) + 20, 10):
            x = round(self.project((metres, 0)).x)
            if FIELD.left < x < FIELD.right:
                pygame.draw.rect(self.screen, INK, (x - 2, ground + 6, 4, 12))
                self.text(f'{metres} M', (x, ground + 30), 14, PAPER, True)

    def hills(self, layout):
        if not layout.hills:
            return
        palette = pscenery.PALETTES[self.scenery_mode]
        grass, light, dark = palette['grass'][:3], palette['grass3'][:3], palette['grass2'][:3]
        ground = self.ground_y()
        for sx in range(0, WIDTH, 3):
            h = terrain_height(self.world_x(sx + 1.5), layout.hills)
            if h <= 0.02:
                continue
            top = snap(ground - h * PIXELS_PER_METRE)
            if top >= HEIGHT:
                continue
            pygame.draw.rect(self.screen, grass, (sx, top, 3, max(0, ground - top + 3)))
            pygame.draw.rect(self.screen, light, (sx, top + 3, 3, 6))
            if (sx // 3) % 4 == 0:
                pygame.draw.rect(self.screen, dark, (sx, top + 18 + (sx // 3) % 7 * 3, 3, 3))
            pygame.draw.rect(self.screen, INK, (sx, top, 3, 3))

    def obstacle(self, obstacle, clock):
        for i, (x0, y0, x1, y1) in enumerate(obstacle_boxes(obstacle, clock)):
            a, b = self.project((x1, y1)), self.project((x0, y0))
            rect = pygame.Rect(snap(a.x), snap(a.y), max(3, snap(b.x) - snap(a.x)), max(3, snap(b.y) - snap(a.y)))
            if not rect.colliderect(FIELD.inflate(200, 200)):
                continue
            kind = obstacle.kind
            if kind == 'tree':
                self._tree_part(rect, trunk=i == 0)
            elif kind == 'hedge':
                self._block(rect, (58, 150, 76), (40, 110, 62), (92, 196, 92), pattern='leaf')
            elif kind == 'wall':
                self._block(rect, STONE, STONE_DARK, STONE_LIGHT, pattern='brick')
            elif kind == 'crate':
                self._block(rect, WOOD, WOOD_DARK, WOOD_LIGHT, pattern='crate')
                if obstacle.y > 0 and obstacle.move_amp:
                    self.text('↕', (rect.centerx, rect.top - 18), 14, PAPER, True)
            else:
                self._block(rect, ROCK, ROCK_DARK, STONE_LIGHT, pattern='rock')

    def _block(self, rect, base, dark, light, pattern):
        s = self.screen
        pygame.draw.rect(s, INK, rect.inflate(6, 6))
        pygame.draw.rect(s, base, rect)
        pygame.draw.rect(s, light, (rect.x, rect.y, rect.w, 6))
        pygame.draw.rect(s, dark, (rect.x, rect.bottom - 6, rect.w, 6))
        clip = s.get_clip()
        s.set_clip(rect)
        if pattern == 'brick':
            for row, y in enumerate(range(rect.y + 15, rect.bottom, 15)):
                pygame.draw.rect(s, dark, (rect.x, y, rect.w, 3))
                for x in range(rect.x + (15 if row % 2 else 0), rect.right, 30):
                    pygame.draw.rect(s, dark, (x, y - 12, 3, 12))
        elif pattern == 'crate':
            pygame.draw.rect(s, dark, rect, 6)
            pygame.draw.line(s, dark, rect.topleft, rect.bottomright, 6)
            pygame.draw.line(s, dark, rect.bottomleft, rect.topright, 6)
        elif pattern == 'leaf':
            for y in range(rect.y + 9, rect.bottom - 6, 12):
                for x in range(rect.x + (y // 12 % 2) * 6, rect.right, 12):
                    pygame.draw.rect(s, light, (x, y, 3, 3))
        else:
            for x in range(rect.x + 9, rect.right - 6, 18):
                pygame.draw.rect(s, dark, (x, rect.y + 12 + (x // 18 % 3) * 9, 6, 3))
        s.set_clip(clip)

    def _tree_part(self, rect, trunk):
        palette = pscenery.PALETTES[self.scenery_mode]
        s = self.screen
        if trunk:
            pygame.draw.rect(s, INK, rect.inflate(6, 0))
            pygame.draw.rect(s, palette['trunk'][:3], rect)
            pygame.draw.rect(s, (96, 60, 42), (rect.right - 6, rect.y, 6, rect.h))
            return
        leaf, leaf2 = palette['tree'][:3], palette['tree2'][:3]
        r = rect
        pygame.draw.ellipse(s, INK, r.inflate(9, 9))
        pygame.draw.ellipse(s, leaf2, r)
        pygame.draw.ellipse(s, leaf, (r.x + 6, r.y + 3, r.w - 18, r.h - 15))
        for x in range(r.x + 12, r.right - 12, 15):
            pygame.draw.rect(s, leaf2, (x, r.y + 15 + (x // 15 % 3) * 12, 3, 3))

    def board(self, layout, clock):
        x = layout.target_x
        cy = layout.target_center(clock)
        center = self.project((x, cy))
        if not FIELD.inflate(160, 260).collidepoint(point(center)):
            return
        key = layout.level.radius
        if key not in self._boards:
            native, c = board_sprite(key)
            self._boards[key] = big(native), pygame.Vector2(c) * 3
        img, offset = self._boards[key]
        # Post from the terrain to the highest board position.
        amp = layout.level.target_motion[0]
        foot = self.project((x, terrain_height(x, layout.hills)))
        top = self.project((x, layout.target_y + amp + layout.level.radius))
        pygame.draw.rect(self.screen, INK, (snap(foot.x) - 6, snap(top.y), 12, snap(foot.y) - snap(top.y)))
        pygame.draw.rect(self.screen, (150, 96, 60), (snap(foot.x) - 3, snap(top.y) + 3, 6, snap(foot.y) - snap(top.y) - 3))
        if amp:
            pygame.draw.rect(self.screen, INK, (snap(foot.x) - 15, snap(top.y) - 3, 30, 6))
        self.screen.blit(img, point(center - offset))
        radius = layout.level.radius * PIXELS_PER_METRE
        label = pygame.Rect(round(center.x - 84), round(center.y - radius - 80), 168, 60)
        self.panel(label, PANEL)
        self.text(f'{x:.0f} M', (label.centerx, label.y + 18), 20, GOLD, True)
        self.text('50 / 25 / 15', (label.centerx, label.y + 42), 14, MUTED, True)

    def stuck_arrows(self, game):
        layout = game.layout
        for record in game.history:
            impact = record.impact
            color = HISTORY_COLORS[(record.number - 1) % len(HISTORY_COLORS)]
            if impact.on_target:
                if impact.target_id != layout.target_id:
                    continue        # that board has moved on
                pos = (layout.target_x + impact.offset[0], layout.target_center(game.clock) + impact.offset[1])
            else:
                pos = impact.position
            screen = self.project(pos)
            if FIELD.collidepoint(point(screen)):
                self.arrow(screen, (-impact.velocity[0], -impact.velocity[1]), color, 35)

    def hitboxes(self, game):
        """Admin debug view: exact board hit circle, rings and obstacle boxes."""
        from campaign import HIT_MARGIN
        layout = game.layout
        center = self.project((layout.target_x, layout.target_center(game.clock)))
        radius = layout.level.radius
        for fraction, color in ((1.0, (90, 196, 216)), (0.8, RED), (0.4, GOLD)):
            pygame.draw.circle(self.screen, color, point(center), round(fraction * radius * PIXELS_PER_METRE), 2)
        pygame.draw.circle(self.screen, PAPER, point(center), round((radius + HIT_MARGIN) * PIXELS_PER_METRE), 1)
        for obstacle in game.level.obstacles:
            for x0, y0, x1, y1 in obstacle_boxes(obstacle, game.clock):
                a, b = self.project((x1, y1)), self.project((x0, y0))
                pygame.draw.rect(self.screen, RED, (round(a.x), round(a.y), round(b.x - a.x), round(b.y - a.y)), 2)

    # ------------------------------------------------------------------ admin screens
    def admin_login(self, admin, stage, typed, message):
        self.buttons = {}
        self.striped_background()
        title = {'login': 'ADMIN MODE', 'new': 'NEW PASSWORD', 'confirm': 'CONFIRM PASSWORD'}[stage]
        self.overlay((340, 200, 600, 380))
        self.ribbon(title, (640, 206), 'purple')
        prompt = 'Enter the admin password.' if stage == 'login' else (
            'Type the new password.' if stage == 'new' else 'Type it again to confirm.')
        self.text(prompt, (640, 262), 16, PAPER, True)
        field = pygame.Rect(400, 300, 480, 66)
        self.panel(field, pui.PANEL_DARK)
        cursor = '_' if (pygame.time.get_ticks() // 500) % 2 == 0 else ' '
        self.text('*' * len(typed) + cursor, (field.x + 24, field.y + 20), 26, GOLD)
        if message:
            ok = message.startswith(('Admin mode unlocked', 'Password changed'))
            self.paragraph(message, (640, 386), 520, 16, GREEN if ok else RED, center=True)
        lock = admin.lockout_left
        self.button('adm_submit', f'WAIT {lock:.0f} S' if lock > 0 else 'ENTER', (400, 470, 230, 66), 'green')
        self.button('menu', 'BACK', (650, 470, 230, 66), 'red')
        self.text('Enter to submit · Esc to go back', (640, 552), 14, MUTED, True)

    def admin_panel(self, admin, progress, message, reset_armed):
        self.buttons = {}
        self.striped_background()
        self.ribbon('ADMIN PANEL', (WIDTH // 2, 42), 'purple', 200)
        o = admin.options
        self.panel((60, 96, 560, 590))
        self.text('CAMPAIGN TOOLS', (88, 116), 20, GOLD)
        self.text('Admin-mode results are never saved.', (88, 146), 14, MUTED, bold=False)
        toggles = (('unlock_all', 'ALL LEVELS UNLOCKED', o.unlock_all),
                   ('infinite_arrows', 'UNLIMITED ARROWS', o.infinite_arrows),
                   ('full_preview', 'FULL AIM PREVIEW', o.full_preview),
                   ('no_wind', 'NO WIND', o.no_wind),
                   ('still_target', 'STILL TARGET', o.still_target),
                   ('show_hitboxes', 'SHOW HITBOXES', o.show_hitboxes),
                   ('target_scale', f'TARGET SIZE x{o.target_scale:g}', o.target_scale != 1.0))
        for i, (key, label, on) in enumerate(toggles):
            y = 178 + i * 68
            self.button(f'adm_toggle_{key}', label, (88, y, 384, 56), 'green' if on else 'grey')
            self.text('ON' if on else 'OFF', (560, y + 16), 20, GREEN if on else MUTED, anchor='midtop')
        self.panel((660, 96, 560, 590))
        self.text('PLAY & MANAGE', (688, 116), 20, GOLD)
        self.button('adm_levels', 'LEVELS · MOUSE', (688, 166, 504, 62), 'blue', 'mouse')
        self.button('adm_levels_camera', 'LEVELS · CAMERA', (688, 240, 504, 62), 'orange', 'camera')
        self.text(f'Saved progress: level {progress.unlocked} unlocked, {sum(progress.stars.values())} stars.',
                  (688, 324), 14, PAPER, bold=False, max_width=504)
        self.button('adm_reset', 'CONFIRM RESET' if reset_armed else 'RESET PROGRESS', (688, 352, 504, 62),
                    'red' if reset_armed else 'pink', 'restart')
        self.button('adm_password', 'CHANGE PASSWORD', (688, 426, 504, 62), 'purple', 'gear')
        self.button('adm_lock', 'LOCK ADMIN & EXIT', (688, 500, 504, 62), 'grey', 'quit')
        y = 584
        if admin.using_default:
            y = self.paragraph('Default password in use: change it above.', (688, y), 504, 14, GOLD) + 6
        if message:
            self.paragraph(message, (688, y), 504, 14, PAPER)
        self.button('menu', 'MENU', (60, 706, 220, 60), 'red', 'home')
        self.text('In a level: F ends the level now. Hitboxes show the exact board hit circle.',
                  (WIDTH // 2 + 110, 736), 14, MUTED, True)

    # ------------------------------------------------------------------ preview
    def partial_preview(self, shot, fraction):
        if shot != self._prediction_shot:
            self._prediction_shot = shot
            self._prediction_path = tuple(shot.preview(.025))
        path = self._prediction_path
        count = max(2, int(len(path) * max(0.05, min(1.0, fraction))))
        shown = path[:count]
        if count >= len(path):
            self.draw_path(shown, PAPER)
        else:
            self.draw_path(shown + (shown[-1],), PAPER)

    # ------------------------------------------------------------------ minimap
    def minimap(self, game, preview_shot=None):
        rect = pygame.Rect(318, 14, 600, 96)
        self.panel(rect, pui.PANEL_DARK)
        plot = rect.inflate(-30, -24)
        layout, level = game.layout, game.level
        far = max(layout.target_x + 8, 30)
        high = 14.0
        for obstacle in level.obstacles:
            high = max(high, obstacle.y + obstacle.h + obstacle.move_amp + 1)

        def mm(p):
            x = plot.right - (p[0] + 2) / (far + 2) * plot.width
            y = plot.bottom - max(-0.5, min(high, p[1])) / high * plot.height
            return round(x), round(y)

        # terrain
        pts = [mm((x, terrain_height(x, layout.hills))) for x in
               [i * far / 120 for i in range(121)]]
        pygame.draw.polygon(self.screen, (74, 156, 72), pts + [mm((far, -0.5)), mm((0, -0.5))])
        pygame.draw.lines(self.screen, (132, 214, 104), False, pts, 2)
        for obstacle in level.obstacles:
            for x0, y0, x1, y1 in obstacle_boxes(obstacle, game.clock):
                a, b = mm((x1, y1)), mm((x0, y0))
                color = {'wall': STONE, 'crate': WOOD, 'hedge': (58, 150, 76),
                         'tree': (58, 150, 76), 'rock': ROCK}[obstacle.kind]
                pygame.draw.rect(self.screen, color, (a[0], a[1], max(2, b[0] - a[0]), max(2, b[1] - a[1])))
        for record in game.history:
            color = HISTORY_COLORS[(record.number - 1) % len(HISTORY_COLORS)]
            vertices = [mm(p) for p in record.path[::4]] + [mm(record.path[-1])]
            if len(vertices) > 1:
                pygame.draw.lines(self.screen, color, False, vertices, 2)
        if preview_shot is not None:
            path = self._prediction_path if preview_shot == self._prediction_shot else tuple(preview_shot.preview(.025))
            count = max(2, int(len(path) * level.preview))
            for p in path[:count:6]:
                pygame.draw.rect(self.screen, PAPER, (*mm(p), 2, 2))
        if game.arrow is not None:
            pygame.draw.circle(self.screen, GOLD, mm(game.arrow.position), 3)
        # board, archer
        cx, cy = mm((layout.target_x, layout.target_center(game.clock)))
        r = max(3, round(level.radius / high * plot.height * 1.6))
        pygame.draw.circle(self.screen, (250, 244, 228), (cx, cy), r + 1)
        pygame.draw.circle(self.screen, RED, (cx, cy), r)
        pygame.draw.circle(self.screen, GOLD, (cx, cy), max(1, r // 2))
        ax, ay = mm((0, ARCHER_HEIGHT))
        pygame.draw.rect(self.screen, SKY_BLUE, (ax - 3, ay - 6, 6, 9))
        self.text(f'{layout.target_x:.0f} M', (cx, rect.y + 6), 14, GOLD, anchor='midtop')

    # ------------------------------------------------------------------ scene
    def scene(self, game, strength, angle, preview=True, world_camera=None):
        self.pan_x = world_camera.pan_x if world_camera else 0.0
        self.pan_y = world_camera.pan_y if world_camera else 0.0
        self.buttons = {}
        parallax = pscenery.get(self.scenery_mode)
        ground = self.ground_y()
        bottom = ground + (pscenery.H - pscenery.GROUND_Y - 2) * 3
        cam = -self.pan_x * PIXELS_PER_METRE * SCENERY_PER_PIXEL
        parallax.draw(self.screen, cam, bottom, 'back', pygame.time.get_ticks() / 1000)
        if bottom < HEIGHT:
            grass = pscenery.PALETTES[self.scenery_mode]['grass']
            self.screen.fill(grass[:3], (0, bottom, WIDTH, HEIGHT - bottom))
        layout = game.layout
        self.hills(layout)
        self.ruler(layout)
        for obstacle in game.level.obstacles:
            self.obstacle(obstacle, game.clock)
        self.board(layout, game.clock)
        for record in game.history:
            color = HISTORY_COLORS[(record.number - 1) % len(HISTORY_COLORS)]
            self.draw_path(record.path, color, spacing=20)
        preview_shot = None
        if preview and game.arrow is None and not game.finished:
            preview_shot = game.prediction(strength, angle)
            self.partial_preview(preview_shot, game.level.preview)
        self.stuck_arrows(game)
        if game.arrow is not None:
            flight = game.arrow
            self.draw_path(flight.trail, GOLD, solid=True)
            self.arrow(self.project(flight.position), (-flight.velocity[0], -flight.velocity[1]))
        self.archer(angle, strength, game.arrow is not None)
        parallax.draw(self.screen, cam, bottom, 'front')
        admin = self.admin is not None and self.admin.active
        if admin and self.admin.options.show_hitboxes:
            self.hitboxes(game)
        self.top_hud(game, preview_shot)
        if admin:
            self.panel((22, 262 if game.level.wind[1] > 0 else 198, 284, 54), (150, 50, 60))
            y = 278 if game.level.wind[1] > 0 else 214
            self.text('ADMIN · F ENDS LEVEL', (40, y), 16, PAPER)
        self._phase = world_camera.phase if world_camera else 'AIM'
        self.side_panels(game, strength, angle)

    def top_hud(self, game, preview_shot):
        level = game.level
        self.panel((22, 14, 284, 96))
        self.text(f'LEVEL {level.number} / {len(LEVELS)}', (40, 26), 14, MUTED)
        self.text(level.name, (40, 46), 20, GOLD, max_width=252)
        self.text(level.bow, (40, 80), 14, PAPER, bold=False)
        self.minimap(game, preview_shot)
        self.panel((930, 14, 328, 96))
        need_color = GREEN if game.passed else GOLD
        self.text('SCORE', (948, 24), 14, MUTED)
        self.text(f'{game.score:03d} / {level.required}', (948, 42), 26, need_color)
        if level.arrows > 12:
            self.text(f'UNLIMITED ARROWS · {game.shots} USED', (948, 82), 14, MUTED, bold=False)
        else:
            self.text(f'{game.arrows_left} ARROWS', (948, 82), 14, MUTED, bold=False)
            self.arrow_pips(level.arrows, game.shots, 1238 - level.arrows * 24, 76)

    def side_panels(self, game, strength, angle):
        self.panel((22, 122, 284, 66), PANEL)
        self.text(f'{strength:.1%} · {game.speed(strength):.1f} M/S', (40, 134), 18, PAPER)
        self.text(f'{angle:+.1f}° ANGLE', (40, 160), 16, PAPER, bold=False)
        wind = game.layout.wind
        if game.level.wind[1] > 0:
            self.panel((22, 198, 284, 54), PANEL)
            label = 'TAILWIND' if wind > 0 else 'HEADWIND'
            self.text(f'WIND {abs(wind):.1f} {label}', (40, 214), 16, SKY_BLUE)
            # Wind toward the target blows left on screen.
            y = 226
            x0, x1 = (288, 254) if wind > 0 else (254, 288)
            pygame.draw.line(self.screen, SKY_BLUE, (x0, y), (x1, y), 3)
            tip = x1
            back = 9 if wind > 0 else -9
            pygame.draw.polygon(self.screen, SKY_BLUE, [(tip, y - 6 + 1), (tip, y + 6 + 1), (tip - back, y + 1)])
        features = []
        if game.level.target_motion[0]:
            features.append('BOARD IS MOVING')
        if game.level.relocate:
            features.append('BOARD MOVES AFTER EACH ARROW')
        for i, words in enumerate(features):
            self.text(words, (WIDTH - 30, 128 + i * 22), 14, GOLD, anchor='topright')

    # ------------------------------------------------------------------ screens
    def level_select(self, progress, mode):
        self.buttons = {}
        self.striped_background()
        self.ribbon('CAMPAIGN · 10 LEVELS', (WIDTH // 2, 42), 'orange', 220)
        self.text(f'{"CAMERA" if mode == "camera" else "MOUSE"} CONTROLS  ·  {progress.total_stars} / 30 STARS',
                  (WIDTH // 2, 90), 16, PAPER, True)
        for i, level in enumerate(LEVELS):
            col, row = i % 5, i // 5
            rect = pygame.Rect(56 + col * 236, 130 + row * 268, 220, 248)
            unlocked = progress.is_unlocked(level.number)
            self.panel(rect, PANEL if unlocked else pui.PANEL_DARK)
            self.text(f'{level.number}', (rect.x + 18, rect.y + 14), 40, GOLD if unlocked else LOCKED)
            stars = progress.stars.get(level.number, 0)
            self.stars(stars, (rect.right - 52, rect.y + 32), 9, 24)
            self.text(level.name, (rect.x + 18, rect.y + 66), 16, PAPER if unlocked else LOCKED,
                      max_width=rect.w - 30)
            info = (f'{level.distance[0]}-{level.distance[1]} M  ·  {level.arrows} ARROWS',
                    f'NEED {level.required} / {level.max_score}')
            for j, words in enumerate(info):
                self.text(words, (rect.x + 18, rect.y + 98 + j * 22), 14, MUTED if unlocked else LOCKED,
                          bold=False, max_width=rect.w - 30)
            best = progress.best.get(level.number)
            if best is not None:
                self.text(f'BEST {best}', (rect.x + 18, rect.y + 150), 14, GREEN)
            if unlocked:
                self.button(f'level_{level.number}', 'PLAY', (rect.x + 18, rect.bottom - 54, rect.w - 36, 42),
                            'green' if stars == 0 else 'blue')
            else:
                self.text('LOCKED', (rect.centerx, rect.bottom - 34), 16, LOCKED, True)
        self.button('menu', 'BACK', (56, 690, 220, 60), 'red')
        self.text('Clear a level to unlock the next. Keys 1-9 and 0 also start unlocked levels.',
                  (WIDTH // 2 + 120, 720), 14, MUTED, True)

    def striped_background(self):
        self.screen.fill(pui.BG)
        for x in range(-HEIGHT, WIDTH, 48):
            pygame.draw.line(self.screen, (50, 42, 86), (x, 0), (x + HEIGHT, HEIGHT), 18)

    def briefing(self, game):
        level = game.level
        self.overlay((250, 160, 780, 470))
        self.ribbon(f'LEVEL {level.number}: {level.name}', (640, 166), 'orange')
        y = self.paragraph(level.tagline, (290, 214), 700, 18, PAPER)
        stats = (('TARGET', f'{game.layout.target_x:.0f} M'), ('ARROWS', str(level.arrows)),
                 ('TO CLEAR', f'{level.required} / {level.max_score}'), ('BOW', f'{level.max_speed:.0f} M/S'))
        for i, (label, value) in enumerate(stats):
            x = 290 + i * 180
            self.text(label, (x, y + 16), 14, MUTED)
            self.text(value, (x, y + 38), 20, GOLD)
        y += 90
        for words in level.features:
            self.text('· ' + words, (300, y), 16, PAPER, bold=False)
            y += 26
        if level.wind[1] > 0:
            wind = game.layout.wind
            self.text(f'· Wind now: {abs(wind):.1f} m/s² {"tailwind" if wind > 0 else "headwind"}',
                      (300, y), 16, SKY_BLUE, bold=False)
        if self.mode == 'camera':
            self.text('Camera: close and open your drawing hand to start.', (640, 516), 14, GOLD, True)
        self.button('start_level', 'SPACE / START', (290, 540, 330, 66), 'green', 'play')
        self.button('levels', 'LEVELS', (640, 540, 170, 66), 'blue')
        self.button('menu', 'MENU', (826, 540, 170, 66), 'purple')

    def result(self, game, progress):
        level = game.level
        cleared = game.passed
        self.overlay((300, 170, 680, 450))
        self.ribbon('LEVEL CLEARED!' if cleared else 'LEVEL FAILED', (640, 176), 'green' if cleared else 'red')
        self.text(f'{game.score} / {level.required}', (640, 270), 64, GOLD if cleared else RED, True)
        self.stars(game.stars, (640, 342), 18)
        results = '  '.join(str(hit.points) for hit in game.impacts)
        self.text(f'ARROWS: {results}', (640, 392), 16, MUTED, True, max_width=620)
        if not cleared and game.hopeless and game.arrows_left:
            self.text('Not enough arrows left to reach the required score.', (640, 420), 14, PAPER, True)
        y = 460
        if cleared and level.number < len(LEVELS):
            self.button('next_level', 'NEXT LEVEL', (330, y, 220, 66), 'green', 'play')
            self.button('retry_level', 'RETRY', (566, y, 170, 66), 'blue', 'restart')
        elif cleared:
            self.text('CAMPAIGN COMPLETE! YOU ARE THE CHAMPION.', (640, 432), 16, GREEN, True)
            self.button('retry_level', 'RETRY', (330, y, 220, 66), 'blue', 'restart')
        else:
            self.button('retry_level', 'TRY AGAIN', (330, y, 220, 66), 'green', 'restart')
        self.button('levels', 'LEVELS', (752, y, 200, 66), 'purple')
        self.text('SPACE / R retry · N next · L levels · Esc menu', (640, 570), 14, MUTED, True)
        if self.admin is not None and self.admin.active:
            self.text('ADMIN MODE · RESULT NOT SAVED', (640, 150), 16, RED, True)
        if self.mode == 'camera':
            action = 'next level' if cleared and level.number < len(LEVELS) else 'retry'
            self.text(f'Camera: close and open your drawing hand for {action}.', (640, 594), 14, GOLD, True)
