"""Archidon entry point: one window and one loop for the official game.

Run from anywhere: ../.venv/bin/python main.py
Use --mouse to practice without MediaPipe or a webcam.
"""
import argparse
import os
from pathlib import Path
from game_mechanics import GameRound, STATE_MENU, STATE_PLAY, STATE_CALIBRATE, STATE_FINISH
from physics import clamp_elevation
from tracking_clock import monotonic_seconds
from viewport import WorldCamera

FPS = 60
DUEL_SELECT, DUEL_CALIBRATE, DUEL_PLAY, DUEL_FINISH = (
    'DUEL_SELECT', 'DUEL_CALIBRATE', 'DUEL_PLAY', 'DUEL_FINISH')
DUEL_STATES = (DUEL_SELECT, DUEL_CALIBRATE, DUEL_PLAY, DUEL_FINISH)
CAMPAIGN_SELECT = 'CAMPAIGN_SELECT'
ADMIN_LOGIN, ADMIN_PANEL = 'ADMIN_LOGIN', 'ADMIN_PANEL'
ADMIN_STATES = (ADMIN_LOGIN, ADMIN_PANEL)
ADMIN_TOGGLES = ('unlock_all', 'infinite_arrows', 'full_preview', 'no_wind', 'still_target',
                 'show_hitboxes', 'target_scale')
LEVEL_KEYS = '1234567890'


def load_ui():
    # A spawned camera process imports this entry module too. Delay the GUI
    # imports so that child never loads Pygame's copy of SDL alongside OpenCV.
    global pygame, Renderer, DuelRenderer, CharacterSelection, CampaignRenderer, WIDTH, HEIGHT, FIELD
    import pygame
    from renderer import Renderer, WIDTH, HEIGHT, FIELD
    from campaign_renderer import CampaignRenderer
    from duel_renderer import DuelRenderer
    from character_selection import CharacterSelection


class Archidon:
    GESTURE_PAUSE = 1.5     # s before a gesture on the result screen counts
    def __init__(self, screen, background='pixelMakinaG.jpeg', camera_index=0, scenery='day',
                 progress_path=None, admin_path=None):
        load_ui()
        from campaign import CampaignProgress, PROGRESS_FILE
        from admin import Admin, CONFIG_FILE
        self.admin = Admin(CONFIG_FILE if admin_path is None else admin_path)
        self.admin_input = ''
        self.admin_message = ''
        self.admin_stage = 'login'      # login | new | confirm
        self.admin_new = ''
        self.admin_reset_armed = False
        self.renderer = Renderer(screen, background, scenery)
        self.campaign_renderer = CampaignRenderer(screen, background, scenery)
        self.progress = CampaignProgress(PROGRESS_FILE if progress_path is None else progress_path)
        self.campaign = False          # True while a campaign level is open
        self.campaign_mode = 'mouse'
        self.briefing = False
        self._recorded = False
        self.finish_time = 0.0
        self.duel_renderer = DuelRenderer(screen, background, scenery)
        self.character_selection = CharacterSelection()
        self.duel = self.duel_camera = None
        self.duel_mode = 'camera'
        self.characters = ['ranger', 'storm']
        self.duel_observations = [None, None]
        self.game = GameRound()
        self.world_camera = WorldCamera()
        self.camera_index = camera_index
        self.state = STATE_MENU
        self.mode = 'mouse'
        self.controller = self.camera = None
        self.measurement = self.camera_rgb = None
        self.tracking_message = ''
        self.error = ''
        self.strength = 0.75
        self.angle = 24.0
        self.drag_start = None
        self.drag_angle = 24.0
        self.running = True

    def start_mouse(self):
        self.close_camera()
        self.renderer.character = self.characters[0]
        self.campaign = self.briefing = False
        self.game = GameRound()
        self.mode = 'mouse'
        self.game.reset()
        self.world_camera.reset()
        self.state = STATE_PLAY
        self.strength, self.angle = 0.75, 24.0
        self.drag_start = None
        self.error = ''

    def start_camera(self, keep_game=False):
        self.close_camera()
        self.renderer.character = self.characters[0]
        if not keep_game:
            self.campaign = self.briefing = False
            self.game = GameRound()
        self.error = ''
        try:
            # Mouse mode can run without importing any vision dependencies.
            from controls import InputController
            from camera import CameraSession
            self.controller = InputController(self.shoot)
            self.camera = CameraSession(self.controller, self.camera_index)
        except Exception as exc:
            self.close_camera()
            print(f'Camera setup: {exc}')
            self.error = 'Camera unavailable. Check permission and models, or choose mouse practice.'
            self.state = STATE_MENU
            return
        self.mode = 'camera'
        if not keep_game:
            self.game.reset()
        self.world_camera.reset()
        self.state = STATE_CALIBRATE
        self.strength = self.angle = 0.0
        self.drag_start = None

    def close_camera(self):
        if self.camera is not None:
            self.camera.close()
        self.camera = self.controller = None
        self.measurement = self.camera_rgb = None
        if self.duel_camera is not None:
            self.duel_camera.close()
        self.duel_camera = None
        self.duel_observations = [None, None]

    # ------------------------------------------------------------------ campaign
    @property
    def view(self):
        return self.campaign_renderer if self.campaign or self.state == CAMPAIGN_SELECT else self.renderer

    def open_campaign(self, mode=None):
        """Level select. The webcam stays open (and calibrated) between levels."""
        if mode is not None and mode != self.campaign_mode:
            self.close_camera()
            self.campaign_mode = mode
        if self.campaign_mode != 'camera':
            self.close_camera()
        self.campaign = self.briefing = False
        self.drag_start = None
        self.world_camera.reset()
        if self.controller:
            self.controller.cancel_draw()
        self.error = ''
        self.state = CAMPAIGN_SELECT

    def start_level(self, number, seed=None, force=False):
        from campaign import CampaignRound
        from levels import LEVELS
        if not 1 <= number <= len(LEVELS):
            return False
        if not (self.progress.is_unlocked(number) or (self.admin.active and force)):
            return False
        self.campaign_renderer.character = self.characters[0]
        self.campaign_renderer.scenery_mode = self.renderer.scenery_mode
        level = self.admin.options.apply(LEVELS[number - 1]) if self.admin.active else LEVELS[number - 1]
        self.game = CampaignRound(level, seed)
        self.campaign = self.briefing = True
        self._recorded = False
        self.world_camera.reset()
        self.drag_start = None
        if self.campaign_mode == 'camera':
            if self.controller is None:
                self.start_camera(keep_game=True)
                if self.controller is None:      # camera failed; error shown in the menu
                    self.campaign = self.briefing = False
                    return False
                return True
            self.controller.reset()
            self.mode = 'camera'
            self.strength = self.angle = 0.0
        else:
            self.mode = 'mouse'
            self.strength, self.angle = 0.75, 24.0
        self.state = STATE_PLAY
        return True

    def begin_level(self):
        self.briefing = False
        if self.controller:
            # A hand already closed during the briefing must not fire at once.
            self.controller.cancel_draw()

    def gesture_command(self):
        """Camera players stand away from the keyboard: a draw-and-release
        starts the level from the briefing, and on the result screen (after a
        short pause) continues to the next level or retries."""
        if self.state == STATE_PLAY and self.briefing:
            self.begin_level()
            return True
        if self.state == STATE_FINISH:
            if monotonic_seconds() - self.finish_time >= self.GESTURE_PAUSE:
                self.next_level() if self.game.passed and self.game.level.number < 10 else self.retry_level()
            return True
        return False

    def retry_level(self):
        if self.campaign:
            self.start_level(self.game.level.number)

    def next_level(self):
        if self.campaign and self.game.passed:
            self.start_level(self.game.level.number + 1, force=True)

    def campaign_key(self, key):
        """Keyboard shortcuts while a campaign level, briefing or result is open."""
        if self.state == STATE_PLAY and self.briefing and key in (pygame.K_SPACE, pygame.K_RETURN):
            self.begin_level()
        elif self.state == STATE_FINISH and key in (pygame.K_SPACE, pygame.K_r, pygame.K_RETURN):
            if key == pygame.K_RETURN and self.game.passed:
                self.next_level()
            else:
                self.retry_level()
        elif self.state == STATE_FINISH and key == pygame.K_n:
            self.next_level()
        elif key == pygame.K_l:
            self.open_campaign()
        elif key == pygame.K_f and self.admin.active and self.state == STATE_PLAY and not self.briefing:
            self.game.force_finish()
        elif key == pygame.K_r and self.state == STATE_PLAY:
            self.retry_level()
        else:
            return False
        return True

    # ------------------------------------------------------------------ admin
    def open_admin(self):
        self.close_camera()
        self.campaign = self.briefing = False
        self.admin_input = self.admin_new = ''
        self.admin_reset_armed = False
        if self.admin.active:
            self.admin_message = ''
            self.state = ADMIN_PANEL
        else:
            self.admin_stage = 'login'
            self.admin_message = ''
            self.state = ADMIN_LOGIN

    def sync_admin(self):
        self.progress.unlock_all = self.admin.active and self.admin.options.unlock_all

    def submit_admin(self):
        text, self.admin_input = self.admin_input, ''
        if self.admin_stage == 'login':
            ok, self.admin_message = self.admin.login(text)
            if ok:
                self.sync_admin()
                self.state = ADMIN_PANEL
        elif self.admin_stage == 'new':
            if len(text) < 4:
                self.admin_message = 'Use at least 4 characters.'
                return
            self.admin_new = text
            self.admin_stage = 'confirm'
            self.admin_message = 'Type the new password again.'
        elif self.admin_stage == 'confirm':
            if text != self.admin_new:
                self.admin_stage = 'new'
                self.admin_message = 'The passwords did not match. Type a new password.'
            else:
                ok, self.admin_message = self.admin.set_password(text)
                self.admin_stage = 'login'
                self.state = ADMIN_PANEL
            self.admin_new = '' if self.admin_stage != 'confirm' else self.admin_new

    def admin_action(self, name):
        if name == 'admin':
            self.open_admin()
        elif not self.admin.active:
            return
        elif name.startswith('adm_toggle_'):
            self.admin.toggle(name[len('adm_toggle_'):])
            self.sync_admin()
        elif name == 'adm_levels':
            self.open_campaign('mouse')
        elif name == 'adm_levels_camera':
            self.open_campaign('camera')
        elif name == 'adm_reset':
            if self.admin_reset_armed:
                self.progress.unlocked, self.progress.best, self.progress.stars = 1, {}, {}
                self.progress.save()
                self.admin_message = 'Campaign progress reset.'
                self.admin_reset_armed = False
            else:
                self.admin_reset_armed = True
                self.admin_message = 'Press RESET PROGRESS again to confirm.'
        elif name == 'adm_password':
            self.admin_stage = 'new'
            self.admin_input = ''
            self.admin_message = 'Type a new password (at least 4 characters).'
            self.state = ADMIN_LOGIN
        elif name == 'adm_lock':
            self.admin.logout()
            self.sync_admin()
            self.menu()

    def admin_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.state == ADMIN_LOGIN and self.admin.active:
                    self.admin_stage = 'login'
                    self.state = ADMIN_PANEL
                else:
                    self.menu()
            elif self.state == ADMIN_LOGIN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.submit_admin()
                elif event.key == pygame.K_BACKSPACE:
                    self.admin_input = self.admin_input[:-1]
                elif event.unicode and event.unicode.isprintable() and len(self.admin_input) < 32:
                    self.admin_input += event.unicode
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clicked = next((name for name, rect in self.campaign_renderer.buttons.items()
                            if rect.collidepoint(event.pos)), None)
            if clicked == 'menu':
                self.menu()
            elif clicked == 'adm_submit':
                self.submit_admin()
            elif clicked:
                self.admin_action(clicked)

    def select_duel(self, mode='camera'):
        self.close_camera()
        self.duel_mode = mode
        self.error = ''
        self.character_selection.reset()
        self.state = DUEL_SELECT

    def begin_duel(self):
        from duel import DuelMatch
        self.close_camera()
        self.duel = DuelMatch(tuple(self.characters), keyboard=self.duel_mode == 'keyboard')
        self.tracking_message = ''
        if self.duel_mode == 'camera':
            try:
                from duel_camera import DuelSession
                self.duel_camera = DuelSession(camera_index=self.camera_index)
            except Exception as exc:
                self.menu()
                self.error = f'Camera duel unavailable: {exc}'
                return
            self.state = DUEL_CALIBRATE
        else:
            self.state = DUEL_PLAY

    def restart_duel(self, recalibrate=False):
        self.duel.reset(recalibrate=recalibrate and self.duel_mode == 'camera')
        self.state = DUEL_PLAY if self.duel.ready else DUEL_CALIBRATE

    def menu(self):
        self.close_camera()
        self.campaign = self.briefing = False
        self.drag_start = None
        self.world_camera.reset()
        self.state = STATE_MENU

    def restart(self, recalibrate=False):
        self.game.reset()
        self.world_camera.reset()
        self.drag_start = None
        if self.controller:
            self.controller.reset(recalibrate)
            self.strength = self.angle = 0.0
            self.state = STATE_CALIBRATE if recalibrate else STATE_PLAY
        else:
            self.strength, self.angle = 0.75, 24.0
            self.state = STATE_PLAY

    def action(self, name):
        if name.startswith('pick_'):
            _, player, character = name.split('_', 2)
            self.character_selection.choose(self.characters, int(player), character)
        elif name.startswith('ready_') and self.state == DUEL_SELECT:
            player = int(name.rsplit('_', 1)[1])
            self.character_selection.ready[player] = not self.character_selection.ready[player]
        elif name == 'duel_camera':
            self.select_duel('camera')
        elif name == 'duel_keyboard':
            self.select_duel('keyboard')
        elif name == 'begin_duel':
            self.character_selection.ready[:] = [True, True]
            self.begin_duel()
        elif name == 'duel_characters':
            self.select_duel(self.duel_mode)
        elif name == 'duel_capture' and self.duel:
            self.duel.request_capture()
        elif name == 'duel_again' and self.duel:
            self.restart_duel()
        elif name == 'camera':
            self.start_camera()
        elif name == 'mouse':
            self.start_mouse()
        elif name == 'admin' or name.startswith('adm_'):
            self.admin_action(name)
        elif name in ('campaign_camera', 'campaign_mouse'):
            self.open_campaign(name.split('_')[1])
        elif name.startswith('level_'):
            self.start_level(int(name.split('_')[1]))
        elif name == 'start_level':
            self.begin_level()
        elif name == 'retry_level':
            self.retry_level()
        elif name == 'next_level':
            self.next_level()
        elif name == 'levels':
            self.open_campaign()
        elif name == 'quit':
            self.running = False
        elif name == 'toggle_scenery':
            # Day / night campus, shared by the duel and practice screens.
            self.renderer.scenery_mode = self.duel_renderer.toggle_scenery()
            self.campaign_renderer.scenery_mode = self.renderer.scenery_mode
        elif name == 'capture' and self.controller:
            self.controller.calibration.start_capture()
        elif name == 'again':
            self.restart()
        elif name == 'menu':
            self.menu()

    def shoot(self, strength, angle):
        """All mouse, keyboard and gesture releases use the same readiness gate."""
        if self.campaign and self.mode == 'camera' and self.gesture_command():
            return False
        if self.state != STATE_PLAY or not self.world_camera.can_shoot or self.briefing:
            return False
        if not self.game.shoot(strength, angle):
            return False
        self.strength = self.game.arrow.strength
        self.angle = self.game.arrow.shot.angle
        self.drag_start = None
        self.world_camera.update(0, self.game.arrow)
        if self.controller:
            self.controller.arrow = self.game.arrow
        return True

    def events(self):
        for event in pygame.event.get():
            if self.state in DUEL_STATES or self.state == STATE_MENU:
                self.duel_event(event)
                continue
            if self.state == CAMPAIGN_SELECT:
                self.select_event(event)
                continue
            if self.state in ADMIN_STATES:
                self.admin_event(event)
                continue
            if (event.type == pygame.KEYDOWN and self.campaign and self.state != STATE_CALIBRATE
                    and self.campaign_key(event.key)):
                continue
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    self.running = False
                elif event.key == pygame.K_ESCAPE:
                    self.menu()
                elif event.key == pygame.K_r and self.state in (STATE_PLAY, STATE_FINISH):
                    self.restart()
                elif event.key == pygame.K_c and self.controller:
                    self.restart(recalibrate=True)
                elif event.key == pygame.K_h and self.controller:
                    self.controller.drawing_hand = 'Left' if self.controller.drawing_hand == 'Right' else 'Right'
                    self.restart(recalibrate=True)
                elif event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
                    self.nudge(event.key)
                elif event.key == pygame.K_SPACE:
                    if self.state == STATE_CALIBRATE:
                        self.controller.calibration.start_capture()
                    elif self.state == STATE_PLAY:
                        if self.mode == 'mouse':
                            self.shoot(self.strength, self.angle)
                        elif (self.measurement is not None and self.controller.controls_clear
                              and 0 <= int(monotonic_seconds()*1000) - self.measurement['stamp'] <= 250):
                            # A manual release uses the held shot when there is an active draw.
                            held = self.controller.last_draw or (self.strength, self.angle)
                            self.controller.shoot(*held)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked = next((name for name, rect in self.view.buttons.items()
                                if rect.collidepoint(event.pos)), None)
                if clicked:
                    self.action(clicked)
                elif self.state == STATE_PLAY and self.mode == 'mouse' and FIELD.collidepoint(event.pos):
                    if self.game.arrow is None and self.world_camera.can_shoot and not self.briefing:
                        self.drag_start = event.pos
                        self.drag_angle = self.angle
                        self.strength = 0.0
            elif event.type == pygame.MOUSEMOTION and self.drag_start:
                self.update_mouse(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag_start:
                self.update_mouse(event.pos)
                self.drag_start = None
                self.shoot(self.strength, self.angle)
            elif event.type == pygame.WINDOWFOCUSLOST:
                self.drag_start = None
                if self.controller:
                    self.controller.cancel_draw()

    def select_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                self.running = False
            elif event.key == pygame.K_ESCAPE:
                self.menu()
            elif event.unicode and event.unicode in LEVEL_KEYS:
                self.start_level(LEVEL_KEYS.index(event.unicode) + 1)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clicked = next((name for name, rect in self.campaign_renderer.buttons.items()
                            if rect.collidepoint(event.pos)), None)
            if clicked:
                self.action(clicked)

    def nudge(self, key):
        """Mouse mode fine-tuning for long range: Up/Down change the angle by
        0.1° and Left/Right the pull by 0.2 %; hold Shift for 1° / 2 % steps."""
        if self.mode != 'mouse' or self.state != STATE_PLAY or self.drag_start:
            return
        coarse = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
        if key in (pygame.K_UP, pygame.K_DOWN):
            step = 1.0 if coarse else 0.1
            self.angle = clamp_elevation(round(self.angle + (step if key == pygame.K_UP else -step), 2))
        else:
            step = 0.02 if coarse else 0.002
            self.strength = max(0.0, min(1.0, round(self.strength + (step if key == pygame.K_RIGHT else -step), 4)))

    def duel_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                self.running = False
            elif event.key == pygame.K_ESCAPE:
                self.menu()
            elif self.state == DUEL_SELECT:
                if self.character_selection.key(event.key, self.characters):
                    self.begin_duel()
            elif event.key == pygame.K_TAB and self.state in (DUEL_PLAY, DUEL_CALIBRATE, DUEL_FINISH):
                self.select_duel(self.duel_mode)
            elif event.key == pygame.K_SPACE and self.state == DUEL_CALIBRATE:
                self.duel.request_capture()
            elif event.key == pygame.K_r and self.state in (DUEL_PLAY, DUEL_FINISH):
                self.restart_duel()
            elif event.key == pygame.K_c and self.duel_mode == 'camera' and self.state in (DUEL_PLAY, DUEL_CALIBRATE, DUEL_FINISH):
                self.restart_duel(recalibrate=True)
        elif event.type == pygame.KEYUP and self.state == DUEL_PLAY and self.duel_mode == 'keyboard':
            if event.key in (pygame.K_f, pygame.K_RETURN):
                self.duel.keyboard(0 if event.key == pygame.K_f else 1, release=True)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            clicked = next((name for name, rect in self.duel_renderer.buttons.items()
                            if rect.collidepoint(event.pos)), None)
            if clicked:
                self.action(clicked)
        elif event.type == pygame.WINDOWFOCUSLOST and self.duel:
            for player in self.duel.players:
                player.drawing = False
                player.strength = 0
            # Controllers must also forget the held draw after focus is lost.
            if hasattr(self.duel, 'cancel_draws'):
                self.duel.cancel_draws()

    def update_mouse(self, position):
        self.strength = min(1.0, abs(position[0] - self.drag_start[0]) / 240)
        self.angle = clamp_elevation(self.drag_angle + (self.drag_start[1] - position[1]) / 5)

    def update(self, dt):
        if self.state in DUEL_STATES:
            self.update_duel(dt)
            return
        if self.camera and (self.state in (STATE_PLAY, STATE_CALIBRATE)
                            or (self.campaign and self.state == STATE_FINISH)):
            try:
                frame, self.measurement, self.tracking_message, stamp = self.camera.read()
                self.camera_rgb = self.camera.preview(frame)
            except RuntimeError as exc:
                print(exc)
                self.menu()
                self.error = str(exc)
                return
            if self.state == STATE_CALIBRATE:
                self.controller.calibration.update(self.measurement, stamp, self.tracking_message)
                if self.controller.calibration.ready():
                    self.controller.reset()
                    self.state = STATE_PLAY
                    if self.campaign:
                        self.briefing = True
            elif self.state == STATE_FINISH:
                self.controller.arrow = None
                self.controller.update_controls(self.measurement, stamp)
            else:
                self.controller.arrow = self.game.arrow
                if self.game.arrow is not None or self.world_camera.can_shoot:
                    # During the briefing, aim is live but release is blocked in shoot().
                    self.controller.update_controls(self.measurement, stamp)
                else:
                    # Ignore gestures until the scenery returns, consuming these
                    # samples so an old closed hand cannot queue another shot.
                    self.controller.cancel_draw()
                    self.controller.controls_clear = False
                    self.controller.hand_state = self.measurement['state'] if self.measurement else 'Unknown'
                    if self.measurement:
                        self.controller.last_control_stamp = self.measurement['stamp']
                self.strength = self.controller.strength
                self.angle = self.controller.aim_degrees
        if self.state == STATE_PLAY:
            flight = self.game.arrow
            time_to_impact = flight.shot.end_time - flight.elapsed if flight else None
            self.game.update(dt)
            latest = self.game.impacts[-1] if self.game.impacts else None
            # When a frame crosses impact, only its remainder belongs to the
            # landing view. Reusing the full frame can skip the hold/return.
            camera_dt = (max(0.0, dt - time_to_impact)
                         if flight is not None and self.game.arrow is None else dt)
            self.world_camera.update(camera_dt, self.game.arrow, latest)
            if self.campaign and self.world_camera.can_shoot:
                self.game.settle()
            if self.game.finished and self.world_camera.can_shoot:
                self.state = STATE_FINISH
                self.drag_start = None
                if self.controller:
                    self.controller.cancel_draw()
                if self.campaign and not self._recorded:
                    if not self.admin.active:      # admin-mode results are never saved
                        self.progress.record(self.game)
                    self._recorded = True
                    self.finish_time = monotonic_seconds()

    def update_duel(self, dt):
        if self.state == DUEL_SELECT:
            return
        if self.duel_camera and self.state in (DUEL_CALIBRATE, DUEL_PLAY):
            try:
                self.camera_rgb, self.duel_observations, self.tracking_message, stamp = self.duel_camera.read()
            except RuntimeError as exc:
                self.menu()
                self.error = str(exc)
                return
            self.duel.apply_tracking(self.duel_observations, stamp)
            if self.state == DUEL_CALIBRATE and self.duel.ready:
                self.state = DUEL_PLAY
        if self.state == DUEL_PLAY:
            if self.duel_mode == 'keyboard':
                keys = pygame.key.get_pressed()
                self.duel.keyboard(0, move=int(keys[pygame.K_d])-int(keys[pygame.K_a]),
                                   aim=int(keys[pygame.K_w])-int(keys[pygame.K_s]), draw=bool(keys[pygame.K_f]), dt=dt)
                self.duel.keyboard(1, move=int(keys[pygame.K_RIGHT])-int(keys[pygame.K_LEFT]),
                                   aim=int(keys[pygame.K_UP])-int(keys[pygame.K_DOWN]), draw=bool(keys[pygame.K_RETURN]), dt=dt)
            self.duel.update(dt)
            if self.duel.finished:
                self.state = DUEL_FINISH

    def draw(self):
        if self.state == STATE_MENU:
            self.duel_renderer.menu(self.error)
            self.renderer.buttons = self.duel_renderer.buttons
            return
        if self.state == DUEL_SELECT:
            self.character_selection.draw(self.duel_renderer, self.characters, self.duel_mode)
            return
        self.campaign_renderer.admin = self.admin
        self.duel_renderer.admin_active = self.admin.active
        if self.state == CAMPAIGN_SELECT:
            self.campaign_renderer.level_select(self.progress, self.campaign_mode)
            return
        if self.state == ADMIN_LOGIN:
            self.campaign_renderer.admin_login(self.admin, self.admin_stage, self.admin_input, self.admin_message)
            return
        if self.state == ADMIN_PANEL:
            self.campaign_renderer.admin_panel(self.admin, self.progress, self.admin_message,
                                               self.admin_reset_armed)
            return
        if self.campaign:
            self.draw_campaign()
            return
        if self.state in DUEL_STATES:
            self.duel_renderer.play(self.duel, self.duel_mode, self.camera_rgb,
                                    calibrating=self.state == DUEL_CALIBRATE,
                                    tracking_message=self.tracking_message)
            self.character_selection.draw_reopen(self.duel_renderer)
            return
        self.renderer.scene(self.game, self.strength, self.angle,
                            preview=self.state == STATE_PLAY and self.world_camera.can_shoot,
                            world_camera=self.world_camera)
        status = (self.controller.status if self.controller else
                  'Drag to pull and aim. Release to shoot. SPACE fires the current preview.')
        if self.controller and self.measurement is None:
            status = self.tracking_message
        if self.state == STATE_PLAY and not self.world_camera.can_shoot:
            status = {'FOLLOW': 'Follow the arrow. Its path will stay visible for your next shot.',
                      'IMPACT': 'Shot recorded. Review its landing and flight path.',
                      'RETURN': 'Returning to the archer. Shooting resumes when the view settles.'}[self.world_camera.phase]
        hand = self.controller.drawing_hand if self.controller else 'Right'
        self.renderer.hud(self.game, self.strength, self.angle, status, self.mode, hand)
        if self.state == STATE_MENU:
            self.renderer.menu(self.error)
        elif self.state == STATE_CALIBRATE:
            self.renderer.calibration(self.controller.calibration, self.tracking_message)
        elif self.state == STATE_FINISH:
            self.renderer.finish(self.game)
        # Tracking continues during flight, but its inset would cover a steep
        # arrow near the right edge. Show it again when aiming/calibrating.
        if self.camera and self.world_camera.can_shoot:
            self.renderer.camera(self.camera_rgb, hand, self.controller.hand_state)

    def draw_campaign(self):
        view = self.campaign_renderer
        view.mode = self.mode
        view.scene(self.game, self.strength, self.angle,
                   preview=self.state == STATE_PLAY and self.world_camera.can_shoot,
                   world_camera=self.world_camera)
        status = (self.controller.status if self.controller else
                  'Drag to pull and aim. Arrow keys fine-tune (Shift: bigger). SPACE fires.')
        if self.controller and self.measurement is None:
            status = self.tracking_message
        if self.state == STATE_PLAY and not self.world_camera.can_shoot:
            status = {'FOLLOW': 'Follow the arrow.',
                      'IMPACT': 'Shot recorded. Check the minimap for your path.',
                      'RETURN': 'Returning to the archer. Shooting resumes when the view settles.'}[self.world_camera.phase]
        hand = self.controller.drawing_hand if self.controller else 'Right'
        view.hud(self.game, self.strength, self.angle, status, self.mode, hand)
        if self.state == STATE_CALIBRATE:
            view.calibration(self.controller.calibration, self.tracking_message)
        elif self.state == STATE_FINISH:
            view.result(self.game, self.progress)
        elif self.briefing:
            view.briefing(self.game)
        if self.camera and self.world_camera.can_shoot and not self.briefing and self.state != STATE_FINISH:
            view.camera(self.camera_rgb, hand, self.controller.hand_state)


def main():
    parser = argparse.ArgumentParser(description='Archidon: the official ME461 archery game')
    parser.add_argument('--mouse', action='store_true', help='Start mouse practice without a webcam')
    parser.add_argument('--campaign', action='store_true', help='Open the 10-level campaign (mouse controls)')
    parser.add_argument('--campaign-camera', action='store_true', help='Open the 10-level campaign with camera controls')
    parser.add_argument('--level', type=int, default=0, help='With --campaign: start this level directly (must be unlocked)')
    parser.add_argument('--unlock-all', action='store_true', help='Unlock every campaign level for this run')
    parser.add_argument('--admin', action='store_true', help='Open the admin password screen')
    parser.add_argument('--duel', action='store_true', help='Choose characters for a two-player camera duel')
    parser.add_argument('--duel-keyboard', action='store_true', help='Choose characters for a two-player keyboard duel')
    parser.add_argument('--duel-demo', action='store_true', help='Start a keyboard duel immediately for render validation')
    parser.add_argument('--camera', type=int, default=0, help='Webcam index (default: 0)')
    parser.add_argument('--background', choices=['pixelMakinaG.jpeg', 'p_background.jpg', 'background.jpeg', 'makinaG.jpeg'],
                        default='pixelMakinaG.jpeg', help='Use one of the supplied campus backgrounds')
    parser.add_argument('--scenery', choices=['day', 'night'], default='day',
                        help='Time of day for the pixel campus (toggle in the menu too)')
    parser.add_argument('--headless', action='store_true', help='Render using SDL dummy driver for validation')
    parser.add_argument('--frames', type=int, default=0, help='Exit after N frames (0: keep playing)')
    parser.add_argument('--screenshot', type=Path, help='Save the final rendered frame as a PNG')
    args = parser.parse_args()
    if args.headless:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    load_ui()
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption('Archidon | ME461 Archery')
    app = Archidon(screen, args.background, args.camera, args.scenery)
    if args.unlock_all:
        app.progress.unlock_all = True
    if args.admin:
        app.open_admin()
    elif args.campaign or args.campaign_camera:
        app.open_campaign('camera' if args.campaign_camera else 'mouse')
        if args.level:
            app.start_level(args.level)
    elif args.duel_demo:
        app.select_duel('keyboard')
        app.begin_duel()
    elif args.duel or args.duel_keyboard:
        app.select_duel('keyboard' if args.duel_keyboard else 'camera')
    elif args.mouse:
        app.start_mouse()
    clock = pygame.time.Clock()
    frames = 0
    try:
        while app.running:
            dt = clock.tick(FPS) / 1000.0
            # Read tracking before input, so keyboard releases use the current sample.
            app.update(dt)
            app.events()
            app.draw()
            pygame.display.flip()
            frames += 1
            if args.frames and frames >= args.frames:
                break
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(screen, str(args.screenshot))
    finally:
        app.close_camera()
        pygame.quit()


if __name__ == '__main__':
    main()
