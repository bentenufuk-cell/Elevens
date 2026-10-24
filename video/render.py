"""ElevenLabs seslendirmesinden dikey (1080x1920) Shorts/Reels videosu üretir.

Tüm görseller kod ile üretilir (PIL + numpy), kareler ffmpeg'e borulanır.
Kullanım:  python3 render.py            -> out/elevens1_shorts.mp4
           python3 render.py --preview 4.5 12 27   -> belirtilen saniyelerin PNG önizlemesi
"""
import json
import math
import os
import random
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from sound import build_mix

W, H, FPS = 1080, 1920, 30
AUDIO = "assets/elevens1.mp3"
DUR = 47.2
OUT = "out/elevens1_shorts.mp4"

# ---------------------------------------------------------------- palet
BG = (7, 9, 16)
PANEL = (20, 24, 38)
PANEL_LINE = (44, 52, 76)
TXT = (232, 236, 245)
DIM = (140, 148, 170)
LIME = (212, 255, 58)
GREEN = (52, 227, 154)
AMBER = (255, 194, 61)
RED = (255, 77, 94)
CYAN = (61, 224, 255)
VIOLET = (139, 108, 255)
BLUE = (45, 107, 255)

FD = "/usr/share/fonts/opentype/inter/"
F_BLACK = FD + "InterDisplay-Black.otf"
F_XB = FD + "InterDisplay-ExtraBold.otf"
F_BOLD = FD + "Inter-Bold.otf"
F_SEMI = FD + "Inter-SemiBold.otf"
F_MED = FD + "Inter-Medium.otf"
F_MONO = "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Bold.ttf"
F_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

WORDS = json.load(open("words.json"))

# sahne sınırları
S_BOUNDS = [0.0, 5.55, 11.35, 25.45, 31.0, 39.4, DUR]


def wt(word, after=0.0):
    """`word` ile başlayan ilk kelimenin (başlangıç, bitiş) zamanı (after sonrasında)."""
    for x in WORDS:
        if x["s"] >= after - 1e-3 and x["w"].lower().strip("“”,.!?:").startswith(word.lower()):
            return x["s"], x["e"]
    raise KeyError(word)


# ---------------------------------------------------------------- yardımcılar
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def prog(t, t0, d):
    return clamp((t - t0) / d) if d > 0 else float(t >= t0)


def e_out(p):
    return 1 - (1 - p) ** 3


def e_in(p):
    return p ** 3


def e_inout(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def e_back(p, s=1.9):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def e_elastic(p):
    if p <= 0 or p >= 1:
        return p
    return 2 ** (-10 * p) * math.sin((p * 10 - 0.75) * (2 * math.pi / 3)) + 1


def mix(a, b, p):
    return tuple(int(a[i] + (b[i] - a[i]) * p) for i in range(len(a)))


def tr_upper(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=4096)
def text_sprite(text, fpath, size, fill, shadow=0, glow=None):
    """Ortak taban çizgili metin sprite'ı. (img, pad) döner; metin (pad,pad)'den başlar."""
    f = font(fpath, size)
    asc, desc = f.getmetrics()
    tw = int(math.ceil(f.getlength(text)))
    pad = max(8, shadow * 3, glow[1] * 3 if glow else 0)
    im = Image.new("RGBA", (tw + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((pad, pad + shadow // 2), text, font=f, fill=(0, 0, 0, 200))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(shadow)))
    if glow:
        gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(gl).text((pad, pad), text, font=f, fill=glow[0] + (255,))
        gl = gl.filter(ImageFilter.GaussianBlur(glow[1]))
        im = Image.alpha_composite(Image.alpha_composite(im, gl), gl)
    ImageDraw.Draw(im).text((pad, pad), text, font=f, fill=fill)
    return im, pad


@lru_cache(maxsize=256)
def emoji(ch, size):
    f = font(F_EMOJI, 109)
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    s = size / max(im.size)
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


@lru_cache(maxsize=512)
def rrect(w, h, r, fill, outline=None, width=0, shadow=0):
    pad = shadow * 2
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((pad, pad + shadow // 2, pad + w, pad + h + shadow // 2), r,
                                             fill=(0, 0, 0, 150))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(shadow)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1), r, fill=fill, outline=outline, width=width)
    return im


@lru_cache(maxsize=64)
def glow_ring(w, h, r, color, blur):
    pad = blur * 3
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w, pad + h), r, outline=color + (255,), width=6)
    return im.filter(ImageFilter.GaussianBlur(blur))


def set_alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


def paste(canvas, im, x, y):
    """Sınır dışına taşmayı tolere eden alpha_composite (x,y = sol üst)."""
    x, y = int(round(x)), int(round(y))
    sx, sy = max(0, -x), max(0, -y)
    ex, ey = min(im.width, canvas.width - x), min(im.height, canvas.height - y)
    if ex <= sx or ey <= sy:
        return
    if (sx, sy, ex, ey) != (0, 0, im.width, im.height):
        im = im.crop((sx, sy, ex, ey))
    canvas.alpha_composite(im, (x + sx, y + sy))


def place(canvas, im, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    if alpha <= 0.004 or scale <= 0.01:
        return
    if abs(scale - 1) > 1e-3:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if abs(rot) > 0.05:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    im = set_alpha(im, alpha)
    paste(canvas, im, cx - im.width / 2, cy - im.height / 2)


def text_c(canvas, text, fpath, size, fill, cx, cy, scale=1.0, alpha=1.0, rot=0.0, shadow=0, glow=None):
    im, _ = text_sprite(text, fpath, size, fill, shadow, glow)
    place(canvas, im, cx, cy, scale, alpha, rot)


def wrap(text, fpath, size, maxw):
    f = font(fpath, size)
    lines, cur = [], ""
    for w in text.split():
        nxt = (cur + " " + w).strip()
        if f.getlength(nxt) <= maxw or not cur:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def pill(text, fpath, size, fg, bg, padx=34, pady=18, outline=None, em=None):
    f = font(fpath, size)
    tw = int(f.getlength(text))
    asc, desc = f.getmetrics()
    h = asc + desc + 2 * pady - 10
    ew = int(size * 1.1) + 16 if em else 0
    im = rrect(tw + 2 * padx + ew, h, h // 2, bg, outline, 3 if outline else 0).copy()
    if em:
        e = emoji(em, int(size * 1.1))
        im.alpha_composite(e, (padx, (h - e.height) // 2))
    ImageDraw.Draw(im).text((padx + ew, pady - 5), text, font=f, fill=fg)
    return im


def shake_xy(t, events):
    dx = dy = 0.0
    for t0, amp, decay in events:
        if t >= t0:
            a = amp * math.exp(-(t - t0) * decay)
            if a > 0.3:
                dx += a * math.sin(t * 91.0 + t0 * 7)
                dy += a * math.cos(t * 77.0 + t0 * 3)
    return dx, dy


# ---------------------------------------------------------------- arka plan
LW, LH = 135, 240
_yy, _xx = np.mgrid[0:LH, 0:LW].astype(np.float32)

SCENE_TINTS = [  # her sahne için 3 renk lekesi
    [(45, 107, 255), (139, 108, 255), (61, 224, 255)],
    [(212, 255, 58), (61, 224, 255), (45, 107, 255)],
    [(45, 107, 255), (61, 224, 255), (139, 108, 255)],
    [(52, 227, 154), (61, 224, 255), (255, 194, 61)],
    [(255, 77, 94), (255, 120, 60), (139, 108, 255)],
    [(139, 108, 255), (61, 224, 255), (212, 255, 58)],
]


def scene_index(t):
    for i in range(len(S_BOUNDS) - 1):
        if t < S_BOUNDS[i + 1]:
            return i
    return len(S_BOUNDS) - 2


def background(t, energy):
    i = scene_index(t)
    tint = SCENE_TINTS[i]
    # sahne geçişlerinde renk yumuşak geçsin
    if i > 0 and t - S_BOUNDS[i] < 0.6:
        p = (t - S_BOUNDS[i]) / 0.6
        tint = [mix(a, b, p) for a, b in zip(SCENE_TINTS[i - 1], tint)]
    img = np.zeros((LH, LW, 3), np.float32)
    img[:] = BG
    k = 0.20 + 0.12 * energy
    for j, col in enumerate(tint):
        cx = LW * (0.5 + 0.38 * math.sin(t * 0.21 + j * 2.1))
        cy = LH * (0.45 + 0.35 * math.cos(t * 0.17 + j * 1.7))
        r = (55 + 12 * math.sin(t * 0.5 + j)) ** 2
        g = np.exp(-((_xx - cx) ** 2 + (_yy - cy) ** 2) / r)[..., None]
        img += g * np.array(col, np.float32) * (k if j else k * 1.3)
    small = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return small.resize((W, H), Image.BICUBIC).convert("RGBA")


def make_static_layers():
    rng = np.random.default_rng(7)
    dots = Image.new("RGBA", (W, H + 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(dots)
    for y in range(0, H + 60, 60):
        for x in range(30, W, 60):
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 255, 255, 16))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = 1 - 0.55 * np.clip(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2, 0, 1)
    grains = [rng.normal(0, 3.0, (H, W, 1)).astype(np.float32)]  # durağan gren: dosya boyutu makul kalsın
    return dots, v[..., None].astype(np.float32), grains


DOTS, VIGNETTE, GRAINS = None, None, None


# ---------------------------------------------------------------- sahne 1: kendinden emin yanlış cevap
Q_TEXT = "Ay'a ilk ayak basan kim?"
A_TEXT = "Elbette! Ay'a ilk ayak basan kişi Yuri Gagarin'dir (1961)."


def avatar(size=92):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for r in range(size // 2, 0, -1):
        c = mix(VIOLET, CYAN, 1 - r / (size / 2))
        d.ellipse((size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r), fill=c + (255,))
    f = font(F_BLACK, int(size * 0.42))
    d.text((size / 2, size / 2), "AI", font=f, fill=(255, 255, 255), anchor="mm")
    return im


AVATAR = None


def scene1(c, t):
    # kanca başlığı
    ph = prog(t, 0.0, 0.4)
    text_c(c, "ChatGPT'yi daha dürüst yapan", F_BOLD, 50, TXT + (255,), 540, 300 - (1 - e_out(ph)) * 40, 1, ph)
    text_c(c, "TEK CÜMLE", F_BLACK, 120, LIME + (255,), 540, 400, 0.7 + 0.3 * e_back(prog(t, 0.12, 0.4)),
           prog(t, 0.12, 0.3), glow=(LIME, 14))
    # kullanıcı balonu
    p = prog(t, 0.05, 0.35)
    fq = font(F_SEMI, 58)
    qw = int(fq.getlength(Q_TEXT)) + 80
    qb = rrect(qw, 116, 50, BLUE + (255,), shadow=14).copy()
    ImageDraw.Draw(qb).text((28 + 40, 28 + 24), Q_TEXT, font=fq, fill=(255, 255, 255))
    place(c, qb, 1020 - qw / 2 + (1 - e_out(p)) * 120, 600, 0.85 + 0.15 * e_back(p), p)

    # yapay zekâ avatarı + yazıyor noktaları / cevap balonu
    pa = prog(t, 0.35, 0.3)
    place(c, AVATAR, 100, 790, e_back(pa), pa)
    fa = font(F_SEMI, 58)
    lines = wrap(A_TEXT, F_SEMI, 58, 760)
    t_type0, t_type1 = 0.75, 2.6
    n = int(len(A_TEXT) * prog(t, t_type0, t_type1 - t_type0))
    wrong = prog(t, 4.36, 0.12)
    bw, lh = 860, 78
    if t < t_type0:
        if pa > 0:
            bub = rrect(200, 100, 44, PANEL + (255,), PANEL_LINE + (255,), 2, shadow=14).copy()
            d = ImageDraw.Draw(bub)
            for k in range(3):
                a = 0.5 + 0.5 * math.sin(t * 12 - k * 1.1)
                d.ellipse((28 + 52 + k * 40 - 10, 28 + 40, 28 + 52 + k * 40 + 10, 28 + 60),
                          fill=mix(DIM, TXT, a) + (255,))
            place(c, bub, 170 + 100, 800, e_back(pa), pa)
        return
    # yazılan satırlar
    shown, left = [], n
    for ln in lines:
        if left <= 0:
            break
        shown.append(ln[:left])
        left -= len(ln) + 1
    bh = 56 + lh * max(1, len(shown))
    border = mix(PANEL_LINE, RED, wrong)
    bub = rrect(bw, bh, 40, mix(PANEL, (48, 16, 26), wrong * 0.8) + (255,), border + (255,), 3, shadow=14).copy()
    d = ImageDraw.Draw(bub)
    for k, ln in enumerate(shown):
        d.text((28 + 40, 28 + 26 + k * lh), ln, font=fa, fill=TXT)
    if t < t_type1 + 0.2 and int(t * 4) % 2 == 0:
        last = shown[-1]
        x = 28 + 40 + fa.getlength(last) + 4
        y = 28 + 26 + (len(shown) - 1) * lh
        d.rectangle((x, y + 6, x + 5, y + 64), fill=LIME)
    gx, gy = 0, 0
    if 4.36 <= t < 4.75:  # glitch sarsıntısı
        rnd = random.Random(int(t * FPS))
        gx = rnd.randint(-22, 22)
    bx, by = 170, 745
    paste(c, bub, bx - 28 + gx, by - 28 + gy)
    if 4.36 <= t < 4.7:  # balonda yatay kayma şeritleri
        rnd = random.Random(int(t * FPS) * 3)
        for _ in range(4):
            y0 = rnd.randint(0, bh - 30)
            strip = bub.crop((0, 28 + y0, bub.width, 28 + y0 + rnd.randint(10, 34)))
            paste(c, strip, bx - 28 + rnd.randint(-60, 60), by + y0)

    # "%100 EMİN" damgası
    ps = prog(t, 2.85, 0.22)
    if ps > 0:
        st = pill("%100 EMİN ✓", F_BLACK, 46, (6, 30, 18), GREEN + (255,), 30, 18)
        a = ps * (1 - wrong * 0.75)
        place(c, st, 850, by - 14, 1.8 - 0.8 * e_out(ps), a, -8)
    # "YANLIŞ" damgası
    pw = prog(t, 4.45, 0.2)
    if pw > 0:
        stamp = text_sprite("YANLIŞ", F_BLACK, 170, RED + (255,), shadow=0, glow=(RED, 10))[0]
        place(c, stamp, 560, by + bh / 2 + 10, 2.2 - 1.2 * e_out(pw), pw, 7)
    # doğrusu
    pc = prog(t, 4.85, 0.3)
    if pc > 0:
        cor = pill("Doğrusu: Neil Armstrong, 1969", F_BOLD, 46, GREEN, (12, 40, 30, 235), 30, 18,
                   outline=GREEN + (150,))
        place(c, cor, 540, by + bh + 90 + (1 - e_out(pc)) * 40, 1, pc)


# ---------------------------------------------------------------- sahne 2: soru işareti -> yöntem
def scene2(c, t):
    t0 = 5.55
    s_card, _ = wt("sana")
    p_in = prog(t, t0 + 0.05, 0.5)
    p_out = prog(t, s_card - 0.25, 0.3)
    if p_out < 1:
        bob = math.sin(t * 2.4) * 6
        sc = e_back(p_in) * (1 - e_in(p_out))
        qm, _ = text_sprite("?", F_BLACK, 640, LIME + (255,), glow=(LIME, 26))
        # yörüngede dönen noktalar
        for k in range(3):
            for trail in range(10):
                ang = t * 2.2 + k * 2.094 - trail * 0.06
                x = 540 + math.cos(ang) * 330 * sc
                y = 720 + math.sin(ang) * 110 * sc + math.sin(ang) * math.cos(t) * 40
                r = (14 - trail) * sc
                if r > 1:
                    col = (CYAN, VIOLET, LIME)[k]
                    ImageDraw.Draw(c).ellipse((x - r, y - r, x + r, y + r),
                                              fill=col + (int(255 * (1 - trail / 10) * p_in),))
        place(c, qm, 540, 700 + bob, sc, p_in, math.sin(t * 1.7) * 6)
    if t < s_card - 0.25:
        return
    # yöntem kartı
    pc = prog(t, s_card - 0.1, 0.45)
    card = rrect(860, 640, 56, PANEL + (245,), PANEL_LINE + (255,), 3, shadow=24)
    ring = glow_ring(860, 640, 56, LIME, 14)
    yy = 760 + (1 - e_out(pc)) * 200
    place(c, ring, 540, yy, 0.9 + 0.1 * e_back(pc), pc * (0.6 + 0.3 * math.sin(t * 4)))
    place(c, card, 540, yy, 0.9 + 0.1 * e_back(pc), pc)
    place(c, emoji("💡", 150), 540, yy - 190, e_back(prog(t, s_card, 0.4)), pc)
    for word, col, x in (("basit", CYAN, 360), ("etkili", VIOLET, 720)):
        ts, _ = wt(word, s_card)
        pp = prog(t, ts, 0.3)
        tag = pill(tr_upper(word) + " ✓", F_BLACK, 52, BG, col + (255,), 36, 20)
        place(c, tag, x, yy - 10, e_back(pp), pp)
    ty, _ = wt("yöntem", s_card)
    pt = prog(t, ty - 0.05, 0.35)
    text_c(c, "TEK CÜMLE", F_BLACK, 132, (255, 255, 255, 255), 540, yy + 170, 0.6 + 0.4 * e_back(pt), pt)


# ---------------------------------------------------------------- sahne 3: cümleyi ekle (yazma efekti)
PROMPT_IDX = [i for i, x in enumerate(WORDS) if 5 <= x["seg"] <= 8]
PROMPT_COLORS = {0: GREEN, 1: GREEN, 2: GREEN, 3: AMBER, 5: RED, 6: RED, 7: RED, 14: CYAN}
P_SIZE, P_LH, P_X0, P_MAXW = 54, 76, 120, 840


def prompt_layout():
    f = font(F_SEMI, P_SIZE)
    sp = f.getlength(" ")
    x, y, out = 0.0, 0, []
    for k, i in enumerate(PROMPT_IDX):
        w = WORDS[i]["w"]
        fp = F_BOLD if k in PROMPT_COLORS else F_SEMI
        wl = font(fp, P_SIZE).getlength(w)
        if x > 0 and x + wl > P_MAXW:
            x, y = 0.0, y + 1
        out.append((k, i, w, fp, x, y, wl))
        x += wl + sp
    return out


P_LAYOUT = prompt_layout()
P_LINES = P_LAYOUT[-1][5] + 1


def scene3(c, t):
    t0 = 11.35
    s_type = WORDS[PROMPT_IDX[0]]["s"]
    e_type = WORDS[PROMPT_IDX[-1]]["e"]
    # adım 1: soru balonu (iskelet)
    p1 = prog(t, t0 + 0.05, 0.4)
    up = e_inout(prog(t, s_type - 0.5, 0.5))
    qy = 470 - up * 120
    qa = p1 * (1 - 0.65 * up)
    sk = rrect(620, 150, 44, BLUE + (255,), shadow=12).copy()
    d = ImageDraw.Draw(sk)
    d.rounded_rectangle((28 + 40, 28 + 36, 28 + 520, 28 + 60), 12, fill=(255, 255, 255, 120))
    d.rounded_rectangle((28 + 40, 28 + 86, 28 + 380, 28 + 110), 12, fill=(255, 255, 255, 90))
    place(c, sk, 1010 - 310, qy, 0.9 + 0.1 * e_back(p1), qa)
    lab = pill("1  ÖNEMLİ SORUN", F_BLACK, 34, BG, (255, 255, 255, 230), 24, 14)
    place(c, lab, 1010 - 310, qy - 108, e_back(p1), qa)

    # ok
    ts, _ = wt("sonra", t0)
    pa = prog(t, ts, 0.3)
    if up < 1:
        arr = emoji("👇", 90)
        place(c, arr, 540, 650 + math.sin(t * 8) * 8, e_back(pa), pa * (1 - up))

    # adım 2: composer
    tc, _ = wt("cümleyi", t0)
    pb = prog(t, tc - 0.1, 0.4)
    if pb <= 0:
        return
    n_lines_shown = 1
    for k, i, w, fp, x, y, wl in P_LAYOUT:
        if t >= WORDS[i]["s"]:
            n_lines_shown = y + 1
    box_h = int(80 + P_LINES * P_LH)  # sabit yükseklik: ekran görüntüsü için rahat
    box_y = int(780 - up * 190)
    bx = 60
    ring = glow_ring(960, box_h, 46, LIME, 16)
    box = rrect(960, box_h, 46, (16, 19, 31, 250), (70, 80, 110, 255), 3, shadow=22)
    sc = 0.85 + 0.15 * e_back(pb)
    cy = box_y + box_h / 2 + (1 - e_out(pb)) * 120
    place(c, ring, 540, cy, sc, pb * (0.45 + 0.25 * math.sin(t * 3)))
    place(c, box, 540, cy, sc, pb)
    lab2 = pill("2  BU CÜMLEYİ EKLE", F_BLACK, 34, BG, LIME + (255,), 24, 14)
    place(c, lab2, 60 + 190, cy - box_h / 2 * sc - 48, e_back(pb), pb)

    # yazılan metin
    if t >= s_type - 0.3:
        dl = ImageDraw.Draw(c)
        top = box_y + 46
        cursor = None
        for k, i, w, fp, x, y, wl in P_LAYOUT:
            ws, we = WORDS[i]["s"], WORDS[i]["e"]
            if t < ws:
                break
            f = font(fp, P_SIZE)
            col = PROMPT_COLORS.get(k, TXT)
            frac = clamp((t - ws) / max(0.08, (we - ws) * 0.8))
            part = w[: max(1, int(round(len(w) * frac)))]
            X, Y = P_X0 + x, top + y * P_LH
            if t < we:
                dl.rounded_rectangle((X - 8, Y + 2, X + wl + 8, Y + P_LH - 6), 12, fill=LIME + (60,))
            dl.text((X, Y + 4), part, font=f, fill=col)
            cursor = (X + f.getlength(part) + 3, Y)
        if cursor and (t < e_type + 0.1 or int(t * 3) % 2 == 0):
            dl.rectangle((cursor[0], cursor[1] + 10, cursor[0] + 5, cursor[1] + 66), fill=LIME)
        # gönder butonu
        pbtn = prog(t, e_type - 0.25, 0.3)
        press = math.exp(-max(0, t - (e_type + 0.05)) * 10) if t > e_type + 0.05 else 0
        btn = Image.new("RGBA", (110, 110), (0, 0, 0, 0))
        db = ImageDraw.Draw(btn)
        db.ellipse((0, 0, 109, 109), fill=LIME)
        db.polygon([(55, 28), (82, 58), (64, 58), (64, 84), (46, 84), (46, 58), (28, 58)], fill=BG)
        place(c, btn, 930, box_y + box_h + 80, e_back(pbtn) * (1 - 0.15 * press), pbtn)
    # kaydet ipucu
    tk, _ = wt("emin", s_type)
    pk = prog(t, tk, 0.35)
    if pk > 0:
        sv = pill("Ekran görüntüsü al!", F_BOLD, 40, TXT, (30, 34, 52, 240), 30, 18, outline=PANEL_LINE + (255,),
                  em="📌")
        place(c, sv, 330, box_y + box_h + 80, e_back(pk), pk)


# ---------------------------------------------------------------- sahne 4: üç katmanlı cevap
ROWS = [("✅", "KESİN", "Bildiği gerçekler", GREEN),
        ("🤔", "TAHMİN", "Olasılıklar, yorumlar", AMBER),
        ("⚠️", "DOĞRULA", "Kontrol edilmesi gerekenler", RED)]


def scene4(c, t):
    t0 = 25.45
    pc = prog(t, t0 + 0.05, 0.4)
    card_y = 760
    card = rrect(920, 820, 52, PANEL + (245,), PANEL_LINE + (255,), 3, shadow=26)
    place(c, card, 540, card_y, 0.85 + 0.15 * e_back(pc), pc)
    place(c, AVATAR, 150, card_y - 320, e_back(pc) * 0.8, pc)
    text_c(c, "Yanıt artık şöyle:", F_BOLD, 44, DIM + (255,), 370, card_y - 320, 1, pc)
    t_emin, _ = wt("emin", t0)
    t_fark, _ = wt("fark", t0)
    for k, (em, title, sub, col) in enumerate(ROWS):
        tr = t0 + 0.35 + k * 0.6
        pr = prog(t, tr, 0.35)
        if pr <= 0:
            continue
        y = card_y - 170 + k * 200
        hl = prog(t, t_emin + (k - 1) * 0.35, 0.25) if k > 0 else 0
        dim = prog(t, t_emin, 0.3) if k == 0 else 0
        pulse = hl * (0.5 + 0.5 * math.sin((t - t_emin) * 9))
        row = rrect(820, 170, 34, mix((26, 31, 48), tuple(v // 4 for v in col), 0.5 + 0.5 * hl) + (255,),
                    mix(PANEL_LINE, col, hl) + (255,), 3 + int(3 * hl)).copy()
        d = ImageDraw.Draw(row)
        row.alpha_composite(emoji(em, 86), (32, 42))
        d.text((150, 30), title, font=font(F_BLACK, 56), fill=col)
        d.text((152, 100), sub, font=font(F_MED, 36), fill=DIM)
        for j in range(3):  # iskelet çizgiler sağda
            d.rounded_rectangle((560, 52 + j * 26, 560 + (210 - j * 50), 64 + j * 26), 6, fill=(255, 255, 255, 30))
        x = 540 - (1 - e_out(pr)) * 300
        if hl > 0:
            place(c, glow_ring(820, 170, 34, col, 12), x, y, 1, 0.4 + 0.6 * pulse)
        place(c, row, x, y, 1 + 0.03 * pulse, pr * (1 - 0.5 * dim))
    # büyüteç
    pm = prog(t, t_emin, 0.3)
    if pm > 0:
        sweep = e_inout(prog(t, t_emin, max(0.5, t_fark - t_emin)))
        mx = 820 + math.sin(t * 5) * 20
        my = card_y + 30 + sweep * 200
        place(c, emoji("🔍", 140), mx, my, e_back(pm), pm, -15)


# ---------------------------------------------------------------- sahne 5: dikkat
def hazard_band(width, height, offset):
    im = Image.new("RGBA", (width, height), AMBER + (255,))
    d = ImageDraw.Draw(im)
    step = 80
    for x in range(-height - step * 2, width + step * 2, step):
        xo = x + offset % step
        d.polygon([(xo, height), (xo + step / 2, height), (xo + step / 2 + height, 0), (xo + height, 0)],
                  fill=(20, 20, 24, 255))
    return im


def scene5(c, t):
    t0 = 31.0
    t_bu, _ = wt("bu", t0 + 0.5)
    t_oz, _ = wt("özellikle", t0)
    # A: DİKKAT
    pa_out = prog(t, t_bu - 0.15, 0.3)
    if pa_out < 1:
        pa = prog(t, t0, 0.25)
        off = (t - t0) * 400
        for yb, dirn in ((300, 1), (1160, -1)):
            band = hazard_band(W + 200, 70, off * dirn)
            place(c, band, 540 + (1 - e_out(pa)) * 1200 * dirn - e_in(pa_out) * 1200 * dirn, yb, 1, 1, -4)
        sc = (1.6 - 0.6 * e_out(pa)) * (1 - e_in(pa_out))
        place(c, emoji("⚠️", 260), 540, 600, sc, pa)
        text_c(c, "DİKKAT!", F_BLACK, 210, (255, 255, 255, 255), 540, 870, sc, pa, glow=(RED, 22))
    # B: yanlışlar azalır ama sıfırlanmaz
    pb = prog(t, t_bu - 0.05, 0.35)
    pb_out = prog(t, t_oz - 0.2, 0.3)
    if pb > 0 and pb_out < 1:
        xs = -e_in(pb_out) * 1100
        a = pb
        text_c(c, "YANLIŞLAR", F_BLACK, 70, DIM + (255,), 540 + xs, 400, 1, a)
        base = 1100
        ty, _ = wt("yanlışları", t0)
        tk, _ = wt("kaldırmaz", t0)
        grow = e_out(prog(t, t_bu, 0.5))
        shrink = e_inout(prog(t, ty, 0.6))
        h1 = 560 * grow
        h2 = 560 * grow * (1 - 0.68 * shrink)
        d = ImageDraw.Draw(c)
        for x, h, col, lab in ((330, h1, RED, "ÖNCE"), (750, h2, AMBER, "SONRA")):
            if h > 4:
                d.rounded_rectangle((x - 120 + xs, base - h, x + 120 + xs, base), 26, fill=col + (int(255 * a),))
            text_c(c, lab, F_BLACK, 52, (255, 255, 255, 255), x + xs, base + 60, 1, a)
        pk = prog(t, tk, 0.3)
        if pk > 0:
            text_c(c, "≠ 0", F_BLACK, 140, (255, 255, 255, 255), 750 + xs, base - h2 - 100,
                   e_back(pk) * (1 + 0.05 * math.sin(t * 10)), pk, glow=(AMBER, 16))
    # C: kaynak kontrol listesi
    pc = prog(t, t_oz - 0.15, 0.4)
    if pc > 0:
        xs = (1 - e_out(pc)) * 1100
        text_c(c, "KAYNAĞINDAN", F_BLACK, 92, (255, 255, 255, 255), 540 + xs, 400, 1, pc)
        text_c(c, "KONTROL ET", F_BLACK, 92, LIME + (255,), 540 + xs, 500, 1, pc, glow=(LIME, 12))
        items = [("📚", "Resmî kaynaklar", "güvenilir"), ("🔬", "Bilimsel çalışmalar", "kaynaklardan"),
                 ("🎓", "Uzman görüşü", "kontrol")]
        for k, (em, txt, cue) in enumerate(items):
            ti = t_oz + 0.3 + k * 0.25
            pi = prog(t, ti, 0.35)
            if pi <= 0:
                continue
            tt, _ = wt(cue, t_oz)
            pt = prog(t, tt, 0.25)
            y = 700 + k * 175
            row = rrect(860, 140, 34, mix((26, 31, 48), (30, 52, 22), pt) + (250,),
                        mix(PANEL_LINE, LIME, pt) + (255,), 3).copy()
            d = ImageDraw.Draw(row)
            row.alpha_composite(emoji(em, 78), (34, 31))
            d.text((140, 42), txt, font=font(F_BOLD, 50), fill=TXT)
            d.rounded_rectangle((720, 30, 800, 110), 20, outline=mix(DIM, LIME, pt), width=5,
                                fill=LIME if pt > 0.5 else None)
            if pt > 0:
                q = e_out(pt)
                pts = [(738, 70), (755, 88), (785, 50)]
                seg = [pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * min(1, q * 2),
                                pts[0][1] + (pts[1][1] - pts[0][1]) * min(1, q * 2))]
                if q > 0.5:
                    seg.append((pts[1][0] + (pts[2][0] - pts[1][0]) * (q - 0.5) * 2,
                                pts[1][1] + (pts[2][1] - pts[1][1]) * (q - 0.5) * 2))
                d.line(seg, fill=BG, width=10, joint="curve")
            place(c, row, 540 + xs + (1 - e_out(pi)) * 400, y, 1 + 0.04 * (1 - pt) * pt * 4, pi)


# ---------------------------------------------------------------- sahne 6: emin ≠ doğru
def scene6(c, t):
    t0 = 39.4
    tu, _ = wt("unutma")
    pu = prog(t, tu, 0.3)
    tag = pill("UNUTMA", F_BLACK, 50, BG, LIME + (255,), 40, 22)
    place(c, tag, 540, 360, e_back(pu), pu)
    tk, _ = wt("kendinden", t0)
    te, _ = wt("emin", t0)
    pk = prog(t, tk, 0.3)
    pe = prog(t, te, 0.3)
    text_c(c, "KENDİNDEN", F_BLACK, 96, DIM + (255,), 540, 520, 0.7 + 0.3 * e_back(pk), pk)
    text_c(c, "EMİN", F_BLACK, 210, CYAN + (255,), 540, 660, 0.5 + 0.5 * e_back(pe), pe, glow=(CYAN, 18))
    td, _ = wt("doğru", t0)
    pd = prog(t, td, 0.3)
    text_c(c, "DOĞRU", F_BLACK, 210, GREEN + (255,), 540, 1080, 0.5 + 0.5 * e_back(pd), pd, glow=(GREEN, 18))
    tg, _ = wt("gelmez", t0)
    pg = prog(t, tg - 0.05, 0.25)
    if pg > 0:
        sc = 2.4 - 1.4 * e_out(pg)
        neq, _ = text_sprite("≠", F_BLACK, 300, RED + (255,), glow=(RED, 24))
        place(c, neq, 540, 880, sc * (1 + 0.04 * math.sin(t * 6)), pg)
    # kapanış
    po = prog(t, 45.9, 0.4)
    if po > 0:
        cta = pill("Kaydet  •  Paylaş", F_BOLD, 46, TXT, (30, 34, 52, 240), 40, 22, outline=PANEL_LINE + (255,),
                   em="🔖")
        place(c, cta, 540, 1330 + (1 - e_out(po)) * 60, 1, po)


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6]


# ---------------------------------------------------------------- altyazı
def build_caption_groups():
    groups, cur = [], []
    for i, x in enumerate(WORDS):
        if cur and (x["seg"] != WORDS[cur[0]]["seg"] or len(cur) >= 3 or
                    sum(len(WORDS[j]["w"]) for j in cur) + len(x["w"]) > 17):
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
        nxt = WORDS[groups[gi + 1][0]]["s"] - 0.06 if gi + 1 < len(groups) else e + 0.4
        cut = min(b for b in S_BOUNDS if b > WORDS[g[-1]]["e"])  # sahne değişince altyazı da kesilsin
        out.append((s, min(nxt, e + 0.35, cut), g))
    return out


CAP_GROUPS = build_caption_groups()
CAP_HIDE = (WORDS[PROMPT_IDX[0]]["s"] - 0.1, WORDS[PROMPT_IDX[-1]]["e"] + 0.3)  # metin zaten ekranda
CAP_Y, CAP_SIZE = 1390, 86


def captions(c, t):
    if CAP_HIDE[0] <= t < CAP_HIDE[1]:
        return
    for s, e, g in CAP_GROUPS:
        if not (s <= t < e):
            continue
        f = font(F_BLACK, CAP_SIZE)
        words = [tr_upper(WORDS[i]["w"]) for i in g]
        sp = 24
        widths = [f.getlength(w) for w in words]
        lines, cur, cw = [], [], 0
        for k, wl in enumerate(widths):
            if cur and cw + sp + wl > 940:
                lines.append(cur)
                cur, cw = [], 0
            cw += (sp if cur else 0) + wl
            cur.append(k)
        lines.append(cur)
        pg = prog(t, s, 0.14)
        gs = 0.8 + 0.2 * e_back(pg)
        for li, ln in enumerate(lines):
            lw = sum(widths[k] for k in ln) + sp * (len(ln) - 1)
            x = 540 - lw / 2
            y = CAP_Y + (li - (len(lines) - 1) / 2) * 104
            for k in ln:
                i = g[k]
                ws, we = WORDS[i]["s"], WORDS[i]["e"]
                active = ws <= t < we + 0.04
                col = LIME if active else (255, 255, 255)
                im, pad = text_sprite(words[k], F_BLACK, CAP_SIZE, col + (255,), shadow=12)
                pop = 1 + 0.12 * (1 - e_out(prog(t, ws, 0.15))) if active else 1.0
                cx = x + widths[k] / 2
                place(c, im, 540 + (cx - 540) * gs, y, gs * pop, pg * (1 if t >= ws - 0.02 else 0.8))
                x += widths[k] + sp


# ---------------------------------------------------------------- kompozisyon
TRANS = {"glitch": [5.55, 39.4], "whip": [11.35], "zoom": [25.45], "flash": [31.0]}


def content_layer(i, t):
    c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    SCENES[i](c, t)
    return c


def transform(im, scale=1.0, dx=0.0, dy=0.0, rot=0.0):
    if abs(scale - 1) < 1e-4 and abs(dx) < 0.5 and abs(dy) < 0.5 and abs(rot) < 0.01:
        return im
    a = math.radians(rot)
    ca, sa = math.cos(a) / scale, math.sin(a) / scale
    cx, cy = W / 2, H / 2
    # çıktı (x,y) -> girdi
    mat = (ca, sa, cx - ca * (cx + dx) - sa * (cy + dy), -sa, ca, cy + sa * (cx + dx) - ca * (cy + dy))
    return im.transform((W, H), Image.AFFINE, mat, resample=Image.BILINEAR)


def motion_blur(im, dx, dy, n=4):
    if abs(dx) + abs(dy) < 2:
        return im
    acc = np.zeros((H, W, 4), np.float32)
    for k in range(n):
        f = (k / (n - 1) - 0.5)
        acc += np.asarray(transform(im, 1, dx * f, dy * f), np.float32)
    return Image.fromarray((acc / n).astype(np.uint8))


def zoom_blur(im, amt, n=4):
    if amt < 0.01:
        return im
    acc = np.zeros((H, W, 4), np.float32)
    for k in range(n):
        acc += np.asarray(transform(im, 1 + amt * k / (n - 1)), np.float32)
    return Image.fromarray((acc / n).astype(np.uint8))


SHAKES = None


def init_events():
    global SHAKES
    SHAKES = [(4.45, 14, 6), (31.0, 34, 4), (wt("gelmez", 39)[0] - 0.05 + 0.2, 26, 5), (5.55, 10, 8)]


def render_frame(fi):
    t = fi / FPS
    energy = float(ENERGY[min(fi, len(ENERGY) - 1)])
    frame = background(t, energy)
    # nokta ızgarası (yavaşça yukarı akar)
    off = int(t * 18) % 60
    frame.alpha_composite(DOTS.crop((0, off, W, off + H)))

    i = scene_index(t)
    push = 1 + 0.035 * prog(t, S_BOUNDS[i], S_BOUNDS[i + 1] - S_BOUNDS[i])  # her sahnede hafif yakınlaşma
    sx, sy = shake_xy(t, SHAKES)
    layer = None
    # geçişler
    b = S_BOUNDS[i]
    nb = S_BOUNDS[i + 1]
    if nb in TRANS["whip"] and nb - t < 0.2:
        p = e_in(prog(t, nb - 0.2, 0.2))
        layer = motion_blur(transform(content_layer(i, t), push, 0, -p * 900), 0, 160 * p)
    elif b in TRANS["whip"] and t - b < 0.25:
        p = e_out(prog(t, b, 0.25))
        layer = motion_blur(transform(content_layer(i, t), push, 0, (1 - p) * 900), 0, 160 * (1 - p))
    elif nb in TRANS["zoom"] and nb - t < 0.22:
        p = e_in(prog(t, nb - 0.22, 0.22))
        layer = set_alpha(zoom_blur(transform(content_layer(i, t), push * (1 + 0.6 * p)), 0.25 * p), 1 - p)
    elif b in TRANS["zoom"] and t - b < 0.3:
        p = e_out(prog(t, b, 0.3))
        layer = set_alpha(zoom_blur(transform(content_layer(i, t), 0.75 + 0.25 * p), 0.2 * (1 - p)), p)
    if layer is None:
        layer = transform(content_layer(i, t), push, sx, sy)
    frame.alpha_composite(layer)
    captions(frame, t)

    # ilerleme çubuğu
    d = ImageDraw.Draw(frame)
    d.rectangle((0, 0, int(W * t / DUR), 9), fill=LIME + (230,))

    arr = np.asarray(frame.convert("RGB"), np.float32)
    # glitch / renk kayması
    g = 0.0
    for tb in TRANS["glitch"]:
        g = max(g, 1 - abs(t - tb) / 0.22)
    g = max(g, 1 - abs(t - 4.4) / 0.15) * 1.0 if 4.25 < t < 4.55 else g
    if g > 0:
        rnd = random.Random(fi)
        sh = int(26 * g)
        arr[..., 0] = np.roll(arr[..., 0], sh, axis=1)
        arr[..., 2] = np.roll(arr[..., 2], -sh, axis=1)
        for _ in range(int(10 * g)):
            y0 = rnd.randint(0, H - 80)
            h = rnd.randint(8, 90)
            arr[y0:y0 + h] = np.roll(arr[y0:y0 + h], rnd.randint(-120, 120), axis=1)
    # flaşlar
    fl = 0.0
    flc = np.array([255, 255, 255], np.float32)
    if 31.0 <= t < 31.45:
        fl = 0.75 * (1 - (t - 31.0) / 0.45) ** 2
        flc = np.array(RED, np.float32)
    for tb in TRANS["glitch"]:
        if tb <= t < tb + 0.15:
            fl = max(fl, 0.5 * (1 - (t - tb) / 0.15))
    tg = wt("gelmez", 39)[0] + 0.15
    if tg <= t < tg + 0.2:
        fl = 0.45 * (1 - (t - tg) / 0.2)
        flc = np.array(RED, np.float32)
    if fl > 0:
        arr = arr * (1 - fl) + flc * fl
    # outro kararması
    if t > DUR - 0.35:
        arr *= clamp((DUR - t) / 0.35)
    arr = arr * VIGNETTE + GRAINS[0]
    return np.clip(arr, 0, 255).astype(np.uint8).tobytes()


def init_globals():
    global DOTS, VIGNETTE, GRAINS, AVATAR
    DOTS, VIGNETTE, GRAINS = make_static_layers()
    AVATAR = avatar()
    init_events()


ENERGY = None


def main():
    global ENERGY
    os.makedirs("out", exist_ok=True)
    mix_path, ENERGY = build_mix(AUDIO, DUR, FPS, WORDS, "out/mix.wav")
    init_globals()
    if "--preview" in sys.argv:
        for s in sys.argv[sys.argv.index("--preview") + 1:]:
            fi = int(float(s) * FPS)
            Image.frombytes("RGB", (W, H), render_frame(fi)).save(f"out/preview_{float(s):05.2f}.png")
            print("preview", s)
        return
    n = int(DUR * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", mix_path,
                           "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-maxrate", "12M", "-bufsize", "24M",
                           "-pix_fmt", "yuv420p", "-profile:v", "high",
                           "-ar", "48000",
                           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                           "-shortest", OUT], stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for k, buf in enumerate(pool.imap(render_frame, range(n), chunksize=6)):
            ff.stdin.write(buf)
            if k % 150 == 0:
                print(f"{k}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("bitti:", OUT)


if __name__ == "__main__":
    main()
