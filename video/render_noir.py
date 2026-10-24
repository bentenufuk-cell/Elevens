"""Kara film (noir) dedektif hikâyesi: "Sorgu Odası".

Yapay zekâ tanık, izleyici dedektif. Siyah-beyaz film dokusu, tek vurgu rengi kırmızı;
lamba ışığı ve panjur gölgeleri, daktilo belgeler, lastik damgalar, delil panosu, yalan makinesi şeridi.

Kullanım:  python3 render_noir.py                 -> out/elevens1_shorts_noir.mp4
           python3 render_noir.py --preview 4.5 20
"""
import math
import os
import random
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from render import (AUDIO, PROMPT_IDX, S_BOUNDS, WORDS, clamp, e_back, e_in, e_inout, e_out, paste, place, prog,
                    scene_index, set_alpha, tr_upper, wt)

W, H, FPS = 1080, 1920, 30
DUR = 47.2
OUT = "out/elevens1_shorts_noir.mp4"

# ---------------------------------------------------------------- palet
DESK = (24, 24, 27)
PAPER = (228, 222, 206)
INK = (30, 30, 33)
GRAY = (118, 116, 112)
CREAM = (236, 230, 214)
RED = (198, 32, 40)
RED_L = (228, 58, 58)
FOLDER = (168, 156, 132)

FDIR = "assets/fonts/"
FONTS = {"elite": FDIR + "SpecialElite-Regular.ttf", "bebas": FDIR + "BebasNeue-Regular.ttf",
         "anton": FDIR + "Anton-Regular.ttf", "hand": FDIR + "Kalam-Bold.ttf"}


@lru_cache(maxsize=None)
def font(key, size):
    return ImageFont.truetype(FONTS[key], size)


@lru_cache(maxsize=4000)
def txt(text, key, size, color):
    f = font(key, size)
    asc, desc = f.getmetrics()
    pad = max(4, size // 8)
    im = Image.new("RGBA", (int(math.ceil(f.getlength(text))) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), text, font=f, fill=color + (255,))
    return im


def tc(c, text, key, size, color, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    place(c, txt(text, key, size, color), cx, cy, scale, alpha, rot)


def typed(d, text, key, size, color, x, y, t, t0, dur):
    """Daktilo: harf harf belirir. Sol-orta hizalı. Yazılan karakter sayısını döndürür."""
    n = int(len(text) * clamp((t - t0) / dur)) if t >= t0 else 0
    if n:
        d.text((x, y), text[:n], font=font(key, size), fill=color + (255,), anchor="lm")
    return n


# ---------------------------------------------------------------- dokular
def _noise(h, w, seed, scale):
    rng = np.random.default_rng(seed)
    small = rng.normal(0, 1, (max(2, h // scale), max(2, w // scale))).astype(np.float32)
    return np.asarray(Image.fromarray(small, "F").resize((w, h), Image.BICUBIC))


@lru_cache(maxsize=32)
def paper(w, h, seed=0, tone=PAPER, edge=0.18):
    rng = np.random.default_rng(seed)
    base = np.ones((h, w, 3), np.float32) * np.array(tone, np.float32)
    blot = _noise(h, w, seed + 1, 60)[..., None] * 7
    fine = rng.normal(0, 5, (h, w, 1)).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy))
    ed = 1 - edge * np.exp(-d / 22)[..., None]
    arr = np.clip((base + blot + fine) * ed, 0, 255).astype(np.uint8)
    im = Image.fromarray(arr).convert("RGBA")
    # gölgeli kenar
    pad = 24
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((pad + 8, pad + 14, pad + w + 8, pad + h + 14), fill=(0, 0, 0, 170))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    out.alpha_composite(im, (pad, pad))
    return out


PAPER_PAD = 24


@lru_cache(maxsize=32)
def stamp(text, color, size, lines=1, seed=0):
    """Mürekkebi eksik basılmış lastik damga."""
    f = font("anton", size)
    parts = text.split("\n")
    tw = int(max(f.getlength(p) for p in parts))
    asc, desc = f.getmetrics()
    lh = int(size * 1.08)
    w, h = tw + 80, lh * len(parts) + 50
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    d.rectangle((6, 6, w - 7, h - 7), outline=255, width=9)
    d.rectangle((20, 20, w - 21, h - 21), outline=255, width=3)
    for k, p in enumerate(parts):
        d.text((w / 2, 25 + lh * k + lh / 2), p, font=f, fill=255, anchor="mm")
    n = _noise(h, w, seed + 5, 4) + 0.6 * _noise(h, w, seed + 6, 18)
    mask = (n > -0.9).astype(np.float32) * 0.92
    a = (np.asarray(im, np.float32) * mask).astype(np.uint8)
    out = Image.new("RGBA", (w, h), color + (0,))
    out.putalpha(Image.fromarray(a))
    return out


@lru_cache(maxsize=4)
def stamp_neq(color, size, seed=0):
    """Elle basılmış "≠" (fontlardaki işaret yeterince belirgin değil)."""
    w, h = int(size * 1.2), size
    im = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(im)
    bar = size * 0.16
    for y in (h * 0.30, h * 0.62):
        d.rectangle((w * 0.08, y, w * 0.92, y + bar), fill=255)
    d.line((w * 0.68, h * 0.04, w * 0.32, h * 0.96), fill=255, width=int(size * 0.14))
    n = _noise(h, w, seed + 5, 4) + 0.6 * _noise(h, w, seed + 6, 18)
    a = (np.asarray(im, np.float32) * (n > -0.9) * 0.95).astype(np.uint8)
    out = Image.new("RGBA", (w, h), color + (0,))
    out.putalpha(Image.fromarray(a))
    return out


@lru_cache(maxsize=4)
def desk_tex(seed=0, cork=False):
    if cork:
        rng = np.random.default_rng(seed)
        base = np.ones((H, W, 3), np.float32) * np.array((62, 58, 54), np.float32)
        arr = base + _noise(H, W, seed, 30)[..., None] * 6 + rng.normal(0, 12, (H, W, 1))
        speck = rng.random((H, W, 1)) > 0.996
        arr = np.where(speck, arr * 0.5, arr)
    else:
        arr = np.ones((H, W, 3), np.float32) * np.array(DESK, np.float32)
        arr += _noise(H, W, seed, 40)[..., None] * 4
        # yatay ahşap damarı
        yy = np.arange(H, dtype=np.float32)[:, None, None]
        arr += 3 * np.sin(yy / 9 + _noise(H, W, seed + 2, 80)[..., None] * 3)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


# ---------------------------------------------------------------- yalan makinesi şeridi
def polygraph(d, x0, y0, x1, y1, t, calm=1.0, scroll=160):
    for gx in range(int(x0), int(x1), 30):
        d.line((gx, y0, gx, y1), fill=(200, 170, 165, 255), width=1)
    for gy in range(int(y0), int(y1), 30):
        d.line((x0, gy, x1, gy), fill=(200, 170, 165, 255), width=1)
    mid = (y0 + y1) / 2
    amp = (y1 - y0) * 0.12 * calm
    nx = x1 - 60
    pts = []
    for x in range(int(x0), int(nx), 4):
        u = (x - nx) + t * scroll
        y = mid + amp * (math.sin(u / 23) + 0.45 * math.sin(u / 7.3) + 0.25 * math.sin(u / 3.1))
        pts.append((x, y))
    d.line(pts, fill=INK + (255,), width=4, joint="curve")
    d.line((nx, y0 - 10, pts[-1][0], pts[-1][1]), fill=(60, 60, 64, 255), width=3)
    d.ellipse((pts[-1][0] - 6, pts[-1][1] - 6, pts[-1][0] + 6, pts[-1][1] + 6), fill=RED + (255,))


def check(d, x, y, s, p, color=RED, w=10):
    pts = [(x - 26 * s, y), (x - 6 * s, y + 24 * s), (x + 34 * s, y - 34 * s)]
    q = e_out(clamp(p))
    seg = [pts[0], (pts[0][0] + (pts[1][0] - pts[0][0]) * min(1, q * 2), pts[0][1] + (pts[1][1] - pts[0][1]) * min(1, q * 2))]
    if q > 0.5:
        seg.append((pts[1][0] + (pts[2][0] - pts[1][0]) * (q - 0.5) * 2, pts[1][1] + (pts[2][1] - pts[1][1]) * (q - 0.5) * 2))
    d.line(seg, fill=color + (255,), width=w, joint="curve")


def sheet_place(c, sheet, cx, cy, rot=0.0, scale=1.0, alpha=1.0):
    place(c, sheet, cx, cy, scale, alpha, rot)


# ---------------------------------------------------------------- sahne 1: ifade tutanağı
Q_LINES = ["Beynimizin sadece %10'unu mu", "kullanırız?"]
A_LINES = ["Evet, kesinlikle. Beynimizin", "yalnızca %10'u çalışır."]


def scene1(c, t):
    c.alpha_composite(desk_tex(1))
    sh = paper(880, 1080, 3).copy()
    d = ImageDraw.Draw(sh)
    o = PAPER_PAD
    d.text((o + 60, o + 80), "İFADE TUTANAĞI", font=font("bebas", 96), fill=INK, anchor="lm")
    d.text((o + 820, o + 80), "No. 0147", font=font("elite", 34), fill=GRAY, anchor="rm")
    d.line((o + 60, o + 140, o + 820, o + 140), fill=INK, width=3)
    typed(d, "Tanık : Yapay Zekâ", "elite", 42, INK, o + 60, o + 195, t, 0.15, 0.5)
    typed(d, "Durum : Kendinden emin", "elite", 42, INK, o + 60, o + 250, t, 0.5, 0.55)
    if t > 0.9:
        d.text((o + 60, o + 335), "SORU", font=font("bebas", 54), fill=GRAY, anchor="lm")
    typed(d, Q_LINES[0], "elite", 46, INK, o + 60, o + 395, t, 0.95, 0.75)
    typed(d, Q_LINES[1], "elite", 46, INK, o + 60, o + 450, t, 1.7, 0.3)
    if t > 1.95:
        d.text((o + 60, o + 535), "CEVAP", font=font("bebas", 54), fill=GRAY, anchor="lm")
    typed(d, A_LINES[0], "elite", 50, INK, o + 60, o + 598, t, 2.0, 0.8)
    typed(d, A_LINES[1], "elite", 50, INK, o + 60, o + 656, t, 2.8, 0.6)
    # yalan makinesi: sakin
    if t > 0.6:
        d.text((o + 60, o + 860), "NABIZ / SES TONU", font=font("elite", 30), fill=GRAY, anchor="lm")
        d.text((o + 820, o + 860), "SAKİN", font=font("bebas", 44), fill=INK, anchor="rm")
        polygraph(d, o + 60, o + 890, o + 820, o + 1040, t, 0.8)
    if t > 4.85:  # kırmızı kalem notu
        pp = clamp((t - 4.85) / 0.7)
        im = txt("Gerçek: beynin neredeyse tamamı çalışır.", "hand", 40, RED)
        im = im.crop((0, 0, max(1, int(im.width * pp)), im.height))
        sh.alpha_composite(im, (o + 54, o + 735))
        d.line((o + 60, o + 790, o + 60 + 700 * e_out(pp), o + 786), fill=RED + (255,), width=4)
    ps = prog(t, 4.45, 0.18)
    if ps > 0:
        st = stamp("ASILSIZ", RED, 160, seed=1)
        place(sh, st, o + 470, o + 600, 1.6 - 0.6 * e_out(ps), min(1, ps * 1.5), 14)
    sheet_place(c, sh, 540, 790, -1.5)


# ---------------------------------------------------------------- sahne 2: ne yapmalı -> dosya
def scene2(c, t):
    c.alpha_composite(desk_tex(2))
    s_f, _ = wt("sana")
    pout = prog(t, s_f - 0.35, 0.35)
    if pout < 1:
        tp, _ = wt("peki")
        tn, _ = wt("ne", 6.5)
        for word, size, y, t0 in (("PEKİ", 280, 560, tp), ("NE YAPMALI?", 200, 800, tn)):
            p = prog(t, t0, 0.2)
            tc(c, word, "bebas", size, CREAM, 540, y - e_in(pout) * 300, 1.25 - 0.25 * e_out(p), p * (1 - pout))
    if t < s_f - 0.2:
        return
    pf = prog(t, s_f - 0.15, 0.45)
    fo = paper(860, 700, 7, FOLDER, 0.25).copy()
    d = ImageDraw.Draw(fo)
    o = PAPER_PAD
    d.text((o + 50, o + 70), "DOSYA No. 1", font=font("elite", 40), fill=INK, anchor="lm")
    d.line((o + 50, o + 110, o + 810, o + 110), fill=(90, 84, 70), width=2)
    d.text((o + 50, o + 170), "KONU: YANLIŞ CEVAPLAR", font=font("elite", 40), fill=INK, anchor="lm")
    d.text((o + 50, o + 260), "YÖNTEM", font=font("bebas", 96), fill=INK, anchor="lm")
    tb, _ = wt("basit", s_f)
    te, _ = wt("etkili", s_f)
    for word, col, x, y, rot, t0, sd in (("BASİT", INK, 270, 450, 8, tb, 3), ("ETKİLİ", RED, 590, 470, -6, te, 4)):
        p = prog(t, t0, 0.16)
        if p > 0:
            place(fo, stamp(word, col, 96, seed=sd), o + x, o + y, 1.5 - 0.5 * e_out(p), min(1, p * 1.5), rot)
    place(c, fo, 540, 860 + (1 - e_out(pf)) * 1200, 1, 1, -2 + (1 - e_out(pf)) * 6)
    ty, _ = wt("yöntem", s_f)
    pt = prog(t, ty - 0.05, 0.3)
    if pt > 0:
        slip = paper(560, 150, 9, (240, 236, 224), 0.1).copy()
        ImageDraw.Draw(slip).text((PAPER_PAD + 280, PAPER_PAD + 75), "TEK CÜMLE", font=font("bebas", 120), fill=RED,
                                  anchor="mm")
        place(c, slip, 600 + (1 - e_out(pt)) * 700, 1230, 1, 1, -3)
        # ataç
        d2 = ImageDraw.Draw(c)
        x = 380 + (1 - e_out(pt)) * 700
        d2.rounded_rectangle((x, 1140, x + 46, 1260), 22, outline=(150, 150, 156, 255), width=6)
        d2.rounded_rectangle((x + 10, 1160, x + 36, 1240), 13, outline=(150, 150, 156, 255), width=5)


# ---------------------------------------------------------------- sahne 3: sorgu talimatı (prompt)
P_SIZE, P_LH, P_X0, P_Y0, P_MAXW = 50, 74, 70, 400, 820
GROUPS = {1: (0, 1, 2), 2: (3,), 3: (5, 6, 7)}  # 1: kesin, 2: tahmin, 3: doğrulanmalı


def p_layout():
    f = font("elite", P_SIZE)
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


P_LAYOUT = p_layout()


def scene3(c, t):
    c.alpha_composite(desk_tex(3))
    t0 = 11.35
    pin = prog(t, t0, 0.45)
    sh = paper(960, 1260, 11).copy()
    d = ImageDraw.Draw(sh)
    o = PAPER_PAD
    d.text((o + 60, o + 80), "SORGU TALİMATI", font=font("bebas", 96), fill=INK, anchor="lm")
    d.text((o + 900, o + 80), "No. 0148", font=font("elite", 34), fill=GRAY, anchor="rm")
    d.line((o + 60, o + 140, o + 900, o + 140), fill=INK, width=3)
    ts, _ = wt("sorduktan", t0)
    tsu, _ = wt("şu", t0)
    typed(d, "1) Önce önemli sorunu sor.", "elite", 44, GRAY, o + 60, o + 205, t, 11.7, 1.3)
    typed(d, "2) Ardından şunu ekle:", "elite", 44, INK, o + 60, o + 275, t, tsu - 0.4, 0.9)
    s_type = WORDS[PROMPT_IDX[0]]["s"]
    f = font("elite", P_SIZE)
    for k, i, w, x, y, wl in P_LAYOUT:
        ws, we = WORDS[i]["s"], WORDS[i]["e"]
        if t < ws:
            break
        n = max(1, int(round(len(w) * clamp((t - ws) / max(0.08, (we - ws) * 0.85)))))
        d.text((o + x, o + y), w[:n], font=f, fill=INK, anchor="lm")
    # kırmızı kalem: grupların altını çiz + numara
    for num, ks in GROUPS.items():
        last = WORDS[P_LAYOUT[ks[-1]][1]]["e"]
        first = WORDS[P_LAYOUT[ks[0]][1]]["s"]
        if t < first:
            continue
        for k in ks:
            _, i, w, x, y, wl = P_LAYOUT[k]
            ws, we = WORDS[i]["s"], WORDS[i]["e"]
            hp = e_out(clamp((t - ws) / max(0.12, we - ws)))
            if hp > 0:
                ext = 14 if k != ks[-1] else 0
                d.line((o + x - 2, o + y + 32, o + x + (wl + ext) * hp, o + y + 30 + 2 * math.sin(k)),
                       fill=RED + (255,), width=5)
        pn = prog(t, last, 0.25)
        if pn > 0:
            _, i, w, x, y, wl = P_LAYOUT[ks[0]]
            cx, cy = o + x - 6, o + y - 40
            d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=RED + (int(255 * pn),), width=4)
            d.text((cx, cy + 1), str(num), font=font("hand", 32), fill=RED + (int(255 * pn),), anchor="mm")
    k14 = P_LAYOUT[14]
    ws = WORDS[k14[1]]["s"]
    if t >= ws:
        _, i, w, x, y, wl = k14
        p = e_out(clamp((t - ws) / 0.4))
        bb = (o + x - 18, o + y - 34, o + x + wl + 18, o + y + 36)
        d.arc(bb, -200, -200 + 380 * p, fill=RED + (255,), width=5)
    te, _ = wt("emin", s_type)
    pn = prog(t, te, 0.6)
    if pn > 0:
        im = txt("Bunu bir yere kaydet!", "hand", 44, RED)
        im = im.crop((0, 0, max(1, int(im.width * pn)), im.height))
        sh.alpha_composite(im, (o + 60, o + 1110))
    place(c, sh, 540, 900 + (1 - e_out(pin)) * 1300, 1, 1, 1.0 - (1 - e_out(pin)) * 5)


# ---------------------------------------------------------------- sahne 4: delil panosu
CARDS = [("KANIT", "kesin bilgiler", INK, 300, 640, -4),
         ("TAHMİN", "olasılıklar", INK, 790, 720, 5),
         ("ŞÜPHELİ", "doğrulanmalı", RED, 540, 1090, -2)]


def card_pins():
    return [(x, y - 125) for _, _, _, x, y, _ in CARDS]


def scene4(c, t):
    c.alpha_composite(desk_tex(4, True))
    t0 = 25.45
    lab = paper(560, 150, 13, (232, 226, 210), 0.12).copy()
    ImageDraw.Draw(lab).text((PAPER_PAD + 280, PAPER_PAD + 75), "DELİL PANOSU", font=font("bebas", 104), fill=INK,
                             anchor="mm")
    pl = prog(t, t0 + 0.05, 0.3)
    place(c, lab, 540, 330, 1.1 - 0.1 * e_out(pl), pl, 1.5)
    d = ImageDraw.Draw(c)
    pins = card_pins()
    for k, (title, sub, col, x, y, rot) in enumerate(CARDS):
        tp = t0 + 0.35 + k * 0.6
        p = prog(t, tp, 0.22)
        if p <= 0:
            continue
        cd = paper(420, 300, 20 + k, (236, 232, 220), 0.12).copy()
        dd = ImageDraw.Draw(cd)
        o = PAPER_PAD
        dd.text((o + 210, o + 120), title, font=font("bebas", 110), fill=col, anchor="mm")
        dd.text((o + 210, o + 220), sub, font=font("elite", 38), fill=GRAY, anchor="mm")
        place(c, cd, x, y, 1.15 - 0.15 * e_out(p), min(1, p * 2), rot)
    # kırmızı ip
    ts = t0 + 2.0
    order = [(0, 1), (1, 2), (2, 0)]
    for j, (a, b) in enumerate(order):
        p = clamp((t - ts - j * 0.25) / 0.3)
        if p <= 0:
            continue
        (x0, y0), (x1, y1) = pins[a], pins[b]
        pts = []
        for q in range(25):
            u = q / 24 * p
            pts.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u + 50 * math.sin(math.pi * u / max(p, 1e-3)) * p))
        d.line(pts, fill=RED + (255,), width=5, joint="curve")
    for k, (x, y) in enumerate(pins):
        if t >= t0 + 0.35 + k * 0.6 + 0.12:
            d.ellipse((x - 17, y - 17, x + 17, y + 17), fill=RED + (255,))
            d.ellipse((x - 7, y - 10, x + 1, y - 2), fill=(255, 150, 150, 255))
    # kırmızı kalem işaretleri
    te, _ = wt("emin", t0)
    for k, mark, dt in ((1, "?", 0.35), (2, "!", 1.15)):
        p = prog(t, te + dt, 0.3)
        if p > 0:
            _, _, _, x, y, _ = CARDS[k]
            tc(c, mark, "hand", 150, RED, x + 160, y - 60, 1.3 - 0.3 * e_out(p), p, 10)


# ---------------------------------------------------------------- sahne 5: dikkat / dava kapanmadı / kaynaklar
CHECK_ITEMS = [("Resmî kayıtlar", "güvenilir"), ("Bilimsel çalışmalar", "kaynaklardan"), ("Uzman tanıklığı", "kontrol")]


def lamp(c, t, ang):
    d = ImageDraw.Draw(c)
    L = 300
    x1, y1 = 540 + L * math.sin(ang), L * math.cos(ang)
    d.line((540, -10, x1, y1), fill=(70, 70, 74, 255), width=6)
    # abajur
    ca, sa = math.cos(ang), math.sin(ang)

    def rot(px, py):
        return x1 + px * ca + py * sa, y1 - px * sa + py * ca

    d.polygon([rot(-40, 0), rot(40, 0), rot(120, 110), rot(-120, 110)], fill=(48, 48, 52, 255))
    d.ellipse([*rot(-30, 95), *rot(30, 125)], fill=(255, 245, 210, 255))


def lamp_angle(t):
    return 0.22 * math.sin((t - 31.0) * 2.6) * math.exp(-max(0, t - 31.0) * 0.12)


def scene5(c, t):
    c.alpha_composite(desk_tex(5))
    t0 = 31.0
    tb, _ = wt("bu", t0 + 0.5)
    to, _ = wt("özellikle", t0)
    lamp(c, t, lamp_angle(t))
    # A: AMA DİKKAT
    pa_out = prog(t, tb - 0.25, 0.3)
    if pa_out < 1:
        ta, _ = wt("ama", t0)
        tdk, _ = wt("dikkat", t0)
        p1 = prog(t, ta, 0.15)
        p2 = prog(t, tdk, 0.15)
        tc(c, "AMA", "bebas", 200, CREAM, 540, 800 - e_in(pa_out) * 400, 1.3 - 0.3 * e_out(p1), p1 * (1 - pa_out))
        tc(c, "DİKKAT.", "bebas", 300, RED, 540, 1020 - e_in(pa_out) * 400, 1.4 - 0.4 * e_out(p2), p2 * (1 - pa_out))
    # B: dava kapanmadı
    pb = prog(t, tb - 0.1, 0.4)
    pb_out = prog(t, to - 0.3, 0.35)
    if pb > 0 and pb_out < 1:
        fo = paper(860, 760, 31, FOLDER, 0.25).copy()
        d = ImageDraw.Draw(fo)
        o = PAPER_PAD
        d.text((o + 50, o + 70), "DOSYA: YANLIŞ BİLGİLER", font=font("elite", 42), fill=INK, anchor="lm")
        d.line((o + 50, o + 110, o + 810, o + 110), fill=(90, 84, 70), width=2)
        ty, _ = wt("yanlışları", t0)
        tk, _ = wt("kaldırmaz", t0)
        p1 = prog(t, ty, 0.16)
        if p1 > 0:
            place(fo, stamp("ÇÖZÜLDÜ?", (52, 52, 56), 110, seed=8), o + 430, o + 330, 1.5 - 0.5 * e_out(p1),
                  min(1, p1 * 1.5), -8)
        p2 = prog(t, tk, 0.4)
        if p2 > 0:
            q = e_out(p2)
            d.line((o + 170, o + 250, o + 170 + 520 * q, o + 250 + 170 * q), fill=RED + (255,), width=12)
            d.line((o + 690, o + 250, o + 690 - 520 * q, o + 250 + 170 * q), fill=RED + (255,), width=12)
        p3 = prog(t, tk + 0.25, 0.16)
        if p3 > 0:
            place(fo, stamp("DAVA\nKAPANMADI", RED, 104, seed=9), o + 440, o + 560, 1.5 - 0.5 * e_out(p3),
                  min(1, p3 * 1.5), 6)
        place(c, fo, 540 + (1 - e_out(pb)) * 1100 - e_in(pb_out) * 1100, 900, 1, 1, 2)
    # C: kaynak kontrolü
    pc = prog(t, to - 0.15, 0.4)
    if pc > 0:
        sh = paper(900, 860, 33).copy()
        d = ImageDraw.Draw(sh)
        o = PAPER_PAD
        d.text((o + 60, o + 80), "KAYNAK KONTROLÜ", font=font("bebas", 96), fill=INK, anchor="lm")
        d.line((o + 60, o + 140, o + 840, o + 140), fill=INK, width=3)
        typed(d, "Önemli bilgiyi doğrula:", "elite", 42, GRAY, o + 60, o + 200, t, to + 0.2, 0.8)
        for k, (lab, cue) in enumerate(CHECK_ITEMS):
            y = o + 320 + k * 150
            ti = to + 0.6 + k * 0.3
            if t >= ti:
                d.rectangle((o + 60, y - 30, o + 120, y + 30), outline=INK, width=5)
            typed(d, lab, "elite", 54, INK, o + 150, y, t, ti, 0.45)
            tcue, _ = wt(cue, to)
            if t >= tcue:
                check(d, o + 92, y - 4, 1.3, (t - tcue) / 0.25)
        place(c, sh, 540, 900 + (1 - e_out(pc)) * 1300, 1, 1, -1)


def magnifier_pos(t):
    """Kaynak listesinde büyüteç: o an işaretlenen satırın üstünde."""
    to, _ = wt("özellikle", 31)
    if t < to + 1.2:
        return None
    cues = [wt(c, to)[0] for _, c in CHECK_ITEMS]
    ys = [900 - 430 + 24 + 320 + k * 150 for k in range(3)]  # sayfa üstü + satır
    k = 0
    for j, tc_ in enumerate(cues):
        if t >= tc_ - 0.3:
            k = j
    prev = ys[max(0, k - 1)]
    p = e_inout(clamp((t - (cues[k] - 0.3)) / 0.3)) if k else 1
    y = prev + (ys[k] - prev) * p
    a = prog(t, to + 1.2, 0.3)
    return 520 + 30 * math.sin(t * 1.3), y, a


# ---------------------------------------------------------------- sahne 6: final
def scene6(c, t):
    c.alpha_composite(desk_tex(6))
    t0 = 39.4
    tu, _ = wt("unutma")
    pu = prog(t, tu, 0.15)
    if pu > 0:
        place(c, stamp("UNUTMA", RED, 90, seed=12), 540, 380, 1.4 - 0.4 * e_out(pu), min(1, pu * 1.5), -3)
    tk, _ = wt("kendinden", t0)
    d = ImageDraw.Draw(c)
    n = int(len("KENDİNDEN EMİN") * clamp((t - tk) / 0.8)) if t >= tk else 0
    if n:
        d.text((540 - font("bebas", 170).getlength("KENDİNDEN EMİN") / 2, 580), "KENDİNDEN EMİN"[:n],
               font=font("bebas", 170), fill=CREAM + (255,), anchor="lm")
    pp = prog(t, tk - 0.3, 0.4)
    if pp > 0:
        strip = paper(900, 190, 41, (236, 232, 220), 0.1).copy()
        ds = ImageDraw.Draw(strip)
        polygraph(ds, PAPER_PAD + 20, PAPER_PAD + 30, PAPER_PAD + 880, PAPER_PAD + 175, t, 0.7)
        ds.text((PAPER_PAD + 24, PAPER_PAD + 16), "SAKİN • İSTİKRARLI • EMİN", font=font("elite", 26), fill=GRAY,
                anchor="lm")
        place(c, strip, 540, 770, 1, pp, 0)
    td, _ = wt("doğru", t0)
    n2 = int(len("DOĞRU") * clamp((t - td) / 0.35)) if t >= td else 0
    if n2:
        d.text((540 - font("bebas", 220).getlength("DOĞRU") / 2, 1215), "DOĞRU"[:n2], font=font("bebas", 220),
               fill=CREAM + (255,), anchor="lm")
    tg, _ = wt("gelmez", t0)
    pg = prog(t, tg - 0.05, 0.16)
    if pg > 0:
        place(c, stamp_neq(RED, 220, 13), 540, 995, 1.6 - 0.6 * e_out(pg), min(1, pg * 1.5), -4)
    po = prog(t, 45.9, 0.4)
    if po > 0:
        tc(c, "Kaydet • Paylaş", "elite", 46, CREAM, 540, 1375, 1, po)


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6]


# ---------------------------------------------------------------- ışık
LW, LH = 135, 240
_yy, _xx = np.mgrid[0:LH, 0:LW].astype(np.float32)
_xx = (_xx + 0.5) * (W / LW)
_yy = (_yy + 0.5) * (H / LH)


def spot(cx, cy, r, k=1.0):
    return k * np.exp(-(((_xx - cx) ** 2 + (_yy - cy) ** 2) / (r * r)))


def blinds(t, strength=0.25, ang=0.5, period=230.0, speed=8.0):
    u = (_xx * math.cos(ang) + _yy * math.sin(ang)) / period + t * speed / period
    s = 0.5 + 0.5 * np.sin(u * 2 * math.pi)
    s = np.clip((s - 0.3) * 1.8, 0, 1)
    return 1 - strength * s


def light_map(t):
    i = scene_index(t)
    if i == 0:
        L = 0.42 + spot(540, 760, 700, 0.8)
        L *= blinds(t, 0.13)
        if t < 0.5:  # lamba yanıyor (titreyerek)
            L *= (0.05 if t < 0.12 else 0.6 if t < 0.2 else 0.25 if t < 0.27 else 1.0)
    elif i == 1:
        L = 0.38 + spot(540, 820, 650, 0.85)
        L *= blinds(t, 0.2, 0.45)
    elif i == 2:
        L = 0.62 + spot(540, 900, 800, 0.5)
        L *= blinds(t, 0.06, 0.55)
    elif i == 3:
        L = 0.5 + spot(540, 760, 700, 0.5)
        te, _ = wt("emin", 25.45)
        tf, _ = wt("fark", 25.45)
        dark = prog(t, te - 0.2, 0.3) * (1 - prog(t, 30.35, 0.4))
        if dark > 0:
            k = clamp((t - te) / max(0.5, tf - te))
            x = 790 + (540 - 790) * e_inout(clamp(k * 1.6 - 0.3))
            y = 720 + (1090 - 720) * e_inout(clamp(k * 1.6 - 0.3))
            beam = 0.3 + spot(x, y, 300, 1.1)
            L = L * (1 - dark) + beam * dark
        if t < 25.62:  # titreyen kesme
            L *= [0.15, 0.9, 0.3, 1.0, 0.6][int((t - 25.45) * 30) % 5]
    elif i == 4:
        ang = lamp_angle(t)
        ax, ay = 540 + 300 * math.sin(ang) + 120 * math.sin(ang), 300 * math.cos(ang) + 110
        dx, dy = math.sin(ang), math.cos(ang)
        vx, vy = _xx - ax, _yy - ay
        along = vx * dx + vy * dy
        across = np.abs(vx * dy - vy * dx)
        cone = np.clip(1 - across / (0.55 * np.maximum(along, 1) + 60), 0, 1) ** 1.5 * (along > 0)
        L = 0.42 + 0.85 * cone
        to, _ = wt("özellikle", 31)
        L = np.maximum(L, 0.7 * prog(t, to - 0.2, 0.5) + 0.0)  # belge okunaklı kalsın
    else:
        L = 0.4 + spot(540, 800, 700, 0.85)
        L *= blinds(t, 0.15, 0.5)
        if t > DUR - 0.9:  # lamba söner
            L *= clamp((DUR - 0.2 - t) / 0.7)
    return np.asarray(Image.fromarray(L.astype(np.float32), "F").resize((W, H), Image.BILINEAR))[..., None]


# ---------------------------------------------------------------- altyazı (sansür şeridi)
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
        nxt = WORDS[groups[gi + 1][0]]["s"] - 0.06 if gi + 1 < len(groups) else e + 0.4
        cut = min(b for b in S_BOUNDS if b > e)
        out.append((s, min(nxt, e + 0.35, cut), g))
    return out


CAPS = caption_groups()
CAP_HIDE = (WORDS[PROMPT_IDX[0]]["s"] - 0.1, WORDS[PROMPT_IDX[-1]]["e"] + 0.3)
CAP_Y, CAP_SIZE = 1480, 96


def captions(c, t):
    if CAP_HIDE[0] <= t < CAP_HIDE[1]:
        return
    for s, e, g in CAPS:
        if not (s <= t < e):
            continue
        f = font("bebas", CAP_SIZE)
        words = [tr_upper(WORDS[i]["w"]) for i in g]
        sp = f.getlength(" ") * 1.2
        widths = [f.getlength(w) for w in words]
        tw = sum(widths) + sp * (len(words) - 1)
        lw, lh = int(tw + 70), 130
        layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rectangle((0, 8, lw, lh - 8), fill=(8, 8, 10, 215))
        x = 35
        for k, w in enumerate(words):
            ws, we = WORDS[g[k]]["s"], WORDS[g[k]]["e"]
            col = RED_L if ws <= t < we + 0.05 else (CREAM if t >= ws - 0.02 else (120, 116, 108))
            d.text((x, lh / 2 + 4), w, font=f, fill=col + (255,), anchor="lm")
            x += widths[k] + sp
        pg = prog(t, s, 0.12)
        # şerit soldan sağa açılır
        reveal = layer.crop((0, 0, max(1, int(lw * e_out(pg))), lh))
        paste(c, set_alpha(reveal, 1 - prog(t, e - 0.08, 0.08)), 540 - lw / 2, CAP_Y - lh / 2)


# ---------------------------------------------------------------- kompozisyon + film dokusu
SHAKES = [(4.45, 12, 7), (31.0, 26, 4), (31.5, 12, 6), (34.75, 10, 7), (45.2, 18, 5)]


def shake_xy(t):
    dx = dy = 0.0
    for t0, amp, k in SHAKES:
        if t >= t0:
            a = amp * math.exp(-(t - t0) * k)
            if a > 0.3:
                dx += a * math.sin(t * 83 + t0)
                dy += a * math.cos(t * 71 + t0 * 2)
    return dx, dy


def compose(t):
    i = scene_index(t)
    c = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    SCENES[i](c, t)
    return c, i


def lit(c, t, fi):
    arr = np.asarray(c.convert("RGB"), np.float32) * light_map(t)
    # büyüteç (kaynak kontrolü)
    mp = magnifier_pos(t) if scene_index(t) == 4 else None
    if mp:
        mx, my, a = mp
        r = 120
        x0, y0 = int(mx - r / 1.35), int(my - r / 1.35)
        src = Image.fromarray(np.clip(arr[y0:y0 + int(2 * r / 1.35), x0:x0 + int(2 * r / 1.35)], 0, 255).astype(np.uint8))
        mag = np.asarray(src.resize((2 * r, 2 * r), Image.BICUBIC), np.float32)
        yy, xx = np.mgrid[0:2 * r, 0:2 * r]
        inside = (((xx - r) ** 2 + (yy - r) ** 2) <= (r - 6) ** 2)[..., None] * a
        reg = arr[int(my - r):int(my + r), int(mx - r):int(mx + r)]
        arr[int(my - r):int(my + r), int(mx - r):int(mx + r)] = reg * (1 - inside) + mag * 1.08 * inside
        im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(im)
        d.ellipse((mx - r, my - r, mx + r, my + r), outline=(40, 40, 44), width=int(12 * a) or 1)
        hx, hy = mx + r * 0.7, my + r * 0.7
        d.line((hx, hy, hx + 150, hy + 150), fill=(36, 36, 40), width=int(26 * a) or 1)
        arr = np.asarray(im, np.float32)
    return arr


def render_frame(fi):
    t = fi / FPS
    c, i = compose(t)
    b = S_BOUNDS[i]
    # sahne 3'e geçiş: yeni sayfa eskisinin üstüne kayar (sahne fonksiyonu kendi kaydırmasını yapar)
    sx, sy = shake_xy(t)
    if abs(sx) > 0.5 or abs(sy) > 0.5:
        c = c.transform((W, H), Image.AFFINE, (1, 0, -sx, 0, 1, -sy), resample=Image.BILINEAR)
    # yavaş kamera itişi
    i0, i1 = S_BOUNDS[i], S_BOUNDS[i + 1]
    z = 1 + 0.04 * prog(t, i0, i1 - i0)
    c = c.transform((W, H), Image.AFFINE, (1 / z, 0, W / 2 * (1 - 1 / z), 0, 1 / z, H / 2 * (1 - 1 / z)),
                    resample=Image.BILINEAR)
    arr = lit(c, t, fi)
    # panjur geçişi (siyah şeritler kapanıp açılır)
    for tb in (5.55, 39.4):
        if abs(t - tb) < 0.2:
            cover = 1 - abs(t - tb) / 0.2
            n = 10
            bh = H / n
            for k in range(n):
                y0 = int(k * bh)
                arr[y0:int(y0 + bh * cover)] *= 0.04
    # kırmızı flaş
    if 31.0 <= t < 31.35:
        f = 0.55 * (1 - (t - 31.0) / 0.35) ** 2
        arr = arr * (1 - f) + np.array(RED, np.float32) * f
    # altyazı ışıktan etkilenmesin
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
    captions(im, t)
    arr = np.asarray(im.convert("RGB"), np.float32)
    # film: titreme, gren, çizik/toz, vinyet, kare kayması
    rnd = random.Random(fi)
    arr *= 1 + rnd.uniform(-0.025, 0.025)
    arr = arr * VIGNETTE + GRAINS[(fi // 2) % len(GRAINS)]
    if rnd.random() < 0.12:
        x = rnd.randint(40, W - 40)
        arr[:, x:x + 2] = arr[:, x:x + 2] * 0.6 + 180 * 0.4
    for _ in range(rnd.randint(0, 3)):
        x, y, r = rnd.randint(0, W - 8), rnd.randint(0, H - 8), rnd.randint(1, 3)
        arr[y:y + r, x:x + r] = 15 if rnd.random() < 0.6 else 210
    if rnd.random() < 0.3:
        arr = np.roll(arr, rnd.choice((-1, 1)), axis=0)
    # ilerleme: ince kırmızı çizgi
    arr[0:6, :int(W * t / DUR)] = np.array(RED, np.float32)
    return np.clip(arr, 0, 255).astype(np.uint8).tobytes()


VIGNETTE, GRAINS = None, None


def init_film():
    global VIGNETTE, GRAINS
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    v = 1 - 0.7 * np.clip(((xx - W / 2) / (W * 0.7)) ** 2 + ((yy - H / 2) / (H * 0.6)) ** 2, 0, 1) ** 1.2
    VIGNETTE = v[..., None]
    rng = np.random.default_rng(9)
    GRAINS = [rng.normal(0, 4.5, (H, W, 1)).astype(np.float32) for _ in range(3)]


def main():
    from sound_noir import build_mix_noir
    os.makedirs("out", exist_ok=True)
    init_film()
    mix_path = build_mix_noir(AUDIO, DUR, WORDS, "out/mix_noir.wav")
    if "--preview" in sys.argv:
        for s in sys.argv[sys.argv.index("--preview") + 1:]:
            Image.frombytes("RGB", (W, H), render_frame(int(float(s) * FPS))).save(
                f"out/preview_noir_{float(s):05.2f}.png")
        return
    n = int(DUR * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", mix_path,
                           "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-maxrate", "12M", "-bufsize", "24M",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", "-ar", "48000",
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
