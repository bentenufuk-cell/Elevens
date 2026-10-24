"""Yapay zekâ ipucu Shorts'u sesi: sakin lo-fi ritim (Rhodes akorları, sub bas, yumuşak davul) + arayüz efektleri.

Efektler kısa ve tonal: dokunma, gönderme, mesaj, çıkartma "pop"u, vurgu "ding"i, uyarı. Uzun hışırtı yok.
Seviyeler sound.finish içinde konuşmaya göre ölçülerek ayarlanır.
"""
import numpy as np

from sound import SR, add, env, fade_edges, finish, onepole_lp, prep_voice, rng, thud, word_finder

BPM = 86
BEAT = 60 / BPM

CHORDS = [  # Fmaj7 | Em7 | Dm7 | Cmaj7 (Hz) + bas kökü
    ([174.61, 220.0, 261.63, 329.63], 87.31),
    ([164.81, 196.0, 246.94, 293.66], 82.41),
    ([146.83, 174.61, 220.0, 261.63], 73.42),
    ([130.81, 164.81, 196.0, 246.94], 65.41),
]


def rhodes(freqs, d):
    n = int(d * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        x += np.sin(2 * np.pi * f * t + 0.6 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 4))
    x *= 1 + 0.15 * np.sin(2 * np.pi * 4.5 * t)
    return x / len(freqs) * env(n, 0.01, d / 2.5)


def sub(f, d):
    n = int(d * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * f * t) * env(n, 0.01, d / 2)


def snap():
    n = int(0.06 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = (onepole_lp(x, 0.4) - onepole_lp(x, 0.05)) * env(n, 0.001, 0.018)
    body = thud(260, 180, 0.06, 0.0) * 0.3
    m = min(len(x), len(body))
    x[:m] += body[:m]
    return x


def hat():
    n = int(0.025 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    return (x - onepole_lp(x, 0.55)) * env(n, 0.0005, 0.006)


def music(n, rests):
    out = np.zeros(n, np.float32)
    bar = BEAT * 4
    b = 0
    while b * bar * SR < n:
        t0 = b * bar
        chord, root = CHORDS[b % 4]
        if not any(a <= t0 < e for a, e in rests):
            add(out, rhodes(chord, bar * 1.05), t0, 0.55)
            add(out, sub(root, bar * 0.9), t0, 0.8)
        for k in range(8):
            tb = t0 + k * BEAT / 2 + (0.03 if k % 2 else 0)  # hafif swing
            if any(a <= tb < e for a, e in rests):
                continue
            if k in (0, 5):
                add(out, thud(110, 45, 0.3, 0.05), tb, 0.9)
            if k in (2, 6):
                add(out, snap(), tb, 0.45)
            add(out, hat(), tb, 0.18 if k % 2 else 0.1)
        b += 1
    return out


def tone(f0, f1, d, decay=None):
    n = int(d * SR)
    f = np.geomspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, decay or d / 3)


def pop():
    return tone(520, 980, 0.09, 0.03)


def tap():
    out = tone(1800, 1400, 0.03, 0.008) * 0.4
    n = int(0.02 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    out[:n] += (x - onepole_lp(x, 0.3)) * env(n, 0.0003, 0.004) * 0.6
    return out


def send():
    return tone(400, 1200, 0.14, 0.06)


def ding(f=1568):
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.01 * t)) * env(n, 0.002, 0.12)


def alert():
    out = np.zeros(int(0.5 * SR), np.float32)
    add(out, tone(880, 860, 0.18, 0.08), 0.0, 1.0)
    add(out, tone(660, 640, 0.22, 0.1), 0.2, 1.0)
    return out


def swish():
    """Tonal geçiş (gürültüsüz): kısa yükselen sinüs."""
    return tone(220, 900, 0.16, 0.08) * 0.7


def build_mix_screen(audio, dur, words, out_path):
    import render_screen as rs
    v, duck = prep_voice(audio, dur, depth=0.6)
    n = len(v)
    wt = word_finder(words)

    m = music(n, [(31.0, 32.3), (45.7, 99)])
    m = fade_edges(m, 0.3, 0.3) * duck
    add(m, rhodes(CHORDS[0][0], 2.5), 45.8, 0.7)

    fx = np.zeros(n, np.float32)
    add(fx, pop(), rs.A_STREAM[0], 0.5)  # yanıt geldi
    add(fx, alert(), 4.4, 0.9)
    for t0 in (4.45, 4.85):
        add(fx, pop(), t0, 0.7)
    add(fx, tap(), 7.95, 0.9)
    sana = wt("sana")
    for cue in ("basit", "etkili"):
        add(fx, pop(), wt(cue, sana), 0.7)
    add(fx, ding(1318), wt("yöntem", sana) - 0.05, 0.6)
    for tc in rs.CUTS:
        add(fx, swish(), tc - 0.1, 0.6)
    add(fx, tap(), rs.T_NEWCHAT + 0.15, 0.8)
    # yazma: kelime başına bir tık (harf başına değil)
    q = rs.QUESTION.split()
    for k in range(len(q)):
        add(fx, tap(), rs.T_Q_TYPE[0] + (rs.T_Q_TYPE[1] - rs.T_Q_TYPE[0]) * k / len(q), 0.35)
    for x in words:
        if 5 <= x["seg"] <= 8:
            add(fx, tap(), x["s"], 0.3)
    add(fx, pop(), wt("emin", 22), 0.6)
    add(fx, tap(), rs.T_SEND, 0.9)
    add(fx, send(), rs.T_SEND + 0.03, 0.7)
    add(fx, pop(), rs.B_STREAM[0], 0.5)
    te = wt("emin", 25.4)
    add(fx, ding(1568), te, 0.5)
    add(fx, ding(1760), te + 0.35, 0.5)
    add(fx, pop(), te + 0.4, 0.5)
    add(fx, alert(), 31.0, 1.0)
    add(fx, thud(140, 50, 0.35, 0.1), 31.0, 0.8)
    add(fx, pop(), wt("yanlışları", 31), 0.6)
    add(fx, pop(), wt("kaldırmaz", 31), 0.6)
    oz = wt("özellikle", 31)
    add(fx, pop(), rs.T_BROWSER + 0.15, 0.5)
    for cue in ("güvenilir", "kaynaklardan", "kontrol"):
        add(fx, ding(2093), wt(cue, oz), 0.5)
    add(fx, pop(), wt("unutma"), 0.6)
    add(fx, thud(150, 55, 0.3, 0.1), wt("gelmez", 44) - 0.05, 0.9)
    add(fx, pop(), 45.9, 0.6)
    add(fx, pop(), 46.05, 0.6)
    return finish(v, m, fx, out_path, dur, 30)[0]
