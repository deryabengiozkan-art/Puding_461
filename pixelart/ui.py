"""Pixel UI kit: buttons (4 states), icon buttons, panels, ribbons, logo, VS badge,
character cards, health / pull bars. All functions return *native-size* surfaces;
scale them with ``kit.big`` (or use ``Painter`` in the renderers)."""
import functools
import numpy as np
import pygame
from .kit import Layer, rgba, shade, INK, WHITE, surface, big, flip, clip_to, to_array, from_array
from .font import render, width as text_width

PALETTE = {
    'green': (92, 214, 120), 'orange': (255, 150, 52), 'blue': (72, 156, 240),
    'red': (238, 72, 72), 'purple': (156, 96, 230), 'pink': (246, 100, 150),
    'yellow': (255, 210, 64), 'teal': (56, 196, 190), 'grey': (150, 150, 168),
    'night': (62, 52, 104),
}
PANEL = (62, 52, 104)
PANEL_DARK = (36, 30, 62)
BG = (44, 36, 76)


def C(c):
    return PALETTE.get(c, c) if isinstance(c, str) else c


def _fit_label(label, max_w, color, outline):
    t = render(label, fill=color, outline=outline, shadow=1)
    if t.get_width() > max_w:
        t = render(label, fill=color, outline=outline, shadow=1, bold=False)
    return t


# --------------------------------------------------------------- buttons
@functools.lru_cache(maxsize=256)
def button(w, h, label, color='green', state='normal', icon_name=None):
    """state: normal | hover | pressed | disabled | selected."""
    base = C('grey') if state == 'disabled' else C(color)
    if state in ('hover', 'selected'):
        base = shade(base, .18)
    lip = 1 if state == 'pressed' else 4
    off = 3 if state == 'pressed' else 0
    L = Layer(w + 2, h + 2)
    L.rrect(1, 1 + off, w, h - off, 4, shade(base, -.45))
    fh = h - lip - off
    L.rrect(1, 1 + off, w, fh, 4, base)
    L.rrect(3, 2 + off, w - 4, max(2, fh // 2 - 1), 3, shade(base, .22))
    L.rect(4, 2 + off, w - 8, 1, shade(base, .55))
    L.rect(w - 3, 3 + off, 1, 2, shade(base, .65))
    L.outline(WHITE if state == 'selected' else INK)
    img = L.surf
    txt_col = (235, 235, 240) if state == 'disabled' else WHITE
    ic = icon(icon_name, WHITE, shade(base, -.55)) if icon_name else None
    ix = ic.get_width() + 3 if ic else 0
    t = _fit_label(label, w - 8 - ix, txt_col, shade(base, -.55))
    tx = (w + 2 - t.get_width() - ix) // 2 + ix
    ty = 1 + off + (fh - t.get_height()) // 2 + 1
    if ic:
        img.blit(ic, (tx - ix, ty + (t.get_height() - ic.get_height()) // 2))
    img.blit(t, (tx, ty))
    if state == 'hover':
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (0, 0)):
            img.set_at((w - 5 + dx, 5 + dy + off), rgba(WHITE))
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
    'mouse':  ['..####...', '.#..#.#..', '.#..#.#..', '.####.#..', '.#....#..', '.#....#..', '.#....#..', '..####...', '.........'],
    'keys':   ['.........', '#########', '#.#.#.#.#', '#########', '#.#.#.#.#', '#########', '#..###..#', '#########', '.........'],
    'quit':   ['.........', '##.....##', '.##...##.', '..##.##..', '...###...', '..##.##..', '.##...##.', '##.....##', '.........'],
    'sun':    ['#...#...#', '.#.....#.', '...###...', '..#####..', '#.#####.#', '..#####..', '...###...', '.#.....#.', '#...#...#'],
    'moon':   ['...####..', '..###....', '.###.....', '.###.....', '.###.....', '.###.....', '..###...#', '...######', '.....###.'],
    'users':  ['.##...##.', '####.####', '####.####', '.##...##.', '.........', '####.####', '#########', '#########', '.........'],
}


@functools.lru_cache(maxsize=128)
def icon(name, color=WHITE, outline=INK):
    rows = ICONS[name]
    L = Layer(len(rows[0]) + 2, len(rows) + 3)
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == '#':
                L.px(x + 1, y + 1, color)
    if outline:
        a = L.arr(); m = a[..., 3] > 0
        g = np.zeros_like(m)
        g[1:] |= m[:-1]; g[:-1] |= m[1:]; g[:, 1:] |= m[:, :-1]; g[:, :-1] |= m[:, 1:]
        sh = np.zeros_like(m); sh[1:] = (g | m)[:-1]
        a[(g | sh) & ~m] = rgba(outline)
        L.set(a)
    return L.surf


@functools.lru_cache(maxsize=128)
def icon_button(name, color='orange', state='normal', size=20):
    base = C('grey') if state == 'disabled' else C(color)
    if state == 'hover':
        base = shade(base, .18)
    off = 2 if state == 'pressed' else 0
    lip = 1 if state == 'pressed' else 3
    L = Layer(size + 2, size + 2)
    r = size // 2
    L.rrect(1, 1 + off, size, size - off, r, shade(base, -.45))
    L.rrect(1, 1 + off, size, size - lip - off, r, base)
    L.rrect(4, 2 + off, size - 6, (size - lip) // 2 - 1, r - 2, shade(base, .22))
    L.outline()
    ic = icon(name, WHITE, shade(base, -.55))
    L.surf.blit(ic, ((size + 2 - ic.get_width()) // 2, 1 + off + (size - lip - ic.get_height()) // 2 + 1))
    return L.surf


# --------------------------------------------------------------- panels
@functools.lru_cache(maxsize=64)
def panel(w, h, color=PANEL, border=None, inset=False):
    border = border or shade(color, .25)
    L = Layer(w, h + 3)
    if inset:
        L.rrect(1, 1, w - 2, h - 2, 4, shade(color, -.35))
        L.rrect(1, 3, w - 2, h - 4, 4, color)
        L.outline()
        return L.surf
    L.rrect(1, 3, w - 2, h - 1, 5, shade(color, -.5))
    L.rrect(1, 1, w - 2, h - 2, 5, border)
    L.rrect(3, 3, w - 6, h - 6, 4, color)
    L.rrect(3, 3, w - 6, 3, 2, shade(color, -.25))
    L.outline()
    return L.surf


@functools.lru_cache(maxsize=64)
def ribbon(text, color='red', width=None):
    t = render(text, fill=WHITE, outline=shade(C(color), -.6), shadow=1)
    w = width or t.get_width() + 28
    h = t.get_height() + 8
    base = C(color)
    L = Layer(w + 2, h + 6)
    dk = shade(base, -.4)
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
    L.surf.blit(t, ((w + 2 - t.get_width()) // 2, 1 + (h - t.get_height()) // 2 + 1))
    return L.surf


# --------------------------------------------------------------- logo
@functools.lru_cache(maxsize=4)
def logo(text='ARCHIDON', sub='CAMERA DUEL'):
    W, H = 150, 86
    L = Layer(W, H)
    cx, cy = W // 2, 30
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
    E = Layer(W, H)
    E.poly([(cx - 17, cy - 24), (cx + 17, cy - 24), (cx + 26, cy - 13), (cx + 26, cy + 8),
            (cx, cy + 26), (cx - 26, cy + 8), (cx - 26, cy - 13)], (92, 214, 120))
    E.auto_shade((92, 214, 120), dx=3, dy=3)
    E.outline()
    for r, c in ((19, WHITE), (15, (238, 72, 72)), (11, WHITE), (7, (238, 72, 72)), (3, (255, 210, 64))):
        E.ell(cx - r, cy - r - 2, 2 * r + 1, 2 * r + 1, c)
    E.outline()
    E.thick((cx + 1, cy - 2), (cx + 14, cy - 15), 1, (122, 82, 52))
    E.poly([(cx + 14, cy - 15), (cx + 19, cy - 17), (cx + 16, cy - 12)], (238, 72, 72))
    L.paste(E)
    t = render(text, grad=((255, 236, 120), (255, 160, 48)), outline=INK, outline_w=1, shadow=1, inner_hi=True)
    t = big(t, 2)
    rb_w = t.get_width() + 30
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
    R.surf.blit(t, ((rb_w + 4 - t.get_width()) // 2, 3 + (22 - t.get_height()) // 2 + 1))
    L.surf.blit(R.surf, ((W - R.w) // 2, 44))
    if sub:
        s = render(sub, fill=(255, 245, 220), outline=INK, shadow=1)
        L.surf.blit(s, ((W - s.get_width()) // 2, 73))
    return L.surf


@functools.lru_cache(maxsize=4)
def vs_badge(size=48):
    L = Layer(size + 2, size + 4)
    c = size // 2 + 1
    L.poly([(c, 1), (size, c), (c, size), (1, c)], shade(WHITE, -.15))
    L.poly([(c, 1), (size, c), (c, size - 3), (1, c)], WHITE)
    L.outline()
    t = render('VS', fill=(238, 72, 72), outline=INK, shadow=1)
    if size >= 40:
        t = big(t, 2)
    L.surf.blit(t, (c - t.get_width() // 2, c - t.get_height() // 2 - 1))
    return L.surf


# --------------------------------------------------------------- card + bars
def card(portrait, name, color, state='normal', w=58, h=45):
    """Character select card. state: normal | selected | locked | hover."""
    base = C(color)
    frame = WHITE if state == 'selected' else shade(base, .62 if state == 'hover' else .45)
    L = Layer(w + 2, h + 4)
    L.rrect(1, 3, w, h, 5, shade(base, -.5))
    L.rrect(1, 1, w, h, 5, frame)
    L.outline()
    img = L.surf
    win = Layer(w + 2, h + 4)
    win.rrect(4, 4, w - 6, h - 17, 4, WHITE)
    art = Layer(w + 2, h + 4)
    art.rect(0, 0, w + 2, h + 4, base)
    for i in range(-h, w + h, 9):
        art.line([(i, h), (i + h, 0)], shade(base, .14), 3)
    art.rect(0, h - 22, w + 2, 10, shade(base, -.18))
    art.surf.blit(portrait, ((w + 2 - portrait.get_width()) // 2, h - 13 - portrait.get_height()))
    img.blit(clip_to(art.surf, win.surf), (0, 0))
    sel = state == 'selected'
    t = render(name, fill=INK if sel else WHITE, outline=None if sel else INK, shadow=0 if sel else 1)
    if t.get_width() > w - 6:
        t = render(name, bold=False, fill=INK if sel else WHITE, outline=None if sel else INK, shadow=0 if sel else 1)
    img.blit(t, ((w + 2 - t.get_width()) // 2, h - 11))
    return img


def health_bar(w, frac, color=(92, 214, 120), lost=0.0, flip_it=False):
    frac = max(0., min(1., frac))
    lost = max(0., min(1. - frac, lost))
    L = Layer(w + 2, 14)
    L.rrect(1, 1, w, 11, 3, (40, 30, 56))
    inner_w = w - 16
    x0 = 14
    fill = int(round(inner_w * frac))
    lostw = int(round(inner_w * lost))
    L.rect(x0, 3, inner_w, 7, (24, 18, 36))
    if lostw:
        L.rect(x0 + fill, 3, lostw, 7, (255, 236, 160))
    if fill:
        L.rect(x0, 3, fill, 7, color)
        L.rect(x0, 3, fill, 2, shade(color, .35))
        L.rect(x0, 8, fill, 2, shade(color, -.25))
    for sx in range(x0 + 8, x0 + inner_w, 8):
        L.rect(sx, 3, 1, 7, (24, 18, 36, 255))
    L.outline()
    img = L.surf
    ht = icon('heart', (238, 72, 72), INK)
    if flip_it:
        img = flip(img)
        img.blit(ht, (w + 2 - ht.get_width() - 2, 1))
    else:
        img.blit(ht, (2, 1))
    return img


def pull_meter(w, frac):
    frac = max(0., min(1., frac))
    L = Layer(w + 2, 9)
    L.rrect(1, 1, w, 7, 2, (40, 30, 56))
    cols = [(92, 214, 120), (255, 210, 64), (255, 150, 52), (238, 72, 72)]
    fill = int((w - 4) * frac)
    for x in range(fill):
        c = cols[min(3, int(4 * x / (w - 4)))]
        L.rect(3 + x, 3, 1, 3, c)
        L.px(3 + x, 3, shade(c, .4))
    L.outline()
    return L.surf


def pill(text, icon_name='coin', color=(255, 210, 64)):
    t = render(text, fill=WHITE, outline=INK, shadow=1)
    w = t.get_width() + 20
    L = Layer(w + 2, 16)
    L.rrect(6, 2, w - 6, 12, 6, (40, 30, 56))
    L.outline()
    img = L.surf
    img.blit(icon(icon_name, color, INK), (0, 1))
    img.blit(t, (14, 3))
    return img


@functools.lru_cache(maxsize=32)
def stamp(text, color='green', angle=8):
    t = render(text, fill=WHITE, outline=shade(C(color), -.6), shadow=1)
    L = Layer(t.get_width() + 10, t.get_height() + 6)
    L.rrect(1, 1, t.get_width() + 8, t.get_height() + 4, 3, C(color))
    L.rect(2, 2, t.get_width() + 6, 1, shade(C(color), .4))
    L.outline()
    L.surf.blit(t, (5, 3))
    return pygame.transform.rotate(L.surf, angle) if angle else L.surf


@functools.lru_cache(maxsize=32)
def arrow_sprite(angle_deg, fletch=(240, 80, 70)):
    """A flying arrow drawn natively for a given screen angle (0 = right, + = up)."""
    import math
    r = math.radians(angle_deg)
    d = (math.cos(r), -math.sin(r))
    n = (-d[1], d[0])
    L = Layer(36, 36)
    c = (18, 18)
    tail = (c[0] - d[0] * 12, c[1] - d[1] * 12)
    tip = (c[0] + d[0] * 10, c[1] + d[1] * 10)
    L.line([tail, tip], (122, 82, 52))
    L.poly([(tip[0] + d[0] * 4, tip[1] + d[1] * 4), (tip[0] + n[0] * 2, tip[1] + n[1] * 2),
            (tip[0] - n[0] * 2, tip[1] - n[1] * 2)], (210, 220, 232))
    for k in (0, 2):
        bx, by = tail[0] + d[0] * k, tail[1] + d[1] * k
        L.line([(bx, by), (bx - d[0] * 2 + n[0] * 2, by - d[1] * 2 + n[1] * 2)], fletch)
        L.line([(bx, by), (bx - d[0] * 2 - n[0] * 2, by - d[1] * 2 - n[1] * 2)], fletch)
    L.outline()
    return L.surf


def ring(radius, color, thickness=1):
    r = max(2, int(radius))
    L = Layer(2 * r + 3, 2 * r + 3)
    pygame.draw.circle(L.surf, rgba(color), (r + 1, r + 1), r, thickness)
    return L.surf
