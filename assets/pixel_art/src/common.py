"""Shared pixel-art helpers: palette, colour ramps, layered sprite builder."""
from PIL import Image, ImageDraw
import numpy as np

INK = (31, 24, 44, 255)          # universal outline (deep purple-black)
WHITE = (255, 251, 240, 255)


def rgba(c, a=255):
    if isinstance(c, str):
        c = c.lstrip('#')
        c = tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3]) + ((c[3],) if len(c) == 4 else (a,))


def shade(c, f):
    """Hue-shifted darken (f<0) / lighten (f>0): shadows drift to purple, lights to yellow."""
    r, g, b, a = rgba(c)
    if f < 0:
        k = 1 + f
        r, g, b = r * k + 30 * -f * .5, g * k, b * k + 60 * -f * .6
    else:
        r, g, b = r + (255 - r) * f, g + (255 - g) * f, b + (235 - b) * f * .8
    return tuple(int(max(0, min(255, v))) for v in (r, g, b)) + (a,)


class Layer:
    """A native-resolution transparent canvas with crisp (non antialiased) drawing."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.ox = self.oy = 0

    def at(self, ox, oy):
        self.ox, self.oy = ox, oy
        return self

    def _p(self, x, y):
        return x + self.ox, y + self.oy

    def rect(self, x, y, w, h, c):
        if w > 0 and h > 0:
            x, y = self._p(x, y)
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=rgba(c))

    def px(self, x, y, c):
        x, y = self._p(x, y)
        if 0 <= x < self.w and 0 <= y < self.h:
            self.img.putpixel((int(x), int(y)), rgba(c))

    def ell(self, x, y, w, h, c):
        x, y = self._p(x, y)
        self.d.ellipse([x, y, x + w - 1, y + h - 1], fill=rgba(c))

    def rrect(self, x, y, w, h, r, c):
        x, y = self._p(x, y)
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], r, fill=rgba(c))

    def poly(self, pts, c):
        self.d.polygon([self._p(*p) for p in pts], fill=rgba(c))

    def line(self, pts, c, width=1):
        self.d.line([self._p(*p) for p in pts], fill=rgba(c), width=width)

    def thick(self, a, b, w, c):
        """Thick pixel line drawn with square stamps (keeps hard pixel edges)."""
        (x0, y0), (x1, y1) = a, b
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n + 1):
            t = i / max(1, n)
            x, y = round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)
            self.rect(x - w // 2, y - w // 2, w, w, c)

    # --- post processing -------------------------------------------------
    def arr(self):
        return np.array(self.img)

    def set(self, a):
        self.img = Image.fromarray(a, 'RGBA')
        self.d = ImageDraw.Draw(self.img)

    def auto_shade(self, base, dx=2, dy=2, hi=True):
        """Shadow band on the bottom/right inside edge, 1px highlight top/left."""
        a = self.arr()
        m = a[..., 3] > 0
        same = np.all(a[..., :3] == np.array(rgba(base)[:3]), axis=-1) & m
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
            up = np.zeros_like(m); up[1:, :] = m[:-1, :]
            a[same & ~sh & (~left | ~up)] = shade(base, .30)
        self.set(a)
        return self

    def outline(self, c=INK, diag=False):
        a = self.arr()
        m = a[..., 3] > 0
        g = np.zeros_like(m)
        g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
        if diag:
            g[1:, 1:] |= m[:-1, :-1]; g[:-1, :-1] |= m[1:, 1:]
            g[1:, :-1] |= m[:-1, 1:]; g[:-1, 1:] |= m[1:, :-1]
        a[g & ~m] = rgba(c)
        self.set(a)
        return self

    def paste(self, other, x=0, y=0):
        src = other.img if isinstance(other, Layer) else other
        self.img.alpha_composite(src, (int(x), int(y)))
        self.d = ImageDraw.Draw(self.img)
        return self


def part(w, h, fn, base=None, outline=True, shade_it=True, **kw):
    """Draw a single sprite part on its own layer, shade + outline it."""
    L = Layer(w, h)
    fn(L)
    if base is not None and shade_it:
        L.auto_shade(base, **kw)
    if outline:
        L.outline()
    return L


def up(img, s):
    return img.resize((img.width * s, img.height * s), Image.NEAREST)
