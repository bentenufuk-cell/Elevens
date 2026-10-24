"""8-bit retro oyun: "Hata Avcısı".

Her şey 216x384 piksellik düşük çözünürlükte çizilir ve 5 kat (en yakın komşu) büyütülür.
RPG diyalog kutuları, can/skor göstergesi, soru blokları, sandık, büyü parşömeni,
envanter, boss savaşı ve görev listesi.

Kullanım:  python3 render_pixel.py                 -> out/elevens1_shorts_pixel.mp4
           python3 render_pixel.py --preview 4.5 20
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

from render import AUDIO, PROMPT_IDX, S_BOUNDS, WORDS, clamp, e_back, e_out, prog, scene_index, tr_upper, wt

LW, LH, K = 216, 384, 5
W, H, FPS = LW * K, LH * K, 30
DUR = 47.2
OUT = "out/elevens1_shorts_pixel.mp4"

# PICO-8 paleti
PAL = [(0, 0, 0), (29, 43, 83), (126, 37, 83), (0, 135, 81), (171, 82, 54), (95, 87, 79), (194, 195, 199),
       (255, 241, 232), (255, 0, 77), (255, 163, 0), (255, 236, 39), (0, 228, 54), (41, 173, 255),
       (131, 118, 156), (255, 119, 168), (255, 204, 170)]
BLACK, NAVY, PLUM, DGREEN, BROWN, DGRAY, LGRAY, WHITE, RED, ORANGE, YELLOW, GREEN, BLUE, LAV, PINK, PEACH = PAL

FDIR = "assets/fonts/"


@lru_cache(maxsize=None)
def font(key, size):
    return ImageFont.truetype(FDIR + {"ps": "PressStart2P-Regular.ttf", "jy": "Jersey10-Regular.ttf"}[key], size)


def draw(img):
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # kenar yumuşatma yok: keskin piksel
    return d


def text(d, s, x, y, col, key="ps", size=8, outline=None, anchor="la"):
    f = font(key, size)
    if outline is not None:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            d.text((x + dx, y + dy), s, font=f, fill=outline, anchor=anchor)
    d.text((x, y), s, font=f, fill=col, anchor=anchor)


def tlen(s, key="ps", size=8):
    return font(key, size).getlength(s)


def wrap_chars(s, n):
    lines, cur = [], ""
    for w in s.split():
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- sprite'lar
def sprite(img, rows, x, y, k=1, recolor=None):
    d = ImageDraw.Draw(img)
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            c = PAL[int(ch, 16)]
            if recolor and ch in recolor:
                c = recolor[ch]
            d.rectangle((x + i * k, y + j * k, x + i * k + k - 1, y + j * k + k - 1), fill=c)


HEART = [".88.88.", "8778888", "8788888", ".88888.", "..888..", "...8..."]
HEART_E = [".55.55.", "5..5..5", "5.....5", ".5...5.", "..5.5..", "...5..."]
ROBOT = [
    ".......88.......",
    ".......77.......",
    "..777777777777..",
    ".76666666666667.",
    ".76EEE6666EEE67.",
    ".76EEE6666EEE67.",
    ".76666666666667.",
    ".76666666666667.",
    ".76666666666667.",
    "..777777777777..",
    "....56666665....",
    "..55766cc66755..",
    "..5.76666667.5..",
    "....76666667....",
    "....66....66....",
    "....55....55....",
]
BUG = [
    "....2.........2.....",
    ".....2.......2......",
    "....22222222222.....",
    "..222222222222222...",
    ".22277722222277722..",
    ".22270722222270722..",
    "2222777222222777222.",
    "2222222222222222222.",
    "2222888888888888222.",
    "222280800808008022..",
    ".22288888888888822..",
    "..2222222222222222..",
    "...22222222222222...",
    "..5..5..5..5..5..5..",
    ".5..5..5..5..5..5...",
]
CHEST_C = [
    "..444444444444..",
    ".49999999999994.",
    ".44444444444444.",
    ".4444444aa444444",
    ".44444444444444.",
    ".49999999999994.",
    ".44444444444444.",
    ".44444444444444.",
    "..444444444444..",
]
CHEST_LID = [
    "..444444444444..",
    ".49999999999994.",
    ".44444444444444.",
]
CHEST_BODY = [
    ".44444444444444.",
    ".4444444aa44444.",
    ".49999999999994.",
    ".44444444444444.",
    ".44444444444444.",
    "..444444444444..",
]
FLOPPY = [
    "1111111111..",
    "116666661111",
    "116666661111",
    "111111111111",
    "117777777711",
    "117555557711",
    "117777777711",
    "111111111111",
]


def gem(img, x, y, col, k=2):
    rows = ["...X...", "..XXX..", ".XWXXX.", "XWXXXXX", ".XXXXX.", "..XXX..", "...X..."]
    d = ImageDraw.Draw(img)
    for j, r in enumerate(rows):
        for i, ch in enumerate(r):
            if ch == ".":
                continue
            c = WHITE if ch == "W" else col
            d.rectangle((x + i * k, y + j * k, x + i * k + k - 1, y + j * k + k - 1), fill=c)


def qblock(img, x, y, t, hit=False):
    d = draw(img)
    c = (BROWN if hit else ORANGE)
    d.rectangle((x, y, x + 19, y + 19), fill=BLACK)
    d.rectangle((x + 1, y + 1, x + 18, y + 18), fill=c)
    d.rectangle((x + 1, y + 1, x + 18, y + 2), fill=YELLOW if not hit else DGRAY)
    for cx, cy in ((x + 3, y + 3), (x + 15, y + 3), (x + 3, y + 15), (x + 15, y + 15)):
        d.point((cx, cy), fill=BLACK)
    if not hit:
        text(d, "?", x + 6, y + 6, WHITE if int(t * 4) % 2 else YELLOW)


def box(img, x0, y0, x1, y1, border=WHITE, fill=BLACK, name=None):
    d = draw(img)
    d.rectangle((x0, y0, x1, y1), fill=fill)
    d.rectangle((x0 + 1, y0 + 1, x1 - 1, y1 - 1), outline=border)
    d.rectangle((x0 + 3, y0 + 3, x1 - 3, y1 - 3), outline=border)
    if name:
        w = tlen(name)
        d.rectangle((x0 + 6, y0 - 7, x0 + 12 + w, y0 + 4), fill=border)
        text(d, name, x0 + 9, y0 - 5, BLACK)
    return d


def tri_down(d, x, y, col):
    d.polygon([(x, y), (x + 6, y), (x + 3, y + 3)], fill=col)


def tri_right(d, x, y, col):
    d.polygon([(x, y), (x, y + 6), (x + 3, y + 3)], fill=col)


def typewrite(d, lines, x, y, t, t0, cps, col, lh=11):
    """Diyalog kutusu yazısı: karakter karakter. Bitti mi döndürür."""
    n = int(max(0, t - t0) * cps)
    for j, ln in enumerate(lines):
        if n <= 0:
            return False
        text(d, ln[:n], x, y + j * lh, col)
        n -= len(ln)
    return n > 0


# ---------------------------------------------------------------- arka plan
_rnd = random.Random(3)
STARS = [(_rnd.randrange(LW), _rnd.randrange(LH), _rnd.random()) for _ in range(70)]
CITY = []
_x = 0
while _x < LW * 3:
    w = _rnd.randint(14, 30)
    h = _rnd.randint(30, 90)
    CITY.append((_x, w, h, _rnd.random()))
    _x += w + _rnd.randint(0, 3)

SCENE_BG = [NAVY, PLUM, (20, 24, 40), NAVY, (60, 10, 30), NAVY]


def background(img, t):
    i = scene_index(t)
    d = draw(img)
    d.rectangle((0, 0, LW, LH), fill=SCENE_BG[i])
    # yatay degrade bantları (dithered)
    for y in range(0, LH, 2):
        if y > 230:
            for x in range((y // 2) % 2, LW, 2):
                d.point((x, y), fill=BLACK)
    for x, y, ph in STARS:
        if y < 300 and math.sin(t * 3 + ph * 20) > -0.3:
            d.point((x, y), fill=WHITE if ph > 0.6 else LAV)
    off = (t * 6) % (LW * 2)
    for bx, bw, bh, ph in CITY:
        x = int(bx - off)
        if x > LW or x + bw < 0:
            x += LW * 3
            if x > LW or x + bw < 0:
                continue
        d.rectangle((x, LH - 70 - bh, x + bw - 1, LH), fill=BLACK)
        for wy in range(LH - 66 - bh, LH - 70, 6):
            for wx in range(x + 3, x + bw - 3, 5):
                if math.sin(wx * 12.9 + wy * 7.3 + ph) > 0.55:
                    d.point((wx, wy), fill=YELLOW if (wx + wy) % 3 else ORANGE)
    # tuğla zemin
    gy = LH - 70
    d.rectangle((0, gy, LW, LH), fill=(40, 30, 28))
    d.rectangle((0, gy, LW, gy + 2), fill=BROWN)
    for r, y in enumerate(range(gy + 4, LH, 8)):
        for x in range(-16 + (8 if r % 2 else 0), LW, 16):
            d.rectangle((x + 1, y, x + 14, y + 6), fill=(70, 46, 40))
            d.line((x + 1, y, x + 14, y), fill=(98, 64, 52))


# ---------------------------------------------------------------- HUD
HEART_LOST = 4.45
COINS = []  # (zaman, puan) — init_events doldurur


def score_at(t):
    return sum(p for tt, p in COINS if t >= tt)


def hud(img, t):
    d = draw(img)
    lost = t >= HEART_LOST
    for k in range(3):
        x = 8 + k * 10
        if k == 2 and lost:
            dt = t - HEART_LOST
            if dt < 0.6 and int(dt * 10) % 2 == 0:
                sprite(img, HEART, x, 8 - int(dt * 20))
            else:
                sprite(img, HEART_E, x, 8)
        else:
            sprite(img, HEART, x, 8)
    text(d, f"SKOR {score_at(t):05d}", LW - 8, 8, WHITE, anchor="ra")
    lv = ["LV1", "LV1", "LV2", "LV2", "BOSS", "SON"][scene_index(t)]
    text(d, lv, LW / 2, 8, YELLOW, anchor="ma")


# ---------------------------------------------------------------- sahne 1: kendinden emin NPC
Q = wrap_chars("Japon balığının hafızası ne kadar?", 22)
A = wrap_chars("Kesinlikle 3 saniye! Bundan çok eminim.", 22)
A_T0, A_CPS = 1.35, 26


def robot(img, x, y, k, t, mood):
    sprite(img, ROBOT, x, y + int(math.sin(t * 5) * 1.5) * (1 if mood != "shock" else 0), k)
    d = ImageDraw.Draw(img)
    yy = y + int(math.sin(t * 5) * 1.5) * (1 if mood != "shock" else 0)
    if mood == "smug":  # ^ ^ gözler, gülümseme
        for ex in (3, 10):
            d.rectangle((x + ex * k, yy + 5 * k, x + (ex + 3) * k - 1, yy + 6 * k - 1), fill=PAL[6])
            d.rectangle((x + ex * k, yy + 4 * k, x + (ex + 1) * k - 1, yy + 5 * k - 1), fill=BLUE)
            d.rectangle((x + (ex + 2) * k, yy + 4 * k, x + (ex + 3) * k - 1, yy + 5 * k - 1), fill=BLUE)
            d.rectangle((x + (ex + 1) * k, yy + 3 * k + k // 2, x + (ex + 2) * k - 1, yy + 4 * k + k // 2 - 1),
                        fill=BLUE)
        d.rectangle((x + 5 * k, yy + 7 * k, x + 11 * k - 1, yy + 8 * k - 1), fill=BLACK)
        d.rectangle((x + 4 * k, yy + 6 * k + k // 2, x + 5 * k - 1, yy + 7 * k + k // 2 - 1), fill=BLACK)
        d.rectangle((x + 11 * k, yy + 6 * k + k // 2, x + 12 * k - 1, yy + 7 * k + k // 2 - 1), fill=BLACK)
    elif mood == "shock":
        for ex in (3, 10):
            d.rectangle((x + ex * k, yy + 4 * k, x + (ex + 3) * k - 1, yy + 6 * k - 1), fill=WHITE)
            d.rectangle((x + (ex + 1) * k, yy + 4 * k + k // 2, x + (ex + 2) * k - 1, yy + 5 * k + k // 2 - 1),
                        fill=BLACK)
        d.rectangle((x + 7 * k, yy + 7 * k, x + 9 * k - 1, yy + 9 * k - 1), fill=BLACK)
        d.rectangle((x + 15 * k, yy + 2 * k, x + 16 * k - 1, yy + 4 * k - 1), fill=BLUE)  # ter
    else:
        d.rectangle((x + 5 * k, yy + 7 * k, x + 11 * k - 1, yy + 8 * k - 1), fill=BLACK)


def scene1(img, t):
    d = draw(img)
    # oyuncu sorusu
    if t > 0.1:
        box(img, 12, 44, 204, 84, WHITE, BLACK, "SEN")
        done = typewrite(d, Q, 22, 56, t, 0.2, 30, WHITE)
        if done and int(t * 3) % 2 == 0 and t < A_T0:
            tri_down(d, 192, 76, WHITE)
    mood = "shock" if t >= 4.36 else ("smug" if t >= A_T0 else "normal")
    pr = prog(t, 0.3, 0.3)
    if pr > 0:
        robot(img, 72, 96 + int((1 - e_out(pr)) * 40), 4, t, mood)
    if t >= 4.36:  # ünlem
        text(d, "!", 134, 92, RED, outline=BLACK, key="jy", size=40)
    # NPC cevabı
    if t > A_T0 - 0.1:
        wrong = t >= 4.36
        bc = RED if wrong and (int(t * 8) % 2 == 0 or t > 4.9) else WHITE
        box(img, 12, 172, 204, 212, bc, BLACK, "BOT")
        typewrite(d, A, 22, 184, t, A_T0, A_CPS, WHITE)
    # güven barı
    pb = prog(t, 2.75, 0.6)
    if pb > 0:
        text(d, "GÜVEN", 14, 222, WHITE, outline=BLACK)
        d.rectangle((60, 220, 186, 231), fill=BLACK)
        d.rectangle((61, 221, 185, 230), outline=WHITE)
        fill = int(122 * e_out(pb))
        for x in range(63, 63 + fill, 4):
            d.rectangle((x, 223, min(x + 2, 183), 228), fill=GREEN if x < 140 else YELLOW)
        if pb >= 1 and int(t * 6) % 2 == 0:
            text(d, "MAX!", 190, 222, YELLOW, outline=BLACK)
    # YANLIŞ!
    pw = prog(t, 4.45, 0.15)
    if pw > 0:
        s = 40 if pw >= 1 else 60
        text(d, "YANLIŞ!", LW / 2, 140, RED, "jy", s, BLACK, anchor="mm")
        if t - 4.45 < 0.9:
            text(d, "-1", 44, 22 - int((t - 4.45) * 12), RED, outline=BLACK)
    pc = prog(t, 4.85, 0.1)
    if pc > 0:
        box(img, 12, 244, 204, 272, GREEN, BLACK)
        typewrite(d, ["GERÇEK: Aylarca hatırlar!"], 22, 254, t, 4.85, 40, GREEN)


# ---------------------------------------------------------------- sahne 2: ? blokları -> sandık
def scene2(img, t):
    d = draw(img)
    s_f, _ = wt("sana")
    tp, _ = wt("peki")
    tn, _ = wt("ne", 6.5)
    pt = prog(t, tp, 0.2)
    if pt > 0:
        text(d, "PEKİ", LW / 2, 64, WHITE, "jy", 40, BLACK, anchor="mm")
    if t >= tn:
        text(d, "NE YAPMALI?", LW / 2, 96, YELLOW, "jy", 40, BLACK, anchor="mm")
    # ? blokları
    hit_t = s_f - 0.05
    for k, x in enumerate((38, 98, 158)):
        bob = int(math.sin(t * 4 + k) * 2)
        hit = k == 1 and t >= hit_t
        dy = -int(8 * math.sin(math.pi * clamp((t - hit_t) / 0.2))) if k == 1 and hit else 0
        if t > 5.65 + k * 0.12:
            qblock(img, x, 130 + bob + dy, t, hit)
    # sandık + eşya
    if t >= hit_t:
        po = prog(t, hit_t + 0.15, 0.3)
        cx, cy = 76, 196
        if po < 1:
            sprite(img, CHEST_C, cx, cy, 4)
        else:
            sprite(img, CHEST_BODY, cx, cy + 12, 4)
            sprite(img, CHEST_LID, cx, cy - 4, 4)
            # ışık hüzmeleri
            for k in range(5):
                x = cx + 8 + k * 12
                if (int(t * 8) + k) % 2 == 0:
                    d.line((x, cy - 4, x - 3 + k * 2, cy - 18), fill=YELLOW)
        pi = prog(t, hit_t + 0.45, 0.4)
        if pi > 0:
            iy = int(cy - 10 - 40 * e_out(pi))
            d.rectangle((LW / 2 - 14, iy - 8, LW / 2 + 14, iy + 8), fill=PEACH, outline=BROWN)
            d.rectangle((LW / 2 - 17, iy - 9, LW / 2 - 13, iy + 9), fill=BROWN)
            d.rectangle((LW / 2 + 13, iy - 9, LW / 2 + 17, iy + 9), fill=BROWN)
            for k in range(3):
                d.line((LW / 2 - 9, iy - 4 + k * 4, LW / 2 + 9, iy - 4 + k * 4), fill=BROWN)
            for k in range(4):  # parıltı
                a = t * 3 + k * 1.57
                sx, sy = LW / 2 + 26 * math.cos(a), iy + 18 * math.sin(a)
                d.point((sx, sy), fill=WHITE)
                d.point((sx + 1, sy), fill=YELLOW)
        for word, col, x, t0 in (("+1 BASİT", GREEN, 40, wt("basit", s_f)[0]), ("+1 ETKİLİ", BLUE, 176,
                                                                                     wt("etkili", s_f)[0])):
            if t >= t0:
                y = 150 - int(min(1, (t - t0) / 0.8) * 20)
                text(d, word, x, y, col, outline=BLACK, anchor="ma")
    ty, _ = wt("yöntem", s_f)
    if t >= ty - 0.1:
        box(img, 12, 252, 204, 284, YELLOW, BLACK)
        text(d, "YENİ EŞYA:", 22, 262, WHITE)
        text(d, "TEK CÜMLE", 108, 262, YELLOW) if int(t * 6) % 2 or t > ty + 0.6 else None


# ---------------------------------------------------------------- sahne 3: büyü parşömeni (prompt)
P_COLS = {0: DGREEN, 1: DGREEN, 2: DGREEN, 3: (200, 110, 0), 5: RED, 6: RED, 7: RED, 14: BLUE}
P_X0, P_Y0, P_LH, P_CH = 18, 104, 12, 23


def p_layout():
    out, x, y = [], 0, 0
    for k, i in enumerate(PROMPT_IDX):
        w = WORDS[i]["w"]
        if x and x + len(w) > P_CH:
            x, y = 0, y + 1
        out.append((k, i, w, P_X0 + x * 8, P_Y0 + y * P_LH))
        x += len(w) + 1
    return out


P_LAYOUT = p_layout()
P_LINES = P_LAYOUT[-1][4]


def scene3(img, t):
    d = draw(img)
    t0 = 11.35
    pin = prog(t, t0, 0.3)
    top = int(36 + (1 - e_out(pin)) * 300)
    bot = P_Y0 + 8 * P_LH + 26 + (top - 36)
    d.rectangle((10, top, 206, bot), fill=PEACH)
    d.rectangle((10, top, 206, bot), outline=BROWN)
    for y in (top - 4, bot - 2):  # rulo uçlar
        d.rectangle((6, y, 210, y + 6), fill=BROWN)
        d.rectangle((6, y + 1, 210, y + 2), fill=ORANGE)
    if pin < 1:
        return
    text(d, "BÜYÜ PARŞÖMENİ", LW / 2, 46, BROWN, anchor="ma")
    d.line((24, 58, 192, 58), fill=BROWN)
    ts, _ = wt("sorduktan", t0)
    tsu, _ = wt("şu", t0)
    typewrite(d, ["1) Sorunu sor."], 18, 66, t, 11.7, 14, DGRAY)
    typewrite(d, ["2) Sonra şunu ekle:"], 18, 82, t, tsu - 0.3, 22, BLACK)
    for k, i, w, x, y in P_LAYOUT:
        ws, we = WORDS[i]["s"], WORDS[i]["e"]
        if t < ws:
            break
        n = max(1, int(round(len(w) * clamp((t - ws) / max(0.08, (we - ws) * 0.85)))))
        col = P_COLS.get(k, BLACK)
        text(d, w[:n], x, y, col)
        if t < we:  # imleç
            d.rectangle((x + n * 8, y, x + n * 8 + 6, y + 7), fill=BROWN if int(t * 8) % 2 else PEACH)
    # parıltılar
    for k in range(6):
        a = t * 1.7 + k
        sx = 14 + (k * 37 + int(t * 9)) % 190
        sy = top + 6 + (k * 53) % (bot - top - 12)
        if math.sin(a * 3) > 0.6:
            d.point((sx, sy), fill=WHITE)
    te, _ = wt("emin", WORDS[PROMPT_IDX[0]]["s"])
    if t >= te and int(t * 3) % 2 == 0:
        text(d, "★ EKRAN GÖRÜNTÜSÜ AL!", LW / 2, bot + 12, YELLOW, outline=BLACK, anchor="ma")


# ---------------------------------------------------------------- sahne 4: envanter
INV = [("KESİN", "Kesin gerçek", GREEN), ("TAHMİN", "Emin değil", YELLOW), ("DOĞRULA", "Kontrol et!", RED)]


def scene4(img, t):
    d = draw(img)
    t0 = 25.45
    po = prog(t, t0 + 0.05, 0.2)
    if po <= 0:
        return
    h = int(200 * e_out(po))
    box(img, 12, 44, 204, 44 + max(12, h), WHITE, BLACK, "ENVANTER")
    if po < 1:
        return
    text(d, "CEVAP 3'E AYRILIR", LW / 2, 56, LGRAY, anchor="ma")
    te, _ = wt("emin", t0)
    sel = -1
    if t >= te:
        sel = 1 if t < te + 1.0 else 2
    for k, (name, desc, col) in enumerate(INV):
        tk = t0 + 0.35 + k * 0.6
        if t < tk:
            continue
        y = 76 + k * 52
        d.rectangle((24, y, 60, y + 36), fill=NAVY, outline=LGRAY)
        gem(img, 32, y + 7, col, 3)
        text(d, name, 70, y + 6, col)
        text(d, desc, 70, y + 22, LGRAY)
        if k == sel and int(t * 6) % 2 == 0:
            d.rectangle((21, y - 3, 63, y + 39), outline=WHITE)
            d.rectangle((20, y - 4, 64, y + 40), outline=WHITE)
        if k == sel:
            tri_right(d, 12 + int(math.sin(t * 10) * 2), y + 15, WHITE)
    if sel >= 1:
        box(img, 12, 252, 204, 280, YELLOW, BLACK)
        text(d, "EMİN DEĞİL! KONTROL ET.", LW / 2, 262, YELLOW, anchor="ma")


# ---------------------------------------------------------------- sahne 5: boss + görev
def scene5(img, t):
    d = draw(img)
    t0 = 31.0
    tb, _ = wt("bu", t0 + 0.5)
    to, _ = wt("özellikle", t0)
    if t < to - 0.2:
        # uyarı şeritleri
        if t < tb + 0.3:
            for y0 in (40, 100):
                d.rectangle((0, y0, LW, y0 + 14), fill=RED if int(t * 6) % 2 else BLACK)
                off = int(t * 60) % 120
                for x in range(-120 + off, LW, 120):
                    text(d, "!UYARI!", x, y0 + 3, YELLOW if int(t * 6) % 2 else RED)
        ta, _ = wt("ama", t0)
        if ta <= t < tb:
            text(d, "AMA", LW / 2, 160, WHITE, "jy", 40, BLACK, anchor="mm")
            text(d, "DİKKAT!", LW / 2, 196, RED, "jy", 60, BLACK, anchor="mm")
        if t >= tb - 0.1:
            # boss
            pb = prog(t, tb - 0.1, 0.4)
            ty, _ = wt("yanlışları", t0)
            tk, _ = wt("kaldırmaz", t0)
            bx, by = 58, int(110 + (1 - e_out(pb)) * -150)
            flash = ty <= t < ty + 0.3 and int(t * 20) % 2 == 0
            sprite(img, BUG, bx, by + int(math.sin(t * 6) * 2), 5,
                   {"2": WHITE} if flash else ({"2": PLUM} if t >= tk and int(t * 4) % 2 else None))
            text(d, "BOSS: YANLIŞ BİLGİ", LW / 2, 64, WHITE, outline=BLACK, anchor="ma")
            hp = 1.0 - 0.85 * e_out(prog(t, ty, 0.5))
            d.rectangle((28, 78, 188, 90), fill=BLACK)
            d.rectangle((29, 79, 187, 89), outline=WHITE)
            d.rectangle((31, 81, 31 + int(154 * hp), 87), fill=RED)
            if ty <= t < ty + 0.6:  # vuruş
                text(d, "-850", 150, 100 - int((t - ty) * 30), YELLOW, outline=BLACK)
                for k in range(6):
                    a = k * 1.05 + t * 9
                    d.line((108, 150, 108 + 40 * math.cos(a), 150 + 40 * math.sin(a)), fill=WHITE)
            if t >= tk:
                box(img, 12, 210, 204, 250, RED, BLACK)
                text(d, "HP 0 OLMAZ!", LW / 2, 218, RED, anchor="ma")
                text(d, "Hatalar azalır, bitmez.", LW / 2, 234, WHITE, anchor="ma")
        return
    # görev listesi
    pq = prog(t, to - 0.15, 0.25)
    box(img, 12, 44, 204, 44 + max(12, int(200 * e_out(pq))), YELLOW, BLACK, "GÖREV")
    if pq < 1:
        return
    text(d, "Kaynağı kontrol et!", LW / 2, 58, YELLOW, anchor="ma")
    for k, (lab, cue) in enumerate((("Resmî kaynak", "güvenilir"), ("Bilimsel çalışma", "kaynaklardan"),
                                    ("Uzman görüşü", "kontrol"))):
        ti = to + 0.4 + k * 0.25
        if t < ti:
            continue
        y = 86 + k * 34
        d.rectangle((24, y, 36, y + 12), outline=WHITE)
        text(d, lab, 46, y + 3, WHITE)
        tc_, _ = wt(cue, to)
        if t >= tc_:
            d.line((26, y + 6, 29, y + 10), fill=GREEN, width=2)
            d.line((29, y + 10, 36, y - 1), fill=GREEN, width=2)
            if t < tc_ + 0.8:
                text(d, "+100", 190, y + 3 - int((t - tc_) * 16), YELLOW, outline=BLACK, anchor="ra")
    if t >= wt("kontrol", to)[0] + 0.4:
        text(d, "GÖREV TAMAM!", LW / 2, 200, GREEN, outline=BLACK, anchor="ma") if int(t * 4) % 2 else None


# ---------------------------------------------------------------- sahne 6: final
def scene6(img, t):
    d = draw(img)
    t0 = 39.4
    tu, _ = wt("unutma")
    if t >= tu:
        text(d, "UNUTMA!", LW / 2, 58, YELLOW if int(t * 4) % 2 else WHITE, "jy", 40, BLACK, anchor="mm")
    tk, _ = wt("kendinden", t0)
    if t >= tk:
        text(d, "KENDİNDEN", LW / 2, 92, LGRAY, outline=BLACK, anchor="ma")
        text(d, "EMİN", LW / 2, 122, BLUE, "jy", 60, BLACK, anchor="mm")
    tg, _ = wt("gelmez", t0)
    pg = prog(t, tg - 0.05, 0.2)
    if pg > 0:
        s = 72 if pg >= 1 else 100
        text(d, "≠", LW / 2, 158, RED, "ps", 32 if pg >= 1 else 40, BLACK, anchor="mm")
    td, _ = wt("doğru", t0)
    if t >= td:
        text(d, "HER ZAMAN", LW / 2, 182, LGRAY, outline=BLACK, anchor="ma")
        text(d, "DOĞRU", LW / 2, 228, GREEN, "jy", 60, BLACK, anchor="mm")
    po = prog(t, 45.9, 0.15)
    if po > 0:
        box(img, 24, 256, 192, 292, WHITE, BLACK)
        sprite(img, FLOPPY, 32, 268)
        text(d, "KAYDET?", 50, 264, WHITE)
        if int(t * 4) % 2 == 0:
            tri_right(d, 50, 277, WHITE)
        text(d, "EVET  HAYIR", 58, 277, YELLOW)


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6]


# ---------------------------------------------------------------- altyazı
def caption_groups():
    groups, cur = [], []
    for i, x in enumerate(WORDS):
        if cur and (x["seg"] != WORDS[cur[0]]["seg"] or len(cur) >= 3 or
                    sum(len(WORDS[j]["w"]) + 1 for j in cur) + len(x["w"]) > 22):
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
        s = WORDS[g[0]]["s"] - 0.05
        e = WORDS[g[-1]]["e"]
        nxt = WORDS[groups[gi + 1][0]]["s"] - 0.05 if gi + 1 < len(groups) else e + 0.4
        cut = min(b for b in S_BOUNDS if b > e)
        out.append((s, min(nxt, e + 0.3, cut), g))
    return out


CAPS = caption_groups()
CAP_HIDE = (WORDS[PROMPT_IDX[0]]["s"] - 0.1, WORDS[PROMPT_IDX[-1]]["e"] + 0.3)
CAP_Y = 296


def captions(img, t):
    if CAP_HIDE[0] <= t < CAP_HIDE[1]:
        return
    d = draw(img)
    for s, e, g in CAPS:
        if not (s <= t < e):
            continue
        words = [tr_upper(WORDS[i]["w"]) for i in g]
        total = sum(len(w) for w in words) + len(words) - 1
        x = LW / 2 - total * 4
        for k, w in enumerate(words):
            ws, we = WORDS[g[k]]["s"], WORDS[g[k]]["e"]
            col = YELLOW if ws <= t < we + 0.05 else (WHITE if t >= ws - 0.02 else LGRAY)
            dy = -2 if ws <= t < ws + 0.08 else 0
            text(d, w, x, CAP_Y + dy, col, outline=BLACK)
            x += (len(w) + 1) * 8


# ---------------------------------------------------------------- kompozisyon
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16
BAYER_FULL = np.tile(BAYER, (LH // 4, LW // 4))[..., None]
SHAKES = [(4.45, 4, 8), (31.0, 6, 5), (33.2, 3, 8), (45.25, 4, 6)]


def frame_lr(t):
    img = Image.new("RGB", (LW, LH), BLACK)
    background(img, t)
    SCENES[scene_index(t)](img, t)
    hud(img, t)
    captions(img, t)
    return img


def render_frame(fi):
    t = fi / FPS
    i = scene_index(t)
    arr = np.asarray(frame_lr(t), np.float32)
    b = S_BOUNDS[i]
    # geçişler: dither çözülme (5.55, 25.45), kutu silme (11.35, 39.4)
    if b in (5.55, 25.45) and t - b < 0.3:
        old = np.asarray(frame_lr(b - 1e-3), np.float32)
        p = (t - b) / 0.3
        arr = np.where(BAYER_FULL < p, arr, old)
    if b in (11.35, 39.4) and t - b < 0.3:
        old = np.asarray(frame_lr(b - 1e-3), np.float32)
        p = e_out((t - b) / 0.3)
        hw, hh = int(LW / 2 * p), int(LH / 2 * p)
        mixed = old.copy()
        mixed[LH // 2 - hh:LH // 2 + hh, LW // 2 - hw:LW // 2 + hw] = arr[LH // 2 - hh:LH // 2 + hh,
                                                                         LW // 2 - hw:LW // 2 + hw]
        arr = mixed
    # kırmızı flaş (boss)
    if 31.0 <= t < 31.3 and int(t * 20) % 2 == 0:
        arr = arr * 0.5 + np.array(RED, np.float32) * 0.5
    # sarsıntı (tam piksel)
    dx = dy = 0
    for t0, amp, k in SHAKES:
        if t >= t0:
            a = amp * math.exp(-(t - t0) * k)
            if a > 0.5:
                dx += int(round(a * math.sin(t * 90 + t0)))
                dy += int(round(a * math.cos(t * 70 + t0)))
    if dx or dy:
        arr = np.roll(arr, (dy, dx), axis=(0, 1))
    # ilerleme çubuğu (en alt satırlar değil; üstte)
    arr[0:2, :int(LW * t / DUR)] = np.array(YELLOW, np.float32)
    if t > DUR - 0.3:
        arr = arr * clamp((DUR - t) / 0.3)
    big = np.repeat(np.repeat(arr.astype(np.uint8), K, axis=0), K, axis=1)
    return big.tobytes()


def init_events():
    to, _ = wt("özellikle", 31)
    COINS.extend([(wt("yöntem", 8)[0], 500)] + [(wt(c, to)[0], 100) for c in ("güvenilir", "kaynaklardan", "kontrol")])


init_events()


def main():
    from sound_pixel import build_mix_pixel
    os.makedirs("out", exist_ok=True)
    mix_path = build_mix_pixel(AUDIO, DUR, WORDS, "out/mix_pixel.wav")
    if "--preview" in sys.argv:
        for s in sys.argv[sys.argv.index("--preview") + 1:]:
            Image.frombytes("RGB", (W, H), render_frame(int(float(s) * FPS))).save(
                f"out/preview_pixel_{float(s):05.2f}.png")
        return
    n = int(DUR * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", mix_path,
                           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-tune", "animation",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", "-ar", "48000",
                           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                           "-shortest", OUT], stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for k, buf in enumerate(pool.imap(render_frame, range(n), chunksize=8)):
            ff.stdin.write(buf)
            if k % 300 == 0:
                print(f"{k}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("bitti:", OUT)


if __name__ == "__main__":
    main()
