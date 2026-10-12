"""Pixel-art presentation for the menu, character selection and the duel arena.

The arena is the endless parallax campus from ``pixelart/scenery.py``; the camera
follows both archers and every scenery layer scrolls at its own speed.
"""
import math
import pygame

from characters import CHARACTERS, CharacterArtist
from pixelart import ui as pui, scenery
from pixelart.kit import SCALE, INK, Layer, big
from pixelart.painter import Painter

WIDTH, HEIGHT = 1280, 800
BG = pui.BG
PANEL = pui.PANEL
WHITE = (255, 245, 220)
MUTED = (200, 196, 230)
MINT = (110, 225, 140)
GOLD = (255, 210, 64)
COLORS = ((110, 225, 140), (255, 150, 52))
BUTTON_COLORS = ('green', 'orange')
ARENA = pygame.Rect(0, 0, WIDTH, HEIGHT)
GROUND = scenery.Parallax.ground_y(HEIGHT)
NATIVE_PER_METRE = WIDTH / 44 / SCALE      # scenery scroll speed at the default zoom
SCENERY_MODES = ('day', 'night')

# Camera zoom ("dolly") that follows the distance between the archers.
BASE_VIEW = 44.0        # metres visible at zoom 1.0 (the 22 m starting distance)
FRAME_MARGIN = 11.0     # metres of breathing room kept beside each archer
SAFE_MARGIN = 5.0       # hard minimum: nobody may leave the frame
ZOOM_MIN, ZOOM_MAX = .6, 1.35
ZOOM_TIME = .8          # seconds: larger = slower, smoother camera


def camera_zoom(separation):
    """Target zoom for a separation in metres: close archers -> zoom in, far -> zoom out.

    1.0 at the 22 m starting distance; clamped so sprites never get tiny or huge.
    """
    return max(ZOOM_MIN, min(ZOOM_MAX, BASE_VIEW / (abs(separation) + 2 * FRAME_MARGIN)))
MODE_TITLES = {'camera': 'CAMERA DUEL', 'keyboard': 'KEYBOARD DUEL'}


def metadata(character_id):
    return next(c for c in CHARACTERS if c['id'] == character_id)


class DuelRenderer(Painter):
    def __init__(self, screen, background='pixelMakinaG.jpeg', scenery_mode='day'):
        super().__init__(screen)
        self.artist = CharacterArtist()
        self.portraits = {}
        self._rgb = self._preview = None
        self.now = 0
        self.view_center = 20.0
        self.view_width = BASE_VIEW
        self.zoom = 1.0
        self._world_canvas = None
        self._match_clock = None
        self._player_objects = ()
        self._walk = []
        self._health_shown = [100., 100.]
        self._cards = {}
        self._stripes = None
        self.scenery_mode = scenery_mode if scenery_mode in SCENERY_MODES else 'day'

    # ------------------------------------------------------------------ shared bits
    @property
    def parallax(self):
        return scenery.get(self.scenery_mode)

    def toggle_scenery(self):
        self.scenery_mode = 'night' if self.scenery_mode == 'day' else 'day'
        return self.scenery_mode

    def box(self, rect, color=PANEL, radius=16, border=None):
        """Compatibility helper: a pixel panel."""
        return self.panel(rect, color)

    def portrait(self, character, size, facing=1):
        key = character, tuple(size), facing
        if key not in self.portraits:
            self.portraits[key] = self.artist.surface(character, size=size, facing=facing)
        return self.portraits[key]

    def striped_background(self):
        if self._stripes is None:
            L = Layer(WIDTH // SCALE + 1, HEIGHT // SCALE + 1)
            L.rect(0, 0, L.w, L.h, BG)
            for i in range(-L.h, L.w, 18):
                L.line([(i, L.h), (i + L.h, 0)], (52, 42, 88), 8)
            self._stripes = big(L.surf)
            if pygame.display.get_surface():
                self._stripes = self._stripes.convert()
        self.screen.blit(self._stripes, (0, 0))

    def base(self, title, subtitle=''):
        self.buttons = {}
        self.striped_background()
        self.ribbon(title.upper(), (WIDTH // 2, 42), 'orange')
        if subtitle:
            self.text(subtitle, (WIDTH // 2, 84), 16, MUTED, center=True)

    def shadow(self, feet, width=26):
        key = ('shadow', width)
        if key not in self._big:
            L = Layer(width, 5)
            L.ell(0, 0, width, 5, (20, 16, 34, 110))
            self._big[key] = big(L.surf)
        img = self._big[key]
        self.screen.blit(img, img.get_rect(center=(round(feet[0]), round(feet[1]))))

    # ------------------------------------------------------------------ main menu
    def menu(self, error=''):
        self.buttons = {}
        t = pygame.time.get_ticks() / 1000
        cam = t * 7
        self.parallax.draw(self.screen, cam, HEIGHT)
        for character, x, facing in (('ranger', 200, 1), ('akinci', 1080, -1)):
            self.shadow((x, GROUND))
            self.artist.draw(self.screen, character, (x, GROUND), facing, pose='idle', time=t)
        self.parallax.draw(self.screen, cam, HEIGHT, 'front', t)
        self.put(pui.logo(), (WIDTH // 2, 14), anchor='midtop', key='logo')
        self.button('duel_camera', 'CAMERA DUEL', (446, 292, 388, 72), 'green', 'camera')
        self.button('duel_keyboard', 'KEYBOARD DUEL', (446, 376, 388, 66), 'orange', 'keys')
        self.text('SOLO PRACTICE', (WIDTH // 2, 462), 16, WHITE, center=True)
        self.button('camera', 'CAMERA', (446, 480, 190, 60), 'blue', 'target')
        self.button('mouse', 'MOUSE', (644, 480, 190, 60), 'purple', 'mouse')
        self.text('CAMPAIGN · 10 LEVELS', (WIDTH // 2, 562), 16, WHITE, center=True)
        self.button('campaign_camera', 'CAMERA', (446, 580, 190, 60), 'orange', 'trophy')
        self.button('campaign_mouse', 'MOUSE', (644, 580, 190, 60), 'teal', 'trophy')
        self.icon_button('quit', 'quit', (WIDTH - 44, 44), 'red')
        admin = getattr(self, 'admin_active', False)
        self.icon_button('admin', 'gear', (WIDTH - 108, 44), 'green' if admin else 'grey')
        self.text('ADMIN ON' if admin else 'ADMIN', (WIDTH - 108, 84), 14, WHITE, center=True)
        self.icon_button('toggle_scenery', 'moon' if self.scenery_mode == 'day' else 'sun', (44, 44), 'teal')
        self.text('NIGHT' if self.scenery_mode == 'day' else 'DAY', (44, 84), 14, WHITE, center=True)
        if error:
            self.panel((40, 700, 1200, 60), (150, 50, 60))
            self.text(str(error)[:96], (WIDTH // 2, 730), 16, WHITE, center=True, max_width=1160)
        else:
            self.text('Camera: show both shoulders and hands for each player.',
                      (WIDTH // 2, 772), 14, WHITE, center=True)

    # ------------------------------------------------------------------ character select
    def card_image(self, cid, state):
        key = cid, state
        if key not in self._cards:
            sprite = self.artist.native(cid, pose='idle')
            face = sprite.subsurface(pygame.Rect(0, 6, 60, 36)).copy()
            meta = metadata(cid)
            name = meta['name'].split()[-1] if len(meta['name']) > 8 else meta['name']
            self._cards[key] = big(pui.card(face, name, meta['color'], state, w=56, h=44))
        return self._cards[key]

    def draw_selection(self, selected, ready, mode):
        self.buttons = {}
        t = pygame.time.get_ticks() / 1000
        self.striped_background()
        self.ribbon('CHOOSE YOUR ARCHERS', (WIDTH // 2, 42), 'orange', 190)
        for player in range(2):
            px = 24 if player == 0 else 656
            color = COLORS[player]
            self.panel((px, 96, 600, 612))
            self.text(f'PLAYER {player + 1}', (px + 30, 116), 24, color)
            if mode == 'camera':
                hint = 'START ON THE LEFT' if player == 0 else 'START ON THE RIGHT'
            else:
                hint = 'A / D  +  F' if player == 0 else '← / →  +  ENTER'
            self.text(hint, (px + 570, 120), 16, MUTED, anchor='topright', bold=False)
            self.panel((px + 30, 150, 540, 168), pui.PANEL_DARK, inset=True)
            cid = selected[player]
            meta = metadata(cid)
            facing = 1 if player == 0 else -1
            feet_x = px + 130 if player == 0 else px + 470
            self.shadow((feet_x, 302), 20)
            sway = math.sin(t * 1.7 + player)
            self.artist.draw(self.screen, cid, (feet_x, 300), facing, 22 + 14 * sway,
                             .55 + .35 * math.sin(t * 2.3 + player), scale=2/3, time=t)
            tx = px + 300 if player == 0 else px + 50
            self.text(meta['name'], (tx, 170), 24, meta['color'], max_width=250)
            self.text(meta['title'], (tx, 208), 16, MUTED, bold=False, max_width=250)
            if ready[player]:
                self.put(pui.stamp('READY!', 'green'), (tx, 240), key='stamp_ready')
            else:
                self.paragraph(meta['tagline'], (tx, 238), 250, 16, WHITE)
            for i, character in enumerate(CHARACTERS):
                rect = pygame.Rect(px + 30 + (i % 3) * 183, 330 + (i // 3) * 150, 174, 144)
                hover = rect.collidepoint(pygame.mouse.get_pos())
                state = 'selected' if character['id'] == cid else ('hover' if hover else 'normal')
                self.screen.blit(self.card_image(character['id'], state), rect)
                self.buttons[f'pick_{player}_{character["id"]}'] = rect
            self.button(f'ready_{player}',
                        f'{meta["name"]} READY · CHANGE' if ready[player] else f'READY AS {meta["name"]}',
                        (px + 30, 632, 540, 66), BUTTON_COLORS[player] if not ready[player] else 'teal',
                        'hand', selected=ready[player])
        self.put(pui.vs_badge(48), (WIDTH // 2, 230), anchor='center', key='vs')
        self.icon_button('menu', 'back', (64, 756), 'blue')
        label = 'CAMERA SETUP' if mode == 'camera' else 'START DUEL'
        self.button('begin_duel', f'CONFIRM BOTH · {label}', (390, 722, 500, 70), 'green', 'play')
        both = all(ready)
        self.text('BOTH READY · SPACE' if both else 'READY UP, OR CONFIRM BOTH',
                  (1236, 748), 16, MINT if both else MUTED, anchor='topright', bold=both)

    def selection(self, selected, mode):
        self.draw_selection(selected, (False, False), mode)

    # ------------------------------------------------------------------ arena
    @property
    def render_zoom(self):
        """Zoom applied to the whole world image (sprites and scenery scale with it)."""
        return max(ZOOM_MIN, min(ZOOM_MAX, BASE_VIEW/self.view_width))

    def world_size(self):
        z = self.render_zoom
        return math.ceil(WIDTH/z), math.ceil(HEIGHT/z)

    def world_project(self, x, y):
        """Metres -> pixels on the unscaled world canvas (3x art pixels, 65 px per metre up)."""
        w, h = self.world_size()
        return (w/2 + (x-self.view_center)*w/self.view_width,
                h-(HEIGHT-GROUND)-y*65)

    def project(self, x, y):
        """Metres -> screen pixels after the camera zoom."""
        w, h = self.world_size()
        wx, wy = self.world_project(x, y)
        return wx*WIDTH/w, wy*HEIGHT/h

    def _world(self):
        if self._world_canvas is None:
            big_size = (math.ceil(WIDTH/ZOOM_MIN)+2, math.ceil(HEIGHT/ZOOM_MIN)+2)
            self._world_canvas = pygame.Surface(big_size)
            if pygame.display.get_surface():
                self._world_canvas = self._world_canvas.convert()
        return self._world_canvas.subsurface((0, 0) + self.world_size())

    def _update_view(self, match):
        players = tuple(match.players)
        reset = (len(self._player_objects) != len(players)
                 or any(old is not new for old, new in zip(self._player_objects, players))
                 or self._match_clock is None or match.time < self._match_clock)
        dt = 0.0 if reset else max(0., min(.15, match.time-self._match_clock))
        if reset:
            self._player_objects = players
            self._walk = [dict(x=p.x, phase=0., amount=0., direction=p.facing) for p in players]
            self._health_shown = [float(p.health) for p in players]
            left, right = min(p.x for p in players), max(p.x for p in players)
            self.view_center = (left+right)/2
            self.zoom = camera_zoom(right-left)
            self.view_width = max(BASE_VIEW/self.zoom, (right-left+2*SAFE_MARGIN)/(1-200/WIDTH))
        self._match_clock = match.time
        self.now = match.time
        left, right = min(p.x for p in players), max(p.x for p in players)
        weight = 1-math.exp(-dt/.3)
        # The camera eases toward the zoom that suits the current distance.
        self.zoom += (1-math.exp(-dt/ZOOM_TIME))*(camera_zoom(right-left)-self.zoom)
        # Safety first: widen at once if someone would otherwise leave the frame.
        self.view_width = max(BASE_VIEW/self.zoom, (right-left+2*SAFE_MARGIN)/(1-200/WIDTH))
        half = self.view_width/2
        center = (left+right)/2
        self.view_center += weight*(center-self.view_center)
        # Safe framing takes precedence over easing when movement is sudden.
        margin = max(4., self.view_width*100/ARENA.width)
        self.view_center = max(right+margin-half, min(left-margin+half, self.view_center))
        for p, walk in zip(players, self._walk):
            dx = p.x-walk['x']
            walk['x'] = p.x
            if dt <= 0:
                continue
            speed = abs(dx)/dt
            target = min(1., speed/3.0) if speed > .10 else 0.
            walk['amount'] += (1-math.exp(-dt/.075))*(target-walk['amount'])
            if abs(dx) > .001:
                walk['direction'] = 1 if dx > 0 else -1
                walk['phase'] = (walk['phase'] + abs(dx)*math.tau/2.4) % math.tau
        for i, p in enumerate(players):
            shown = self._health_shown[i]
            self._health_shown[i] = p.health if p.health > shown else shown + (p.health-shown)*(1-math.exp(-dt/.45))

    def _scenery(self, part='back'):
        sky = (math.ceil(WIDTH/ZOOM_MIN)+2, math.ceil(HEIGHT/ZOOM_MIN)+2)
        self.parallax.draw(self.screen, self.view_center*NATIVE_PER_METRE, self.screen.get_height(),
                           part, self.now, sky)

    def _arrow(self, arrow):
        x, y = self.world_project(arrow.x, arrow.y)
        vx, vy = arrow.vx*self.world_size()[0]/self.view_width, arrow.vy*65
        angle = math.degrees(math.atan2(vy, vx)) if vx*vx + vy*vy > 1e-9 else 90.
        q = round(angle / 5) * 5
        color = COLORS[arrow.owner]
        native = pui.arrow_sprite(q, color)
        img = self.scaled(native, key=('arrow', q, color))
        r = math.radians(q)
        # The native sprite's tip is 14 art pixels ahead of its centre.
        cx, cy = x - math.cos(r)*14*SCALE, y + math.sin(r)*14*SCALE
        self.screen.blit(img, img.get_rect(center=(round(cx), round(cy))))

    def arena(self, match):
        self._update_view(match)
        screen, world = self.screen, self._world()
        self.screen = world          # draw the world unscaled, then zoom it onto the screen
        try:
            self._scenery('back')
            px_per_m = world.get_width()/self.view_width
            for i, p in enumerate(match.players):
                feet = self.world_project(p.x, 0)
                self.shadow(feet)
                radians = math.radians(p.angle)
                visible_angle = math.degrees(math.atan2(65*math.sin(radians), px_per_m*math.cos(radians)))
                walk = self._walk[i]
                self.artist.draw(world, p.character, feet=feet, facing=p.facing,
                                 angle=visible_angle, strength=p.strength, scale=1,
                                 firing=not p.drawing, time=self.now,
                                 walk_phase=walk['phase'], walk_amount=walk['amount'],
                                 move_direction=walk['direction'])
                if p.drawing:
                    for n, position in enumerate(match.prediction(i, duration=1.3, spacing=.12)):
                        sx, sy = self.world_project(*position)
                        size = 6 if n % 2 == 0 else 3
                        pygame.draw.rect(world, INK[:3], (round(sx)-size//2-3, round(sy)-size//2-3, size+6, size+6))
                        pygame.draw.rect(world, COLORS[i], (round(sx)-size//2, round(sy)-size//2, size, size))
            for arrow in match.arrows:
                for n, point in enumerate(arrow.trail[-24:-1]):
                    if n % 2 == 0:
                        tx, ty = self.world_project(*point)
                        pygame.draw.rect(world, (255, 250, 235), (round(tx)-2, round(ty)-2, 4, 4))
                self._arrow(arrow)
            for impact in match.impacts:
                age = match.time - impact['time']
                if age < .9:
                    x, y = self.world_project(*impact['position'])
                    color = COLORS[impact['owner']]
                    radius = 3 + int(age*12)
                    ring = self.scaled(pui.ring(radius, color, 1), key=('ring', radius, color))
                    world.blit(ring, ring.get_rect(center=(round(x), round(y))))
            self._scenery('front')
        finally:
            self.screen = screen
        pygame.transform.scale(world, (WIDTH, HEIGHT), screen)
        # Labels stay readable at every zoom, so they are drawn in screen space.
        z = HEIGHT/world.get_height()
        for i, p in enumerate(match.players):
            fx, fy = self.project(p.x, 0)
            self.text(f'P{i+1}', (fx, fy-250*z), 16, COLORS[i], center=True)
        for arrow in match.arrows:
            sx, sy = self.project(arrow.x, arrow.y)
            if sy < 0:
                ix = max(80, min(WIDTH-80, sx))
                color = COLORS[arrow.owner]
                pygame.draw.polygon(screen, INK[:3], [(ix, 222), (ix-12, 244), (ix+12, 244)])
                pygame.draw.polygon(screen, color, [(ix, 228), (ix-7, 241), (ix+7, 241)])
                self.text(f'P{arrow.owner+1} {arrow.y:.0f}M', (ix, 262), 14, color, center=True)
        for impact in match.impacts:
            age = match.time - impact['time']
            if age < .9 and impact['damage']:
                x, y = self.project(*impact['position'])
                self.text(f'-{impact["damage"]}', (x, y-40-age*40), 28, GOLD, center=True)

    # ------------------------------------------------------------------ HUD
    def player_panel(self, player, number, mode):
        meta = metadata(player.character)
        color = COLORS[number]
        shown = self._health_shown[number] if number < len(self._health_shown) else player.health
        frac = max(0., player.health/100)
        lost = max(0., shown-player.health)/100
        bar = pui.health_bar(150, frac, color, lost, flip_it=number == 1)
        if number == 0:
            self.text(f'P1 {meta["name"]}', (24, 12), 24, color)
            self.put(bar, (20, 46))
            self.text(f'{player.health:.0f} HP', (24, 94), 16, WHITE)
        else:
            self.text(f'{meta["name"]} P2', (WIDTH-24, 12), 24, color, anchor='topright')
            self.put(bar, (WIDTH-20, 46), anchor='topright')
            self.text(f'{player.health:.0f} HP', (WIDTH-24, 94), 16, WHITE, anchor='topright')
        # Pull meter and aim just under the archer's feet.
        feet = self.project(player.x, 0)
        meter = self.put(pui.pull_meter(40, player.strength), (feet[0]-24, feet[1]+14), anchor='midtop')
        self.text(f'{player.angle:+.0f}°', (meter.right+8, meter.top-3), 16, WHITE, bold=False)
        if mode == 'camera':
            state = player.status
        else:
            state = 'DRAWING' if player.drawing else ('Hold F to draw' if number == 0 else 'Hold Enter to draw')
        anchor = 'bottomleft' if number == 0 else 'bottomright'
        self.text(str(state)[:48], (16 if number == 0 else WIDTH-16, HEIGHT-10), 14, WHITE,
                  anchor=anchor, bold=False)

    def camera(self, rgb):
        if rgb is not None:
            if rgb is not self._rgb:
                self._rgb = rgb
                h, w = rgb.shape[:2]
                source = pygame.image.frombuffer(rgb.tobytes(), (w, h), 'RGB')
                self._preview = pygame.transform.smoothscale(source, (210, 156))
            self.panel((526, 222, 228, 204), pui.PANEL_DARK)
            self.screen.blit(self._preview, (535, 256))
            self.text('P1 LEFT · P2 RIGHT', (640, 230), 14, MINT, center=False, anchor='midtop', bold=False)

    def play(self, match, mode, rgb=None, calibrating=False, tracking_message=''):
        self.buttons = {}
        self.arena(match)
        self.ribbon(MODE_TITLES.get(mode, 'DUEL'), (WIDTH // 2, 36), 'purple')
        self.text(f'{match.separation:.1f} M APART', (WIDTH // 2, 74), 16, WHITE, center=False, anchor='midtop')
        self.text('R RESTART · C RECALIBRATE · ESC MENU' if mode == 'camera' else 'R RESTART · ESC MENU',
                  (WIDTH // 2, 102), 14, MUTED, anchor='midtop', bold=False)
        self.icon_button('menu', 'home', (WIDTH // 2 + 36, 160), 'blue')
        for i, player in enumerate(match.players):
            self.player_panel(player, i, mode)
        if match.winner is None and not calibrating:
            self.text(str(match.status)[:70], (WIDTH // 2, 200), 16, GOLD, anchor='midtop')
        if calibrating:
            self.shade_screen(90)
            self.panel((170, 456, 940, 306))
            title, instruction = match.calibration_instructions[min(match.calibration_step, 2)]
            self.ribbon(title, (WIDTH // 2, 460), 'orange')
            y = self.paragraph(instruction, (WIDTH // 2, 502), 860, 18, WHITE, center=True)
            y = self.paragraph(str(match.calibration_message), (WIDTH // 2, y+8), 860, 16, GOLD, center=True)
            self.paragraph(str(tracking_message)[:110], (WIDTH // 2, y+6), 860, 14, MUTED, center=True)
            self.button('duel_capture', 'SPACE · RECORD POSITION', (390, 672, 500, 70), 'green', 'camera')
        elif match.winner is not None:
            self.shade_screen(160)
            self.panel((340, 210, 600, 420))
            caption = 'DOUBLE KNOCKOUT' if match.winner == 'draw' else f'PLAYER {match.winner+1} WINS!'
            self.ribbon(caption, (WIDTH // 2, 214), 'red' if match.winner == 'draw' else 'green')
            winners = range(len(match.players)) if match.winner == 'draw' else (match.winner,)
            xs = (540, 740) if match.winner == 'draw' else (640,)
            for x, index in zip(xs, winners):
                p = match.players[index]
                self.shadow((x, 470), 30)
                self.artist.draw(self.screen, p.character, (x, 470), 1 if index == 0 else -1,
                                 pose='idle', time=pygame.time.get_ticks()/1000)
            self.text('Good shot. Ready for a rematch?', (WIDTH // 2, 500), 16, MUTED, anchor='midtop', bold=False)
            self.button('duel_again', 'REMATCH', (380, 540, 252, 70), 'green', 'restart')
            self.button('menu', 'MENU', (648, 540, 252, 70), 'blue', 'home')
        if mode == 'camera' and match.winner is None:
            self.camera(rgb)
