"""YouTube'daki yapay zekâ ipucu Shorts'ları tarzı: ekran kaydı + otomatik zoom.

Üstte sabit kanca başlığı, ortada koyu temalı bir sohbet uygulamasının (logosuz, temsili) ekran kaydı:
dokunuş göstergesi, akarak yazılan yanıtlar, önemli yere otomatik yakınlaşma, vurgu kutuları ve
çıkartmalar; altta kalın, kelime kelime renklenen altyazı. Önce/sonra kurgusu: aynı soru, önce
kendinden emin bir yanlış, sonra önerilen cümleyle "kesin / tahmin / doğrulanmalı" diye ayrılmış yanıt.

Kullanım:  python3 render_screen.py                 -> out/elevens1_shorts_screen.mp4
           python3 render_screen.py --preview 4.5 20
"""
import math
import os
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from render import (AUDIO, PROMPT_IDX, WORDS, clamp, e_back, e_inout, e_out, emoji, paste, place, prog, set_alpha,
                    tr_upper, wt)

W, H, FPS = 1080, 1920, 30
DUR = 47.2
OUT = "out/elevens1_shorts_screen.mp4"

# çerçeve yerleşimi
VX0, VY0, VW, VH = 50, 330, 980, 1170  # ekran kaydı penceresi
S = 2                                   # ekran 2x çözünürlükte çizilir (zoom'da keskin kalsın)
SW, SH = VW, VH                         # ekranın mantıksal boyutu

# renkler
BG = (10, 10, 16)
UI_BG = (33, 33, 33)
UI_BUB = (48, 48, 48)
UI_TXT = (236, 236, 236)
UI_DIM = (155, 155, 155)
UI_LINE = (64, 64, 64)
LINK = (138, 180, 248)
YEL = (255, 225, 77)
GRN = (66, 245, 108)
RED = (255, 72, 72)
PNK = (255, 120, 180)
BLU = (90, 170, 255)

IFD = "/usr/share/fonts/opentype/inter/"
UIF = {"r": IFD + "Inter-Regular.otf", "m": IFD + "Inter-Medium.otf", "s": IFD + "Inter-SemiBold.otf",
       "b": IFD + "Inter-Bold.otf"}
MONT = "assets/fonts/Montserrat-Variable.ttf"


@lru_cache(maxsize=None)
def uif(w, size):
    return ImageFont.truetype(UIF[w], size)


@lru_cache(maxsize=None)
def mont(weight, size):
    f = ImageFont.truetype(MONT, size)
    f.set_variation_by_name(weight)
    return f


def wrap(text, f, maxw):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split(" "):
            nxt = (cur + " " + w).strip()
            if f.getlength(nxt) <= maxw or not cur:
                cur = nxt
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- ekran çizim yardımcıları (mantıksal px -> 2x)
class Scr:
    def __init__(self):
        self.im = Image.new("RGBA", (SW * S, SH * S), UI_BG + (255,))
        self.d = ImageDraw.Draw(self.im)

    def text(self, x, y, s, w, size, col, anchor="la"):
        self.d.text((x * S, y * S), s, font=uif(w, size * S), fill=col, anchor=anchor)

    def rrect(self, x0, y0, x1, y1, r, fill=None, outline=None, width=1):
        self.d.rounded_rectangle((x0 * S, y0 * S, x1 * S, y1 * S), r * S, fill=fill, outline=outline,
                                 width=width * S)

    def emoji(self, ch, x, y, size):
        e = emoji(ch, size * S)
        self.im.alpha_composite(e, (int(x * S), int(y * S)))

    def overlay(self):
        return ImageDraw.Draw(self.im, "RGBA")


def status_bar(s):
    s.text(40, 14, "9:41", "s", 24, UI_TXT)
    s.rrect(880, 18, 926, 38, 6, outline=UI_TXT, width=2)
    s.rrect(884, 22, 916, 34, 3, fill=UI_TXT)
    s.rrect(928, 24, 932, 32, 2, fill=UI_TXT)
    for k in range(4):
        s.rrect(800 + k * 12, 34 - k * 5, 808 + k * 12, 38, 2, fill=UI_TXT)


def app_header(s, title="ChatGPT"):
    for k in range(2):
        s.rrect(40, 76 + k * 14, 76, 80 + k * 14, 2, fill=UI_TXT)
    s.text(110, 84, title, "s", 32, UI_TXT, anchor="lm")
    tw = uif("s", 32).getlength(title)
    cx = 128 + tw
    s.d.line(((cx - 8) * S, 80 * S, cx * S, 88 * S, (cx + 8) * S, 80 * S), fill=UI_DIM, width=3 * S)
    s.rrect(900, 66, 936, 102, 8, outline=UI_TXT, width=3)
    s.d.line(((914) * S, 92 * S, (930) * S, 72 * S), fill=UI_TXT, width=3 * S)


COMPOSER_LH = 42


KB_TOP = 690


def keyboard(s, top, t, typing=False):
    """Türkçe Q klavye; yazarken rastgele tuşlar yanar."""
    s.d.rectangle((0, top * S, SW * S, SH * S), fill=(24, 24, 24))
    rows = ["qwertyuıopğü", "asdfghjklşi", "zxcvbnmöç"]
    kw, kh, gap = 72, 92, 8
    lit = int(t * 14) if typing else -1
    idx = 0
    for r, row in enumerate(rows):
        total = len(row) * kw + (len(row) - 1) * gap
        x = (SW - total) / 2 + (40 if r == 2 else 0)
        y = top + 20 + r * (kh + 14)
        for ch in row:
            on = typing and (idx * 7 + lit * 5) % 23 == 0
            s.rrect(x, y, x + kw, y + kh, 10, fill=(110, 110, 110) if on else (70, 70, 70))
            s.text(x + kw / 2, y + kh / 2, ch, "r", 34, UI_TXT, anchor="mm")
            x += kw + gap
            idx += 1
    y = top + 20 + 3 * (kh + 14)
    s.rrect(30, y - 106, 130, y - 14, 10, fill=(50, 50, 50))
    s.rrect(850, y - 106, 950, y - 14, 10, fill=(50, 50, 50))
    s.rrect(30, y, 200, y + kh, 10, fill=(50, 50, 50))
    s.text(115, y + kh / 2, "123", "r", 28, UI_TXT, anchor="mm")
    s.rrect(220, y, 760, y + kh, 10, fill=(70, 70, 70))
    s.text(490, y + kh / 2, "boşluk", "r", 28, UI_DIM, anchor="mm")
    s.rrect(780, y, 950, y + kh, 10, fill=(50, 50, 50))
    s.text(865, y + kh / 2, "↵", "r", 30, UI_TXT, anchor="mm")


def composer(s, text, t, focused=False, caret=True, marks=None, bottom=None):
    """Metin kutusu; yazı arttıkça yukarı büyür. Kutunun (y0, y1) değerini döndürür."""
    f = uif("r", 30)
    lines = wrap(text, f, 760) if text else []
    n = max(1, len(lines))
    h = 40 + n * COMPOSER_LH + 30
    y1 = bottom if bottom is not None else SH - 30
    y0 = y1 - h
    s.rrect(30, y0, 950, y1, 44, fill=(47, 47, 47), outline=(110, 110, 110) if focused else UI_LINE, width=2)
    s.text(70, y1 - 52, "+", "r", 40, UI_DIM, anchor="mm")
    if text:
        # vurgu işaretleri (kelime aralıkları): (karakter_baş, karakter_son, renk, alfa)
        if marks:
            ov = s.overlay()
            pos = 0
            for j, ln in enumerate(lines):
                for a, b, col, al in marks:
                    lo, hi = max(a, pos), min(b, pos + len(ln))
                    if hi > lo:
                        x0 = 100 + f.getlength(ln[:lo - pos])
                        x1 = 100 + f.getlength(ln[:hi - pos])
                        yy = y0 + 32 + j * COMPOSER_LH
                        ov.rounded_rectangle((x0 * S - 4, (yy - 2) * S, x1 * S + 4, (yy + 38) * S), 8,
                                             fill=col + (al,))
                pos += len(ln) + 1
        for j, ln in enumerate(lines):
            s.text(100, y0 + 32 + j * COMPOSER_LH, ln, "r", 30, UI_TXT)
        if caret and int(t * 2.5) % 2 == 0:
            x = 100 + f.getlength(lines[-1]) + 3
            yy = y0 + 32 + (n - 1) * COMPOSER_LH
            s.rrect(x, yy, x + 3, yy + 36, 1, fill=UI_TXT)
        # gönder butonu (beyaz)
        s.d.ellipse(((880 - 30) * S, (y1 - 82) * S, (880 + 30) * S, (y1 - 22) * S), fill=UI_TXT)
        cx, cy = 880 * S, (y1 - 52) * S
        s.d.polygon([(cx, cy - 16 * S), (cx + 13 * S, cy - 2 * S), (cx - 13 * S, cy - 2 * S)], fill=(0, 0, 0))
        s.d.rectangle((cx - 3 * S, cy - 4 * S, cx + 3 * S, cy + 15 * S), fill=(0, 0, 0))
    else:
        s.text(100, y1 - 52, "Mesaj yaz", "r", 30, UI_DIM, anchor="lm")
        s.d.ellipse(((880 - 30) * S, (y1 - 82) * S, (880 + 30) * S, (y1 - 22) * S), fill=(70, 70, 70))
        s.rrect(873, y1 - 66, 887, y1 - 44, 7, fill=UI_TXT)
        s.d.arc(((880 - 14) * S, (y1 - 62) * S, (880 + 14) * S, (y1 - 38) * S), 0, 180, fill=UI_TXT, width=3 * S)
        if focused and int(t * 2.5) % 2 == 0:
            s.rrect(100, y1 - 70, 103, y1 - 34, 1, fill=UI_TXT)
    return y0, y1


def user_bubble(s, text, y, maxw=700, size=30, lh=42):
    f = uif("r", size)
    lines = wrap(text, f, maxw - 60)
    w = max(f.getlength(ln) for ln in lines) + 60
    h = len(lines) * lh + 40
    x1 = 950
    s.rrect(x1 - w, y, x1, y + h, 34, fill=UI_BUB)
    for j, ln in enumerate(lines):
        s.text(x1 - w + 30, y + 20 + j * lh, ln, "r", size, UI_TXT)
    return y + h


def stream_blocks(s, blocks, y, nchar, t, x=40, maxw=740):
    """Asistan yanıtı: [(tür, emoji, metin)] bloklarını nchar karaktere kadar çizer.
    Her bloğun (y0, y1) aralığını ve akışın sonundaki y'yi döndürür."""
    spans = []
    left = nchar
    end_y = y
    for kind, em, text in blocks:
        if kind == "h":
            f, size, w, lh, gap = uif("b", 32), 32, "b", 46, 18
        else:
            f, size, w, lh, gap = uif("r", 31), 31, "r", 46, 26
        ex = 46 if em else 0
        lines = wrap(text, f, maxw - ex)
        y0 = y
        for j, ln in enumerate(lines):
            if left <= 0:
                break
            part = ln[:left]
            if j == 0 and em:
                s.emoji(em, x, y + 4, 34)
            s.text(x + (ex if j == 0 or kind == "h" else 0), y, part, w, size, UI_TXT)
            left -= len(ln) + 1
            end_y = y + lh
            y += lh
        if left > 0:
            y = y0 + len(lines) * lh
        spans.append((y0 - 8, y0 + len(lines) * lh))
        y += gap
        if left <= 0:
            break
    return spans, end_y


def touch(s, x, y, t, tap_t=None):
    ov = s.overlay()
    r = 26
    ov.ellipse(((x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S), fill=(255, 255, 255, 90),
               outline=(255, 255, 255, 170), width=2 * S)
    if tap_t is not None and 0 <= t - tap_t < 0.45:
        p = (t - tap_t) / 0.45
        rr = r + 50 * e_out(p)
        ov.ellipse(((x - rr) * S, (y - rr) * S, (x + rr) * S, (y + rr) * S),
                   outline=(255, 255, 255, int(200 * (1 - p))), width=3 * S)


def draw_box(s, x0, y0, x1, y1, p, col, width=5, r=18):
    """Vurgu kutusu: çevresi p oranında çizilir."""
    if p <= 0:
        return
    ov = s.overlay()
    if p >= 1:
        ov.rounded_rectangle((x0 * S, y0 * S, x1 * S, y1 * S), r * S, outline=col + (255,), width=width * S)
        return
    per = 2 * (x1 - x0) + 2 * (y1 - y0)
    L = per * p
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        seg = math.dist(a, b)
        if L >= seg:
            out.append(b)
            L -= seg
        else:
            u = L / seg
            out.append((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u))
            break
    ov.line([(q[0] * S, q[1] * S) for q in out], fill=col + (255,), width=width * S, joint="curve")


# ---------------------------------------------------------------- içerik
QUESTION = "Einstein okulda matematikten kaldı mı?"
ANSWER_A = ("Evet, kesinlikle! Einstein okulda matematikten kalmıştı. Bu, bilim tarihinin en bilinen "
            "gerçeklerinden biridir.")
A_STREAM = (0.55, 2.9)
PROMPT_TEXT = " ".join(WORDS[i]["w"] for i in PROMPT_IDX)
ANSWER_B = [
    ("h", "✅", "Kesin bildiklerim"),
    ("p", "", "Einstein matematikte çok başarılıydı; 15 yaşına gelmeden kalkülüsü öğrenmişti."),
    ("h", "🤔", "Tahminlerim"),
    ("p", "", "“Matematikten kaldı” efsanesi, İsviçre'deki not sisteminin yanlış anlaşılmasından doğmuş olabilir."),
    ("h", "⚠️", "Doğrulanması gerekenler"),
    ("p", "", "Efsanenin ilk nerede ortaya çıktığını bilmiyorum; güvenilir bir kaynaktan kontrol etmelisin."),
]
B_STREAM = (25.75, 28.3)
B_TOTAL = sum(len(t) + 1 for _, _, t in ANSWER_B)

T_SEND = 25.2
T_NEWCHAT = 11.35
T_BROWSER = 35.15
T_OUTRO = 39.4
T_Q_TYPE = (11.75, 13.35)
SEARCH_Q = "Einstein matematik notları"
RESULTS = [("📚", "Ansiklopedi", "Albert Einstein'ın eğitimi ve okul yılları", "güvenilir"),
           ("🏛️", "Üniversite arşivi", "Einstein'ın okul karneleri: notlar ne diyor?", "kaynaklardan"),
           ("🔬", "Bilim dergisi", "“Matematikten kaldı” efsanesi nereden çıktı?", "kontrol")]


def prompt_chars(t):
    """Composer'daki metin: önce soru (hızlı yazım), sonra cümle konuşmayla eşzamanlı."""
    q = QUESTION[:int(len(QUESTION) * clamp((t - T_Q_TYPE[0]) / (T_Q_TYPE[1] - T_Q_TYPE[0])))]
    ts, _ = wt("sonra", 13)
    if t < ts:
        return q, []
    out = q + "\n"
    marks = []
    groups = {0: GRN, 1: GRN, 2: GRN, 3: YEL, 5: PNK, 6: PNK, 7: PNK, 14: BLU}
    for k, i in enumerate(PROMPT_IDX):
        ws, we = WORDS[i]["s"], WORDS[i]["e"]
        if t < ws:
            break
        w = WORDS[i]["w"]
        n = max(1, int(round(len(w) * clamp((t - ws) / max(0.08, (we - ws) * 0.85)))))
        if not out.endswith("\n"):
            out += " "
        a = len(out)
        out += w[:n]
        if k in groups:
            al = int(110 * e_out(clamp((t - ws) / 0.2)))
            marks.append((a, a + n, groups[k], al))
    return out, marks


def screen_chat_a(s, t):
    status_bar(s)
    app_header(s)
    y = user_bubble(s, QUESTION, 150)
    n = int(len(ANSWER_A) * clamp((t - A_STREAM[0]) / (A_STREAM[1] - A_STREAM[0])))
    spans, end_y = stream_blocks(s, [("p", "", ANSWER_A)], y + 50, n, t)
    if A_STREAM[0] < t < A_STREAM[1]:
        s.d.ellipse((60 * S - 10, (end_y + 10) * S, 60 * S + 10, (end_y + 10) * S + 20), fill=UI_TXT)
    if t > A_STREAM[1]:
        for k in range(4):  # eylem simgeleri
            s.rrect(40 + k * 56, end_y + 18, 70 + k * 56, end_y + 48, 6, outline=UI_DIM, width=2)
    p = clamp((t - 4.36) / 0.3)
    if p > 0:
        draw_box(s, 24, spans[0][0] - 6, 806, spans[0][1] + 6, p, RED, 5)
    # dokunuş: composer'a git
    tap = 7.95
    focused = t >= tap
    if focused:  # klavye açılır
        kt = KB_TOP + (SH - KB_TOP) * (1 - e_out(clamp((t - tap) / 0.25)))
        keyboard(s, kt, t)
        composer(s, "", t, True, bottom=kt - 16)
    else:
        composer(s, "", t, False)
    if 6.9 <= t < tap + 0.6:
        p = e_inout(clamp((t - 6.9) / 0.9))
        x, y = 640 + (420 - 640) * p, 760 + (SH - 82 - 760) * p
        touch(s, x, y, t, tap)
    return spans


def screen_compose(s, t):
    status_bar(s)
    app_header(s)
    s.text(SW / 2, 330, "Bugün ne öğrenmek istersin?", "s", 40, UI_TXT, anchor="mm")
    text, marks = prompt_chars(t)
    caret = t < T_SEND
    typing = (T_Q_TYPE[0] <= t < T_Q_TYPE[1]) or any(
        WORDS[i]["s"] <= t < WORDS[i]["e"] for i in PROMPT_IDX)
    keyboard(s, KB_TOP, t, typing)
    y0, y1 = composer(s, text, t, True, caret, marks, bottom=KB_TOP - 16)
    if T_SEND - 0.55 <= t:
        p = e_inout(clamp((t - (T_SEND - 0.55)) / 0.45))
        x, y = 560 + (880 - 560) * p, (y0 - 60) + ((y1 - 52) - (y0 - 60)) * p
        touch(s, x, y, t, T_SEND)
    if t < T_Q_TYPE[0] + 0.3 and t > T_NEWCHAT + 0.1:
        touch(s, 420, SH - 82, t, T_NEWCHAT + 0.15)
    return y0, y1


def chat_b_layout(s, t, scroll=0.0, overlays=True):
    status_bar(s)
    app_header(s)
    s.d.rectangle((0, 124 * S, SW * S, SH * S), fill=UI_BG)
    top = 150 - scroll
    y = user_bubble(s, QUESTION + "\n" + PROMPT_TEXT, top, 760, 26, 36)
    n = int(B_TOTAL * clamp((t - B_STREAM[0]) / (B_STREAM[1] - B_STREAM[0])))
    spans, end_y = stream_blocks(s, ANSWER_B, y + 44, n, t)
    if B_STREAM[0] < t < B_STREAM[1]:
        s.d.ellipse((60 * S - 10, (end_y + 10) * S, 60 * S + 10, (end_y + 10) * S + 20), fill=UI_TXT)
    if overlays:
        te, _ = wt("emin", 25.4)
        for k, col in ((1, YEL), (2, RED)):
            if len(spans) >= 2 * k + 2:
                a, b = spans[2 * k][0], spans[2 * k + 1][1]
                draw_box(s, 24, a - 4, 806, b + 4, clamp((t - te - (k - 1) * 0.35) / 0.35), col, 5)
    status_bar_cover(s)
    composer(s, "", t, False)
    return spans, end_y


def status_bar_cover(s):
    s.d.rectangle((0, 0, SW * S, 124 * S), fill=UI_BG)
    status_bar(s)
    app_header(s)


def b_scroll(t):
    """Yanıt akarken otomatik kaydırma (mantıksal px)."""
    return 330 * e_inout(clamp((t - B_STREAM[0] - 0.4) / 2.2))


def screen_chat_b(s, t):
    return chat_b_layout(s, t, b_scroll(t))


def screen_browser(s, t):
    status_bar(s)
    s.rrect(30, 60, 950, 130, 35, fill=(47, 47, 47))
    s.emoji("🔍", 55, 75, 38)
    q = SEARCH_Q[:int(len(SEARCH_Q) * clamp((t - (T_BROWSER + 0.3)) / 0.8))]
    s.text(110, 95, q, "r", 32, UI_TXT, anchor="lm")
    if t < T_BROWSER + 1.2 and int(t * 2.5) % 2 == 0:
        x = 110 + uif("r", 32).getlength(q) + 3
        s.rrect(x, 78, x + 3, 112, 1, fill=UI_TXT)
    oz, _ = wt("özellikle", 31)
    for k, (em, src, title, cue) in enumerate(RESULTS):
        ta = T_BROWSER + 1.25 + k * 0.15
        if t < ta:
            continue
        y = 180 + k * 300
        s.rrect(30, y, 950, y + 270, 24, fill=(40, 40, 40), outline=UI_LINE, width=2)
        s.emoji(em, 60, y + 30, 44)
        s.text(122, y + 52, src, "s", 28, UI_DIM, anchor="lm")
        f = uif("m", 34)
        for j, ln in enumerate(wrap(title, f, 840)[:2]):
            s.text(60, y + 105 + j * 46, ln, "m", 34, LINK)
        s.rrect(60, y + 210, 600, y + 222, 6, fill=(70, 70, 70))
        s.rrect(60, y + 236, 480, y + 248, 6, fill=(70, 70, 70))
        tc_, _ = wt(cue, oz)
        p = clamp((t - tc_) / 0.25)
        if p > 0:
            ov = s.overlay()
            sc = 0.6 + 0.4 * e_back(p)
            cx, cy = 820, y + 52
            w, h = 220 * sc, 52 * sc
            ov.rounded_rectangle(((cx - w / 2) * S, (cy - h / 2) * S, (cx + w / 2) * S, (cy + h / 2) * S), int(26 * S),
                                 fill=(30, 120, 60, 255))
            s.d.text((cx * S, cy * S), "✓ Güvenilir", font=uif("b", int(26 * sc) * S), fill=(220, 255, 225),
                     anchor="mm")
            draw_box(s, 22, y - 8, 958, y + 278, clamp((t - tc_) / 0.3), GRN, 4, 28)


# ---------------------------------------------------------------- kamera (ekranın mantıksal koordinatlarında)
def lerp_cam(a, b, p):
    return (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p,
            math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * p))


FULL = (SW / 2, SH / 2, 1.0)


def camera(t):
    """(merkez x, merkez y, zoom) + o anki ekran fonksiyonu."""
    if t < T_NEWCHAT:
        keys = [(0.0, FULL), (0.45, FULL), (1.0, (423, 330, 1.2)), (4.36, (423, 330, 1.2)),
                (4.5, (423, 320, 1.27)), (5.45, (423, 320, 1.27)), (6.0, FULL), (7.95, FULL),
                (8.4, (490, 640, 1.12)), (11.4, (490, 640, 1.12))]
    elif t < T_SEND + 0.25:
        y0, y1 = composer_extent(t)
        z = clamp(0.62 * SH / (y1 - y0 + 120), 1.0, 1.2)
        cy = (y0 + y1) / 2 + 0.16 * SH / z
        target = (490, cy, z)
        keys = [(T_NEWCHAT, FULL), (T_NEWCHAT + 0.35, FULL), (T_Q_TYPE[0] + 0.15, target), (99, target)]
        if t >= T_SEND - 0.6:
            keys = [(T_SEND - 0.6, target), (99, target)]
    elif t < T_BROWSER:
        te, _ = wt("emin", 25.4)
        follow = (420, 520, 1.22)
        keys = [(T_SEND + 0.25, FULL), (B_STREAM[0] + 0.2, FULL), (B_STREAM[0] + 0.8, follow), (te - 0.3, follow),
                (te + 0.3, (490, 640, 1.08)), (30.9, (490, 640, 1.08)), (31.0, (490, 640, 1.25)),
                (31.4, (490, 640, 1.12)), (99, (490, 640, 1.12))]
    elif t < T_OUTRO:
        oz, _ = wt("özellikle", 31)
        cues = [wt(c, oz)[0] for *_, c in RESULTS]
        zb = 1.1
        keys = [(T_BROWSER, (490, 340, zb)), (T_BROWSER + 1.2, (490, 340, zb)), (T_BROWSER + 1.6, (490, 560, 1.0)),
                (cues[0], (490, 400, zb)), (cues[1] - 0.2, (490, 400, zb)), (cues[1], (490, 640, zb)),
                (cues[2] - 0.2, (490, 640, zb)), (cues[2], (490, 860, zb)), (99, (490, 860, zb))]
    else:
        keys = [(T_OUTRO, (490, 640, 1.12)), (T_OUTRO + 0.8, FULL), (99, FULL)]
    for (t0, a), (t1, b) in zip(keys, keys[1:]):
        if t0 <= t < t1:
            return lerp_cam(a, b, e_inout(clamp((t - t0) / max(1e-3, t1 - t0))))
    return keys[-1][1]


@lru_cache(maxsize=64)
def _composer_extent_cached(tq):
    s = Scr()
    return composer(s, prompt_chars(tq / 100)[0], tq / 100, True, False, bottom=KB_TOP - 16)


def composer_extent(t):
    return _composer_extent_cached(int(t * 100))


def render_screen(t):
    s = Scr()
    if t < T_NEWCHAT:
        screen_chat_a(s, t)
    elif t < T_SEND + 0.25:
        screen_compose(s, t)
    elif t < T_BROWSER:
        screen_chat_b(s, t)
    elif t < T_OUTRO:
        screen_browser(s, t)
    else:
        chat_b_layout(s, B_STREAM[1] + 1, b_scroll(B_STREAM[1] + 1), True)
    return s.im


@lru_cache(maxsize=1)
def viewport_mask():
    m = Image.new("L", (VW, VH), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, VW - 1, VH - 1), 44, fill=255)
    return m


def viewport(t):
    scr = render_screen(t)
    cx, cy, z = camera(t)
    vw, vh = SW / z, SH / z
    cx = clamp(cx, vw / 2, SW - vw / 2)
    cy = clamp(cy, vh / 2, SH - vh / 2)
    box = ((cx - vw / 2) * S, (cy - vh / 2) * S, (cx + vw / 2) * S, (cy + vh / 2) * S)
    v = scr.resize((VW, VH), Image.BICUBIC, box=box)
    v.putalpha(viewport_mask())
    return v


# ---------------------------------------------------------------- çerçeve öğeleri
@lru_cache(maxsize=1)
def frame_bg():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = np.exp(-(((xx - 200) / 700) ** 2 + ((yy - 300) / 600) ** 2))[..., None] * np.array((60, 40, 140))
    g += np.exp(-(((xx - 950) / 600) ** 2 + ((yy - 1700) / 700) ** 2))[..., None] * np.array((20, 70, 140))
    arr = np.clip(np.array(BG, np.float32) + g * 0.55, 0, 255).astype(np.uint8)
    im = Image.fromarray(arr).convert("RGBA")
    d = ImageDraw.Draw(im)
    for x in range(0, W, 60):
        d.line((x, 0, x, H), fill=(255, 255, 255, 6))
    for y in range(0, H, 60):
        d.line((0, y, W, y), fill=(255, 255, 255, 6))
    # pencere gölgesi + kenarlık
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((VX0 - 6, VY0 + 4, VX0 + VW + 6, VY0 + VH + 20), 50, fill=(0, 0, 0, 200))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(24)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle((VX0 - 3, VY0 - 3, VX0 + VW + 3, VY0 + VH + 3), 47,
                                           outline=(140, 110, 255, 160), width=4)
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6)))
    return im


@lru_cache(maxsize=1)
def title_sprite():
    im = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f1, f2 = mont("ExtraBold", 58), mont("Black", 70)
    d.text((W / 2, 62), "ChatGPT'nin uydurmasını", font=f1, fill=(255, 255, 255), anchor="mm",
           stroke_width=3, stroke_fill=(0, 0, 0))
    part1, part2 = "AZALTAN ", "TEK CÜMLE"
    w1, w2 = f2.getlength(part1), f2.getlength(part2)
    x = W / 2 - (w1 + w2 + 70) / 2
    d.text((x, 150), part1, font=f2, fill=(255, 255, 255), anchor="lm", stroke_width=3, stroke_fill=(0, 0, 0))
    d.rounded_rectangle((x + w1 - 10, 108, x + w1 + w2 + 12, 194), 14, fill=YEL)
    d.text((x + w1, 150), part2, font=f2, fill=(10, 10, 10), anchor="lm")
    im.alpha_composite(emoji("👇", 64), (int(x + w1 + w2 + 22), 118))
    return im


@lru_cache(maxsize=64)
def sticker(text, em, bg, fg, size=46, pad=26):
    f = mont("Black", size)
    tw = f.getlength(text)
    ew = int(size * 1.15) + 14 if em else 0
    h = int(size * 1.6)
    im = Image.new("RGBA", (int(tw + ew + 2 * pad) + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 14, im.width - 10, h + 14), h // 3, fill=(0, 0, 0, 120))
    d.rounded_rectangle((10, 8, im.width - 10, h + 8), h // 3, fill=bg + (255,))
    if em:
        e = emoji(em, int(size * 1.15))
        im.alpha_composite(e, (10 + pad, 8 + (h - e.height) // 2))
    d.text((10 + pad + ew, 8 + h / 2), text, font=f, fill=fg, anchor="lm")
    return im


def pop(c, im, x, y, t, t0, rot=0.0, t1=None, wobble=True):
    if t < t0 or (t1 is not None and t >= t1 + 0.15):
        return
    p = clamp((t - t0) / 0.28)
    a = 1.0
    if t1 is not None and t >= t1:
        a = 1 - (t - t1) / 0.15
    sc = 0.4 + 0.6 * e_back(p, 2.6)
    if wobble:
        sc *= 1 + 0.02 * math.sin((t - t0) * 6)
    place(c, im, x, y, sc, min(1, p * 3) * a, rot)


def stickers(c, t):
    pop(c, sticker("YANLIŞ!", "❌", RED, (255, 255, 255), 60), 760, 560, t, 4.45, 7, 5.9)
    pop(c, sticker("Gerçek: Matematikte çok başarılıydı", "✅", (24, 150, 70), (255, 255, 255), 34), 540, 1080, t,
        4.85, -2, 5.9)
    s_f, _ = wt("sana")
    pop(c, sticker("BASİT", "💡", YEL, (10, 10, 10), 54), 300, 620, t, wt("basit", s_f)[0], -7, T_NEWCHAT - 0.1)
    pop(c, sticker("ETKİLİ", "🔥", (255, 110, 40), (255, 255, 255), 54), 780, 700, t, wt("etkili", s_f)[0], 6,
        T_NEWCHAT - 0.1)
    pop(c, sticker("TEK CÜMLE", "👇", (255, 255, 255), (10, 10, 10), 66), 540, 860, t, wt("yöntem", s_f)[0] - 0.05,
        0, T_NEWCHAT - 0.1)
    te, _ = wt("emin", 22)
    pop(c, sticker("KAYDET!", "📌", (255, 255, 255), (10, 10, 10), 46), 830, 470, t, te, 8, T_SEND)
    te2, _ = wt("emin", 25.4)
    pop(c, sticker("Emin olmadığı yerler", "👀", YEL, (10, 10, 10), 40), 540, 1120, t, te2 + 0.4, -3, 30.95)
    pop(c, sticker("AMA DİKKAT!", "⚠️", RED, (255, 255, 255), 72), 540, 760, t, 31.0, -4, wt("bu", 31.5)[0] - 0.1)
    ty, _ = wt("yanlışları", 31)
    tk, _ = wt("kaldırmaz", 31)
    pop(c, sticker("Hatalar AZALIR", "📉", (255, 255, 255), (10, 10, 10), 56), 540, 720, t, ty, -3, T_BROWSER - 0.1)
    pop(c, sticker("ama SIFIRLANMAZ", "❗", RED, (255, 255, 255), 56), 540, 860, t, tk, 3, T_BROWSER - 0.1)
    pop(c, sticker("Kaynağı kontrol et", "🔍", (255, 255, 255), (10, 10, 10), 48), 540, 1130, t, T_BROWSER + 0.15,
        -2, T_OUTRO - 0.1)


def scrim_alpha(t):
    """Ekranı karartma (çıkartmalar öne çıksın)."""
    a = 0.0
    tb, _ = wt("bu", 31.5)
    a = max(a, 0.55 * clamp((t - (tb - 0.1)) / 0.3) * (1 - clamp((t - (T_BROWSER - 0.1)) / 0.1)))
    a = max(a, 0.7 * clamp((t - T_OUTRO - 0.4) / 0.5))
    return a


def outro(c, t):
    if t < T_OUTRO:
        return
    tu, _ = wt("unutma")
    tk, _ = wt("kendinden", 40)
    td, _ = wt("doğru", 43)
    tg, _ = wt("gelmez", 44)
    pop(c, sticker("UNUTMA", "🧠", YEL, (10, 10, 10), 52), 540, 470, t, tu + 0.1, -3, wobble=False)
    for txt_, col, y, t0, size in (("KENDİNDEN EMİN", (255, 255, 255), 640, tk, 92), ("HER ZAMAN DOĞRU", GRN, 960, td, 88)):
        p = clamp((t - t0) / 0.25)
        if p > 0:
            im = Image.new("RGBA", (W, 160), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((W / 2, 80), txt_, font=mont("Black", size), fill=col, anchor="mm",
                                    stroke_width=8, stroke_fill=(0, 0, 0))
            place(c, im, 540, y, 0.6 + 0.4 * e_back(p, 2.2), min(1, p * 3))
    p = clamp((t - tg + 0.05) / 0.25)
    if p > 0:
        im = Image.new("RGBA", (300, 260), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((150, 130), "≠", font=mont("Black", 220), fill=RED, anchor="mm", stroke_width=8,
                                stroke_fill=(0, 0, 0))
        place(c, im, 540, 800, 1.6 - 0.6 * e_out(p), min(1, p * 3), -6 * (1 - p))
    if t >= 45.9:
        pop(c, sticker("Kaydet", "📌", (255, 255, 255), (10, 10, 10), 46), 330, 1220, t, 45.9, -3, wobble=False)
        pop(c, sticker("Takip et", "🔔", (255, 60, 60), (255, 255, 255), 46), 760, 1220, t, 46.05, 3, wobble=False)


# ---------------------------------------------------------------- altyazı (kalın, kontürlü, kelime vurgulu)
EMOJI_FOR = {"yanlış": "❌", "şüphe": "🤔", "basit": "💡", "etkili": "🔥", "dikkat!": "⚠️", "kaynaklardan": "📚",
             "unutma,": "🧠", "gelmez.": "🚫", "ekle:": "👇", "kaldırmaz.": "❗"}


def caption_groups():
    groups, cur = [], []
    for i, x in enumerate(WORDS):
        if cur and (x["seg"] != WORDS[cur[0]]["seg"] or len(cur) >= 3 or
                    sum(len(WORDS[j]["w"]) for j in cur) + len(x["w"]) > 15):
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
        s = WORDS[g[0]]["s"] - 0.04
        e = WORDS[g[-1]]["e"]
        nxt = WORDS[groups[gi + 1][0]]["s"] - 0.04 if gi + 1 < len(groups) else e + 0.3
        out.append((s, min(nxt, e + 0.25), g))
    return out


CAPS = caption_groups()
CAP_HIDE = (WORDS[PROMPT_IDX[0]]["s"] - 0.1, WORDS[PROMPT_IDX[-1]]["e"] + 0.3)
CAP_Y, CAP_SIZE = 1330, 80


def captions(c, t):
    if CAP_HIDE[0] <= t < CAP_HIDE[1] or t >= T_OUTRO + 0.6 and t < 39.5:
        return
    for s, e, g in CAPS:
        if not (s <= t < e):
            continue
        f = mont("Black", CAP_SIZE)
        words = [tr_upper(WORDS[i]["w"]) for i in g]
        sp = f.getlength(" ")
        widths = [f.getlength(w) for w in words]
        x = W / 2 - (sum(widths) + sp * (len(words) - 1)) / 2
        pg = clamp((t - s) / 0.1)
        for k, w in enumerate(words):
            i = g[k]
            ws, we = WORDS[i]["s"], WORDS[i]["e"]
            active = ws <= t < we + 0.04
            col = GRN if active else (255, 255, 255)
            im = Image.new("RGBA", (int(widths[k]) + 40, CAP_SIZE + 60), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((20, 30), w, font=f, fill=col, stroke_width=9, stroke_fill=(0, 0, 0))
            sc = (1.14 - 0.14 * e_out(clamp((t - ws) / 0.12))) if active else 1.0
            place(c, im, x + widths[k] / 2, CAP_Y, sc * (0.85 + 0.15 * pg), pg)
            em = EMOJI_FOR.get(WORDS[i]["w"].lower())
            if em and t >= ws:
                pe = clamp((t - ws) / 0.25)
                place(c, emoji(em, 96), x + widths[k] / 2, CAP_Y - 115, 0.4 + 0.6 * e_back(pe, 2.5), pe,
                      -10 + 20 * ((i * 7) % 3) / 2)
            x += widths[k] + sp


# ---------------------------------------------------------------- kompozisyon
CUTS = [T_NEWCHAT, T_SEND + 0.25, T_BROWSER, T_OUTRO]
SHAKES = [(4.45, 14, 8), (31.0, 22, 6), (45.2, 12, 7)]


def render_frame(fi):
    t = fi / FPS
    c = frame_bg().copy()
    c.alpha_composite(title_sprite(), (0, 70))
    v = viewport(t)
    a = scrim_alpha(t)
    if a > 0:
        dark = Image.new("RGBA", v.size, (0, 0, 0, int(255 * a)))
        dark.putalpha(Image.fromarray((np.asarray(viewport_mask(), np.float32) * a).astype(np.uint8)))
        v.alpha_composite(dark)
    # kesmelerde küçük zıplama (punch)
    bump = 0.0
    for tc_ in CUTS:
        if 0 <= t - tc_ < 0.22:
            bump = max(bump, 0.06 * (1 - (t - tc_) / 0.22))
    dx = dy = 0.0
    for t0, amp, k in SHAKES:
        if t >= t0:
            q = amp * math.exp(-(t - t0) * k)
            if q > 0.4:
                dx += q * math.sin(t * 87 + t0)
                dy += q * math.cos(t * 69 + t0)
    place(c, v, VX0 + VW / 2 + dx, VY0 + VH / 2 + dy, 1 + bump)
    if 31.0 <= t < 31.35:  # kırmızı uyarı kenarı
        al = int(160 * (1 - (t - 31.0) / 0.35))
        red = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(red).rectangle((0, 0, W - 1, H - 1), outline=RED + (al,), width=40)
        c.alpha_composite(red.filter(ImageFilter.GaussianBlur(20)))
    stickers(c, t)
    outro(c, t)
    captions(c, t)
    d = ImageDraw.Draw(c)
    d.rectangle((0, 0, int(W * t / DUR), 8), fill=GRN + (255,))
    arr = np.asarray(c.convert("RGB"), np.float32)
    for tc_ in CUTS:  # kesmede kısa beyaz parlama
        if 0 <= t - tc_ < 0.07:
            arr = arr * 0.75 + 255 * 0.25
    if t > DUR - 0.3:
        arr *= clamp((DUR - t) / 0.3)
    return np.clip(arr, 0, 255).astype(np.uint8).tobytes()


def main():
    from sound_screen import build_mix_screen
    os.makedirs("out", exist_ok=True)
    mix_path = build_mix_screen(AUDIO, DUR, WORDS, "out/mix_screen.wav")
    if "--preview" in sys.argv:
        for s in sys.argv[sys.argv.index("--preview") + 1:]:
            Image.frombytes("RGB", (W, H), render_frame(int(float(s) * FPS))).save(
                f"out/preview_screen_{float(s):05.2f}.png")
        return
    n = int(DUR * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", mix_path,
                           "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-maxrate", "12M", "-bufsize", "24M",
                           "-pix_fmt", "yuv420p", "-profile:v", "high", "-ar", "48000",
                           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                           "-shortest", OUT], stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for k, buf in enumerate(pool.imap(render_frame, range(n), chunksize=4)):
            ff.stdin.write(buf)
            if k % 300 == 0:
                print(f"{k}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("bitti:", OUT)


if __name__ == "__main__":
    main()
