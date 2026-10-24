"""Defter / karalama anlatımı: tek bir dev defter sayfası, kamera sayfada gezer, her şey elle çiziliyor gibi.

Sahne kesmesi yoktur; tüm öğeler sayfada birikir ve finalde kamera geri çekilip tüm sayfayı gösterir.
Öğeler bildirimsel bir listede (ELEMENTS) tanımlanır; hem görüntü hem ses efektleri bu listeden üretilir.

Kullanım:  python3 render_doodle.py                 -> out/elevens1_shorts_doodle.mp4
           python3 render_doodle.py --preview 4.5 20
"""
import math
import os
import random
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from render import AUDIO, PROMPT_IDX, WORDS, clamp, e_back, e_inout, e_out, paste, place, prog, wt

W, H, FPS = 1080, 1920, 30
DUR = 47.2
OUT = "out/elevens1_shorts_doodle.mp4"
AX, AY = 540, 800  # kameranın odak noktasının ekrandaki yeri

# ---------------------------------------------------------------- palet
DESK = (92, 78, 68)
PAPER = (251, 249, 242)
GRID = (214, 226, 238)
MARGIN = (236, 160, 160)
INK = (34, 38, 64)        # tükenmez kalem lacivert
BLUE = (40, 90, 200)
RED = (214, 58, 48)
GREEN = (38, 150, 90)
AMBER = (214, 140, 20)
GRAY = (110, 110, 125)
HL_YEL = (255, 226, 70)
HL_GRN = (150, 230, 140)
HL_PNK = (255, 150, 190)
HL_BLU = (140, 200, 255)
STICKY_Y = (255, 233, 120)
STICKY_P = (255, 190, 210)

FDIR = "assets/fonts/"
FONTS = {"pen": FDIR + "Kalam-Bold.ttf", "penl": FDIR + "Kalam-Regular.ttf", "marker": FDIR + "CaveatBrush-Regular.ttf",
         "cap": FDIR + "ShantellSans-Variable.ttf"}

PAGE = (-60, -90, 2220, 5720)


@lru_cache(maxsize=None)
def font(key, size):
    f = ImageFont.truetype(FONTS[key], size)
    if key == "cap":
        f.set_variation_by_name("ExtraBold")
    return f


@lru_cache(maxsize=6000)
def txt(text, key, size, color):
    f = font(key, size)
    asc, desc = f.getmetrics()
    pad = max(4, size // 6)
    im = Image.new("RGBA", (int(math.ceil(f.getlength(text))) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), text, font=f, fill=color + (255,))
    return im


def text_w(text, key, size):
    return font(key, size).getlength(text)


# ---------------------------------------------------------------- kamera
START = (540, 840, 1.1)
MOVES = [  # (başlangıç, süre, (odak x, odak y, zoom))
    (0.0, 1.6, (540, 860, 1.0)),
    (5.3, 0.75, (1620, 1060, 1.0)),
    (8.1, 0.6, (1620, 1500, 1.0)),
    (11.15, 0.85, (1080, 2600, 0.95)),
    (15.8, 9.4, (1080, 2690, 1.0)),
    (25.3, 0.8, (600, 3700, 1.0)),
    (30.85, 0.45, (1610, 3290, 1.1)),
    (32.05, 0.6, (1610, 3900, 1.0)),
    (35.05, 0.6, (1610, 4560, 1.0)),
    (39.3, 1.3, (1080, 2300, 0.313)),
    (40.6, 6.6, (1080, 2300, 0.325)),
]


def cam_at(t):
    cx, cy, z = START
    for t0, d, (tx, ty, tz) in MOVES:
        if t <= t0:
            break
        p = e_inout(clamp((t - t0) / d))
        cx, cy = cx + (tx - cx) * p, cy + (ty - cy) * p
        z = math.exp(math.log(z) + (math.log(tz) - math.log(z)) * p)
    # elde tutulan kamera hissi
    cx += 5 * math.sin(t * 0.9) / z
    cy += 4 * math.sin(t * 0.7 + 1) / z
    return cx, cy, z


class Cam:
    def __init__(self, t):
        self.cx, self.cy, self.z = cam_at(t)

    def p(self, x, y):
        return (x - self.cx) * self.z + AX, (y - self.cy) * self.z + AY

    def view(self):
        x0 = self.cx - AX / self.z
        y0 = self.cy - AY / self.z
        return x0, y0, x0 + W / self.z, y0 + H / self.z


# ---------------------------------------------------------------- yol (path) üreticileri
def ellipse_path(cx, cy, rx, ry, a0=0.0, sweep=2 * math.pi, n=None, spiral=0.0):
    n = n or max(12, int(abs(sweep) * max(rx, ry) / 14))
    out = []
    for k in range(n + 1):
        u = k / n
        a = a0 + sweep * u
        s = 1 + spiral * (u - 0.5)
        out.append((cx + rx * s * math.cos(a), cy + ry * s * math.sin(a)))
    return out


def sketch_circle(cx, cy, rx, ry, seed=0):
    """Elle çizilmiş daire: biraz taşar, hafif spiral."""
    a0 = random.Random(seed).uniform(0, 2 * math.pi)
    return ellipse_path(cx, cy, rx, ry, a0, 2 * math.pi * 1.12, spiral=0.06)


def rrect_path(x0, y0, x1, y1, r):
    pts = []
    for (cx, cy, a) in ((x1 - r, y0 + r, -math.pi / 2), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, math.pi / 2),
                        (x0 + r, y0 + r, math.pi)):
        pts += ellipse_path(cx, cy, r, r, a, math.pi / 2, n=6)
    # biraz taşan kapanış
    pts.append((x1 - r + 12, y0 - 2))
    return [(x0 + r - 10, y0 + 2)] + pts


def bezier(p0, p1, p2, n=24):
    return [((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0],
             (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1]) for u in (k / n for k in range(n + 1))]


def line(p0, p1, n=8):
    return [(p0[0] + (p1[0] - p0[0]) * k / n, p0[1] + (p1[1] - p0[1]) * k / n) for k in range(n + 1)]


def check_path(x, y, s=1.0):
    return line((x - 28 * s, y), (x - 6 * s, y + 24 * s), 4) + line((x - 6 * s, y + 24 * s), (x + 36 * s, y - 30 * s), 6)[1:]


def wave_path(x0, x1, y, amp=10, period=40):
    n = int((x1 - x0) / 6)
    return [(x0 + (x1 - x0) * k / n, y + amp * math.sin((x1 - x0) * k / n / period * 2 * math.pi)) for k in range(n + 1)]


def arrow_head(p_prev, p_end, size=26):
    ang = math.atan2(p_end[1] - p_prev[1], p_end[0] - p_prev[0])
    return [line((p_end[0] - size * math.cos(ang - 0.5), p_end[1] - size * math.sin(ang - 0.5)), p_end, 3),
            line((p_end[0] - size * math.cos(ang + 0.5), p_end[1] - size * math.sin(ang + 0.5)), p_end, 3)]


def zigzag_fill(x0, y0, x1, y1, step=16):
    pts, k, x = [], 0, x0
    while x <= x1:
        pts.append((x, y1 if k % 2 else y0))
        x += step
        k += 1
    return pts


# ---------------------------------------------------------------- öğe listesi
ELEMENTS = []


def bbox_of(pts, pad=20):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def T(text, x, y, t0, dur=None, size=56, key="pen", color=INK, anchor="mm", rot=0.0):
    w = text_w(text, key, size)
    cx = x if anchor == "mm" else x + w / 2
    dur = dur if dur is not None else clamp(len(text) * 0.05, 0.3, 1.4)
    ELEMENTS.append(dict(kind="text", text=text, x=cx, y=y, t0=t0, dur=dur, size=size, key=key, color=color,
                         rot=rot, bbox=(cx - w / 2 - 20, y - size, cx + w / 2 + 20, y + size), seed=len(ELEMENTS)))


def P(pts, t0, dur, color=INK, width=6, boil=2.0, fill=None, sound="pencil"):
    ELEMENTS.append(dict(kind="path", pts=pts, t0=t0, dur=dur, color=color, width=width, boil=boil, fill=fill,
                         sound=sound, bbox=bbox_of(pts, width + 10), seed=len(ELEMENTS)))


def HL(pts, t0, dur, color=HL_YEL, width=50, alpha=120):
    ELEMENTS.append(dict(kind="hl", pts=pts, t0=t0, dur=dur, color=color, width=width, alpha=alpha,
                         bbox=bbox_of(pts, width), seed=len(ELEMENTS)))


def STICKY(lines, x, y, t0, color=STICKY_Y, w=420, h=300, rot=3.0, size=64):
    ELEMENTS.append(dict(kind="sticky", lines=tuple(lines), x=x, y=y, t0=t0, color=color, w=w, h=h, rot=rot,
                         size=size, bbox=(x - w, y - h, x + w, y + h)))


def CUSTOM(fn, t0, bbox):
    ELEMENTS.append(dict(kind="custom", fn=fn, t0=t0, bbox=bbox))


# ---------------------------------------------------------------- robot karakter
ROBOT_STATES = [(0.0, "normal"), (1.9, "smug"), (4.38, "shock")]


def robot_paths(x, y, state):
    """(yol, renk, kalınlık) listesi ve dolgu poligonları."""
    paths = []
    head = rrect_path(x - 120, y - 100, x + 120, y + 100, 40)
    body = rrect_path(x - 90, y + 118, x + 90, y + 290, 26)
    paths.append((head, INK, 7))
    paths.append((line((x, y - 100), (x, y - 150)), INK, 7))
    paths.append((ellipse_path(x, y - 166, 16, 16), INK, 7))
    paths.append((body, INK, 7))
    paths.append((line((x - 30, y + 100), (x - 30, y + 118), 2), INK, 7))
    paths.append((line((x + 30, y + 100), (x + 30, y + 118), 2), INK, 7))
    if state == "smug":  # başparmak yukarı kol
        paths.append((bezier((x + 90, y + 160), (x + 150, y + 150), (x + 170, y + 90)), INK, 7))
        paths.append((ellipse_path(x + 172, y + 76, 16, 16), INK, 7))
    else:
        paths.append((bezier((x + 90, y + 160), (x + 140, y + 200), (x + 150, y + 250)), INK, 7))
    paths.append((bezier((x - 90, y + 160), (x - 140, y + 200), (x - 150, y + 250)), INK, 7))
    # yüz
    if state == "smug":
        paths.append((ellipse_path(x - 50, y - 5, 24, 18, math.pi, math.pi), INK, 7))
        paths.append((ellipse_path(x + 50, y - 5, 24, 18, math.pi, math.pi), INK, 7))
        paths.append((bezier((x - 55, y + 40), (x + 10, y + 85), (x + 60, y + 30)), INK, 7))
    elif state == "shock":
        paths.append((ellipse_path(x - 50, y - 10, 24, 24), INK, 6))
        paths.append((ellipse_path(x + 50, y - 10, 24, 24), INK, 6))
        paths.append((ellipse_path(x - 50, y - 6, 7, 7), INK, 8))
        paths.append((ellipse_path(x + 50, y - 6, 7, 7), INK, 8))
        paths.append((ellipse_path(x, y + 55, 18, 14), INK, 7))
        drop = bezier((x + 150, y - 90), (x + 128, y - 45), (x + 150, y - 40)) + \
            bezier((x + 150, y - 40), (x + 172, y - 45), (x + 150, y - 90))[1:]
        paths.append((drop, BLUE, 6))
    else:
        paths.append((ellipse_path(x - 50, y - 8, 9, 9), INK, 9))
        paths.append((ellipse_path(x + 50, y - 8, 9, 9), INK, 9))
        paths.append((line((x - 40, y + 50), (x + 40, y + 50), 4), INK, 7))
    return paths, [head, body]


def robot_draw(c, cam, t, x=230, y=760, t0=0.25, dur=1.2):
    if t < t0:
        return
    state = [s for ts, s in ROBOT_STATES if t >= ts][-1]
    paths, fills = robot_paths(x, y, state)
    prog_all = clamp((t - t0) / dur)
    d = ImageDraw.Draw(c)
    if prog_all > 0.3:
        for f in fills:
            d.polygon([cam.p(*q) for q in f], fill=(255, 255, 255, 255))
    total = len(paths)
    for k, (pts, col, w) in enumerate(paths):
        pk = clamp(prog_all * total - k)
        if pk > 0:
            draw_path(c, cam, pts, pk, col, w, 2.0, 100 + k, t)
    if prog_all > 0.8:
        im = txt("AI", "pen", max(6, round(56 * cam.z)), INK)
        place(c, im, *cam.p(x, y + 205), 1, clamp((prog_all - 0.8) * 5))
    if state == "shock" and t < 4.38 + 0.4:  # şok anında küçük zıplama çizgileri
        for a in (-0.6, 0, 0.6):
            p0 = (x + 150 * math.sin(a), y - 200 - 40 * math.cos(a))
            p1 = (x + 190 * math.sin(a), y - 240 - 60 * math.cos(a))
            draw_path(c, cam, line(p0, p1, 3), 1, RED, 6, 1, 7, t)


# ---------------------------------------------------------------- çizim çekirdeği
def boil_offset(seed, t, s, amp):
    """Elle çizim 'kaynama' efekti: çizgiler saniyede 8 kez hafifçe yeniden çizilir."""
    blk = int(t * 8)
    rnd = random.Random(seed * 7919 + blk)
    ph1, ph2 = rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)
    return amp * math.sin(s * 0.035 + ph1), amp * math.cos(s * 0.03 + ph2)


def draw_path(c, cam, pts, p, color, width, boil, seed, t, alpha=255):
    if p <= 0 or len(pts) < 2:
        return
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    L = sum(seg)
    target = L * clamp(p)
    out, acc = [pts[0]], 0.0
    for i, sl in enumerate(seg):
        if acc + sl >= target:
            u = (target - acc) / sl if sl else 0
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * u, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * u))
            break
        out.append(pts[i + 1])
        acc += sl
    scr, s = [], 0.0
    for i, q in enumerate(out):
        if i:
            s += math.dist(out[i - 1], q)
        ox, oy = boil_offset(seed, t, s, boil)
        scr.append(cam.p(q[0] + ox, q[1] + oy))
    w = max(1, int(round(width * cam.z)))
    d = ImageDraw.Draw(c)
    col = color + (alpha,)
    d.line(scr, fill=col, width=w, joint="curve")
    r = w / 2
    for q in (scr[0], scr[-1]):
        d.ellipse((q[0] - r, q[1] - r, q[0] + r, q[1] + r), fill=col)


def draw_text(c, cam, e, t):
    p = clamp((t - e["t0"]) / e["dur"])
    if p <= 0:
        return
    size = max(6, round(e["size"] * cam.z))
    im = txt(e["text"], e["key"], size, e["color"])
    if p < 1:  # kalemle yazılıyormuş gibi soldan sağa açılır
        pad = max(4, size // 6)
        w = int(pad + (im.width - 2 * pad) * p) + 2
        im = im.crop((0, 0, max(1, w), im.height))
        cx, cy = cam.p(e["x"], e["y"])
        full_w = txt(e["text"], e["key"], size, e["color"]).width
        ox, oy = boil_offset(e["seed"], t, 0, 1.2)
        place(c, im, cx - full_w / 2 + im.width / 2 + ox, cy + oy, 1, 1, e["rot"])
    else:
        ox, oy = boil_offset(e["seed"], t, 0, 1.2)
        place(c, im, cam.p(e["x"], e["y"])[0] + ox, cam.p(e["x"], e["y"])[1] + oy, 1, 1, e["rot"])


def draw_hl(c, cam, e, t):
    p = clamp((t - e["t0"]) / e["dur"])
    if p <= 0:
        return
    x0, y0, x1, y1 = e["bbox"]
    sx0, sy0 = cam.p(x0, y0)
    sx1, sy1 = cam.p(x1, y1)
    lw, lh = int(sx1 - sx0) + 2, int(sy1 - sy0) + 2
    if lw <= 2 or lh <= 2:
        return
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))

    class Local:  # yerel koordinatlı kamera
        z = cam.z

        @staticmethod
        def p(x, y):
            q = cam.p(x, y)
            return q[0] - sx0, q[1] - sy0

    draw_path(layer, Local, e["pts"], p, e["color"], e["width"], 0.8, e["seed"], t, 255)
    layer.putalpha(layer.getchannel("A").point(lambda v: v * e["alpha"] // 255))
    paste(c, layer, sx0, sy0)


@lru_cache(maxsize=32)
def sticky_sprite(lines, color, w, h, size):
    pad = 30
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k in range(10, 0, -1):  # yumuşak gölge
        d.rounded_rectangle((pad + 6 - k, pad + 12 - k, pad + w + k, pad + h + k), 8, fill=(60, 40, 20, 5))
    d.polygon([(pad, pad), (pad + w, pad), (pad + w, pad + h - 30), (pad + w - 40, pad + h), (pad, pad + h)],
              fill=color + (255,))
    d.polygon([(pad + w, pad + h - 30), (pad + w - 40, pad + h), (pad + w - 34, pad + h - 26)],
              fill=tuple(int(v * 0.85) for v in color) + (255,))
    d.rectangle((pad + w / 2 - 70, pad - 18, pad + w / 2 + 70, pad + 22), fill=(235, 225, 200, 170))  # bant
    f = font("marker", size)
    lh = size * 1.1
    y = pad + h / 2 - lh * (len(lines) - 1) / 2
    for ln in lines:
        d.text((pad + w / 2, y), ln, font=f, fill=INK + (255,), anchor="mm")
        y += lh
    return im


def draw_sticky(c, cam, e, t):
    p = prog(t, e["t0"], 0.28)
    if p <= 0:
        return
    im = sticky_sprite(e["lines"], e["color"], e["w"], e["h"], e["size"])
    sc = cam.z * (1.25 - 0.25 * e_out(p))
    place(c, im, *cam.p(e["x"], e["y"]), sc, min(1, p * 2), e["rot"] + (1 - e_out(p)) * 8)


# ---------------------------------------------------------------- SAYFA İÇERİĞİ
# A) Kanca: kendinden emin ama yanlış robot
T("Bu cevaba güvenir miydin?", 540, 300, 0.05, 0.9, 88, "marker", INK)
P(wave_path(170, 910, 360, 6, 70), 0.95, 0.35, RED, 7)
T("Soru: Çin Seddi uzaydan görülür mü?", 560, 470, 0.35, 1.1, 46, "pen", BLUE)
CUSTOM(robot_draw, 0.25, (0, 560, 460, 1120))
_bub = rrect_path(430, 560, 1030, 960, 50)
P(_bub, 1.45, 0.45, INK, 7)
P(bezier((440, 880), (400, 905), (370, 905)) + bezier((370, 905), (410, 900), (448, 920))[1:], 1.8, 0.15, INK, 7)
T("Kesinlikle evet!", 730, 650, 1.9, 0.55, 66, "pen", INK)
T("Çıplak gözle bile görülür.", 730, 735, 2.35, 0.7, 46, "penl", INK)
T("Güven:", 525, 860, 2.6, 0.3, 46, "pen", GRAY)
P(rrect_path(620, 835, 900, 885, 14), 2.7, 0.3, INK, 5)
P(zigzag_fill(632, 844, 888, 876, 14), 2.95, 0.55, GREEN, 6, 1.0)
T("%100", 962, 860, 3.45, 0.3, 46, "pen", GREEN, rot=0)
P(sketch_circle(730, 760, 345, 245, 3), 4.36, 0.32, RED, 10, 2.5, sound="marker")
T("YANLIŞ!", 790, 1080, 4.5, 0.35, 104, "marker", RED, rot=-7)
T("Çıplak gözle görülmez.", 760, 1185, 4.85, 0.6, 48, "pen", RED)

# B) Peki ne yapmalı? -> ampul, tek cümle
T("Peki ne yapabilirsin?", 1620, 640, 5.75, 0.95, 84, "marker", INK)
_q = ellipse_path(1620, 860, 110, 100, math.radians(195), math.radians(255)) + \
    bezier((1650, 958), (1620, 990), (1620, 1060))[1:]
P(_q, 6.1, 0.7, BLUE, 24, 2.5, sound="marker")
P(sketch_circle(1620, 1135, 14, 14, 9), 6.85, 0.15, BLUE, 26, 1.0)
for k, (dx, dy) in enumerate(((-210, -40), (200, 10), (-170, 160), (190, 190))):
    P(line((1620 + dx, 900 + dy), (1620 + dx * 1.15, 900 + dy * 1.15 - 25), 3), 7.0 + k * 0.08, 0.15, AMBER, 7)
_s, _ = wt("sana")
_bulb = ellipse_path(1620, 1330, 115, 125, math.radians(115), math.radians(310))
P(_bulb, _s, 0.45, INK, 8)
P(line((1565, 1440), (1572, 1500)) + line((1572, 1500), (1668, 1500))[1:] + line((1668, 1500), (1675, 1440))[1:],
  _s + 0.4, 0.25, INK, 8)
P(line((1580, 1525), (1660, 1525)), _s + 0.6, 0.12, INK, 8)
P(zigzag_fill(1590, 1360, 1650, 1400, 15), _s + 0.5, 0.25, AMBER, 5)
for k in range(7):
    a = math.radians(-180 + k * 30)
    P(line((1620 + 160 * math.cos(a), 1320 + 170 * math.sin(a)), (1620 + 215 * math.cos(a), 1320 + 225 * math.sin(a)), 3),
      _s + 0.75 + k * 0.04, 0.12, AMBER, 8)
HL(ellipse_path(1620, 1330, 70, 80, 0, 2 * math.pi), _s + 0.8, 0.4, HL_YEL, 70, 140)
_b, _ = wt("basit", _s)
_e, _ = wt("etkili", _s)
T("basit", 1400, 1620, _b, 0.35, 70, "pen", BLUE)
P(check_path(1530, 1610, 1.1), _b + 0.3, 0.2, GREEN, 8)
T("etkili", 1800, 1620, _e, 0.35, 70, "pen", BLUE)
P(check_path(1935, 1610, 1.1), _e + 0.3, 0.2, GREEN, 8)
_y, _ = wt("yöntem", _s)
T("TEK CÜMLE!", 1620, 1790, _y - 0.1, 0.5, 120, "marker", RED)
P(sketch_circle(1620, 1785, 300, 95, 21), _y + 0.4, 0.35, RED, 7)

# C) Sorudan sonra şunu ekle (indeks kartı)
T("Önemli sorundan sonra", 1080, 2150, 11.6, 1.2, 56, "pen", GRAY)
_su, _ = wt("şu", 13)
T("şunu ekle:", 1080, 2250, _su, 0.6, 104, "marker", INK)
_ar = bezier((1310, 2215), (1420, 2240), (1400, 2330))
P(_ar, _su + 0.55, 0.3, RED, 7)
for h in arrow_head(_ar[-3], _ar[-1]):
    P(h, _su + 0.82, 0.08, RED, 7)
CARD = (575, 2340, 1585, 3080)
CARD_T0 = wt("cümleyi", 13)[0] - 0.1
P_SIZE, P_LH = 56, 86
P_X0, P_Y0, P_MAXW = 640, 2470, 880
P_COLORS = {0: HL_GRN, 1: HL_GRN, 2: HL_GRN, 3: HL_YEL, 5: HL_PNK, 6: HL_PNK, 7: HL_PNK}


def prompt_layout():
    f = font("pen", P_SIZE)
    sp = f.getlength(" ")
    x, y, out = 0.0, 0, []
    for k, i in enumerate(PROMPT_IDX):
        w = WORDS[i]["w"]
        wl = f.getlength(w)
        if x > 0 and x + wl > P_MAXW:
            x, y = 0.0, y + 1
        out.append((k, i, w, P_X0 + x, P_Y0 + y * P_LH, wl))
        x += wl + sp
    return out


P_LAYOUT = prompt_layout()


@lru_cache(maxsize=1)
def card_sprite():
    x0, y0, x1, y1 = CARD
    w, h = x1 - x0, y1 - y0
    pad = 30
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k in range(12, 0, -1):
        d.rectangle((pad + 4 - k, pad + 10 - k, pad + w + k, pad + h + k), fill=(60, 40, 20, 4))
    d.rectangle((pad, pad, pad + w, pad + h), fill=(255, 255, 252, 255))
    d.line((pad, pad + 95, pad + w, pad + 95), fill=(235, 130, 130, 255), width=3)
    yy = P_Y0 - y0 + pad + 40
    while yy < pad + h - 20:
        d.line((pad, yy, pad + w, yy), fill=(190, 210, 240, 255), width=2)
        yy += P_LH
    f = font("marker", 46)
    d.text((pad + 40, pad + 50), "Sorundan sonra ekle:", font=f, fill=(150, 150, 165, 255), anchor="lm")
    for tx in (pad + 40, pad + w - 180):  # bantlar
        d.polygon([(tx, pad - 20), (tx + 140, pad - 30), (tx + 150, pad + 22), (tx + 10, pad + 32)],
                  fill=(235, 225, 200, 180))
    return im


def card_draw(c, cam, t):
    p = prog(t, CARD_T0, 0.3)
    if p <= 0:
        return
    x0, y0, x1, y1 = CARD
    sc = cam.z * (1.12 - 0.12 * e_out(p))
    place(c, card_sprite(), *cam.p((x0 + x1) / 2, (y0 + y1) / 2 + (1 - e_out(p)) * 40), sc, min(1, p * 2),
          (1 - e_out(p)) * -4)
    # fosforlu kalem şeritleri (kelime söylenirken)
    for k, i, w, x, y, wl in P_LAYOUT:
        col = P_COLORS.get(k)
        ws, we = WORDS[i]["s"], WORDS[i]["e"]
        if col and t >= ws:
            nxt = next(((kk, xx, yy) for kk, ii, ww, xx, yy, _ in P_LAYOUT if kk == k + 1), None)
            x_end = x + wl + (18 if nxt and P_COLORS.get(k + 1) == col and nxt[2] == y else 0)
            hp = e_out(clamp((t - ws) / max(0.15, we - ws)))
            e = dict(pts=line((x - 6, y + 8), (x - 6 + (x_end - x + 12) * hp, y + 4), 4), t0=ws, dur=1e-3, color=col,
                     width=58, alpha=130, bbox=(x - 40, y - 50, x_end + 40, y + 60), seed=500 + k)
            draw_hl(c, cam, e, t)
    # kelime kelime yazılan metin
    for k, i, w, x, y, wl in P_LAYOUT:
        ws, we = WORDS[i]["s"], WORDS[i]["e"]
        if t < ws:
            break
        frac = clamp((t - ws) / max(0.08, (we - ws) * 0.85))
        size = max(6, round(P_SIZE * cam.z))
        im = txt(w, "pen", size, INK)
        pad = max(4, size // 6)
        if frac < 1:
            im = im.crop((0, 0, max(1, int(pad + (im.width - 2 * pad) * frac) + 2), im.height))
        sx, sy = cam.p(x, y)
        paste(c, im, sx - pad, sy - im.height / 2)
    # "bilmiyorum" etrafına mavi daire
    k14 = next(e for e in P_LAYOUT if e[0] == 14)
    ws = WORDS[k14[1]]["s"]
    if t >= ws:
        _, _, _, x, y, wl = k14
        draw_path(c, cam, sketch_circle(x + wl / 2, y, wl / 2 + 26, 46, 33), (t - ws) / 0.4, BLUE, 6, 1.8, 33, t)


CUSTOM(card_draw, CARD_T0, CARD)
_em, _ = wt("emin", 22)
STICKY(("Ekran görüntüsü", "al!"), 700, 3120, _em, STICKY_P, 380, 220, -4.0, 54)

# D) Cevap üçe ayrılır
T("Böylece cevap 3'e ayrılır:", 600, 3330, 25.55, 1.0, 76, "marker", INK)
_rows = [("Kesin bilgiler", GREEN), ("Tahminler", AMBER), ("Doğrulanması gerekenler", RED)]
for k, (lab, col) in enumerate(_rows):
    y = 3520 + k * 215
    t0 = 25.8 + k * 0.6
    P(rrect_path(120, y - 85, 1080, y + 85, 30), t0, 0.4, INK, 6)
    if k == 0:
        P(check_path(210, y, 1.3), t0 + 0.35, 0.2, col, 10)
    elif k == 1:
        P(wave_path(165, 260, y, 14, 48), t0 + 0.35, 0.2, col, 10)
    else:
        P(ellipse_path(212, y - 22, 34, 30, math.radians(190), math.radians(250)) +
          bezier((228, y + 4), (212, y + 15), (212, y + 30))[1:], t0 + 0.35, 0.2, col, 10)
        P(sketch_circle(212, y + 58, 4, 4, 5), t0 + 0.55, 0.05, col, 12)
    T(lab, 300, y, t0 + 0.3, 0.5, 60 if k < 2 else 54, "pen", col, anchor="lm")
_eo, _ = wt("emin", 27)
P(sketch_circle(600, 3845, 545, 245, 41), _eo, 0.45, RED, 9, 2.5, sound="marker")
_ea = bezier((330, 4150), (240, 4150), (210, 4085))
P(_ea, _eo + 0.45, 0.2, RED, 7)
for h in arrow_head(_ea[-3], _ea[-1], 22):
    P(h, _eo + 0.62, 0.05, RED, 7)
T("emin olmadığı yerler", 360, 4150, _eo + 0.5, 0.8, 58, "pen", RED, anchor="lm")

# E) Ama dikkat!
_tri = [(1610, 3030), (1760, 3270), (1460, 3270), (1612, 3026)]
P(_tri, 31.0, 0.35, RED, 12, 2.5, sound="marker")
T("!", 1610, 3195, 31.3, 0.15, 120, "marker", RED)
T("AMA DİKKAT!", 1610, 3430, 31.13, 0.6, 128, "marker", RED)
T("Yanlışlar azalır…", 1610, 3620, 32.3, 0.7, 64, "pen", INK)
_ax = line((1260, 4160), (1260, 3720), 8)
P(_ax, 32.4, 0.25, INK, 6)
for h in arrow_head(_ax[-2], _ax[-1], 22):
    P(h, 32.62, 0.05, INK, 6)
_ay = line((1260, 4160), (1990, 4160), 8)
P(_ay, 32.55, 0.25, INK, 6)
for h in arrow_head(_ay[-2], _ay[-1], 22):
    P(h, 32.78, 0.05, INK, 6)
T("hata", 1300, 3700, 32.7, 0.3, 44, "pen", GRAY, anchor="lm")
T("zaman", 1880, 4210, 32.8, 0.3, 44, "pen", GRAY)
_ty, _ = wt("yanlışları", 32)
_curve = [(1280 + k * 7, 3760 + 200 * (1 - math.exp(-k / 28))) for k in range(0, 100)]
P(_curve, _ty, 1.0, RED, 9, 1.5, sound="marker")
_tk, _ = wt("kaldırmaz", 32)
P(line((1975, 3972), (1975, 4150), 4), _tk, 0.15, BLUE, 6)
for h in arrow_head((1975, 4060), (1975, 3972), 16) + arrow_head((1975, 4060), (1975, 4150), 16):
    P(h, _tk + 0.15, 0.05, BLUE, 6)
T("…ama sıfırlanmaz!", 1620, 4080, _tk, 0.6, 62, "marker", BLUE, rot=-3)

_oz, _ = wt("özellikle", 35)
T("Önemli bilgiyi kontrol et:", 1610, 4400, _oz, 1.0, 74, "marker", INK)
for k, (lab, cue) in enumerate((("Resmî kaynaklar", "güvenilir"), ("Bilimsel çalışmalar", "kaynaklardan"),
                                ("Uzman görüşü", "kontrol"))):
    y = 4560 + k * 140
    t0 = _oz + 0.6 + k * 0.3
    P(rrect_path(1260, y - 34, 1328, y + 34, 10), t0, 0.25, INK, 6)
    T(lab, 1370, y, t0 + 0.15, 0.5, 58, "pen", INK, anchor="lm")
    tc_, _ = wt(cue, _oz)
    P(check_path(1300, y - 4, 1.2), tc_, 0.22, GREEN, 10)


# Sayfa altı: geri çekilirken yazılan büyük özet
T("EMİN", 640, 5330, 39.5, 0.5, 240, "marker", INK)
P(line((880, 5290), (1080, 5290), 6), 39.95, 0.15, RED, 16, sound="marker")
P(line((880, 5370), (1080, 5370), 6), 40.05, 0.15, RED, 16, sound="marker")
P(line((1030, 5210), (930, 5450), 6), 40.15, 0.15, RED, 16, sound="marker")
T("DOĞRU", 1500, 5330, 40.2, 0.5, 240, "marker", GREEN)
P(wave_path(380, 1800, 5500, 10, 90), 40.55, 0.4, RED, 10)

# F) Final notu (ekran koordinatlarında)
NOTE_T0 = 40.75


def finale(c, t):
    if t < NOTE_T0:
        return
    p = prog(t, NOTE_T0, 0.3)
    # arkadaki sayfayı biraz soldur
    veil = Image.new("RGBA", (W, H), PAPER + (int(110 * e_out(p)),))
    c.alpha_composite(veil)
    im = sticky_sprite((), STICKY_Y, 900, 820, 10)
    place(c, im, 540, 790 + (1 - e_out(p)) * 60, 1.2 - 0.2 * e_out(p), min(1, p * 2), -2 + (1 - e_out(p)) * 6)

    class S:  # ekran kamerası
        z = 1.0

        @staticmethod
        def p(x, y):
            return x, y

    def write(text, key, size, color, x, y, t0, dur, rot=0):
        pp = clamp((t - t0) / dur)
        if pp <= 0:
            return
        im2 = txt(text, key, size, color)
        pad = max(4, size // 6)
        full = im2.width
        if pp < 1:
            im2 = im2.crop((0, 0, max(1, int(pad + (full - 2 * pad) * pp) + 2), im2.height))
        place(c, im2, x - full / 2 + im2.width / 2, y, 1, 1, rot)

    write("Unutma:", "pen", 60, RED, 540, 470, NOTE_T0 + 0.2, 0.4)
    tk, _ = wt("kendinden", 40)
    write("Kendinden emin", "marker", 118, INK, 540, 610, tk, 0.75)
    td, _ = wt("doğru", 43)
    write("her zaman doğru", "marker", 112, GREEN, 540, 980, td, 0.8)
    write("değildir.", "pen", 60, INK, 540, 1090, td + 0.8, 0.4)
    tg, _ = wt("gelmez", 44)
    gp = clamp((t - tg) / 0.4)
    if gp > 0:
        draw_path(c, S, line((440, 770), (640, 770), 6), gp * 2, RED, 16, 1.5, 901, t)
        draw_path(c, S, line((440, 830), (640, 830), 6), gp * 2 - 0.5, RED, 16, 1.5, 902, t)
        draw_path(c, S, line((600, 700), (480, 900), 6), gp * 2 - 1, RED, 16, 1.5, 903, t)
    po = prog(t, 45.9, 0.5)
    if po > 0:
        lab = txt("Kaydet & paylaş", "cap", 46, INK)
        tape = Image.new("RGBA", (lab.width + 60, lab.height + 20), (255, 252, 235, 235))
        tape.alpha_composite(lab, (30, 10))
        place(c, tape, 540, 1330 + (1 - e_out(po)) * 30, 1, po, 1.5)


# ---------------------------------------------------------------- altyazı (bant şerit)
def caption_groups():
    groups, cur = [], []
    for i, x in enumerate(WORDS):
        if cur and (x["seg"] != WORDS[cur[0]]["seg"] or len(cur) >= 3 or
                    sum(len(WORDS[j]["w"]) for j in cur) + len(x["w"]) > 18):
            groups.append(cur)
            cur = []
        cur.append(i)
        if x["w"][-1] in ",.!?:":
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    out = []
    for gi, g in enumerate(groups):
        s = WORDS[g[0]]["s"] - 0.06
        e = WORDS[g[-1]]["e"]
        nxt = WORDS[groups[gi + 1][0]]["s"] - 0.06 if gi + 1 < len(groups) else e + 0.5
        out.append((s, min(nxt, e + 0.4), g, gi))
    return out


CAPS = caption_groups()
CAP_HIDE = (WORDS[PROMPT_IDX[0]]["s"] - 0.1, WORDS[PROMPT_IDX[-1]]["e"] + 0.3)
CAP_Y, CAP_SIZE = 1470, 64


def captions(c, t):
    if CAP_HIDE[0] <= t < CAP_HIDE[1]:
        return
    for s, e, g, gi in CAPS:
        if not (s <= t < e):
            continue
        f = font("cap", CAP_SIZE)
        words = [WORDS[i]["w"] for i in g]
        sp = f.getlength(" ")
        widths = [f.getlength(w) for w in words]
        tw = sum(widths) + sp * (len(words) - 1)
        lw, lh = int(tw + 90), 130
        layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        rnd = random.Random(gi)
        # yırtık kenarlı kâğıt bant
        top = [(x, 14 + rnd.uniform(-3, 3)) for x in range(0, lw, 24)]
        bot = [(x, lh - 14 + rnd.uniform(-3, 3)) for x in range(lw, -1, -24)]
        d.polygon([(4, 10)] + top + [(lw - 4, 12), (lw - 10, lh / 2), (lw - 2, lh - 12)] + bot +
                  [(2, lh - 10), (10, lh / 2)], fill=(255, 252, 238, 240))
        x = 45
        for k, w in enumerate(words):
            i = g[k]
            ws, we = WORDS[i]["s"], WORDS[i]["e"]
            active = ws <= t < we + 0.05
            col = RED if active else (INK if t >= ws - 0.02 else (150, 150, 165))
            d.text((x, lh / 2), w, font=f, fill=col + (255,), anchor="lm")
            if active:  # el çizimi alt çizgi
                hp = e_out(clamp((t - ws) / 0.18))
                pts = [(x + (widths[k]) * u * hp, lh / 2 + 36 + 4 * math.sin(u * 9 + gi)) for u in
                       (q / 12 for q in range(13))]
                d.line(pts, fill=RED + (255,), width=6, joint="curve")
            x += widths[k] + sp
        pg = prog(t, s, 0.18)
        rot = 1.2 if gi % 2 else -1.2
        place(c, layer, 540, CAP_Y + (1 - e_out(pg)) * 20, 0.9 + 0.1 * e_back(pg), pg * (1 - prog(t, e - 0.1, 0.1)),
              rot)


# ---------------------------------------------------------------- kompozisyon
def background(cam):
    frame = Image.new("RGBA", (W, H), DESK + (255,))
    d = ImageDraw.Draw(frame)
    px0, py0 = cam.p(PAGE[0], PAGE[1])
    px1, py1 = cam.p(PAGE[2], PAGE[3])
    for k in range(8, 0, -1):  # sayfa gölgesi
        d.rectangle((px0 + 6 - k * 2, py0 + 10 - k * 2, px1 + k * 2 + 6, py1 + k * 2 + 10), fill=(40, 30, 25, 18))
    d.rectangle((px0, py0, px1, py1), fill=PAPER + (255,))
    x0, y0, x1, y1 = cam.view()
    step = 64
    gw = max(1, int(round(2 * cam.z)))
    gx = math.ceil(max(x0, PAGE[0]) / step) * step
    while gx < min(x1, PAGE[2]):
        sx = cam.p(gx, 0)[0]
        d.line((sx, max(py0, 0), sx, min(py1, H)), fill=GRID + (255,), width=gw)
        gx += step
    gy = math.ceil(max(y0, PAGE[1]) / step) * step
    while gy < min(y1, PAGE[3]):
        sy = cam.p(0, gy)[1]
        d.line((max(px0, 0), sy, min(px1, W), sy), fill=GRID + (255,), width=gw)
        gy += step
    mx = cam.p(150, 0)[0]
    d.line((mx, max(py0, 0), mx, min(py1, H)), fill=MARGIN + (255,), width=max(1, int(3 * cam.z)))
    return frame


def visible(e, cam):
    x0, y0, x1, y1 = cam.view()
    b = e["bbox"]
    return not (b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1)


def render_frame(fi):
    t = fi / FPS
    cam = Cam(t)
    frame = background(cam)
    for e in ELEMENTS:
        if t < e["t0"] or not visible(e, cam):
            continue
        k = e["kind"]
        if k == "text":
            draw_text(frame, cam, e, t)
        elif k == "path":
            if e["fill"]:
                ImageDraw.Draw(frame).polygon([cam.p(*q) for q in e["pts"]], fill=e["fill"] + (255,))
            draw_path(frame, cam, e["pts"], (t - e["t0"]) / e["dur"], e["color"], e["width"], e["boil"], e["seed"], t)
        elif k == "hl":
            draw_hl(frame, cam, e, t)
        elif k == "sticky":
            draw_sticky(frame, cam, e, t)
        elif k == "custom":
            e["fn"](frame, cam, t)
    finale(frame, t)
    captions(frame, t)
    # ilerleme: kurşun kalem çizgisi
    d = ImageDraw.Draw(frame)
    d.line((40, 40, 40 + (W - 80) * t / DUR, 40 + 2 * math.sin(t * 3)), fill=INK + (200,), width=6)
    arr = np.asarray(frame.convert("RGB"), np.float32) + GRAIN
    fade = max(1 - t / 0.25, (t - (DUR - 0.5)) / 0.5, 0)
    if fade > 0:
        arr = arr * (1 - fade) + np.array(PAPER, np.float32) * fade
    return np.clip(arr, 0, 255).astype(np.uint8).tobytes()


GRAIN = None


def main():
    global GRAIN
    from sound_doodle import build_mix_doodle
    os.makedirs("out", exist_ok=True)
    GRAIN = np.random.default_rng(5).normal(0, 2.2, (H, W, 1)).astype(np.float32)
    mix_path = build_mix_doodle(AUDIO, DUR, WORDS, ELEMENTS, MOVES, "out/mix_doodle.wav")
    if "--preview" in sys.argv:
        for s in sys.argv[sys.argv.index("--preview") + 1:]:
            Image.frombytes("RGB", (W, H), render_frame(int(float(s) * FPS))).save(
                f"out/preview_doodle_{float(s):05.2f}.png")
        return
    n = int(DUR * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", mix_path,
                           "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-maxrate", "12M", "-bufsize", "24M",
                           "-pix_fmt", "yuv420p", "-profile:v", "high",
                           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
                           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                           "-shortest", OUT], stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for k, buf in enumerate(pool.imap(render_frame, range(n), chunksize=6)):
            ff.stdin.write(buf)
            if k % 300 == 0:
                print(f"{k}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("bitti:", OUT)


if __name__ == "__main__":
    main()
