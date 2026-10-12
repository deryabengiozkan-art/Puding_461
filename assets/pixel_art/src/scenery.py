"""Continuous parallax campus scenery.

Seven layers, each a seamless horizontal loop with a DIFFERENT period, scrolled at a
different parallax speed. Because the periods are unrelated (e.g. 1104 / 432 / 336 / 288 / 96),
the combined picture practically never repeats — it is not one picture copied twice.
Every layer is drawn with wrap-around, so its left and right edges join perfectly.

Native pixel resolution; scale x3 in game.
"""
import random
import numpy as np
from PIL import Image
from common import Layer, rgba, shade, INK
from font import render

H = 180
GROUND_Y = 150          # feet line

PALETTES = {
    'day': dict(
        sky=[(110, 196, 255), (140, 212, 255), (178, 228, 255), (214, 240, 250), (255, 236, 200)],
        sun=(255, 244, 190), cloud=(255, 255, 255), cloud_sh=(208, 228, 248),
        hill=(140, 196, 214), hill2=(112, 172, 196),
        tree_far=(86, 164, 120), tree_far2=(66, 140, 108),
        concrete=(216, 204, 182), concrete2=(190, 176, 156), brick=(204, 98, 74), brick2=(170, 74, 62),
        glass=(120, 196, 236), glass2=(84, 150, 206), lit=(255, 236, 150), roof=(120, 110, 120),
        tree=(92, 196, 92), tree2=(58, 150, 76), trunk=(130, 84, 56),
        stone=[(200, 188, 164), (184, 170, 146), (214, 200, 172), (176, 160, 140)], mortar=(110, 98, 92),
        rail=(64, 120, 92), slab=(222, 214, 194), slab2=(196, 186, 166),
        grass=(96, 186, 86), grass2=(74, 156, 72), grass3=(132, 214, 104), flower=[(255, 236, 120), (255, 255, 255), (246, 120, 160)],
        lamp=(70, 76, 96), lamp_glow=(255, 240, 180), outline=INK, stars=False),
    'night': dict(
        sky=[(22, 20, 52), (30, 28, 70), (40, 40, 92), (52, 56, 108), (72, 72, 122)],
        sun=(240, 240, 255), cloud=(80, 84, 130), cloud_sh=(58, 60, 104),
        hill=(48, 56, 100), hill2=(40, 46, 86),
        tree_far=(36, 70, 80), tree_far2=(28, 58, 70),
        concrete=(132, 126, 130), concrete2=(108, 102, 112), brick=(120, 64, 72), brick2=(96, 50, 62),
        glass=(52, 64, 104), glass2=(40, 50, 86), lit=(132, 255, 140), roof=(70, 64, 84),
        tree=(52, 120, 78), tree2=(36, 92, 70), trunk=(84, 60, 56),
        stone=[(130, 124, 126), (116, 110, 116), (142, 134, 132), (106, 100, 108)], mortar=(52, 46, 64),
        rail=(46, 84, 76), slab=(138, 132, 136), slab2=(116, 110, 118),
        grass=(52, 120, 72), grass2=(40, 98, 64), grass3=(70, 146, 84), flower=[(200, 200, 140), (200, 200, 220), (180, 110, 150)],
        lamp=(40, 44, 64), lamp_glow=(255, 236, 150), outline=INK, stars=True),
}


class Wrap:
    """Draw on an extended canvas, then fold the margins so the tile loops seamlessly."""

    def __init__(self, period, h=H, margin=160):
        self.P, self.M = period, margin
        self.L = Layer(period + 2 * margin, h).at(margin, 0)

    def __getattr__(self, k):
        return getattr(self.L, k)

    def new_part(self):
        return Layer(self.P + 2 * self.M, self.L.h).at(self.M, 0)

    def add(self, part, bases=(), outline=True, **kw):
        part.at(0, 0)
        for b in bases:
            part.auto_shade(b, **kw)
        if outline:
            part.outline()
        self.L.paste(part)

    def tile(self):
        img, P, M = self.L.img, self.P, self.M
        out = img.crop((M, 0, M + P, img.height))
        if M == 0:
            return out
        out.alpha_composite(img.crop((M + P, 0, M + P + M, img.height)), (0, 0))
        out.alpha_composite(img.crop((0, 0, M, img.height)), (P - M, 0))
        return out


# ------------------------------------------------------------------ layers
def sky(P, w=2000):
    L = Layer(w, H)
    bands = P['sky']
    n = len(bands)
    top = 0
    bh = 118 / n
    for i, c in enumerate(bands):
        y0, y1 = int(i * bh), int((i + 1) * bh)
        L.rect(0, y0, w, y1 - y0 + 1, c)
        if i + 1 < n:                     # 2-row checker dither between bands
            for x in range(0, w, 2):
                L.px(x, y1 - 1, bands[i + 1]); L.px(x + 1, y1 - 2, bands[i + 1])
    L.rect(0, 118, w, H - 118, bands[-1])
    rng = random.Random(4)
    if P['stars']:
        for _ in range(70):
            x, y = rng.randrange(w), rng.randrange(90)
            L.px(x, y, (255, 255, 230) if rng.random() < .7 else (180, 200, 255))
        for _ in range(6):
            x, y = rng.randrange(w), rng.randrange(70)
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                L.px(x + dx, y + dy, (255, 255, 230))
        L.ell(300, 14, 20, 20, P['sun']); L.ell(304, 17, 5, 4, (200, 204, 230)); L.ell(311, 25, 4, 4, (200, 204, 230))
    else:
        L.ell(300, 16, 26, 26, shade(P['sun'], .1))
        L.ell(304, 20, 18, 18, (255, 255, 240))
    return L.img


def clouds(P, period=640):
    Wp = Wrap(period)
    rng = random.Random(11)
    x = 0
    while x < period:
        cw = rng.randint(30, 60); y = rng.randint(8, 50)
        p = Wp.new_part()
        for k in range(4):
            r = rng.randint(6, 11)
            p.ell(x + k * cw // 4, y - r + rng.randint(0, 3), 2 * r, 2 * r, P['cloud'])
        p.rrect(x - 4, y - 2, cw + 14, 9, 4, P['cloud'])
        a = p.arr(); m = a[..., 3] > 0
        lower = np.zeros_like(m); lower[:-3] = m[3:]
        a[m & ~lower] = rgba(P['cloud_sh'])
        p.set(a)
        Wp.add(p, outline=False)
        x += cw + rng.randint(60, 140)
    return Wp.tile()


def hills(P, period=432):
    Wp = Wrap(period, margin=0)
    p = Wp.new_part()
    L = p.at(0, 0)
    for x in range(period):
        t = x / period * 2 * np.pi
        y = 78 + 10 * np.sin(t) + 7 * np.sin(3 * t + 1) + 3 * np.sin(7 * t + 2)
        L.rect(x, int(y), 1, H - int(y), P['hill'])
        y2 = 96 + 6 * np.sin(2 * t + 2) + 4 * np.sin(5 * t)
        L.rect(x, int(y2), 1, H - int(y2), P['hill2'])
    Wp.L.paste(L)
    return Wp.tile()


def treeline(P, period=336):
    Wp = Wrap(period)
    rng = random.Random(7)
    p = Wp.new_part()
    x = -10
    while x < period + 10:
        r = rng.randint(7, 13)
        cy = 108 - rng.randint(0, 10)
        c = P['tree_far'] if rng.random() < .6 else P['tree_far2']
        p.ell(x - r, cy - r, 2 * r, 2 * r + 4, c)
        if rng.random() < .3:              # occasional poplar
            p.ell(x - 4, cy - r - 14, 9, 26, P['tree_far2'])
        x += rng.randint(6, 14)
    p.rect(0, 106, period, 20, P['tree_far2'])
    Wp.add(p, [P['tree_far']], outline=False, dx=0, dy=3)
    return Wp.tile()


# --- buildings -----------------------------------------------------------
BASE = 122   # building foot line (hidden behind wall)


def b_concrete(Wp, P, x, w, h, rng, sign=None):
    p = Wp.new_part()
    top = BASE - h
    p.rect(x, top, w, h, P['concrete'])
    p.rect(x - 1, top - 3, w + 2, 4, P['roof'])
    for sx in range(x + 12, x + w - 4, 14):
        p.rect(sx, top + 1, 1, h, P['concrete2'])
    for fy in range(top + 8, BASE - 12, 18):
        for wx in range(x + 4, x + w - 12, 14):
            lit = rng.random() < (.35 if P['stars'] else .15)
            c = P['lit'] if lit else P['glass']
            p.rect(wx, fy, 10, 9, INK)
            p.rect(wx + 1, fy + 1, 8, 7, c)
            p.rect(wx + 5, fy + 1, 1, 7, INK)
            p.rect(wx + 1, fy + 4, 8, 1, INK)
            if not lit:
                p.px(wx + 2, fy + 1, shade(c, .5)); p.px(wx + 1, fy + 2, shade(c, .5))
        p.rect(x, fy + 10, w, 1, P['concrete2'])
    # stains
    for _ in range(w // 10):
        sx = rng.randrange(x + 2, x + w - 2)
        p.rect(sx, top + rng.randint(2, h - 20), 1, rng.randint(3, 8), P['concrete2'])
    if sign:
        t = render(sign, fill=INK, outline=None, shadow=0, bold=False)
        sx = x + (w - t.width) // 2 - 4
        p.rect(sx + 3, top - 8, 1, 6, P['roof']); p.rect(sx + t.width + 4, top - 8, 1, 6, P['roof'])
        p.rect(sx, top - 18, t.width + 8, t.height + 2, (240, 236, 224))
        p.rect(sx, top - 18, t.width + 8, 1, (238, 72, 72))
        p.img.alpha_composite(t, (sx + 4 + Wp.M, top - 18))
        # entrance
        p.rect(x + w // 2 - 9, BASE - 18, 18, 18, P['glass2'])
        p.rect(x + w // 2, BASE - 18, 1, 18, INK)
    Wp.add(p, [P['concrete']], dx=3, dy=0)


def b_brick(Wp, P, x, w, h, rng):
    p = Wp.new_part()
    top = BASE - h
    p.rect(x, top, w, h, P['brick'])
    p.poly([(x - 3, top), (x + w // 2, top - 14), (x + w + 2, top)], P['roof'])
    for yy in range(top + 2, BASE, 3):
        off = 0 if (yy // 3) % 2 else 3
        for xx in range(x + off, x + w, 6):
            p.px(xx, yy, P['brick2'])
    for wx in range(x + 6, x + w - 8, 12):
        for fy in (top + 8, top + 30):
            if fy + 16 > BASE - 4:
                continue
            lit = rng.random() < (.4 if P['stars'] else .1)
            c = P['lit'] if lit else P['glass']
            p.rect(wx - 1, fy + 2, 9, 14, (236, 226, 210))
            p.ell(wx - 1, fy - 1, 9, 8, (236, 226, 210))
            p.rect(wx, fy + 3, 7, 12, c)
            p.ell(wx, fy, 7, 7, c)
            p.rect(wx + 3, fy, 1, 15, (236, 226, 210))
    p.rect(x - 1, BASE - 20, w + 2, 2, (236, 226, 210))
    Wp.add(p, [P['brick']], dx=3, dy=0)


def b_glass(Wp, P, x, w, h, rng):
    p = Wp.new_part()
    top = BASE - h
    p.rect(x, top, w, h, P['glass2'])
    p.rect(x - 2, top - 4, w + 4, 5, P['concrete'])
    for gx in range(x + 3, x + w - 3, 6):
        p.rect(gx, top + 3, 4, h - 6, P['glass'])
        if rng.random() < (.3 if P['stars'] else 0):
            p.rect(gx, top + rng.randint(6, h - 20), 4, 10, P['lit'])
    for k in range(3):             # sky reflection diagonals
        rx = x + rng.randint(0, w - 10)
        for i in range(12):
            p.px(rx + i, top + 10 + k * 16 + i, shade(P['glass'], .45))
    p.rect(x, top + h // 2, w, 2, P['concrete'])
    Wp.add(p, [P['glass2']], dx=2, dy=0, hi=False)


def b_kiosk(Wp, P, x, w, rng):
    p = Wp.new_part()
    top = BASE - 26
    p.rect(x, top, w, 26, P['concrete'])
    p.rect(x + 4, top + 8, w - 8, 12, P['lit'] if P['stars'] else P['glass'])
    for i in range(0, w + 4, 6):
        p.rect(x - 2 + i, top - 6, 3, 7, (238, 72, 72))
        p.rect(x + 1 + i, top - 6, 3, 7, (255, 250, 240))
    p.rect(x - 2, top - 7, w + 4, 1, (238, 72, 72))
    t = render('KANTİN', fill=(238, 72, 72), outline=None, shadow=0, bold=False)
    bx = x + (w - t.width) // 2 - 3
    p.rect(bx, top - 18, t.width + 6, 11, (255, 250, 240))
    p.rect(bx + 2, top - 8, 1, 2, P['lamp']); p.rect(bx + t.width + 3, top - 8, 1, 2, P['lamp'])
    p.img.alpha_composite(t, (bx + 3 + Wp.M, top - 19))
    Wp.add(p, [P['concrete']])


def tree(Wp, P, x, rng, big=False):
    p = Wp.new_part()
    r = rng.randint(14, 18) if big else rng.randint(10, 13)
    base = BASE + 2
    p.rect(x - 2, base - r - 10, 4, r + 10, P['trunk'])
    p.thick((x, base - r), (x + 5, base - r - 6), 2, P['trunk'])
    cy = base - r - 12 - r
    for dx, dy, rr in ((0, 0, r), (-r * .7, r * .35, r * .7), (r * .7, r * .3, r * .72), (0, -r * .5, r * .7)):
        p.ell(int(x + dx - rr), int(cy + dy - rr + r * .3), int(2 * rr), int(2 * rr), P['tree'])
    Wp.add(p, [P['tree']], dx=4, dy=4)
    # leaf clumps on top of the shading
    q = Wp.new_part()
    for _ in range(5):
        ax, ay = x + rng.randint(-r + 4, r - 6), cy + rng.randint(-r // 2, r // 2)
        q.rect(ax, ay, 3, 1, P['tree2']); q.rect(ax + 1, ay + 1, 3, 1, P['tree2'])
    Wp.add(q, outline=False)


def lamp(Wp, P, x):
    p = Wp.new_part()
    p.rect(x, BASE - 44, 2, 44, P['lamp'])
    p.rect(x - 3, BASE - 46, 8, 3, P['lamp'])
    p.rect(x - 2, BASE - 43, 6, 2, P['lamp_glow'])
    Wp.add(p)
    if P['stars']:
        g = Wp.new_part()
        g.ell(x - 6, BASE - 47, 14, 10, (255, 236, 150, 70)); g.ell(x - 3, BASE - 45, 8, 6, (255, 240, 180, 90))
        Wp.add(g, outline=False)


def campus(P, period=1104):
    Wp = Wrap(period)
    rng = random.Random(21)
    plan = [('concrete', 150, 74, 'MAKİNE G'), ('tree', True), ('brick', 92, 52), ('lamp',),
            ('glass', 64, 92), ('tree', False), ('kiosk', 46), ('lamp',), ('concrete', 120, 58, None),
            ('tree', True), ('brick', 110, 62), ('glass', 52, 76), ('tree', False), ('lamp',)]
    x = 8
    items = []
    for it in plan:
        k = it[0]
        if k in ('concrete', 'brick', 'glass'):
            items.append((x, it)); x += it[1] + rng.randint(14, 26)
        elif k == 'kiosk':
            items.append((x, it)); x += it[1] + 16
        else:
            items.append((x - 8, it))
    scale = period / x
    for bx, it in items:
        bx = int(bx * scale)
        k = it[0]
        if k == 'concrete': b_concrete(Wp, P, bx, it[1], it[2], rng, it[3])
        elif k == 'brick': b_brick(Wp, P, bx, it[1], it[2], rng)
        elif k == 'glass': b_glass(Wp, P, bx, it[1], it[2], rng)
        elif k == 'kiosk': b_kiosk(Wp, P, bx, it[1], rng)
    for bx, it in items:               # trees & lamps in front of buildings
        bx = int(bx * scale)
        if it[0] == 'tree': tree(Wp, P, bx, rng, it[1])
        elif it[0] == 'lamp': lamp(Wp, P, bx)
    # lawn strip behind the wall
    p = Wp.new_part(); p.rect(0, BASE - 2, period, 10, P['grass2'])
    Wp.add(p, outline=False)
    return Wp.tile()


def wall(P, period=288):
    Wp = Wrap(period, margin=40)
    rng = random.Random(5)
    top, bot = 124, GROUND_Y - 4
    p = Wp.new_part()
    p.rect(0, top, period, bot - top, P['mortar'])
    y = top + 1
    while y < bot - 2:
        h = rng.randint(5, 7)
        x = 0
        first = rng.randint(3, 12)
        while x < period:
            w = first if x == 0 else rng.randint(7, 15)
            w = min(w, period - x)
            if period - x - w < 5:
                w = period - x
            c = rng.choice(P['stone'])
            p.rect(x + 1, y, w - 1, min(h - 1, bot - y - 1), c)
            p.rect(x + 1, y, w - 1, 1, shade(c, .25))
            p.rect(x + w - 1, y, 1, min(h - 1, bot - y - 1), shade(c, -.15))
            if rng.random() < .25:
                p.px(x + rng.randint(2, w - 2), y + rng.randint(2, max(2, h - 2)), shade(c, -.2))
            x += w
        y += h
    # cap stones
    p.rect(0, top - 4, period, 4, P['slab'])
    for x in range(0, period, 12):
        p.rect(x, top - 4, 1, 4, P['slab2'])
    p.rect(0, top - 1, period, 1, P['slab2'])
    Wp.add(p, outline=False)
    # railing
    r = Wp.new_part()
    for x in range(0, period, 32):
        r.rect(x, top - 26, 2, 22, P['rail'])
    r.rect(0, top - 26, period, 2, P['rail'])
    r.rect(0, top - 15, period, 1, P['rail'])
    Wp.add(r, outline=True)
    # moss / ivy patches
    m = Wp.new_part()
    for _ in range(5):
        x = rng.randrange(period)
        for k in range(rng.randint(4, 9)):
            m.rect(x + rng.randint(-3, 6), top + rng.randint(-1, 3) + k, rng.randint(2, 4), 2, P['grass2'])
    Wp.add(m, outline=False)
    return Wp.tile()


def ground(P, period=96):
    Wp = Wrap(period, margin=24)
    rng = random.Random(9)
    p = Wp.new_part()
    y0 = GROUND_Y - 4
    p.rect(0, y0, period, 10, P['slab'])
    p.rect(0, y0 + 9, period, 1, P['slab2'])
    for x in range(0, period, 16):
        p.rect(x, y0, 1, 10, P['slab2'])
        p.rect(x + 1, y0, 14, 1, shade(P['slab'], .2))
    p.rect(0, y0 + 10, period, H - y0 - 10, P['grass'])
    for _ in range(70):
        x, y = rng.randrange(period), rng.randrange(y0 + 12, H)
        p.rect(x, y, 1, 2, P['grass2'])
        if rng.random() < .3:
            p.px(x + 1, y - 1, P['grass3'])
    for x in range(0, period, 2):          # grass fringe over the path edge
        if rng.random() < .6:
            p.px(x, y0 + 10 - 1, P['grass'])
    Wp.add(p, outline=False)
    return Wp.tile()


def foreground(P, period=520):
    Wp = Wrap(period, margin=20)
    rng = random.Random(13)
    p = Wp.new_part()
    for _ in range(9):
        x = rng.randrange(period)
        for k in range(rng.randint(5, 9)):
            hx = x + k * 2 + rng.randint(-1, 1)
            hh = rng.randint(4, 9)
            p.thick((hx, H), (hx + rng.randint(-2, 2), H - hh), 1, P['grass3'] if k % 2 else P['grass'])
        if rng.random() < .7:
            fx = x + rng.randint(0, 12)
            c = rng.choice(P['flower'])
            p.rect(fx, H - 11, 3, 3, c); p.px(fx + 1, H - 10, (255, 200, 60))
    Wp.add(p, outline=True)
    return Wp.tile()


LAYERS = [  # (name, builder, parallax factor)
    ('sky', sky, 0.0), ('clouds', clouds, 0.08), ('hills', hills, 0.15), ('treeline', treeline, 0.28),
    ('campus', campus, 0.5), ('wall', wall, 0.85), ('ground', ground, 1.0), ('foreground', foreground, 1.25),
]


def build_layers(mode='day'):
    P = PALETTES[mode]
    return [(n, f(P), k) for n, f, k in LAYERS]


def compose(layers, cam_x, view_w=420):
    out = Image.new('RGBA', (view_w, H))
    for name, img, k in layers:
        if k == 0:
            out.alpha_composite(img.crop((0, 0, view_w, H)))
            continue
        off = int(cam_x * k) % img.width
        x = -off
        while x < view_w:
            out.alpha_composite(img, (x, 0)) if x >= 0 else out.alpha_composite(img.crop((-x, 0, img.width, H)), (0, 0))
            x += img.width
    return out
