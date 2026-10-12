"""Original big-head pixel archers (Bowmasters-like proportions, all-new designs).

Native sprite canvas 64x70, facing right, feet centred at (FX, GY).
A character = body parts (legs, torso, head, accessories) + an aim rig
(arms, bow, string, arrow) that is re-drawn natively for any angle/pull so
in-game aiming never needs blurry sprite rotation.
"""
import math
from common import Layer, rgba, shade, INK, WHITE

W, H = 76, 80
TOP = 10                 # headroom for hats / feathers
FX, GY = 24, 68 + TOP
SHOULDER = (27, 42)
ARM = 20
HEAD = (7, 3 + TOP)           # head-local origin on the canvas

SKIN = (255, 196, 150)
SKIN2 = (196, 128, 92)
TAN = (214, 150, 104)
MOUTH = (96, 22, 44)
TONGUE = (234, 82, 96)


# ----------------------------------------------------------------- face kit
def eyes(L, x=16, y=13, gap=7, look=1, h=4, lid=None):
    for ex in (x, x + gap):
        L.rect(ex, y, 3, h, WHITE)
        L.rect(ex + (1 if look > 0 else 0), y + 1, 2, 2 if h < 4 else 3 - (1 if h == 3 else 0), INK)
        if lid:
            L.rect(ex, y, 3, 1, lid)


def brows(L, c, x=15, y=11, gap=7, angry=False):
    for i, ex in enumerate((x, x + gap)):
        L.rect(ex, y, 4, 1, c)
        if angry:
            L.px(ex + (3 if i == 0 else 0), y + 1, c)


def grin(L, x=18, y=24, w=9, h=4):
    L.rect(x, y, w, h, MOUTH)
    L.rect(x + 1, y, w - 2, 1, WHITE)
    L.rect(x + 2, y + h - 1, w - 4, 1, TONGUE)
    L.px(x, y + h - 1, (0, 0, 0, 0)); L.px(x + w - 1, y + h - 1, (0, 0, 0, 0))


def shout(L, x=19, y=23, w=7, h=6):
    L.ell(x, y, w, h, MOUTH)
    L.rect(x + 1, y, w - 2, 1, WHITE)
    L.rect(x + 2, y + h - 2, w - 4, 1, TONGUE)


def nose(L, x=24, y=15, c=SKIN, w=7, h=6):
    L.ell(x, y, w, h, c)
    L.px(x + 1, y + 1, shade(c, .4))


def ear(L, c=SKIN, x=5, y=16):
    L.ell(x, y, 5, 7, c)
    L.rect(x + 1, y + 2, 2, 3, shade(c, -.25))


# ----------------------------------------------------------------- body kit
def legs_fn(cfg, which, walk=0):
    pants, shoes = cfg['pants'], cfg['shoes']
    def f(L):
        if which == 'back':
            x = FX - 6 - walk
            L.rect(x, 52, 4, 12, pants)
            L.rrect(x - 2, 62, 8, 5, 2, shoes)
            L.rect(x - 2, 65, 8, 2, shoes)
        else:
            x = FX + 1 + walk
            L.rect(x, 52, 4, 12, pants)
            L.rrect(x - 1, 62, 8, 5, 2, shoes)
            L.rect(x - 1, 65, 8, 2, shoes)
        if cfg.get('cuff'):
            L.rect(x - (2 if which == 'back' else 1), 61, 8, 1, cfg['cuff'])
    return f


def torso_fn(cfg):
    shirt = cfg['shirt']
    def f(L):
        L.poly([(FX - 8, 36), (FX + 8, 36), (FX + 10, 54), (FX - 10, 54)], shirt)
        if cfg.get('belt'):
            L.rect(FX - 10, 49, 21, 3, cfg['belt'])
            L.rect(FX + 1, 49, 4, 3, cfg.get('buckle', (250, 206, 80)))
            L.rect(FX + 2, 50, 2, 1, cfg['belt'])
        if cfg.get('torso_extra'):
            cfg['torso_extra'](L)
    return f


# ----------------------------------------------------------------- aim rig
def _v(a):
    r = math.radians(a)
    return math.cos(r), -math.sin(r)


def bow_points(cfg, hand, d, n, pull):
    style = cfg.get('bow', 'long')
    R = 13
    pts = []
    for i in range(-10, 11):
        t = i / 10
        bend = 1 - t * t
        along = (5 + 2 * pull) * bend
        if style == 'recurve':
            along = (6 + 2 * pull) * bend - 3.2 * max(0, abs(t) - .72) / .28
        if style == 'compound':
            along = 4 * bend
        pts.append((hand[0] + d[0] * along + n[0] * R * t,
                    hand[1] + d[1] * along + n[1] * R * t))
    return pts


def aim_parts(cfg, angle=15, pull=.7, arrow=True):
    """List of (fn, bases) for the arm/bow rig at a given angle (deg, + up) and pull 0..1."""
    sx, sy = SHOULDER
    d = _v(angle)
    n = (-d[1], d[0])                      # perpendicular (points 'down' when aiming right)
    up = (d[1], -d[0])
    hand = (sx + d[0] * ARM, sy + d[1] * ARM)
    pull_hand = (sx + d[0] * (ARM - 6 - 12 * pull), sy + d[1] * (ARM - 6 - 12 * pull))
    elbow = (sx - d[0] * 6 + up[0] * 2, sy - d[1] * 6 + up[1] * 2)
    sleeve, skin = cfg['sleeve'], cfg.get('hands', SKIN)
    bowc, wood = cfg.get('bowc', (176, 104, 56)), cfg.get('grip', (110, 60, 40))
    bp = bow_points(cfg, hand, d, n, pull)
    tips = (bp[0], bp[-1])
    if cfg.get('bow') == 'compound':
        tips = (bp[2], bp[-3])
    parts = []

    def bow(L):
        for a_, b_ in zip(bp, bp[1:]):
            L.thick(a_, b_, 2, bowc)
        L.thick(bp[8], bp[12], 3, wood)
        if cfg.get('bow') == 'compound':
            for p in (bp[1], bp[-2]):
                L.ell(p[0] - 2, p[1] - 2, 5, 5, (190, 196, 210))
                L.px(p[0], p[1], INK)
        if cfg.get('bow') == 'recurve':
            for p in (bp[0], bp[-1]):
                L.rect(p[0] - 1, p[1] - 1, 2, 2, (250, 206, 80))
    parts.append((bow, [bowc]))

    def string(L):
        L.line([tips[0], pull_hand, tips[1]], cfg.get('stringc', (250, 240, 214)))
    parts.append((string, 'raw'))

    if arrow:
        def arr(L):
            tail = (pull_hand[0] - d[0] * 2, pull_hand[1] - d[1] * 2)
            tip = (pull_hand[0] + d[0] * 25, pull_hand[1] + d[1] * 25)
            L.line([tail, tip], (122, 82, 52))
            head = [(tip[0] + d[0] * 4, tip[1] + d[1] * 4),
                    (tip[0] + n[0] * 2, tip[1] + n[1] * 2),
                    (tip[0] - n[0] * 2, tip[1] - n[1] * 2)]
            L.poly(head, (210, 220, 232))
            fc = cfg.get('fletch', (240, 80, 70))
            for k in (0, 2):
                bx, by = tail[0] + d[0] * k, tail[1] + d[1] * k
                L.line([(bx, by), (bx - d[0] * 2 + n[0] * 2, by - d[1] * 2 + n[1] * 2)], fc)
                L.line([(bx, by), (bx - d[0] * 2 - n[0] * 2, by - d[1] * 2 - n[1] * 2)], fc)
        parts.append((arr, None))

    def front_arm(L):
        mid = (sx + d[0] * 10, sy + d[1] * 10)
        L.thick((sx, sy), mid, 4, sleeve)
        L.thick(mid, hand, 3, cfg.get('forearm', skin))
        L.rect(hand[0] - 2, hand[1] - 2, 4, 4, skin)
        if cfg.get('glove'):
            L.rect(hand[0] - 2, hand[1] - 2, 4, 4, cfg['glove'])
    parts.append((front_arm, [sleeve]))

    def pull_arm(L):
        L.thick((sx, sy), elbow, 4, sleeve)
        L.thick(elbow, pull_hand, 3, cfg.get('forearm', skin))
        c = cfg.get('glove', skin)
        L.rect(pull_hand[0] - 2, pull_hand[1] - 2, 4, 4, c)
    parts.append((pull_arm, [sleeve]))
    return parts


def idle_parts(cfg, bob=0):
    """Relaxed stance: bow held upright at the side, other hand on the hip."""
    sx, sy = SHOULDER
    sleeve, skin = cfg['sleeve'], cfg.get('hands', SKIN)
    hand = (sx + 8, sy + 9 + bob)
    bp = bow_points(cfg, hand, (1, 0), (0, 1), 0)
    bowc, wood = cfg.get('bowc', (176, 104, 56)), cfg.get('grip', (110, 60, 40))
    def string(L):
        L.line([bp[0], bp[-1]], cfg.get('stringc', (250, 240, 214)))
    def bow(L):
        for a_, b_ in zip(bp, bp[1:]):
            L.thick(a_, b_, 2, bowc)
        L.thick(bp[8], bp[12], 3, wood)
    def back_arm(L):
        L.thick((sx - 8, sy), (sx - 11, sy + 6), 4, sleeve)
        L.thick((sx - 11, sy + 6), (sx - 8, sy + 10), 3, cfg.get('forearm', skin))
        L.rect(sx - 9, sy + 9, 4, 4, cfg.get('glove', skin))
    def front_arm(L):
        L.thick((sx, sy), (sx + 4, sy + 5), 4, sleeve)
        L.thick((sx + 4, sy + 5), hand, 3, cfg.get('forearm', skin))
        L.rect(hand[0] - 2, hand[1] - 2, 4, 4, cfg.get('glove', skin))
    return [(back_arm, [sleeve]), (string, 'raw'), (bow, [bowc]), (front_arm, [sleeve])]


# ----------------------------------------------------------------- characters
def fern_head(L):
    green, dk = (86, 186, 92), (52, 128, 68)
    beard = (226, 116, 52)
    return [
        (lambda L: (ear(L), L.rrect(4, 6, 24, 26, 8, SKIN)), [SKIN]),
        (lambda L: (L.rrect(4, 20, 24, 14, 6, beard), L.rect(4, 17, 4, 8, beard)), [beard]),
        (lambda L: (L.rect(15, 21, 13, 3, beard),), [beard]),
        (lambda L: (L.rrect(3, 1, 25, 11, 5, green), L.poly([(3, 3), (-3, 8), (5, 10)], green)), [green]),
        (lambda L: L.rect(2, 9, 28, 3, dk), [dk]),
        (lambda L: (L.poly([(9, 4), (1, -6), (3, -7), (12, 3)], (238, 70, 60)), L.line([(10, 3), (2, -6)], (255, 196, 150))), None),
        (lambda L: nose(L, 24, 14), [SKIN]),
    ], lambda L: (eyes(L, 16, 13, 7), grin(L, 18, 24, 9, 4))


def flint_head(L):
    steel, horn = (178, 194, 214), (255, 238, 196)
    beard = (214, 100, 44)
    return [
        (lambda L: (ear(L), L.rrect(4, 7, 24, 25, 8, SKIN)), [SKIN]),
        (lambda L: (L.poly([(4, 21), (28, 21), (26, 36), (18, 40), (10, 38), (4, 30)], beard)), [beard]),
        (lambda L: L.rect(16, 21, 12, 3, beard), [beard]),
        (lambda L: (L.poly([(6, 4), (1, -2), (0, 3), (3, 8)], horn), L.poly([(25, 4), (31, -2), (32, 3), (28, 8)], horn)), [horn]),
        (lambda L: (L.rrect(4, 1, 24, 12, 6, steel), L.rect(3, 9, 26, 3, steel)), [steel]),
        (lambda L: (L.rect(14, 1, 3, 12, (250, 206, 80)),), [(250, 206, 80)]),
        (lambda L: nose(L, 24, 15), [SKIN]),
        (lambda L: (L.rect(10, 34, 3, 5, (250, 206, 80)), L.rect(19, 38, 3, 4, (250, 206, 80))), None),
    ], lambda L: (eyes(L, 16, 14, 7), brows(L, beard, 15, 12, 7, True), grin(L, 18, 25, 9, 3))


def torque_head(L):
    hair = (226, 230, 238)
    return [
        (lambda L: (L.poly([(6, 6), (-3, 4), (2, 11), (-4, 14), (3, 17), (-2, 22), (6, 22)], hair),
                    L.poly([(26, 6), (33, 2), (31, 9), (35, 12), (28, 14)], hair)), [hair]),
        (lambda L: (ear(L, SKIN, 5, 15), L.rrect(5, 4, 22, 29, 9, SKIN)), [SKIN]),
        (lambda L: (L.rect(4, 7, 25, 3, (70, 60, 72)),), None),
        (lambda L: (L.ell(10, 4, 8, 7, (120, 110, 120)), L.ell(19, 4, 8, 7, (120, 110, 120)),
                    L.rect(12, 6, 4, 3, (255, 150, 60)), L.rect(21, 6, 4, 3, (255, 150, 60)),
                    L.px(12, 6, (255, 230, 170)), L.px(21, 6, (255, 230, 170))), None),
        (lambda L: L.poly([(16, 30), (22, 30), (20, 36), (18, 36)], hair), [hair]),
        (lambda L: nose(L, 24, 15, SKIN, 8, 8), [SKIN]),
    ], lambda L: (L.rect(14, 15, 5, 5, INK), L.rect(21, 15, 5, 5, INK), L.rect(19, 16, 2, 1, INK),
                  L.rect(15, 16, 3, 3, WHITE), L.rect(22, 16, 3, 3, WHITE),
                  L.rect(16, 17, 2, 2, INK), L.rect(23, 17, 2, 2, INK),
                  brows(L, hair, 14, 13, 7, True), shout(L, 18, 24, 7, 6))


def bolt_head(L):
    metal, dk = (120, 204, 210), (60, 120, 140)
    return [
        (lambda L: (L.rect(15, -2, 2, 7, (150, 150, 170)),), None),
        (lambda L: L.ell(13, -5, 6, 5, (255, 74, 84)), [(255, 74, 84)]),
        (lambda L: (L.rrect(4, 4, 26, 26, 4, metal), L.rect(1, 13, 4, 9, dk)), [metal]),
        (lambda L: (L.rrect(10, 11, 21, 9, 3, (28, 36, 60)),), None),
    ], lambda L: (L.rect(17, 13, 4, 5, (90, 255, 230)), L.rect(24, 13, 4, 5, (90, 255, 230)),
                  L.rect(18, 14, 1, 1, WHITE), L.rect(25, 14, 1, 1, WHITE),
                  L.rect(13, 13, 2, 1, (60, 150, 160)),
                  [L.rect(15 + 3 * i, 24, 2, 3, (40, 60, 80)) for i in range(4)],
                  L.rect(7, 7, 1, 1, dk), L.rect(27, 7, 1, 1, dk), L.rect(7, 27, 1, 1, dk), L.rect(27, 27, 1, 1, dk))


def akinci_head(L):
    felt, band = (250, 244, 228), (204, 48, 52)
    must = (46, 32, 36)
    return [
        (lambda L: (ear(L, TAN, 5, 17), L.rrect(5, 8, 22, 25, 8, TAN)), [TAN]),
        (lambda L: L.poly([(6, 10), (8, -6), (14, -11), (22, -9), (27, 10)], felt), [felt]),
        (lambda L: (L.rect(4, 7, 25, 4, band), L.rect(14, 7, 4, 4, (250, 206, 80)), L.rect(15, 8, 2, 2, (60, 170, 120))), [band]),
        (lambda L: nose(L, 24, 16, TAN, 7, 7), [TAN]),
        (lambda L: L.poly([(16, 23), (27, 22), (32, 20), (33, 23), (28, 26), (22, 26), (16, 27), (12, 25)], must), None),
        (lambda L: grin(L, 19, 27, 7, 3), 'raw'),
        (lambda L: L.poly([(14, 31), (20, 31), (18, 36)], must), None),
    ], lambda L: (eyes(L, 16, 15, 7), brows(L, must, 15, 13, 7, True))


def gourd_head(L):
    pump, dk, straw = (255, 140, 40), (214, 92, 26), (248, 210, 96)
    return [
        (lambda L: (L.ell(2, 6, 30, 27, pump),), [pump]),
        (lambda L: (L.rect(11, 8, 1, 23, dk), L.rect(21, 8, 1, 23, dk)), None),
        (lambda L: (L.rect(15, 0, 4, 8, (110, 150, 60)),), [(110, 150, 60)]),
        (lambda L: (L.ell(-1, 1, 36, 7, straw), L.rrect(7, -6, 20, 9, 3, straw), L.rect(7, 0, 20, 2, (200, 60, 60))), [straw]),
    ], lambda L: (L.poly([(15, 13), (20, 13), (17, 17)], (255, 236, 120)),
                  L.poly([(23, 13), (28, 13), (25, 17)], (255, 236, 120)),
                  L.poly([(14, 23), (30, 21), (28, 27), (16, 28)], (255, 236, 120)),
                  L.rect(18, 22, 2, 2, pump), L.rect(24, 22, 2, 2, pump), L.rect(21, 26, 2, 2, pump))


def overall_extra(L):
    L.rect(FX - 6, 42, 13, 10, (70, 120, 200))
    L.rect(FX - 6, 38, 2, 5, (70, 120, 200)); L.rect(FX + 5, 38, 2, 5, (70, 120, 200))
    L.rect(FX - 3, 45, 5, 4, (230, 80, 80))
    L.rect(FX - 5, 40, 1, 1, (250, 206, 80)); L.rect(FX + 5, 40, 1, 1, (250, 206, 80))


def coat_extra(L):
    L.poly([(FX - 9, 40), (FX - 12, 60), (FX - 4, 60), (FX - 3, 50)], (244, 246, 250))
    L.rect(FX - 1, 36, 3, 16, (90, 160, 220))
    L.poly([(FX - 1, 36), (FX + 1, 42), (FX + 3, 36)], (230, 70, 70))


def armor_extra(L):
    L.rect(FX - 8, 38, 17, 2, (178, 194, 214))
    for i in range(3):
        L.rect(FX - 6 + 5 * i, 43, 3, 3, (178, 194, 214))


def robot_extra(L):
    L.rrect(FX - 5, 39, 11, 8, 2, (255, 160, 60))
    L.rect(FX - 3, 41, 2, 2, (90, 255, 230)); L.rect(FX + 1, 41, 2, 2, (255, 74, 84))
    L.rect(FX - 3, 44, 7, 1, (120, 70, 40))


def kaftan_extra(L):
    L.poly([(FX - 2, 36), (FX + 3, 36), (FX + 6, 54), (FX - 1, 54)], (250, 206, 80))
    L.poly([(FX - 1, 36), (FX + 2, 36), (FX + 5, 54), (FX, 54)], (176, 30, 44))
    for y in (40, 44):
        L.rect(FX - 3, y, 9, 1, (250, 206, 80))


def quiver(c=(150, 86, 50)):
    def f(L):
        L.poly([(FX - 12, 33), (FX - 7, 30), (FX - 1, 50), (FX - 6, 52)], c)
        for i, col in enumerate([(240, 80, 70), (250, 240, 214), (240, 80, 70)]):
            L.poly([(FX - 12 + i * 2, 31 - i), (FX - 14 + i * 2, 25 - i), (FX - 10 + i * 2, 27 - i)], col)
    return f


def cape(c):
    def f(L):
        L.poly([(FX - 6, 36), (FX - 15, 62), (FX - 4, 60), (FX + 2, 38)], c)
    return f


def straw_tufts(L):
    for x, y in ((FX - 11, 54), (FX - 8, 56), (FX + 9, 55)):
        L.poly([(x, y), (x - 2, y + 4), (x + 2, y + 2)], (248, 210, 96))


CHARACTERS = {
    'fern': dict(name='FERN', title='FOREST RANGER', color=(110, 225, 140),
                 head=fern_head, shirt=(86, 186, 92), sleeve=(86, 186, 92), pants=(48, 110, 70),
                 shoes=(120, 70, 44), belt=(120, 70, 44), back=quiver(), glove=(150, 90, 52),
                 bow='long', bowc=(232, 160, 64), fletch=(238, 70, 60)),
    'flint': dict(name='FLINT', title='STORM VIKING', color=(255, 184, 84),
                  head=flint_head, shirt=(64, 112, 196), sleeve=(64, 112, 196), pants=(70, 76, 100),
                  shoes=(110, 64, 44), belt=(120, 70, 44), back=cape((196, 52, 76)), cuff=(240, 230, 210),
                  torso_extra=armor_extra, bow='long', bowc=(130, 210, 240), grip=(64, 112, 196)),
    'torque': dict(name='PROF. TORQUE', title='MAD ENGINEER', color=(255, 150, 60),
                   head=torque_head, shirt=(244, 246, 250), sleeve=(244, 246, 250), pants=(110, 80, 64),
                   shoes=(60, 50, 60), torso_extra=coat_extra, bow='compound',
                   bowc=(80, 90, 110), grip=(255, 150, 60), fletch=(90, 160, 220)),
    'bolt': dict(name='BOLT-9', title='SCRAP ROBOT', color=(90, 255, 230),
                 head=bolt_head, shirt=(120, 204, 210), sleeve=(80, 90, 110), pants=(80, 90, 110),
                 shoes=(60, 120, 140), hands=(120, 204, 210), forearm=(80, 90, 110), torso_extra=robot_extra,
                 bow='long', bowc=(90, 255, 230), grip=(60, 70, 90), stringc=(255, 120, 120), fletch=(90, 255, 230)),
    'akinci': dict(name='AKINCI', title='STEPPE ARCHER', color=(240, 80, 80),
                   head=akinci_head, shirt=(204, 48, 52), sleeve=(204, 48, 52), pants=(44, 56, 110),
                   shoes=(250, 206, 80), hands=TAN, torso_extra=kaftan_extra, belt=(60, 170, 120),
                   bow='recurve', bowc=(120, 52, 40), grip=(250, 206, 80), fletch=(250, 244, 228)),
    'gourd': dict(name='GOURD', title='FIELD SPOOK', color=(255, 160, 60),
                  head=gourd_head, shirt=(236, 230, 214), sleeve=(236, 230, 214), pants=(70, 120, 200),
                  shoes=(90, 60, 40), hands=(248, 210, 96), torso_extra=overall_extra,
                  back=straw_tufts, bow='long', bowc=(160, 110, 60), fletch=(110, 150, 60)),
}


def _draw(L_final, fn, bases, origin=(0, TOP)):
    L = Layer(W, H).at(*origin)
    fn(L)
    L.at(0, 0)
    if bases != 'raw':
        for b in bases or []:
            L.auto_shade(b)
        L.outline()
    L_final.paste(L)


def build(cid, angle=15, pull=.7, walk=0, arrow=True, rig=True, pose='aim'):
    cfg = CHARACTERS[cid]
    out = Layer(W, H)
    if pose == 'idle':
        for fn, bases in idle_parts(cfg)[:1]:
            _draw(out, fn, bases)
    if cfg.get('back'):
        _draw(out, cfg['back'], None)
    _draw(out, legs_fn(cfg, 'back', walk), [cfg['pants']])
    _draw(out, torso_fn(cfg), [cfg['shirt']])
    _draw(out, legs_fn(cfg, 'front', walk), [cfg['pants']])
    head_parts, face = cfg['head'](None)
    for fn, bases in head_parts:
        _draw(out, fn, bases, HEAD)
    F = Layer(W, H).at(*HEAD)
    face(F)
    out.paste(F)
    if pose == 'idle':
        for fn, bases in idle_parts(cfg)[1:]:
            _draw(out, fn, bases)
    elif rig:
        for fn, bases in aim_parts(cfg, angle, pull, arrow):
            _draw(out, fn, bases)
    return out.img
