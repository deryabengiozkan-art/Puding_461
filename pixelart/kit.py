"""Low-level pixel-art canvas on top of pygame + numpy (no Pillow needed at runtime).

Everything in ``pixelart`` is drawn at *native* resolution and then scaled up
with nearest-neighbour (``big``), so every on-screen pixel stays crisp.
"""
import numpy as np
import pygame

INK = (31, 24, 44, 255)          # universal outline (deep purple-black)
WHITE = (255, 251, 240, 255)
CLEAR = (0, 0, 0, 0)
SCALE = 3                        # one art pixel = 3x3 screen pixels
_tobytes = getattr(pygame.image, 'tobytes', None) or pygame.image.tostring


def rgba(c, a=255):
    c = tuple(c)
    return c[:3] + ((c[3],) if len(c) == 4 else (a,))


def shade(c, f):
    """Hue-shifted darken (f<0) / lighten (f>0): shadows drift purple, lights warm."""
    r, g, b, a = rgba(c)
    if f < 0:
        k = 1 + f
        r, g, b = r * k + 30 * -f * .5, g * k, b * k + 60 * -f * .6
    else:
        r, g, b = r + (255 - r) * f, g + (255 - g) * f, b + (235 - b) * f * .8
    return tuple(int(max(0, min(255, v))) for v in (r, g, b)) + (a,)


def surface(w, h):
    return pygame.Surface((max(1, int(w)), max(1, int(h))), pygame.SRCALPHA)


def to_array(surf):
    """HxWx4 uint8 copy of a surface."""
    w, h = surf.get_size()
    return np.frombuffer(_tobytes(surf, 'RGBA'), np.uint8).reshape(h, w, 4).copy()


def from_array(a):
    a = np.ascontiguousarray(a, dtype=np.uint8)
    h, w = a.shape[:2]
    return pygame.image.frombuffer(a.tobytes(), (w, h), 'RGBA').copy()


def big(surf, s=SCALE):
    if s == 1:
        return surf
    return pygame.transform.scale(surf, (surf.get_width() * s, surf.get_height() * s))


def flip(surf):
    return pygame.transform.flip(surf, True, False)


class Layer:
    """A transparent native-resolution canvas with crisp (non antialiased) drawing."""

    def __init__(self, w, h):
        self.w, self.h = int(w), int(h)
        self.surf = surface(self.w, self.h)
        self.ox = self.oy = 0

    def at(self, ox, oy):
        self.ox, self.oy = ox, oy
        return self

    def _p(self, x, y):
        return x + self.ox, y + self.oy

    def rect(self, x, y, w, h, c):
        if w > 0 and h > 0:
            x, y = self._p(x, y)
            self.surf.fill(rgba(c), pygame.Rect(round(x), round(y), round(w), round(h)))

    def px(self, x, y, c):
        x, y = self._p(x, y)
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.surf.set_at((x, y), rgba(c))

    def ell(self, x, y, w, h, c):
        x, y = self._p(x, y)
        if w > 0 and h > 0:
            pygame.draw.ellipse(self.surf, rgba(c), pygame.Rect(round(x), round(y), round(w), round(h)))

    def rrect(self, x, y, w, h, r, c):
        x, y = self._p(x, y)
        if w > 0 and h > 0:
            pygame.draw.rect(self.surf, rgba(c), pygame.Rect(round(x), round(y), round(w), round(h)),
                             border_radius=max(0, int(min(r, w // 2, h // 2))))

    def poly(self, pts, c):
        pygame.draw.polygon(self.surf, rgba(c), [self._p(*p) for p in pts])

    def line(self, pts, c, width=1):
        pts = [self._p(*p) for p in pts]
        if len(pts) == 2:
            pygame.draw.line(self.surf, rgba(c), pts[0], pts[1], width)
        else:
            pygame.draw.lines(self.surf, rgba(c), False, pts, width)

    def thick(self, a, b, w, c):
        """Thick pixel line drawn with square stamps (keeps hard pixel edges)."""
        (x0, y0), (x1, y1) = a, b
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n + 1):
            t = i / max(1, n)
            x, y = round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)
            self.rect(x - w // 2, y - w // 2, w, w, c)

    def blit(self, src, x, y):
        x, y = self._p(x, y)
        self.surf.blit(src.surf if isinstance(src, Layer) else src, (round(x), round(y)))
        return self

    # --- post processing -------------------------------------------------
    def arr(self):
        return to_array(self.surf)

    def set(self, a):
        self.surf = from_array(a)

    def auto_shade(self, base, dx=2, dy=2, hi=True):
        """Shadow band on the bottom/right inside edge, 1px highlight top/left."""
        self.set(shade_array(self.arr(), base, dx, dy, hi))
        return self

    def outline(self, c=INK, diag=False):
        self.set(outline_array(self.arr(), c, diag))
        return self

    def finish(self, bases=(), outline=True, **kw):
        """Shade several colours and outline with a single surface round-trip."""
        a = self.arr()
        for b in bases or ():
            a = shade_array(a, b, **kw)
        if outline:
            a = outline_array(a)
        self.set(a)
        return self

    def paste(self, other, x=0, y=0):
        self.surf.blit(other.surf if isinstance(other, Layer) else other, (int(x), int(y)))
        return self


def clip_to(src, mask_surf):
    """Return ``src`` with alpha multiplied by ``mask_surf``'s alpha (same size)."""
    a = to_array(src)
    m = pygame.surfarray.array_alpha(mask_surf).T
    a[..., 3] = (a[..., 3].astype(np.uint16) * m // 255).astype(np.uint8)
    return from_array(a)


def shade_array(a, base, dx=2, dy=2, hi=True):
    m = a[..., 3] > 0
    same = np.all(a[..., :3] == np.array(rgba(base)[:3], np.uint8), axis=-1) & m
    if not same.any():
        return a
    sh = np.zeros_like(m)
    if dx:
        right = np.zeros_like(m); right[:, :-dx] = m[:, dx:]
        sh |= ~right
    if dy:
        below = np.zeros_like(m); below[:-dy, :] = m[dy:, :]
        sh |= ~below
    a[same & sh] = shade(base, -.28)
    if hi:
        left = np.zeros_like(m); left[:, 1:] = m[:, :-1]
        upm = np.zeros_like(m); upm[1:, :] = m[:-1, :]
        a[same & ~sh & (~left | ~upm)] = shade(base, .30)
    return a


def outline_array(a, c=INK, diag=False):
    m = a[..., 3] > 0
    g = np.zeros_like(m)
    g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
    if diag:
        g[1:, 1:] |= m[:-1, :-1]; g[:-1, :-1] |= m[1:, 1:]
        g[1:, :-1] |= m[:-1, 1:]; g[:-1, 1:] |= m[1:, :-1]
    a[g & ~m] = rgba(c)
    return a
