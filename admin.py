"""Password-protected admin mode: settings and password storage.

The password is never stored in plain text: ``admin_config.json`` beside the
game keeps a random salt and a PBKDF2-SHA256 hash. Until a password has been
set there, DEFAULT_PASSWORD works (change it from the admin panel).

This keeps casual players out of the admin tools; anyone who can edit the
game's files can still delete admin_config.json to restore the default.
"""
from dataclasses import dataclass, replace
import hashlib
import hmac
import json
import os
from pathlib import Path

from tracking_clock import monotonic_seconds

DEFAULT_PASSWORD = 'archidon461'
CONFIG_FILE = Path(__file__).resolve().with_name('admin_config.json')
ITERATIONS = 120_000
MAX_ATTEMPTS = 5          # wrong passwords before a lockout
LOCKOUT_SECONDS = 30
TARGET_SCALES = (1.0, 1.5, 2.0)


def _hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)


@dataclass
class AdminOptions:
    """Cheats/tools applied to campaign levels while admin mode is unlocked."""
    unlock_all: bool = True
    infinite_arrows: bool = False
    full_preview: bool = False
    no_wind: bool = False
    still_target: bool = False
    show_hitboxes: bool = False
    target_scale: float = 1.0

    def apply(self, level):
        """Return the level as it should be played with these options."""
        changes = {}
        if self.infinite_arrows:
            changes['arrows'] = 99
        if self.full_preview:
            changes['preview'] = 1.0
        if self.no_wind:
            changes['wind'] = (0.0, 0.0)
        if self.still_target:
            changes['target_motion'] = (0.0, 0.0)
            changes['relocate'] = False
        if self.target_scale != 1.0:
            changes['radius'] = round(level.radius * self.target_scale, 3)
        return replace(level, **changes) if changes else level

    @property
    def changes_play(self):
        return (self.infinite_arrows or self.full_preview or self.no_wind or self.still_target
                or self.target_scale != 1.0)


class Admin:
    def __init__(self, path=CONFIG_FILE):
        self.path = Path(path) if path else None
        self.active = False
        self.options = AdminOptions()
        self.failures = 0
        self.locked_until = 0.0
        self._salt = self._digest = None
        self._load()

    # ------------------------------------------------------------------ storage
    def _load(self):
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self._salt = bytes.fromhex(data['salt'])
                self._digest = bytes.fromhex(data['hash'])
                return
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self._salt = b'archidon-default'
        self._digest = _hash(DEFAULT_PASSWORD, self._salt)

    @property
    def using_default(self):
        return self._salt == b'archidon-default'

    # ------------------------------------------------------------------ login
    @property
    def lockout_left(self):
        return max(0.0, self.locked_until - monotonic_seconds())

    def check(self, password):
        return hmac.compare_digest(_hash(password, self._salt), self._digest)

    def login(self, password):
        """Unlock admin mode. Returns (ok, message)."""
        if self.lockout_left > 0:
            return False, f'Too many attempts. Wait {self.lockout_left:.0f} s.'
        if self.check(password):
            self.active = True
            self.failures = 0
            return True, 'Admin mode unlocked.'
        self.failures += 1
        if self.failures >= MAX_ATTEMPTS:
            self.failures = 0
            self.locked_until = monotonic_seconds() + LOCKOUT_SECONDS
            return False, f'Wrong password. Locked for {LOCKOUT_SECONDS} s.'
        return False, f'Wrong password. {MAX_ATTEMPTS - self.failures} attempts left.'

    def logout(self):
        self.active = False
        self.options = AdminOptions()

    def set_password(self, password):
        if len(password) < 4:
            return False, 'Use at least 4 characters.'
        salt = os.urandom(16)
        digest = _hash(password, salt)
        if self.path:
            try:
                self.path.write_text(json.dumps({'salt': salt.hex(), 'hash': digest.hex()}))
            except OSError as exc:
                return False, f'Could not save: {exc}'
        self._salt, self._digest = salt, digest
        return True, 'Password changed.'

    # ------------------------------------------------------------------ options
    def toggle(self, name):
        if not self.active:
            return
        if name == 'target_scale':
            i = TARGET_SCALES.index(self.options.target_scale) if self.options.target_scale in TARGET_SCALES else 0
            self.options.target_scale = TARGET_SCALES[(i + 1) % len(TARGET_SCALES)]
        else:
            setattr(self.options, name, not getattr(self.options, name))
