"""Renders the design mock-ups, asset sheets and individual PNG exports."""
import os
from PIL import Image
from common import Layer, rgba, shade, INK, WHITE, up
from font import render
import ui
import characters as ch
import scenery as sc

OUT = 'out/final'
S = 3                      # pixel scale used in game
NW, NH = 427, 267          # native screen (x3 = 1281x801 -> cropped to 1280x800)
os.makedirs(OUT, exist_ok=True)
os.makedirs(f'{OUT}/sprites', exist_ok=True)
os.makedirs(f'{OUT}/ui', exist_ok=True)
os.makedirs(f'{OUT}/scenery', exist_ok=True)


def finish(img, name):
    big = up(img, S).crop((0, 0, 1280, 800))
    big.save(f'{OUT}/{name}.png')
    return big


def flip(img):
    return img.transpose(Image.FLIP_LEFT_RIGHT)


def shadow(L, x, y, w=24):
    s = Layer(w, 5); s.ell(0, 0, w, 5, (20, 16, 34, 90))
    L.alpha_composite(s.img, (int(x - w // 2), int(y - 2)))


def portrait(cid):
    return ch.build(cid, pose='idle').crop((0, 4, 64, 80))


def put_char(img, cid, feet_x, feet_y, facing=1, **kw):
    spr = ch.build(cid, **kw)
    if facing < 0:
        spr = flip(spr)
        x = feet_x - (ch.W - ch.FX)
    else:
        x = feet_x - ch.FX
    shadow(img, feet_x, feet_y)
    img.alpha_composite(spr, (int(x), int(feet_y - ch.GY)))


# ------------------------------------------------------------------ main menu
def main_menu():
    layers = sc.build_layers('day')
    img = Image.new('RGBA', (NW, NH))
    view = sc.compose(layers, -60, NW)
    img.alpha_composite(view, (0, NH - sc.H))
    top = Layer(NW, NH - sc.H); top.rect(0, 0, NW, NH - sc.H, sc.PALETTES['day']['sky'][0])
    img.alpha_composite(top.img)
    feet = NH - sc.H + sc.GROUND_Y + 2
    put_char(img, 'fern', 70, feet, 1, pose='idle')
    put_char(img, 'akinci', NW - 70, feet, -1, pose='idle')
    lg = ui.logo()
    lg2 = up(lg, 1)
    img.alpha_composite(lg2, ((NW - lg2.width) // 2, 8))
    bw = 120
    y = 104
    for lab, col, ic in (('PLAY DUEL', 'green', 'play'), ('PRACTICE', 'blue', 'target'), ('CHARACTERS', 'orange', 'hand')):
        b = ui.button(bw, 24, lab, col, 'hover' if lab == 'PLAY DUEL' else 'normal', icon=ui.icon(ic, WHITE, shade(ui.C(col), -.55)))
        img.alpha_composite(b, ((NW - b.width) // 2, y)); y += 30
    img.alpha_composite(ui.icon_button('gear', 'grey'), (6, 6))
    img.alpha_composite(ui.icon_button('sound', 'teal'), (30, 6))
    img.alpha_composite(ui.icon_button('camera', 'pink'), (54, 6))
    p = ui.pill('ME461'); img.alpha_composite(p, (NW - p.width - 6, 9))
    tip = render('RAISE BOTH HANDS TO START', fill=WHITE, bold=False, outline=INK)
    img.alpha_composite(tip, ((NW - tip.width) // 2, NH - 14))
    return finish(img, '1_main_menu')


# ------------------------------------------------------------------ character select
def select_screen():
    img = Image.new('RGBA', (NW, NH), (44, 36, 76, 255))
    L = Layer(NW, NH)
    for i in range(-NH, NW, 18):           # diagonal bg stripes
        L.line([(i, NH), (i + NH, 0)], (52, 42, 88), 8)
    img.alpha_composite(L.img)
    rb = ui.ribbon('CHOOSE YOUR ARCHER', 'orange', 170)
    img.alpha_composite(rb, ((NW - rb.width) // 2, 4))
    ids = list(ch.CHARACTERS)
    sel = {0: 'fern', 1: 'torque'}
    for side in (0, 1):
        pw = 196
        px = 8 if side == 0 else NW - pw - 8
        pn = ui.panel(pw, 204, (62, 52, 104))
        img.alpha_composite(pn, (px, 32))
        col = (110, 225, 140) if side == 0 else (255, 150, 52)
        t = render(f'PLAYER {side + 1}', fill=col, outline=INK)
        img.alpha_composite(t, (px + 10, 40))
        k = render('A/D + F' if side == 0 else '</> + ENTER', fill=(200, 196, 230), bold=False, outline=None, shadow=0)
        img.alpha_composite(k, (px + pw - k.width - 10, 41))
        # big preview
        SH = 80
        stage = Layer(pw - 20, SH)
        stage.rrect(0, 0, pw - 20, SH, 4, (36, 30, 62))
        stage.ell(8 if side == 0 else pw - 108, SH - 14, 80, 10, (52, 44, 88))
        img.alpha_composite(stage.img, (px + 10, 54))
        cid = sel[side]
        spr = ch.build(cid, 25, .8)
        spr = up(spr, 1)
        if side == 1:
            spr = flip(spr)
        sx = px + 14 if side == 0 else px + pw - 14 - spr.width
        img.alpha_composite(spr, (sx, 54 + SH - spr.height - 3))
        cfg = ch.CHARACTERS[cid]
        nm = render(cfg['name'], fill=cfg['color'], outline=INK)
        tl = render(cfg['title'], fill=(200, 196, 230), bold=False, outline=INK, shadow=0)
        tx = px + pw - 16 - max(nm.width, tl.width) if side == 0 else px + 18
        img.alpha_composite(nm, (tx, 62))
        img.alpha_composite(tl, (tx, 74))
        for j, (k_, v_) in enumerate((('POWER', 4), ('SPEED', 3 + side), ('LUCK', 2 + 2 * side))):
            img.alpha_composite(render(k_, fill=(200, 196, 230), bold=False, outline=None, shadow=0), (tx, 88 + j * 10))
            for q in range(5):
                pip = Layer(6, 6); pip.rect(1, 1, 4, 4, cfg['color'] if q < v_ else (60, 52, 96)); pip.outline()
                img.alpha_composite(pip.img, (tx + 34 + q * 6, 89 + j * 10))
        # grid 3 x 2 of cards
        for i, c in enumerate(ids):
            cx = px + 8 + (i % 3) * 62
            cy = 138 + (i // 3) * 48
            st = 'selected' if c == cid else ('locked' if c == 'gourd' else 'normal')
            cd = ui.card(portrait(c).crop((4, 2, 60, 40)), ch.CHARACTERS[c]['name'].split()[0][:7],
                         ch.CHARACTERS[c]['color'], st, w=58, h=45)
            img.alpha_composite(cd, (cx, cy))
    vs = ui.vs_badge(48)
    img.alpha_composite(vs, ((NW - vs.width) // 2, 80))
    st = ui.stamp('READY!', 'green')
    img.alpha_composite(st, (150, 108))
    b = ui.button(110, 22, 'START DUEL', 'green')
    img.alpha_composite(b, ((NW - b.width) // 2, NH - 27))
    img.alpha_composite(ui.icon_button('back', 'blue'), (8, NH - 26))
    return finish(img, '2_character_select')


# ------------------------------------------------------------------ arena
def arena(mode='night', name='3_arena_night', cam=420):
    layers = sc.build_layers(mode)
    img = Image.new('RGBA', (NW, NH), (0, 0, 0, 255))
    view = sc.compose(layers, cam, NW)
    img.alpha_composite(view, (0, NH - sc.H))
    top = Layer(NW, NH - sc.H); top.rect(0, 0, NW, NH - sc.H, sc.PALETTES[mode]['sky'][0])
    img.alpha_composite(top.img)
    feet = NH - sc.H + sc.GROUND_Y + 2
    # foreground layer must be in front of characters -> redraw without it, then on top
    view_bg = sc.compose([l for l in layers if l[0] != 'foreground'], cam, NW)
    img.alpha_composite(view_bg, (0, NH - sc.H))
    put_char(img, 'flint', 80, feet, 1, angle=22, pull=.85)
    put_char(img, 'bolt', NW - 92, feet, -1, angle=30, pull=.4)
    # arrow in flight
    A = Layer(30, 12)
    A.line([(2, 8), (22, 3)], (122, 82, 52)); A.poly([(22, 1), (27, 2), (23, 6)], (210, 220, 232))
    A.line([(2, 8), (0, 5)], (240, 80, 70)); A.line([(2, 8), (0, 11)], (240, 80, 70))
    A.outline()
    img.alpha_composite(A.img, (200, 120))
    for i, (dx, dy) in enumerate(((-8, 6), (-16, 10), (-24, 13))):
        img.putpixel((200 + dx, 128 + dy), rgba((255, 255, 255, 150)))
    fg = sc.compose([l for l in layers if l[0] == 'foreground'], cam, NW)
    img.alpha_composite(fg, (0, NH - sc.H))
    # HUD
    hb1 = ui.health_bar(150, .72, (92, 214, 120), lost=.08)
    hb2 = ui.health_bar(150, .45, (255, 150, 52), flip=True)
    img.alpha_composite(hb1, (8, 18)); img.alpha_composite(hb2, (NW - hb2.width - 8, 18))
    n1 = render('P1 FLINT', fill=(110, 225, 140), outline=INK); img.alpha_composite(n1, (10, 6))
    n2 = render('BOLT-9 P2', fill=(255, 150, 52), outline=INK); img.alpha_composite(n2, (NW - n2.width - 10, 6))
    rb = ui.ribbon('ROUND 2', 'purple')
    img.alpha_composite(rb, ((NW - rb.width) // 2, 4))
    img.alpha_composite(ui.icon_button('pause', 'orange', size=18), ((NW - 20) // 2, 26))
    d = render('14 M', fill=WHITE, outline=INK, bold=False)
    img.alpha_composite(d, ((NW - d.width) // 2, 50))
    pm = ui.pull_meter(40, .85); img.alpha_composite(pm, (60, feet + 6))
    pm2 = ui.pull_meter(40, .4); img.alpha_composite(pm2, (NW - 112, feet + 6))
    a1 = render('+22°', fill=(255, 245, 220), bold=False, outline=INK); img.alpha_composite(a1, (104, feet + 5))
    a2 = render('+30°', fill=(255, 245, 220), bold=False, outline=INK); img.alpha_composite(a2, (NW - 68, feet + 5))
    return finish(img, name)


# ------------------------------------------------------------------ sheets
def roster_sheet():
    ids = list(ch.CHARACTERS)
    cw = ch.W + 6
    img = Image.new('RGBA', (cw * 6 + 8, 3 * (ch.H + 4) + 40), (56, 196, 190, 255))
    t = render('ROSTER - IDLE / AIM / HIGH SHOT', fill=WHITE, outline=INK)
    img.alpha_composite(t, (6, 4))
    for i, c in enumerate(ids):
        x = 6 + i * cw
        for r, kw in enumerate((dict(pose='idle'), dict(angle=10, pull=.9), dict(angle=60, pull=.3))):
            y = 20 + r * (ch.H + 4)
            shadow(img, x + ch.FX, y + ch.GY)
            img.alpha_composite(ch.build(c, **kw), (x, y))
        cfg = ch.CHARACTERS[c]
        nm = render(cfg['name'], fill=cfg['color'], outline=INK, bold=len(cfg['name']) < 9)
        img.alpha_composite(nm, (x + 2, 20 + 3 * (ch.H + 4) - 4))
    big = up(img, 3)
    big.save(f'{OUT}/4_character_roster.png')
    return big


def ui_sheet():
    img = Image.new('RGBA', (480, 340), (44, 36, 76, 255))
    def lab(s, x, y):
        img.alpha_composite(render(s, fill=(255, 210, 64), outline=INK), (x, y))
    lab('BUTTONS  NORMAL / HOVER / PRESSED / DISABLED', 6, 4)
    y = 16
    for c, l in (('green', 'PLAY'), ('blue', 'PRACTICE'), ('orange', 'DUEL'), ('red', 'QUIT'), ('purple', 'RETRY')):
        for j, st in enumerate(('normal', 'hover', 'pressed', 'disabled')):
            img.alpha_composite(ui.button(72, 22, l, c, st), (6 + j * 78, y))
        y += 27
    lab('ICON BUTTONS', 6, y + 2); y += 14
    x = 6
    for n, c in (('play', 'green'), ('pause', 'orange'), ('back', 'blue'), ('restart', 'purple'), ('gear', 'grey'),
                 ('sound', 'teal'), ('camera', 'pink'), ('home', 'yellow'), ('trophy', 'orange'), ('target', 'red')):
        img.alpha_composite(ui.icon_button(n, c), (x, y)); x += 25
    y += 28
    lab('HUD', 6, y); y += 12
    img.alpha_composite(ui.health_bar(150, .7, lost=.1), (6, y))
    img.alpha_composite(ui.health_bar(150, .35, (255, 150, 52), flip=True), (164, y))
    img.alpha_composite(ui.button(96, 28, 'BIG BUTTON', 'pink'), (330, 200))
    img.alpha_composite(ui.button(96, 28, 'BIG BUTTON', 'teal', 'pressed'), (330, 236))
    img.alpha_composite(ui.pull_meter(60, .9), (6, y + 18))
    img.alpha_composite(ui.pill('620'), (74, y + 16))
    img.alpha_composite(ui.pill('3', 'trophy', (255, 210, 64)), (120, y + 16))
    img.alpha_composite(ui.stamp('READY!'), (160, y + 14))
    img.alpha_composite(ui.stamp('K.O.!', 'red'), (210, y + 14))
    img.alpha_composite(ui.ribbon('ROUND 1', 'purple'), (250, y + 14))
    img.alpha_composite(ui.vs_badge(48), (372, 24))
    lg = ui.logo(); img.alpha_composite(lg, (326, 90))
    pn = ui.panel(120, 60, (62, 52, 104)); img.alpha_composite(pn, (6, y + 40))
    img.alpha_composite(render('PANEL', fill=WHITE, outline=INK), (16, y + 48))
    img.alpha_composite(render('BODY TEXT LOOKS', fill=(220, 214, 250), bold=False, outline=None, shadow=0), (16, y + 62))
    img.alpha_composite(render('LIKE THIS.', fill=(220, 214, 250), bold=False, outline=None, shadow=0), (16, y + 72))
    for i, cid in enumerate(('flint', 'akinci')):
        cd = ui.card(portrait(cid).crop((4, 0, 60, 60)), ch.CHARACTERS[cid]['name'], ch.CHARACTERS[cid]['color'],
                     'selected' if i == 0 else 'normal', w=58, h=76)
        img.alpha_composite(cd, (136 + i * 64, y + 38))
    big = up(img, 3)
    big.save(f'{OUT}/5_ui_kit.png')
    return big


def font_sheet():
    img = Image.new('RGBA', (300, 120), (44, 36, 76, 255))
    y = 4
    rows = [
        ('TITLE STYLE', dict(grad=((255, 236, 120), (255, 160, 48)), inner_hi=True), 2),
        ('ABCDEFGHIJKLMNOPQRSTUVWXYZ', {}, 1),
        ('ÇĞİÖŞÜ 0123456789 .,!?:-+/%()°×♥', {}, 1),
        ('REGULAR: ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789', dict(bold=False), 1),
        ('YAY KURULDU! ATIŞ AÇISI +45° · GÜÇ %80', dict(fill=(110, 225, 140)), 1),
    ]
    for text, kw, sc_ in rows:
        r = render(text, outline=INK, **kw)
        if sc_ > 1:
            r = up(r, sc_)
        img.alpha_composite(r, (6, y)); y += r.height + 6
    big = up(img, 3)
    big.save(f'{OUT}/6_font_specimen.png')
    return big


def scenery_exports():
    for mode in ('day', 'night'):
        layers = sc.build_layers(mode)
        for name, im, k in layers:
            im.save(f'{OUT}/scenery/{mode}_{name}_x{k}.png')
        pano = sc.compose(layers, 0, 1600)
        up(pano, 2).save(f'{OUT}/7_scenery_panorama_{mode}.png')


def scroll_gif():
    layers = sc.build_layers('day')
    frames = []
    for i in range(0, 120):
        cam = i * 9
        f = sc.compose(layers, cam, 320)
        frames.append(up(f, 2).convert('P', palette=Image.ADAPTIVE, colors=128))
    frames[0].save(f'{OUT}/8_parallax_scroll.gif', save_all=True, append_images=frames[1:], duration=40, loop=0)


def sprite_exports():
    for cid in ch.CHARACTERS:
        ch.build(cid, pose='idle').save(f'{OUT}/sprites/{cid}_idle.png')
        for a in (-60, -30, 0, 30, 60, 90):
            ch.build(cid, a, .8).save(f'{OUT}/sprites/{cid}_aim_{a:+d}.png')
    ui.logo().save(f'{OUT}/ui/logo.png')
    ui.vs_badge(48).save(f'{OUT}/ui/vs_badge.png')
    for c in ('green', 'blue', 'orange', 'red', 'purple'):
        for st in ('normal', 'hover', 'pressed', 'disabled'):
            ui.button(72, 22, '', c, st).save(f'{OUT}/ui/button_{c}_{st}.png')
    for n in ui.ICONS:
        ui.icon(n).save(f'{OUT}/ui/icon_{n}.png')


if __name__ == '__main__':
    main_menu(); select_screen(); arena('night', '3_arena_night'); arena('day', '3b_arena_day', 900)
    roster_sheet(); ui_sheet(); font_sheet(); scenery_exports(); scroll_gif(); sprite_exports()
    print('done')
