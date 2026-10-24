"""Defter teması sesi: oyuncaklı marimba ezgisi + kalem/keçeli kalem cızırtısı, kâğıt hışırtısı, not yapıştırma."""
import numpy as np

from sound import (NOTE, SR, add, click, ding, env, fade_edges, finish, onepole_lp, prep_voice, rng, thud,
                   word_finder)

BPM = 104
BEAT = 60 / BPM
PROG = [["C4", "E4", "G4", "C4"], ["A3", "C4", "E4", "A3"], ["F3", "A3", "C4", "F3"], ["G3", "B3", "D4", "G3"]]


def marimba(f, d=0.45):
    n = int(d * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 30)
    return x * env(n, 0.002, d / 4)


def bass(f, d=0.5):
    n = int(d * SR)
    t = np.arange(n) / SR
    return np.tanh(1.5 * np.sin(2 * np.pi * f * t)) * env(n, 0.004, d / 3)


def shaker():
    n = int(0.05 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = x - onepole_lp(x, 0.6)
    return x * env(n, 0.008, 0.012)


def music(n, rests):
    out = np.zeros(n, np.float32)
    step = BEAT / 2
    k = 0
    while k * step * SR < n:
        t0 = k * step
        if not any(a <= t0 < b for a, b in rests):
            bar = int(t0 / (BEAT * 4)) % 4
            notes = PROG[bar]
            pat = [0, 1, 2, 1, 3, 2, 1, 2]
            f = NOTE[notes[pat[k % 8]]] * 2
            if k % 8 not in (3, 7) or k % 16 == 3:
                add(out, marimba(f), t0, 0.5 if k % 2 == 0 else 0.32)
            if k % 4 == 0:
                add(out, bass(NOTE[notes[0]] / 2), t0, 0.45)
            add(out, shaker(), t0, 0.12 if k % 2 else 0.06)
        k += 1
    return out


def scribble(d, bright=0.25, rate=(9, 16)):
    """Kalem cızırtısı: band geçiren gürültü + düzensiz genlik modülasyonu."""
    n = max(1, int(d * SR))
    x = rng.normal(0, 1, n).astype(np.float32)
    x = onepole_lp(x, bright) - onepole_lp(x, bright * 0.12)
    t = np.arange(n) / SR
    f = rng.uniform(*rate)
    am = 0.35 + 0.65 * np.abs(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)))
    edge = np.minimum(1, np.minimum(t / 0.015, (d - t) / 0.03).clip(0))
    return x * am * edge


def squeak(d):
    """Keçeli kalem: biraz daha tiz ve 'gıcırtılı'."""
    n = max(1, int(d * SR))
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * (1700 + 300 * np.sin(2 * np.pi * 3 * t)) * t) * 0.15
    return scribble(d, 0.45, (5, 9)) + tone * np.minimum(1, np.minimum(t / 0.02, (d - t) / 0.03).clip(0))


def paper_swish(d=0.6):
    n = int(d * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    p = np.linspace(0, 1, n)
    y = onepole_lp(x, 0.03 + 0.12 * np.sin(np.pi * p))
    return y * np.sin(np.pi * p) ** 2 * 2.2


def slap():
    body = thud(240, 110, 0.12, 0.3) * 0.5
    n = int(0.08 * SR)
    body[:n] += onepole_lp(rng.normal(0, 1, n).astype(np.float32), 0.2) * env(n, 0.0005, 0.015) * 1.2
    return body


def buzz():
    out = np.zeros(int(0.42 * SR), np.float32)
    for k in range(2):
        n = int(0.14 * SR)
        t = np.arange(n) / SR
        b = np.sign(np.sin(2 * np.pi * 150 * t)) * env(n, 0.003, 0.08)
        out[int(k * 0.2 * SR):int(k * 0.2 * SR) + n] += onepole_lp(b.astype(np.float32), 0.12)
    return out


def build_mix_doodle(audio, dur, words, elements, moves, out_path):
    v, duck = prep_voice(audio, dur, depth=0.6)
    n = len(v)
    wt = word_finder(words)

    m = music(n, [(31.0, 32.3), (45.6, 99)]) * 0.075
    m = fade_edges(m, 0.2, 1.0) * duck

    fx = np.zeros(n, np.float32)
    for e in elements:
        k, t0 = e["kind"], e["t0"]
        if k == "text":
            d = e["dur"]
            add(fx, squeak(d) if e["key"] == "marker" else scribble(d), t0, 0.05 if e["key"] == "marker" else 0.07)
        elif k == "path" and e["dur"] >= 0.1:
            snd = squeak(e["dur"]) if e.get("sound") == "marker" else scribble(e["dur"], 0.3)
            add(fx, snd, t0, 0.05)
        elif k == "path":
            add(fx, click(), t0, 0.08)
        elif k == "sticky":
            add(fx, slap(), t0 + 0.2, 0.35)
        elif k == "custom" and e["fn"].__name__ == "card_draw":
            add(fx, slap(), t0 + 0.22, 0.3)
        elif k == "custom" and e["fn"].__name__ == "robot_draw":
            add(fx, scribble(1.2), t0, 0.06)
    # karttaki kelime kelime yazım
    for x in words:
        if 5 <= x["seg"] <= 8:
            add(fx, scribble(max(0.1, (x["e"] - x["s"]) * 0.85)), x["s"], 0.045)
    for t0, d, _ in moves:
        if 0.3 < d < 1.5:
            add(fx, paper_swish(d + 0.2), t0 - 0.1, 0.22)
    add(fx, buzz(), 4.38, 0.22)
    add(fx, ding(1568, 0.8), wt("sana") + 0.85, 0.12)
    for cue in ("basit", "etkili"):
        add(fx, ding(2093, 0.4), wt(cue) + 0.35, 0.06)
    oz = wt("özellikle")
    for cue in ("güvenilir", "kaynaklardan", "kontrol"):
        add(fx, ding(1318, 0.5), wt(cue, oz), 0.08)
    add(fx, thud(140, 50, 0.4, 0.4), 31.0, 0.45)
    add(fx, slap(), 40.95, 0.4)
    add(fx, ding(1046, 1.4), wt("gelmez", 44), 0.12)
    add(fx, ding(1568, 1.4), wt("gelmez", 44) + 0.15, 0.08)
    return finish(v, m, fx, out_path, dur, 30)[0]
