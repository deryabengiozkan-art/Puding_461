"""Pixel UI kit: buttons (4 states), icon buttons, panels, ribbons, logo, VS badge,
character cards, health / pull bars. Everything renders at native pixel size."""
import math
from PIL import Image
from common import Layer, rgba, shade, INK, WHITE
from font import render, text_width

PALETTE = {
    'green': (92, 214, 120), 'orange': (255, 150, 52), 'blue': (72, 156, 240),
    'red': (238, 72, 72), 'purple': (156, 96, 230), 'pink': (246, 100, 150),
    'yellow': (255, 210, 64), 'teal': (56, 196, 190), 'grey': (150, 150, 168),
}


def C(c):
    return PALETTE.get(c, c) if isinstance(c, str) else c


# --------------------------------------------------------------- buttons
def button(w, h, label, color='green', state='normal', icon=None):
    """state: normal | hover | pressed | disabled. Returns native RGBA image."""
    base = C('grey') if state == 'disabled' else C(color)
    if state == 'hover':
        base = shade(base, .18)
    lip = 1 if state == 'pressed' else 4
    off = 3 if state == 'pressed' else 0
    L = Layer(w + 2, h + 2)
    # dark lip / drop
    L.rrect(1, 1 + off, w, h - off, 4, shade(base, -.45))
    # face
    fh = h - lip - off
    L.rrect(1, 1 + off, w, fh, 4, base)
    L.rrect(3, 2 + off, w - 4, max(2, fh // 2 - 1), 3, shade(base, .22))      # glossy top half
    L.rect(4, 2 + off, w - 8, 1, shade(base, .55))                               # specular line
    L.rect(1 + w - 4, 3 + off, 1, 2, shade(base, .65))
    L.outline()
    img = L.img
    txt_col = (235, 235, 240) if state == 'disabled' else WHITE
    t = render(label, fill=txt_col, outline=shade(base, -.55), shadow=1)
    ix = 0
    if icon is not None:
        ix = icon.width + 3
    tx = (w + 2 - t.width - ix) // 2 + ix
    ty = 1 + off + (fh - t.height) // 2 + 1
    if icon is not None:
        img.alpha_composite(icon, (tx - ix, ty + (t.height - icon.height) // 2))
    img.alpha_composite(t, (tx, ty))
    if state == 'hover':                      # sparkle
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (0, 0)):
            L2 = img
            L2.putpixel((w - 5 + dx, 5 + dy + off), rgba(WHITE))
    return img


# --------------------------------------------------------------- icons (9x9 masks)
ICONS = {
    'play':   ['.#.......', '.##......', '.###.....', '.####....', '.#####...', '.####....', '.###.....', '.##......', '.#.......'],
    'pause':  ['.........', '.##..##..', '.##..##..', '.##..##..', '.##..##..', '.##..##..', '.##..##..', '.##..##..', '.........'],
    'back':   ['...#.....', '..##.....', '.#######.', '########.', '.#######.', '..##.....', '...#.....', '.........', '.........'],
    'restart': ['..####...', '.#....#.#', '#......##', '#.....###', '#........', '#......#.', '.#....#..', '..####...', '.........'],
    'gear':   ['...#.#...', '.#######.', '.##...##.', '##.....##', '.#..#..#.', '##.....##', '.##...##.', '.#######.', '...#.#...'],
    'sound':  ['....#....', '...##..#.', '####.#..#', '##.#..#.#', '##.#..#.#', '####.#..#', '...##..#.', '....#....', '.........'],
    'camera': ['.........', '..###....', '#########', '#..###..#', '#.#...#.#', '#.#...#.#', '#..###..#', '#########', '.........'],
    'home':   ['....#....', '...###...', '..#####..', '.#######.', '#########', '.##...##.', '.##.#.##.', '.##.#.##.', '.........'],
    'trophy': ['#########', '#.#####.#', '#.#####.#', '.#.###.#.', '...###...', '....#....', '....#....', '..#####..', '.#######.'],
    'heart':  ['.........', '.##...##.', '####.####', '#########', '#########', '.#######.', '..#####..', '...###...', '....#....'],
    'target': ['..#####..', '.#.....#.', '#..###..#', '#.#...#.#', '#.#.#.#.#', '#.#...#.#', '#..###..#', '.#.....#.', '..#####..'],
    'hand':   ['...#.#...', '.#.#.#.#.', '.#.#.#.#.', '.#######.', '########.', '.#######.', '.######..', '..#####..', '..#####..'],
    'coin':   ['..#####..', '.#######.', '##.....##', '##.###.##', '##.#.#.##', '##.###.##', '##.....##', '.#######.', '..#####..'],
}


def icon(name, color=WHITE, outline=INK, scale=1):
    rows = ICONS[name]
    L = Layer(len(rows[0]) + 2, len(rows) + 3)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == '#':
                L.px(x + 1, y + 1, color)
    if outline:
        a = L.arr(); m = a[..., 3] > 0
        import numpy as np
        g = np.zeros_like(m)
        g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
        sh = np.zeros_like(m); sh[1:] = (g | m)[:-1]
        a[(g | sh) & ~m] = rgba(outline)
        L.set(a)
    img = L.img
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST) if scale > 1 else img


def icon_button(name, color='orange', state='normal', size=20, round_=True):
    base = C('grey') if state == 'disabled' else C(color)
    if state == 'hover':
        base = shade(base, .18)
    off = 2 if state == 'pressed' else 0
    lip = 1 if state == 'pressed' else 3
    L = Layer(size + 2, size + 2)
    r = size // 2 if round_ else 4
    L.rrect(1, 1 + off, size, size - off, r, shade(base, -.45))
    L.rrect(1, 1 + off, size, size - lip - off, r, base)
    L.rrect(4, 2 + off, size - 6, (size - lip) // 2 - 1, r - 2 if r > 2 else 1, shade(base, .22))
    L.outline()
    ic = icon(name, WHITE, shade(base, -.55))
    L.img.alpha_composite(ic, ((size + 2 - ic.width) // 2, 1 + off + (size - lip - ic.height) // 2 + 1))
    return L.img


# --------------------------------------------------------------- panels
def panel(w, h, color=(58, 50, 92), border=None, title=None, title_color='orange'):
    border = border or shade(color, .25)
    L = Layer(w, h + 3)
    L.rrect(1, 3, w - 2, h - 1, 5, shade(color, -.5))            # drop
    L.rrect(1, 1, w - 2, h - 2, 5, border)
    L.rrect(3, 3, w - 6, h - 6, 4, color)
    L.rrect(3, 3, w - 6, 3, 2, shade(color, -.25))                 # inner top shadow
    L.outline()
    img = L.img
    if title:
        rb = ribbon(title, title_color, max(text_width(title) + 30, w // 2))
        img.alpha_composite(rb, ((w - rb.width) // 2, 0)) if rb.height < h else None
    return img


def ribbon(text, color='red', width=None):
    t = render(text, fill=WHITE, outline=shade(C(color), -.6), shadow=1)
    w = width or t.width + 28
    h = t.height + 8
    base = C(color)
    L = Layer(w + 2, h + 6)
    dk = shade(base, -.4)
    # tails
    L.poly([(1, 5), (12, 5), (12, h + 4), (1, h + 4), (5, h // 2 + 4)], dk)
    L.poly([(w, 5), (w - 11, 5), (w - 11, h + 4), (w, h + 4), (w - 4, h // 2 + 4)], dk)
    L.outline()
    L2 = Layer(w + 2, h + 6)
    L2.rect(8, 1, w - 14, h, base)
    L2.rect(8, 1, w - 14, 2, shade(base, .3))
    L2.rect(8, h - 1, w - 14, 1, shade(base, -.25))
    L2.poly([(8, h + 1), (12, h + 4), (12, h)], shade(base, -.6))
    L2.poly([(w - 7, h + 1), (w - 11, h + 4), (w - 11, h)], shade(base, -.6))
    L2.outline()
    L.paste(L2)
    L.img.alpha_composite(t, ((w + 2 - t.width) // 2, 1 + (h - t.height) // 2 + 1))
    return L.img


# --------------------------------------------------------------- logo
def logo(text='ARCHIDON', sub='CAMERA DUEL'):
    W, H = 150, 86
    L = Layer(W, H)
    cx, cy = W // 2, 30
    # crossed arrows behind the emblem
    A = Layer(W, H)
    for sgn in (-1, 1):
        a0 = (cx - sgn * 40, cy + 26); a1 = (cx + sgn * 40, cy - 26)
        A.thick(a0, a1, 2, (190, 120, 64))
        tip = a1
        A.poly([(tip[0] + sgn * 5, tip[1] - 4), (tip[0] - sgn * 3, tip[1] - 2), (tip[0] + sgn * 1, tip[1] + 4)], (220, 228, 240))
        for k in (0, 4):
            b = (a0[0] + sgn * k, a0[1] - k * 26 / 40)
            A.poly([(b[0], b[1]), (b[0] - sgn * 5, b[1] - 1), (b[0] - sgn * 3, b[1] + 4)], (238, 72, 72))
    A.auto_shade((190, 120, 64), hi=False)
    A.outline()
    L.paste(A)
    # target emblem (shield-like octagon)
    E = Layer(W, H)
    E.poly([(cx - 17, cy - 24), (cx + 17, cy - 24), (cx + 26, cy - 13), (cx + 26, cy + 8),
            (cx, cy + 26), (cx - 26, cy + 8), (cx - 26, cy - 13)], (92, 214, 120))
    E.auto_shade((92, 214, 120), dx=3, dy=3)
    E.outline()
    for r, c in ((19, WHITE), (15, (238, 72, 72)), (11, WHITE), (7, (238, 72, 72)), (3, (255, 210, 64))):
        E.ell(cx - r, cy - r - 2, 2 * r + 1, 2 * r + 1, c)
    E.outline()
    # arrow stuck in bullseye
    E.thick((cx + 1, cy - 2), (cx + 14, cy - 15), 1, (122, 82, 52))
    E.poly([(cx + 14, cy - 15), (cx + 19, cy - 17), (cx + 16, cy - 12)], (238, 72, 72))
    L.paste(E)
    # title banner
    t = render(text, grad=((255, 236, 120), (255, 160, 48)), outline=INK, outline_w=1, shadow=1,
               inner_hi=True, spacing=1)
    t = t.resize((t.width * 2, t.height * 2), Image.NEAREST)
    rb_w = t.width + 30
    R = Layer(rb_w + 4, 30)
    red = (226, 64, 52)
    R.poly([(0, 8), (14, 8), (14, 28), (0, 28), (5, 18)], shade(red, -.4))
    R.poly([(rb_w + 3, 8), (rb_w - 11, 8), (rb_w - 11, 28), (rb_w + 3, 28), (rb_w - 2, 18)], shade(red, -.4))
    R.outline()
    R2 = Layer(rb_w + 4, 30)
    R2.poly([(8, 3), (rb_w - 5, 3), (rb_w - 5, 25), (8, 25)], red)
    R2.rect(8, 3, rb_w - 12, 3, shade(red, .3))
    R2.rect(8, 23, rb_w - 12, 2, shade(red, -.25))
    R2.outline()
    R.paste(R2)
    R.img.alpha_composite(t, ((rb_w + 4 - t.width) // 2, 3 + (22 - t.height) // 2 + 1))
    L.img.alpha_composite(R.img, ((W - R.w) // 2, 44))
    if sub:
        s = render(sub, fill=(255, 245, 220), outline=INK, shadow=1)
        L.img.alpha_composite(s, ((W - s.width) // 2, 73))
    return L.img


def vs_badge(size=40):
    L = Layer(size + 2, size + 4)
    c = size // 2 + 1
    L.poly([(c, 1), (size, c), (c, size), (1, c)], shade(WHITE, -.15))
    L.poly([(c, 1), (size, c), (c, size - 3), (1, c)], WHITE)
    L.outline()
    t = render('VS', fill=(238, 72, 72), outline=INK, shadow=1)
    if size >= 40:
        t = t.resize((t.width * 2, t.height * 2), Image.NEAREST)
    L.img.alpha_composite(t, (c - t.width // 2, c - t.height // 2 - 1))
    return L.img


# --------------------------------------------------------------- card + bars
def card(portrait, name, color, state='normal', w=64, h=84):
    """Character select card. state: normal | selected | locked."""
    base = C(color)
    frame = WHITE if state == 'selected' else shade(base, .45)
    L = Layer(w + 2, h + 4)
    L.rrect(1, 3, w, h, 5, shade(base, -.5))
    L.rrect(1, 1, w, h, 5, frame)
    L.outline()
    img = L.img
    # art window: base colour + diagonal stripes + portrait, clipped to rounded rect
    win = Layer(w + 2, h + 4)
    win.rrect(4, 4, w - 6, h - 21, 4, WHITE)
    m = win.img.split()[3]
    art = Layer(w + 2, h + 4)
    art.rect(0, 0, w + 2, h + 4, base)
    for i in range(-h, w + h, 9):
        art.line([(i, h), (i + h, 0)], shade(base, .14), 3)
    art.rect(0, h - 30, w + 2, 14, shade(base, -.18))       # floor band
    art.img.alpha_composite(portrait, ((w + 2 - portrait.width) // 2, h - 17 - portrait.height))
    if state == 'locked':
        art.img.alpha_composite(Image.new('RGBA', art.img.size, (20, 16, 34, 190)))
        q = render('?', fill=(200, 200, 215), outline=INK)
        q = q.resize((q.width * 3, q.height * 3), Image.NEAREST)
        art.img.alpha_composite(q, ((w + 2 - q.width) // 2, (h - 20) // 2 - q.height // 2))
    img.paste(art.img, (0, 0), m)
    # name plate
    sel = state == 'selected'
    t = render(name, fill=INK if sel else WHITE, outline=None if sel else INK, shadow=0 if sel else 1)
    if t.width > w - 6:
        t = render(name, bold=False, fill=INK if sel else WHITE, outline=None if sel else INK, shadow=0 if sel else 1)
    img.alpha_composite(t, ((w + 2 - t.width) // 2, h - 13))
    return img


def health_bar(w, frac, color=(92, 214, 120), lost=0.0, name=None, flip=False):
    L = Layer(w + 2, 14)
    L.rrect(1, 1, w, 11, 3, (40, 30, 56))
    inner_w = w - 16
    x0 = 14
    fill = int(inner_w * frac)
    lostw = int(inner_w * lost)
    L.rect(x0, 3, inner_w, 7, (24, 18, 36))
    if lostw:
        L.rect(x0 + fill, 3, lostw, 7, (255, 236, 160))
    if fill:
        L.rect(x0, 3, fill, 7, color)
        L.rect(x0, 3, fill, 2, shade(color, .35))
        L.rect(x0, 8, fill, 2, shade(color, -.25))
    for sx in range(x0 + 8, x0 + inner_w, 8):
        L.rect(sx, 3, 1, 7, (24, 18, 36, 110))
    L.outline()
    img = L.img
    ht = icon('heart', (238, 72, 72), INK)
    img.alpha_composite(ht, (2, 1))
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        ht2 = icon('heart', (238, 72, 72), INK)
        img.alpha_composite(ht2, (w + 2 - ht2.width - 2, 1))
        # re-blank the mirrored heart on the left
    return img


def pull_meter(w, frac):
    L = Layer(w + 2, 9)
    L.rrect(1, 1, w, 7, 2, (40, 30, 56))
    cols = [(92, 214, 120), (255, 210, 64), (255, 150, 52), (238, 72, 72)]
    fill = int((w - 4) * frac)
    for x in range(fill):
        c = cols[min(3, int(4 * x / (w - 4)))]
        L.rect(3 + x, 3, 1, 3, c)
        L.px(3 + x, 3, shade(c, .4))
    L.outline()
    return L.img


def pill(text, icon_name='coin', color=(255, 210, 64)):
    t = render(text, fill=WHITE, outline=INK, shadow=1)
    w = t.width + 20
    L = Layer(w + 2, 16)
    L.rrect(6, 2, w - 6, 12, 6, (40, 30, 56))
    L.outline()
    img = L.img
    ic = icon(icon_name, color, INK)
    img.alpha_composite(ic, (0, 1))
    img.alpha_composite(t, (14, 3))
    return img


def stamp(text, color='green'):
    t = render(text, fill=WHITE, outline=shade(C(color), -.6), shadow=1)
    L = Layer(t.width + 10, t.height + 6)
    L.rrect(1, 1, t.width + 8, t.height + 4, 3, C(color))
    L.rect(2, 2, t.width + 6, 1, shade(C(color), .4))
    L.outline()
    L.img.alpha_composite(t, (5, 3))
    return L.img.rotate(8, resample=Image.NEAREST, expand=True)
