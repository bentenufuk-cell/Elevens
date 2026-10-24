"""Kara film teması sesi: yürüyen kontrbas + caz piyano akorları + hafif ride; daktilo, damga, lamba efektleri.

Gürültü tabanlı uzun efekt yok (hışırtı/whoosh kullanılmaz); efektler kısa ve tok tutulur.
Seviyeler sound.finish içinde konuşmaya göre ölçülerek ayarlanır.
"""
import numpy as np

from sound import SR, add, env, fade_edges, finish, onepole_lp, prep_voice, rng, thud, word_finder

BPM = 92
BEAT = 60 / BPM

# Re minör caz döngüsü: Dm7 | Gm7 | Em7b5 | A7
CHORDS = [
    ([146.83, 174.61, 220.0, 261.63], [73.42, 87.31, 110.0, 103.83]),   # Dm7  + bas yürüyüşü
    ([196.0, 233.08, 293.66, 349.23], [98.0, 116.54, 146.83, 138.59]),  # Gm7
    ([164.81, 196.0, 233.08, 293.66], [82.41, 98.0, 116.54, 103.83]),   # Em7b5
    ([138.59, 196.0, 220.0, 277.18], [110.0, 138.59, 164.81, 77.78]),   # A7
]


def upright(f, d=0.55):
    n = int(d * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 9) \
        + 0.2 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 14)
    return onepole_lp((x * env(n, 0.006, d / 3.5)).astype(np.float32), 0.18)


def piano(freqs, d=1.6):
    n = int(d * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        x += np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 3) \
            + 0.12 * np.sin(2 * np.pi * 3 * f * t) * np.exp(-t * 5)
    return (x / len(freqs)) * env(n, 0.004, d / 3.2)


def ride(d=0.35):
    """Metalik ama gürültüsüz: uyumsuz kısmi sinüsler."""
    n = int(d * SR)
    t = np.arange(n) / SR
    x = sum(np.sin(2 * np.pi * f * t + k) for k, f in enumerate((3150, 4370, 5590, 6830, 8120)))
    return x / 5 * env(n, 0.001, 0.07)


def music(n, rests):
    out = np.zeros(n, np.float32)
    bar = BEAT * 4
    t0 = 0.0
    b = 0
    while t0 * SR < n:
        chord, walk = CHORDS[b % 4]
        for k in range(4):
            tb = t0 + k * BEAT
            if any(a <= tb < e for a, e in rests):
                continue
            add(out, upright(walk[k]), tb, 0.9)
            # swing ride: 1, 2, 2a, 3, 4, 4a
            add(out, ride(), tb, 0.10)
            if k in (1, 3):
                add(out, ride(0.25), tb + BEAT * 2 / 3, 0.06)
        for tb, g in ((t0, 0.55), (t0 + BEAT * 1.67, 0.35)):
            if not any(a <= tb < e for a, e in rests):
                add(out, piano(chord), tb, g)
        t0 += bar
        b += 1
    return out


def key():
    """Daktilo tuşu: kısa tık + küçük gövde."""
    n = int(0.03 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = (x - onepole_lp(x, 0.35)) * env(n, 0.0003, 0.004)
    body = thud(520, 260, 0.04, 0.0) * 0.5
    body[:n] += x
    return body * rng.uniform(0.7, 1.0)


def bell():
    n = int(1.0 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * 2637 * t) + 0.5 * np.sin(2 * np.pi * 3951 * t)) * env(n, 0.001, 0.25) * 0.5


def lamp_click():
    n = int(0.05 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = (x - onepole_lp(x, 0.2)) * env(n, 0.0003, 0.006)
    x[:int(0.04 * SR)] += thud(900, 400, 0.04, 0.0) * 0.3
    return x


def stamp_hit():
    return thud(180, 55, 0.3, 0.25)


def pin():
    return thud(700, 300, 0.06, 0.1) * 0.8


def stinger():
    """Dramatik alçak piyano kümesi."""
    return piano([36.71, 73.42, 77.78, 110.0, 155.56], 2.4) * 1.3


def whomp(d=0.35):
    n = int(d * SR)
    f = np.geomspace(140, 55, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.02, d / 3)


def type_line(fx, text, t0, dur, gain=1.0):
    n = len(text.replace(" ", ""))
    for k in range(n):
        add(fx, key(), t0 + dur * k / max(1, n), gain)


def build_mix_noir(audio, dur, words, out_path):
    v, duck = prep_voice(audio, dur, depth=0.55)
    n = len(v)
    wt = word_finder(words)

    m = music(n, [(0.0, 0.45), (31.0, 32.3), (45.8, 99)])
    m = fade_edges(m, 0.3, 0.3) * duck
    add(m, piano([73.42, 110.0, 146.83, 174.61, 220.0, 329.63], 3.0), 45.9, 0.9)

    fx = np.zeros(n, np.float32)
    add(fx, lamp_click(), 0.02, 1.0)
    add(fx, lamp_click(), 0.2, 0.6)
    # sahne 1 daktilo
    for text, t0, d in (("Tanık : Yapay Zekâ", 0.15, 0.5), ("Durum : Kendinden emin", 0.5, 0.55),
                        ("Beynimizin sadece %10'unu mu", 0.95, 0.75), ("kullanırız?", 1.7, 0.3),
                        ("Evet, kesinlikle. Beynimizin", 2.0, 0.8), ("yalnızca %10'u çalışır.", 2.8, 0.6)):
        type_line(fx, text, t0, d, 0.5)
    add(fx, bell(), 3.45, 0.5)
    add(fx, stamp_hit(), 4.45, 1.0)
    # geçişler
    for tb in (5.55, 39.4):
        add(fx, whomp(), tb - 0.15, 0.8)
    sana = wt("sana")
    add(fx, whomp(0.3), sana - 0.15, 0.5)
    add(fx, stamp_hit(), wt("basit", sana), 0.9)
    add(fx, stamp_hit(), wt("etkili", sana), 0.9)
    add(fx, pin(), wt("yöntem", sana) + 0.2, 0.7)
    # sahne 3
    add(fx, whomp(0.3), 11.35, 0.5)
    type_line(fx, "1) Önce önemli sorunu sor.", 11.7, 1.3, 0.4)
    su = wt("şu", 12)
    type_line(fx, "2) Ardından şunu ekle:", su - 0.4, 0.9, 0.4)
    for x in words:
        if 5 <= x["seg"] <= 8:
            type_line(fx, x["w"], x["s"], (x["e"] - x["s"]) * 0.85, 0.35)
    add(fx, bell(), words[[i for i, x in enumerate(words) if x["seg"] == 8][-1]]["e"] + 0.05, 0.5)
    # sahne 4
    add(fx, lamp_click(), 25.45, 0.8)
    for k in range(3):
        add(fx, pin(), 25.45 + 0.35 + k * 0.6 + 0.12, 0.9)
    # sahne 5
    add(fx, stinger(), 31.0, 1.0)
    add(fx, stamp_hit(), wt("yanlışları", 31), 0.8)
    add(fx, stamp_hit(), wt("kaldırmaz", 31) + 0.25, 1.0)
    oz = wt("özellikle", 31)
    add(fx, whomp(0.3), oz - 0.15, 0.4)
    for cue in ("güvenilir", "kaynaklardan", "kontrol"):
        add(fx, pin(), wt(cue, oz), 0.6)
    # sahne 6
    add(fx, stamp_hit(), wt("unutma"), 0.8)
    add(fx, stamp_hit(), wt("gelmez", 44) - 0.05, 1.0)
    add(fx, lamp_click(), dur - 0.9, 0.8)  # lamba söner
    return finish(v, m, fx, out_path, dur, 30)[0]

