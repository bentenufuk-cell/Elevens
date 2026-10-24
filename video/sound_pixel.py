"""8-bit oyun teması sesi: chiptune (kare dalga melodi, üçgen bas) + kısa tonal oyun efektleri.

Uzun gürültü efekti yok; tüm efektler kısa ve tonal. Diyalog "bip"leri harf başına değil kelime başınadır.
Seviyeler sound.finish içinde konuşmaya göre ölçülerek ayarlanır.
"""
import numpy as np

from sound import SR, add, env, fade_edges, finish, onepole_lp, prep_voice, rng, word_finder

BPM = 128
STEP = 60 / BPM / 2  # 8'lik


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def square(f, d, duty=0.25, decay=None):
    n = int(d * SR)
    t = np.arange(n) / SR
    ph = (f * t) % 1.0
    x = np.where(ph < duty, 1.0, -1.0)
    x = onepole_lp(x.astype(np.float32), 0.35)  # sert kenarları biraz yumuşat
    e = env(n, 0.003, decay if decay else d / 2)
    rel = np.minimum(1, (n - np.arange(n)) / (0.01 * SR))
    return x * e * rel


def triangle(f, d):
    n = int(d * SR)
    t = np.arange(n) / SR
    x = 2 * np.abs(2 * ((f * t) % 1.0) - 1) - 1
    return x * env(n, 0.003, d / 1.5) * np.minimum(1, (n - np.arange(n)) / (0.01 * SR))


def hat():
    n = int(0.02 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    return (x - onepole_lp(x, 0.5)) * env(n, 0.0005, 0.005)


# Am - F - C - G döngüsü; melodi 8'likler (None = sus)
CHORDS = [(57, 60, 64), (53, 57, 60), (48, 55, 64), (55, 59, 62)]
MELODY = [
    [76, None, 72, 74, 76, None, 79, 76],
    [77, None, 76, 74, 72, None, 69, None],
    [72, None, 74, 76, 79, None, 76, 74],
    [74, None, 71, 72, 74, None, None, None],
]
BOSS_MEL = [69, 72, 75, 72, 69, 72, 75, 78]


def music(n, sections):
    """sections: [(başlangıç, bitiş, mod)] mod: 'main' | 'boss' | 'rest'"""
    out = np.zeros(n, np.float32)
    k = 0
    while k * STEP * SR < n:
        t0 = k * STEP
        mode = "main"
        for a, b, m in sections:
            if a <= t0 < b:
                mode = m
        bar = (k // 8) % 4
        s = k % 8
        if mode == "rest":
            k += 1
            continue
        root = CHORDS[bar][0] - 12
        if mode == "boss":
            if s % 2 == 0:
                add(out, triangle(midi(45 if bar % 2 == 0 else 46), STEP * 1.8), t0, 0.9)
            add(out, square(midi(BOSS_MEL[s]), STEP * 0.9, 0.5, 0.06), t0, 0.22)
        else:
            if s in (0, 3, 4, 6):
                add(out, triangle(midi(root if s != 6 else root + 7), STEP * 1.6), t0, 0.9)
            note = MELODY[bar][s]
            if note:
                add(out, square(midi(note), STEP * 1.6, 0.25, 0.12), t0, 0.25)
            # arpej (yumuşak)
            add(out, square(midi(CHORDS[bar][s % 3] + 12), STEP * 0.8, 0.125, 0.04), t0, 0.08)
        if s % 2 == 1:
            add(out, hat(), t0, 0.25)
        k += 1
    return out


def blip(f=880):
    return square(f, 0.035, 0.5, 0.015)


def jingle(notes, step=0.07, duty=0.5, last=0.3):
    out = np.zeros(int((len(notes) * step + last) * SR), np.float32)
    for j, m in enumerate(notes):
        d = last if j == len(notes) - 1 else step * 1.2
        add(out, square(midi(m), d, duty, d / 2), j * step, 1.0)
    return out


def hurt():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = np.geomspace(600, 120, n)
    ph = np.cumsum(f) / SR % 1.0
    return np.where(ph < 0.5, 1.0, -1.0) * env(n, 0.002, 0.12)


def hit():
    n = int(0.12 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = onepole_lp(x, 0.3) * env(n, 0.001, 0.03)
    return x + square(110, 0.12, 0.5, 0.04) * 0.6


def siren(d=1.0):
    out = np.zeros(int(d * SR), np.float32)
    for j in range(int(d / 0.25)):
        add(out, square(midi(81 if j % 2 == 0 else 76), 0.24, 0.5, 0.2), j * 0.25, 0.7)
    return out


def build_mix_pixel(audio, dur, words, out_path):
    v, duck = prep_voice(audio, dur, depth=0.6)
    n = len(v)
    wt = word_finder(words)
    to = wt("özellikle", 31)

    m = music(n, [(0.0, 0.25, "rest"), (31.0, 32.0, "rest"), (32.0, to - 0.2, "boss"), (45.8, 99, "rest")])
    m = fade_edges(m, 0.2, 0.2) * duck
    add(m, jingle([72, 76, 79, 84, 79, 84], 0.09, 0.5, 0.6), 45.85, 1.2)  # zafer

    fx = np.zeros(n, np.float32)
    add(fx, jingle([60, 67, 72], 0.06, 0.5, 0.15), 0.0, 0.6)
    # diyalog bipleri: kelime başına
    for text_, t0, cps in (("Japon balığının hafızası ne kadar?", 0.2, 30),
                           ("Kesinlikle 3 saniye! Bundan çok eminim.", 1.35, 26)):
        pos = 0
        for w in text_.split():
            add(fx, blip(880 if t0 < 1 else 660), t0 + pos / cps, 0.35)
            pos += len(w) + 1
    add(fx, jingle([72, 76, 79, 83], 0.05, 0.5, 0.12), 2.75, 0.5)  # güven barı
    add(fx, hurt(), 4.45, 1.0)
    add(fx, blip(1320), 4.85, 0.4)
    # geçişler
    for tb in (5.55, 11.35, 25.45, 39.4):
        add(fx, jingle([67, 72], 0.05, 0.5, 0.08), tb - 0.05, 0.4)
    sana = wt("sana")
    add(fx, square(midi(60), 0.08, 0.5, 0.05), sana - 0.05, 0.6)  # bloğa vuruş
    add(fx, jingle([60, 64, 67, 72, 76, 79, 84], 0.05, 0.25, 0.25), sana + 0.15, 0.6)  # sandık
    add(fx, jingle([79, 84], 0.06, 0.5, 0.15), wt("basit", sana), 0.45)
    add(fx, jingle([81, 86], 0.06, 0.5, 0.15), wt("etkili", sana), 0.45)
    add(fx, jingle([72, 76, 79, 84, 88], 0.06, 0.25, 0.3), wt("yöntem", sana) - 0.1, 0.6)
    # parşömen yazımı: kelime başına çok kısık bip
    for x in words:
        if 5 <= x["seg"] <= 8:
            add(fx, blip(1046), x["s"], 0.12)
    # envanter
    for k in range(3):
        add(fx, jingle([76 + k * 2, 83 + k * 2], 0.05, 0.5, 0.1), 25.8 + k * 0.6, 0.4)
    te = wt("emin", 25.4)
    add(fx, blip(1320), te, 0.4)
    add(fx, blip(1320), te + 1.0, 0.4)
    # boss
    add(fx, siren(1.2), 31.0, 0.8)
    add(fx, hit(), wt("yanlışları", 31), 1.0)
    add(fx, jingle([60, 59, 58, 57], 0.09, 0.5, 0.3), wt("kaldırmaz", 31), 0.6)
    add(fx, jingle([72, 79], 0.06, 0.5, 0.15), to - 0.15, 0.5)
    for cue in ("güvenilir", "kaynaklardan", "kontrol"):
        add(fx, jingle([83, 88], 0.06, 0.5, 0.2), wt(cue, to), 0.5)  # para
    add(fx, jingle([67, 72, 76], 0.07, 0.5, 0.2), wt("kontrol", to) + 0.4, 0.5)
    # final
    add(fx, blip(988), wt("unutma"), 0.5)
    add(fx, hit(), wt("gelmez", 40) - 0.05, 0.9)
    return finish(v, m, fx, out_path, dur, 30)[0]
