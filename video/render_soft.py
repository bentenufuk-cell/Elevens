"""Yumuşak / sade tema: krem kâğıt zemin, pastel tonlar, beyaz kartlar, yumuşak geçişler.

Aynı seslendirme ve kelime zamanlamasını kullanır; yardımcılar render.py'den gelir.
Kullanım:  python3 render_soft.py                -> out/elevens1_shorts_soft.mp4
           python3 render_soft.py --preview 4.5 20
"""
import math
import os
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from render import (AUDIO, DUR, F_BOLD, F_MED, F_SEMI, FD, FPS, H, PROMPT_IDX, S_BOUNDS, W, WORDS, clamp,
                    e_back, e_inout, e_out, emoji, font, mix, paste, place, prog, scene_index, wrap, wt)
from sound import build_mix_soft

OUT = "out/elevens1_shorts_soft.mp4"

# ---------------------------------------------------------------- palet
PAPER = (247, 242, 235)
PAPER2 = (239, 231, 221)
INK = (46, 43, 40)
MUTED = (138, 132, 124)
LINE = (232, 225, 215)
CARD = (255, 255, 255)
SAGE = (110, 159, 127)
HONEY = (205, 150, 52)
ROSE = (205, 104, 104)
SKY = (106, 143, 199)
PEACH = (250, 217, 200)
SAGE_T = (226, 238, 229)
HONEY_T = (248, 236, 210)
ROSE_T = (248, 225, 223)
SKY_T = (223, 232, 246)
LAV_T = (234, 228, 248)

F_DSEMI = FD + "InterDisplay-SemiBold.otf"
F_DBOLD = FD + "InterDisplay-Bold.otf"
F_DLIGHT = FD + "InterDisplay-Light.otf"
F_ITAL = FD + "InterDisplay-MediumItalic.otf"


# ---------------------------------------------------------------- yumuşak primitifler
@lru_cache(maxsize=512)
def card(w, h, r, fill=CARD, outline=LINE, shadow=26, salpha=34):
    """Beyaz kart + geniş, soluk gölge. Sprite (w+4s, h+4s); kart (2s, 2s)'den başlar."""
    pad = shadow * 2
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((pad, pad + shadow // 2, pad + w, pad + h + shadow // 2), r,
                                             fill=(90, 70, 50, salpha))
        im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(shadow)))
    ImageDraw.Draw(im).rounded_rectangle((pad, pad, pad + w - 1, pad + h - 1), r, fill=fill + (255,),
                                         outline=outline + (255,) if outline else None, width=2 if outline else 0)
    return im


@lru_cache(maxsize=2048)
def txt(text, fpath, size, fill):
    f = font(fpath, size)
    asc, desc = f.getmetrics()
    pad = 6
    im = Image.new("RGBA", (int(math.ceil(f.getlength(text))) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), text, font=f, fill=fill)
    return im


def tc(c, text, fpath, size, fill, cx, cy, scale=1.0, alpha=1.0, rot=0.0):
    place(c, txt(text, fpath, size, fill + (255,)), cx, cy, scale, alpha, rot)


def chip(text, size, fg, bg, padx=30, pady=16, em=None, fpath=F_SEMI):
    f = font(fpath, size)
    asc, desc = f.getmetrics()
    h = asc + desc + 2 * pady - 8
    ew = int(size * 1.05) + 14 if em else 0
    im = Image.new("RGBA", (int(f.getlength(text)) + 2 * padx + ew, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, h - 1), h // 2, fill=bg + (255,))
    if em:
        e = emoji(em, int(size * 1.05))
        im.alpha_composite(e, (padx, (h - e.height) // 2))
    d.text((padx + ew, pady - 4), text, font=f, fill=fg)
    return im


def rise(p, dist=40):
    """Yumuşak giriş: aşağıdan yukarı süzülme ofseti."""
    return (1 - e_out(p)) * dist


# ---------------------------------------------------------------- arka plan
LW, LH = 108, 192
_yy, _xx = np.mgrid[0:LH, 0:LW].astype(np.float32)
BLOBS = [PEACH, SAGE_T, LAV_T, SKY_T]
SCENE_BLOBS = [(0, 3), (0, 2), (3, 1), (1, 0), (0, 2), (2, 3)]


def background(t, energy):
    base = np.empty((LH, LW, 3), np.float32)
    g = (_yy / LH)[..., None]
    base[:] = np.array(PAPER, np.float32) * (1 - g) + np.array(PAPER2, np.float32) * g
    i = scene_index(t)
    for j, bi in enumerate(SCENE_BLOBS[i]):
        col = np.array(BLOBS[bi], np.float32)
        if i > 0 and t - S_BOUNDS[i] < 1.0:  # renk geçişi
            p = (t - S_BOUNDS[i]) / 1.0
            col = np.array(BLOBS[SCENE_BLOBS[i - 1][j]], np.float32) * (1 - p) + col * p
        cx = LW * (0.3 + 0.4 * j + 0.12 * math.sin(t * 0.15 + j * 2))
        cy = LH * (0.25 + 0.5 * j + 0.08 * math.cos(t * 0.12 + j))
        r = (46 + 6 * math.sin(t * 0.3 + j) + 6 * energy) ** 2
        m = np.exp(-((_xx - cx) ** 2 + (_yy - cy) ** 2) / r)[..., None] * 0.75
        base = base * (1 - m) + col * m
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).convert("RGBA")


GRAIN = None


# ---------------------------------------------------------------- sahne 1
Q_TEXT = "Ay'a ilk ayak basan kim?"
A_TEXT = "Elbette! Ay'a ilk ayak basan kişi Yuri Gagarin'dir (1961)."


def avatar(size=84):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=SAGE_T + (255,), outline=SAGE + (255,), width=3)
    d.text((size / 2, size / 2), "AI", font=font(F_DBOLD, int(size * 0.38)), fill=SAGE, anchor="mm")
    return im


AVATAR = None


def scene1(c, t):
    ph = prog(t, 0.0, 0.6)
    tc(c, "Küçük bir ipucu", F_ITAL, 44, MUTED, 540, 270 + rise(ph, 20), 1, ph)
    pt = prog(t, 0.15, 0.7)
    tc(c, "ChatGPT'yi daha dürüst", F_DSEMI, 74, INK, 540, 360 + rise(pt), 1, pt)
    tc(c, "yapan tek cümle", F_DSEMI, 74, INK, 540, 445 + rise(pt), 1, pt)
    # ince çizgi
    pl = e_out(prog(t, 0.5, 0.6))
    if pl > 0:
        ImageDraw.Draw(c).rounded_rectangle((540 - 60 * pl, 510, 540 + 60 * pl, 515), 3, fill=HONEY + (255,))

    p = prog(t, 0.1, 0.5)
    fq = font(F_MED, 54)
    qw = int(fq.getlength(Q_TEXT)) + 80
    qb = card(qw, 112, 50, SKY_T, None, 18, 22).copy()
    ImageDraw.Draw(qb).text((36 + 40, 36 + 24), Q_TEXT, font=fq, fill=INK)
    place(c, qb, 1010 - qw / 2, 650 + rise(p), 1, p)

    pa = prog(t, 0.4, 0.4)
    place(c, AVATAR, 100, 830 + rise(pa), 1, pa)
    fa = font(F_MED, 54)
    lines = wrap(A_TEXT, F_MED, 54, 740)
    t0, t1 = 0.75, 2.6
    n = int(len(A_TEXT) * prog(t, t0, t1 - t0))
    wrong = prog(t, 4.36, 0.4)
    bx, by, bw, lh = 160, 790, 860, 74
    if t < t0:
        if pa > 0:
            bub = card(170, 96, 44, CARD, LINE, 18, 26).copy()
            d = ImageDraw.Draw(bub)
            for k in range(3):
                a = 0.5 + 0.5 * math.sin(t * 8 - k * 1.1)
                d.ellipse((36 + 45 + k * 36 - 8, 36 + 40, 36 + 45 + k * 36 + 8, 36 + 56), fill=mix(LINE, MUTED, a))
            paste(c, set_a(bub, pa), bx - 36, by - 36 + rise(pa))
        return
    shown, left = [], n
    for ln in lines:
        if left <= 0:
            break
        shown.append(ln[:left])
        left -= len(ln) + 1
    bh = 52 + lh * max(1, len(shown))
    bub = card(bw, bh, 40, mix(CARD, ROSE_T, wrong), mix(LINE, ROSE, wrong * 0.6), 18, 26).copy()
    d = ImageDraw.Draw(bub)
    for k, ln in enumerate(shown):
        d.text((36 + 40, 36 + 24 + k * lh), ln, font=fa, fill=INK)
    if shown and t < t1 + 0.3 and int(t * 3) % 2 == 0:
        x = 36 + 40 + fa.getlength(shown[-1]) + 4
        y = 36 + 24 + (len(shown) - 1) * lh
        d.rounded_rectangle((x, y + 8, x + 4, y + 60), 2, fill=SAGE)
    # "Gagarin" kelimesinin altına yanlış çizgisi
    if wrong > 0 and len(shown) == len(lines):
        for k, ln in enumerate(lines):
            j = ln.find("Yuri Gagarin")
            if j >= 0:
                x0 = 36 + 40 + fa.getlength(ln[:j])
                x1 = x0 + fa.getlength("Yuri Gagarin'dir") * e_out(wrong)
                y = 36 + 24 + k * lh + 66
                pts = [(x, y + 4 * math.sin((x - x0) / 9)) for x in np.arange(x0, x1, 3)]
                if len(pts) > 1:
                    d.line(pts, fill=ROSE, width=5, joint="curve")
    paste(c, bub, bx - 36, by - 36)

    ps = prog(t, 2.85, 0.4)
    if ps > 0:
        st = chip("%100 emin ✓", 40, SAGE, SAGE_T, em=None, fpath=F_BOLD)
        place(c, st, 870, by - 10 + rise(ps, 20), 1, ps * (1 - 0.8 * wrong))
    pw = prog(t, 4.45, 0.4)
    if pw > 0:
        st = chip("Aslında yanlış", 40, ROSE, ROSE_T, fpath=F_BOLD)
        place(c, st, 840, by - 10 + rise(pw, 20), 1, pw)
    pc = prog(t, 4.85, 0.5)
    if pc > 0:
        cor = chip("Doğrusu: Neil Armstrong, 1969", 42, SAGE, SAGE_T, em="🌙", fpath=F_SEMI)
        place(c, cor, 540, by + bh + 80 + rise(pc, 20), 1, pc)


def set_a(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


# ---------------------------------------------------------------- sahne 2
def scene2(c, t):
    t0 = 5.55
    s_card, _ = wt("sana")
    pin = prog(t, t0 + 0.1, 0.7)
    pout = prog(t, s_card - 0.4, 0.4)
    if pout < 1:
        br = 1 + 0.025 * math.sin(t * 2.2)
        a = pin * (1 - pout)
        r = 230 * br
        circ = Image.new("RGBA", (520, 520), (0, 0, 0, 0))
        ImageDraw.Draw(circ).ellipse((260 - r, 260 - r, 260 + r, 260 + r), fill=PEACH + (255,))
        place(c, circ, 540, 760 + rise(pin, 60), 1, a)
        # dış halka
        ring = Image.new("RGBA", (640, 640), (0, 0, 0, 0))
        rr = 290 + 10 * math.sin(t * 1.4)
        ImageDraw.Draw(ring).ellipse((320 - rr, 320 - rr, 320 + rr, 320 + rr), outline=HONEY + (120,), width=3)
        place(c, ring, 540, 760 + rise(pin, 60), 1, a * 0.8)
        tc(c, "?", F_DSEMI, 300, INK, 540, 745 + rise(pin, 60), 1, a)
    if t < s_card - 0.3:
        return
    pc = prog(t, s_card - 0.15, 0.6)
    cy = 780 + rise(pc, 60)
    place(c, card(840, 640, 48), 540, cy, 1, pc)
    place(c, emoji("💡", 120), 540, cy - 200, 1, prog(t, s_card, 0.5))
    for word, fg, bg, x in (("basit", SKY, SKY_T, 380), ("etkili", SAGE, SAGE_T, 700)):
        ts, _ = wt(word, s_card)
        pp = prog(t, ts, 0.4)
        place(c, chip(word.capitalize(), 50, fg, bg, 38, 18, fpath=F_SEMI), x, cy - 30 + rise(pp, 20), 1, pp)
    ty, _ = wt("yöntem", s_card)
    pt = prog(t, ty - 0.1, 0.5)
    tc(c, "Tek cümle.", F_DSEMI, 120, INK, 540, cy + 150 + rise(pt, 24), 1, pt)
    tc(c, "basit ama etkili bir yöntem", F_ITAL, 40, MUTED, 540, cy + 250 + rise(pt, 24), 1, pt)


# ---------------------------------------------------------------- sahne 3
P_COLORS = {0: SAGE, 1: SAGE, 2: SAGE, 3: HONEY, 5: ROSE, 6: ROSE, 7: ROSE, 14: SKY}
P_SIZE, P_LH, P_X0, P_MAXW = 52, 74, 124, 830


def p_layout():
    f = font(F_MED, P_SIZE)
    sp = f.getlength(" ")
    x, y, out = 0.0, 0, []
    for k, i in enumerate(PROMPT_IDX):
        w = WORDS[i]["w"]
        fp = F_SEMI if k in P_COLORS else F_MED
        wl = font(fp, P_SIZE).getlength(w)
        if x > 0 and x + wl > P_MAXW:
            x, y = 0.0, y + 1
        out.append((k, i, w, fp, x, y, wl))
        x += wl + sp
    return out


P_LAYOUT = p_layout()
P_LINES = P_LAYOUT[-1][5] + 1


def scene3(c, t):
    t0 = 11.35
    s_type = WORDS[PROMPT_IDX[0]]["s"]
    e_type = WORDS[PROMPT_IDX[-1]]["e"]
    p1 = prog(t, t0 + 0.1, 0.6)
    tc(c, "Önemli bir sorudan sonra", F_ITAL, 46, MUTED, 540, 330 + rise(p1, 20), 1, p1)
    tc(c, "bunu ekle", F_DSEMI, 84, INK, 540, 420 + rise(p1, 20), 1, p1)

    tcm, _ = wt("cümleyi", t0)
    pb = prog(t, tcm - 0.2, 0.6)
    if pb <= 0:
        return
    box_h = int(90 + P_LINES * P_LH)
    box_y = 560
    cy = box_y + box_h / 2 + rise(pb, 50)
    place(c, card(940, box_h, 44, CARD, LINE, 30, 30), 540, cy, 1, pb)
    if t < s_type:
        # yer tutucu
        tc(c, "Mesaj yaz…", F_MED, P_SIZE, LINE, 330, box_y + 82 + rise(pb, 50), 1, pb)
    dl = ImageDraw.Draw(c)
    top = box_y + 48 + rise(pb, 50)
    cursor = None
    for k, i, w, fp, x, y, wl in P_LAYOUT:
        ws, we = WORDS[i]["s"], WORDS[i]["e"]
        if t < ws:
            break
        f = font(fp, P_SIZE)
        col = P_COLORS.get(k, INK)
        frac = clamp((t - ws) / max(0.08, (we - ws) * 0.8))
        part = w[: max(1, int(round(len(w) * frac)))]
        X, Y = P_X0 + x, top + y * P_LH
        if t < we + 0.15:  # fosforlu kalem: kelime söylenirken soldan sağa dolar
            hp = e_out(clamp((t - ws) / max(0.1, we - ws)))
            fade = 1 - clamp((t - we) / 0.15)
            dl.rounded_rectangle((X - 6, Y + 36, X + (wl + 6) * hp, Y + P_LH - 8), 8,
                                 fill=PEACH + (int(255 * fade),))
        dl.text((X, Y + 4), part, font=f, fill=col)
        cursor = (X + f.getlength(part) + 3, Y)
    if cursor and (t < e_type + 0.1 or int(t * 2.5) % 2 == 0):
        dl.rounded_rectangle((cursor[0], cursor[1] + 12, cursor[0] + 4, cursor[1] + 64), 2, fill=SAGE)
    # gönder butonu
    pbt = prog(t, e_type - 0.3, 0.5)
    if pbt > 0:
        btn = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        db = ImageDraw.Draw(btn)
        db.ellipse((0, 0, 99, 99), fill=INK)
        db.polygon([(50, 26), (74, 52), (58, 52), (58, 76), (42, 76), (42, 52), (26, 52)], fill=PAPER)
        place(c, btn, 940, box_y + box_h + 80, 1, pbt)
    tk, _ = wt("emin", s_type)
    pk = prog(t, tk, 0.5)
    if pk > 0:
        place(c, chip("Ekran görüntüsü al", 40, INK, CARD, em="📌", fpath=F_MED), 330,
              box_y + box_h + 80 + rise(pk, 20), 1, pk)


# ---------------------------------------------------------------- sahne 4
ROWS = [("✅", "Kesin", "Bildiği gerçekler", SAGE, SAGE_T),
        ("🤔", "Tahmin", "Olasılıklar, yorumlar", HONEY, HONEY_T),
        ("🔎", "Doğrulanmalı", "Kontrol edilmesi gerekenler", ROSE, ROSE_T)]


def scene4(c, t):
    t0 = 25.45
    ph = prog(t, t0 + 0.1, 0.6)
    tc(c, "Yanıt artık", F_ITAL, 46, MUTED, 540, 330 + rise(ph, 20), 1, ph)
    tc(c, "üçe ayrılır", F_DSEMI, 84, INK, 540, 420 + rise(ph, 20), 1, ph)
    t_emin, _ = wt("emin", t0)
    for k, (em, title, sub, col, tint) in enumerate(ROWS):
        pr = prog(t, t0 + 0.35 + k * 0.6, 0.6)
        if pr <= 0:
            continue
        y = 640 + k * 210
        focus = prog(t, t_emin + (k - 1) * 0.3, 0.5) if k > 0 else 0
        dim = prog(t, t_emin, 0.5) if k == 0 else 0
        row = card(900, 170, 40, CARD, mix(LINE, col, focus * 0.8), 22, 28).copy()
        d = ImageDraw.Draw(row)
        o = 44
        d.rounded_rectangle((o + 28, o + 28, o + 142, o + 142), 30, fill=tint)
        e = emoji(em, 64)
        row.alpha_composite(e, (o + 85 - e.width // 2, o + 85 - e.height // 2))
        d.text((o + 175, o + 30), title, font=font(F_DSEMI, 54), fill=col)
        d.text((o + 177, o + 98), sub, font=font(F_MED, 34), fill=MUTED)
        place(c, row, 540, y + rise(pr, 40), 1 + 0.015 * focus, pr * (1 - 0.45 * dim))


# ---------------------------------------------------------------- sahne 5
def scene5(c, t):
    t0 = 31.0
    t_bu, _ = wt("bu", t0 + 0.5)
    t_oz, _ = wt("özellikle", t0)
    pa = prog(t, t0 + 0.05, 0.5)
    pa_out = prog(t, t_bu - 0.3, 0.4)
    if pa_out < 1:
        a = pa * (1 - pa_out)
        circ = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        ImageDraw.Draw(circ).ellipse((10, 10, 289, 289), fill=ROSE_T + (255,))
        place(c, circ, 540, 680 + rise(pa, 40), 1 + 0.02 * math.sin(t * 3), a)
        tc(c, "!", F_DSEMI, 180, ROSE, 540, 672 + rise(pa, 40), 1, a)
        tc(c, "Ama dikkat.", F_DSEMI, 110, INK, 540, 940 + rise(pa, 40), 1, a)
    # B: azalır ama sıfırlanmaz
    pb = prog(t, t_bu - 0.1, 0.5)
    pb_out = prog(t, t_oz - 0.4, 0.4)
    if pb > 0 and pb_out < 1:
        a = pb * (1 - pb_out)
        tc(c, "Yanlışlar azalır,", F_DSEMI, 80, INK, 540, 360 + rise(pb, 20), 1, a)
        tc(c, "ama sıfırlanmaz", F_ITAL, 56, MUTED, 540, 450 + rise(pb, 20), 1, a)
        ty, _ = wt("yanlışları", t0)
        tk, _ = wt("kaldırmaz", t0)
        grow = e_out(prog(t, t_bu, 0.7))
        shrink = e_inout(prog(t, ty, 0.8))
        base = 1120
        h1 = 440 * grow
        h2 = 440 * grow * (1 - 0.65 * shrink)
        bars = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(bars)
        for x, h, col, lab in ((360, h1, (234, 174, 168), "Önce"), (720, h2, (172, 206, 182), "Sonra")):
            if h > 4:
                d.rounded_rectangle((x - 110, base - h, x + 110, base), 30, fill=col + (255,))
            d.text((x, base + 50), lab, font=font(F_SEMI, 46), fill=MUTED, anchor="mm")
        d.rounded_rectangle((200, base, 880, base + 4), 2, fill=LINE + (255,))
        paste(c, set_a(bars, a), 0, 0)
        pk = prog(t, tk, 0.5)
        if pk > 0:
            place(c, chip("≠ 0", 54, ROSE, CARD, 34, 18, fpath=F_BOLD), 720, base - h2 - 70 + rise(pk, 16), 1,
                  pk * a)
    # C: kaynak listesi
    pc = prog(t, t_oz - 0.2, 0.6)
    if pc > 0:
        tc(c, "Önemli bilgiyi", F_ITAL, 50, MUTED, 540, 360 + rise(pc, 20), 1, pc)
        tc(c, "kaynağından kontrol et", F_DSEMI, 74, INK, 540, 445 + rise(pc, 20), 1, pc)
        items = [("📚", "Resmî kaynaklar", "güvenilir"), ("🔬", "Bilimsel çalışmalar", "kaynaklardan"),
                 ("🎓", "Uzman görüşü", "kontrol")]
        for k, (em, label, cue) in enumerate(items):
            pi = prog(t, t_oz + 0.3 + k * 0.3, 0.6)
            if pi <= 0:
                continue
            tt, _ = wt(cue, t_oz)
            pt = prog(t, tt, 0.4)
            y = 640 + k * 180
            row = card(880, 140, 36, CARD, LINE, 20, 26).copy()
            d = ImageDraw.Draw(row)
            o = 40
            e = emoji(em, 64)
            row.alpha_composite(e, (o + 40, o + 70 - e.height // 2))
            d.text((o + 140, o + 42), label, font=font(F_MED, 48), fill=INK)
            cx, cy2 = o + 790, o + 70
            r = 34
            d.ellipse((cx - r, cy2 - r, cx + r, cy2 + r), fill=mix(CARD, SAGE_T, pt), outline=mix(LINE, SAGE, pt),
                      width=4)
            if pt > 0:
                q = e_out(pt)
                p0, p1_, p2 = (cx - 15, cy2 + 1), (cx - 4, cy2 + 12), (cx + 16, cy2 - 12)
                seg = [p0, (p0[0] + (p1_[0] - p0[0]) * min(1, q * 2), p0[1] + (p1_[1] - p0[1]) * min(1, q * 2))]
                if q > 0.5:
                    seg.append((p1_[0] + (p2[0] - p1_[0]) * (q - 0.5) * 2, p1_[1] + (p2[1] - p1_[1]) * (q - 0.5) * 2))
                d.line(seg, fill=SAGE, width=6, joint="curve")
            place(c, row, 540, y + rise(pi, 40), 1, pi)


# ---------------------------------------------------------------- sahne 6
def scene6(c, t):
    t0 = 39.4
    tu, _ = wt("unutma")
    pu = prog(t, tu, 0.5)
    place(c, chip("Unutma", 44, HONEY, HONEY_T, 40, 20, fpath=F_SEMI), 540, 380 + rise(pu, 20), 1, pu)
    tk, _ = wt("kendinden", t0)
    pk = prog(t, tk, 0.6)
    tc(c, "Kendinden emin", F_DSEMI, 104, INK, 540, 600 + rise(pk, 30), 1, pk)
    tg, _ = wt("gelmez", t0)
    pg = prog(t, tg - 0.1, 0.6)
    if pg > 0:
        circ = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
        ImageDraw.Draw(circ).ellipse((0, 0, 219, 219), fill=ROSE_T + (255,))
        place(c, circ, 540, 790, 0.6 + 0.4 * e_back(pg, 1.2), pg)
        tc(c, "≠", F_DSEMI, 150, ROSE, 540, 772, 0.6 + 0.4 * e_back(pg, 1.2), pg)
    td, _ = wt("doğru", t0)
    pd = prog(t, td, 0.6)
    tc(c, "her zaman doğru", F_DSEMI, 104, SAGE, 540, 980 + rise(pd, 30), 1, pd)
    tc(c, "değildir.", F_ITAL, 60, MUTED, 540, 1080 + rise(pd, 30), 1, prog(t, td + 0.3, 0.6))
    po = prog(t, 45.9, 0.6)
    if po > 0:
        place(c, chip("Kaydet  ·  Paylaş", 44, INK, CARD, 40, 20, em="🔖", fpath=F_MED), 540,
              1360 + rise(po, 20), 1, po)


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6]


# ---------------------------------------------------------------- altyazı
def caption_groups():
    groups, cur = [], []
    for i, x in enumerate(WORDS):
        if cur and (x["seg"] != WORDS[cur[0]]["seg"] or len(cur) >= 4 or
                    sum(len(WORDS[j]["w"]) for j in cur) + len(x["w"]) > 22):
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
        s = WORDS[g[0]]["s"] - 0.08
        e = WORDS[g[-1]]["e"]
        nxt = WORDS[groups[gi + 1][0]]["s"] - 0.08 if gi + 1 < len(groups) else e + 0.5
        cut = min(b for b in S_BOUNDS if b > e)
        out.append((s, min(nxt, e + 0.4, cut), g))
    return out


CAPS = caption_groups()
CAP_HIDE = (WORDS[PROMPT_IDX[0]]["s"] - 0.1, WORDS[PROMPT_IDX[-1]]["e"] + 0.3)
CAP_Y, CAP_SIZE = 1420, 66


def captions(c, t):
    if CAP_HIDE[0] <= t < CAP_HIDE[1]:
        return
    for s, e, g in CAPS:
        if not (s <= t < e):
            continue
        f = font(F_SEMI, CAP_SIZE)
        words = [WORDS[i]["w"] for i in g]
        sp = f.getlength(" ")
        widths = [f.getlength(w) for w in words]
        lines, cur, cw = [], [], 0
        for k, wl in enumerate(widths):
            if cur and cw + sp + wl > 860:
                lines.append(cur)
                cur, cw = [], 0
            cw += (sp if cur else 0) + wl
            cur.append(k)
        lines.append(cur)
        pg = prog(t, s, 0.25)
        a = pg * (1 - prog(t, e - 0.12, 0.12))
        layer = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        maxw = max(sum(widths[k] for k in ln) + sp * (len(ln) - 1) for ln in lines)
        bh = 40 + 84 * len(lines)
        d.rounded_rectangle((540 - maxw / 2 - 40, 150 - bh / 2, 540 + maxw / 2 + 40, 150 + bh / 2), 40,
                            fill=(255, 255, 255, 215))
        for li, ln in enumerate(lines):
            lw = sum(widths[k] for k in ln) + sp * (len(ln) - 1)
            x = 540 - lw / 2
            y = 150 + (li - (len(lines) - 1) / 2) * 84
            for k in ln:
                i = g[k]
                ws, we = WORDS[i]["s"], WORDS[i]["e"]
                if ws <= t < we + 0.05:
                    hp = e_out(clamp((t - ws) / 0.15))
                    d.rounded_rectangle((x - 8, y - 36, x + widths[k] + 8, y + 38), 18, fill=PEACH + (int(255 * hp),))
                col = INK if t >= ws - 0.02 else MUTED
                d.text((x, y), words[k], font=f, fill=col, anchor="lm")
                x += widths[k] + sp
        paste(c, set_a(layer, a), 0, CAP_Y - 150 + rise(pg, 14))


# ---------------------------------------------------------------- kompozisyon
def render_frame(fi):
    t = fi / FPS
    frame = background(t, float(ENERGY[min(fi, len(ENERGY) - 1)]))
    i = scene_index(t)
    # yumuşak çapraz geçiş: önceki sahne yukarı süzülüp solarken yenisi aşağıdan gelir
    layers = []
    b = S_BOUNDS[i]
    if i > 0 and t - b < 0.25:
        q = e_out(clamp((t - b) / 0.25))
        layers.append((i - 1, (1 - q) ** 2, -40 * q))
    layers.append((i, 1.0, 0.0))
    for si, a, dy in layers:
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        SCENES[si](c, t if si == i else b - 1e-3)
        if a < 0.999 or dy:
            paste(frame, set_a(c, a), 0, dy)
        else:
            frame.alpha_composite(c)
    captions(frame, t)
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((60, 60, W - 60, 66), 3, fill=LINE + (255,))
    d.rounded_rectangle((60, 60, 60 + (W - 120) * t / DUR, 66), 3, fill=HONEY + (255,))
    arr = np.asarray(frame.convert("RGB"), np.float32)
    # başta ve sonda kâğıt rengine yumuşak geçiş
    fade = max(1 - t / 0.35, (t - (DUR - 0.6)) / 0.6, 0)
    if fade > 0:
        arr = arr * (1 - fade) + np.array(PAPER, np.float32) * fade
    arr = arr + GRAIN
    return np.clip(arr, 0, 255).astype(np.uint8).tobytes()


ENERGY = None


def main():
    global ENERGY, GRAIN, AVATAR
    os.makedirs("out", exist_ok=True)
    mix_path, ENERGY = build_mix_soft(AUDIO, DUR, FPS, WORDS, "out/mix_soft.wav")
    GRAIN = np.random.default_rng(3).normal(0, 2.0, (H, W, 1)).astype(np.float32)
    AVATAR = avatar()
    if "--preview" in sys.argv:
        for s in sys.argv[sys.argv.index("--preview") + 1:]:
            Image.frombytes("RGB", (W, H), render_frame(int(float(s) * FPS))).save(
                f"out/preview_soft_{float(s):05.2f}.png")
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
