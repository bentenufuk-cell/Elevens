"""Ses tasarımı: seslendirme + sentezlenmiş ambiyans pad, hafif ritim ve geçiş efektleri."""
import subprocess
import wave

import numpy as np

SR = 44100
rng = np.random.default_rng(11)


def load(path):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def onepole_lp(x, a):
    """Basit tek kutuplu alçak geçiren filtre; a skaler veya örnek başına dizi."""
    y = np.empty_like(x)
    acc = 0.0
    a = np.broadcast_to(np.asarray(a, np.float32), x.shape)
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def whoosh(d=0.5):
    n = int(d * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    p = np.linspace(0, 1, n)
    cut = 0.02 + 0.25 * np.sin(np.pi * p) ** 2
    y = onepole_lp(x, cut) - onepole_lp(x, cut * 0.15)
    return y * np.sin(np.pi * p) ** 1.5 * 1.6


def pop(f0=900, f1=420, d=0.09):
    n = int(d * SR)
    t = np.arange(n) / SR
    f = np.linspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, d / 3.5)


def click():
    n = int(0.012 * SR)
    x = rng.normal(0, 1, n).astype(np.float32)
    x = x - onepole_lp(x, 0.3)
    return x * env(n, 0.0005, 0.003) * rng.uniform(0.5, 1)


def thud(f0=160, f1=55, d=0.25, noise=0.4):
    n = int(d * SR)
    f = np.geomspace(f0, f1, n)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, d / 3)
    nz = onepole_lp(rng.normal(0, 1, n).astype(np.float32), 0.15) * env(n, 0.0005, 0.03) * noise
    return np.tanh((s + nz) * 1.8)


def boom(d=1.4):
    n = int(d * SR)
    f = np.geomspace(90, 32, n)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.002, 0.45)
    nz = onepole_lp(rng.normal(0, 1, n).astype(np.float32), 0.05) * env(n, 0.001, 0.12) * 1.5
    return np.tanh((s + nz) * 2.2) * 0.9


def ding(f=1320, d=0.6):
    n = int(d * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 1.5 * t)
            + 0.2 * np.sin(2 * np.pi * f * 2.0 * t)) * env(n, 0.002, 0.15) * 0.6


def glitch(d=0.28):
    n = int(d * SR)
    out = np.zeros(n, np.float32)
    i = 0
    while i < n:
        L = int(rng.integers(300, 2200))
        f = rng.choice([80, 160, 440, 1200, 2400])
        t = np.arange(min(L, n - i)) / SR
        out[i:i + L] = np.sign(np.sin(2 * np.pi * f * t)) * rng.uniform(0.2, 0.7)
        i += L
    return out * env(n, 0.002, d / 2) * 0.7


def stamp():
    return thud(220, 70, 0.22, 0.8) * 0.9


NOTE = {"A2": 110.0, "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.0, "A3": 220.0,
        "B3": 246.94, "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.0, "A4": 440.0}

CHORDS = [  # (başlangıç sn, notalar)
    (0.0, ["A2", "E3", "G3", "C4", "E4"]),
    (5.55, ["F3", "A3", "C4", "E4", "G4"]),
    (11.35, ["C3", "G3", "B3", "E4", "G4"]),
    (25.45, ["G3", "B3", "D4", "F4", "A4"]),
    (31.0, ["D3", "A3", "C4", "F4", "A4"]),
    (39.4, ["F3", "C4", "E4", "G4", "A4"]),
    (43.6, ["A2", "E3", "A3", "C4", "E4"]),
]


def pad(n):
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    bounds = [int(c[0] * SR) for c in CHORDS] + [n]
    xf = int(0.8 * SR)
    for k, (t0, notes) in enumerate(CHORDS):
        a, b = max(0, bounds[k] - xf // 2), min(n, bounds[k + 1] + xf // 2)
        tt = t[a:b]
        seg = np.zeros(b - a, np.float32)
        for nn in notes:
            f = NOTE[nn]
            for det in (-0.0025, 0.0025):
                for h in range(1, 5):
                    seg += np.sin(2 * np.pi * f * (1 + det) * h * tt + h) / h ** 1.6
        w = np.ones(b - a, np.float32)
        r = np.linspace(0, 1, min(xf, b - a))
        w[:len(r)] = np.minimum(w[:len(r)], r)
        w[-len(r):] = np.minimum(w[-len(r):], r[::-1])
        out[a:b] += seg * w
    out *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.23 * t)
    return out / np.abs(out).max()


def beat(n, bpm, mute):
    out = np.zeros(n, np.float32)
    step = 60 / bpm
    k = 0
    while k * step * SR < n:
        t0 = k * step
        if not any(a <= t0 < b for a, b in mute):
            i = int(t0 * SR)
            kick = thud(110, 45, 0.3, 0.1) * 0.9
            out[i:i + len(kick)] += kick[: n - i]
            j = int((t0 + step / 2) * SR)
            if j < n:
                hat = rng.normal(0, 1, int(0.03 * SR)).astype(np.float32)
                hat = (hat - onepole_lp(hat, 0.5)) * env(len(hat), 0.0005, 0.008) * 0.35
                out[j:j + len(hat)] += hat[: n - j]
        k += 1
    return out


def add(buf, snd, t, gain):
    i = int(t * SR)
    if i < 0 or i >= len(buf):
        return
    m = min(len(snd), len(buf) - i)
    buf[i:i + m] += snd[:m] * gain


def word_finder(words):
    def wt(w, after=0.0):
        for x in words:
            if x["s"] >= after - 1e-3 and x["w"].lower().strip("“”,.!?:").startswith(w):
                return x["s"]
        raise KeyError(w)
    return wt


def prep_voice(audio, dur, depth=0.55):
    """Seslendirmeyi normalize eder; müzik için sidechain kısma eğrisini döndürür."""
    voice = load(audio)
    n = int(dur * SR)
    v = np.zeros(n, np.float32)
    v[:len(voice)] = voice[:n]
    v *= 0.9 / (np.abs(v).max() + 1e-6)
    e = np.sqrt(np.convolve(v ** 2, np.ones(2048) / 2048, "same"))
    duck = 1 - depth * np.clip(e / 0.08, 0, 1)
    return v, onepole_lp(duck.astype(np.float32), 0.0015)


def fade_edges(x, fin=0.3, fout=0.8):
    n = len(x)
    return x * np.clip(np.arange(n) / (fin * SR), 0, 1) * np.clip((n - np.arange(n)) / (fout * SR), 0, 1)


def loudness(x):
    """ffmpeg ebur128 ile (entegre LUFS, en yüksek kısa süreli LUFS) ölçer."""
    import re
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav") as tf:
        with wave.open(tf.name, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", tf.name, "-af", "ebur128", "-f", "null",
                              "-"], capture_output=True, text=True).stderr
    st = [float(m) for m in re.findall(r"S:\s*(-?[\d.]+)", err)]
    integ = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])
    return integ, max(st) if st else -70.0


# Seviye kuralları (konuşmaya göre, LU): efektler ve müzik sesi asla bastırmasın.
FX_REL, FX_PEAK_REL = -20.0, -10.0     # efekt: entegre -20, en gürültülü anı bile konuşmanın 10 altında
MUSIC_REL, MUSIC_PEAK_REL = -17.0, -9.0
TARGET_LUFS = -14.0


def fit_level(x, ref_i, rel, peak_rel, name):
    if not np.any(x):
        return x
    i, st = loudness(x)
    g_db = min(ref_i + rel - i, ref_i + peak_rel - st)
    y = x * 10 ** (g_db / 20)
    print(f"  {name:6s}: {i:6.1f} LUFS (kısa süreli maks {st:6.1f}) -> kazanç {g_db:+5.1f} dB "
          f"=> konuşmanın {i + g_db - ref_i:+5.1f} LU altında")
    return y


def finish(v, music, fx, out_path, dur, fps):
    """Katmanları ölçüp kurallara göre dengeler, sabit kazançla -14 LUFS'a getirir, wav yazar.
    Kare başına yumuşatılmış ses enerjisini döndürür."""
    vi, _ = loudness(v)
    print(f"ses dengesi (konuşma {vi:.1f} LUFS):")
    music = fit_level(music, vi, MUSIC_REL, MUSIC_PEAK_REL, "müzik")
    fx = fit_level(fx, vi, FX_REL, FX_PEAK_REL, "efekt")
    mixd = v + music + fx
    mi, _ = loudness(mixd)
    mixd = mixd * 10 ** ((TARGET_LUFS - mi) / 20)
    # yumuşak tepe sınırlayıcı (~ -2.5 dBFS; AAC sonrası taşmasın); sabit kazanç, sessiz anlar şişirilmez
    lim = 10 ** (-2.5 / 20)
    over = np.abs(mixd) > lim * 0.8
    if over.any():
        k = lim * 0.8
        mixd = np.where(over, np.sign(mixd) * (k + (lim - k) * np.tanh((np.abs(mixd) - k) / (lim - k))), mixd)
    print(f"  miks  : {loudness(mixd)[0]:.1f} LUFS, tepe {20 * np.log10(np.abs(mixd).max()):.1f} dBFS")
    pcm = (np.clip(mixd, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())

    hop = SR // fps
    nf = int(dur * fps)
    fe = np.array([np.sqrt(np.mean(v[i * hop:(i + 1) * hop] ** 2) + 1e-9) for i in range(nf)])
    fe = fe / (fe.max() + 1e-9)
    sm = np.zeros_like(fe)
    acc = 0.0
    for i, x in enumerate(fe):
        acc += (0.5 if x > acc else 0.12) * (x - acc)
        sm[i] = acc
    return out_path, sm


def build_mix(audio, dur, fps, words, out_path):
    v, duck = prep_voice(audio, dur)
    n = len(v)
    wt = word_finder(words)

    music = pad(n) * 0.11 + beat(n, 100, [(31.0, 32.3), (45.4, 99)]) * 0.10
    music = fade_edges(music) * duck

    fx = np.zeros(n, np.float32)
    # sahne 1
    add(fx, pop(700, 1100), 0.02, 0.35)
    for k in range(40):
        add(fx, click(), 0.75 + k * (1.85 / 40), 0.12)
    add(fx, stamp(), 2.85, 0.45)
    add(fx, glitch(), 4.36, 0.30)
    add(fx, stamp(), 4.45, 0.55)
    add(fx, pop(500, 900), 4.85, 0.25)
    # geçişler
    for tb in (5.55, 11.35, 25.45, 39.4):
        add(fx, whoosh(0.5), tb - 0.3, 0.45)
    add(fx, glitch(0.22), 5.5, 0.22)
    add(fx, glitch(0.22), 39.35, 0.22)
    # sahne 2
    add(fx, pop(400, 1200, 0.14), 5.6, 0.3)
    sc = wt("sana")
    add(fx, pop(600, 1000), sc - 0.1, 0.3)
    add(fx, pop(900, 1500), wt("basit"), 0.3)
    add(fx, pop(900, 1500), wt("etkili"), 0.3)
    add(fx, thud(200, 70, 0.2, 0.3), wt("yöntem", sc) - 0.05, 0.4)
    # sahne 3
    add(fx, pop(700, 1100), 11.4, 0.25)
    add(fx, pop(900, 1300), wt("cümleyi") - 0.1, 0.3)
    s_typ = wt("kesin")
    for x in words:
        if 5 <= x["seg"] <= 8:
            L = len(x["w"])
            for c in range(L):
                add(fx, click(), x["s"] + (x["e"] - x["s"]) * 0.8 * c / L, 0.07)
    add(fx, pop(500, 1400, 0.12), wt("emin", s_typ), 0.2)
    add(fx, pop(1200, 600, 0.12), 25.2, 0.3)
    # sahne 4
    for k in range(3):
        add(fx, pop(600 + k * 200, 1000 + k * 200), 25.8 + k * 0.6, 0.3)
    add(fx, whoosh(0.4), wt("emin", 25.4) - 0.1, 0.18)
    # sahne 5
    add(fx, boom(), 31.0, 0.85)
    add(fx, glitch(0.2), 30.95, 0.25)
    b = wt("bu", 31.5)
    add(fx, whoosh(0.4), b - 0.25, 0.3)
    add(fx, whoosh(0.6), wt("yanlışları"), 0.15)
    add(fx, thud(260, 90, 0.2, 0.5), wt("kaldırmaz"), 0.4)
    oz = wt("özellikle")
    add(fx, whoosh(0.45), oz - 0.35, 0.35)
    for cue in ("güvenilir", "kaynaklardan", "kontrol"):
        add(fx, ding(1320), wt(cue, oz), 0.2)
    # sahne 6
    add(fx, pop(600, 1200), wt("unutma"), 0.3)
    add(fx, thud(180, 60, 0.25, 0.3), wt("emin", 40), 0.35)
    add(fx, thud(180, 60, 0.25, 0.3), wt("doğru", 40), 0.35)
    g = wt("gelmez", 40)
    add(fx, boom(1.8), g - 0.05 + 0.15, 0.75)
    add(fx, ding(880, 1.2), 45.9, 0.18)

    return finish(v, music, fx, out_path, dur, fps)


# ---------------------------------------------------------------- yumuşak tema
SOFT_CHORDS = [
    (0.0, ["C4", "E4", "G4", "B3"]),
    (5.55, ["A3", "C4", "E4", "G4"]),
    (11.35, ["F3", "A3", "C4", "E4"]),
    (25.45, ["C4", "E4", "G4", "D4"]),
    (31.0, ["D4", "F4", "A3", "C4"]),
    (39.4, ["F3", "A3", "C4", "G4"]),
    (43.6, ["C4", "E4", "G4", "B3"]),
]


def soft_pad(n):
    """Saf sinüslerden sıcak, hafif bir pad."""
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    bounds = [int(c[0] * SR) for c in SOFT_CHORDS] + [n]
    xf = int(1.2 * SR)
    for k, (_, notes) in enumerate(SOFT_CHORDS):
        a, b = max(0, bounds[k] - xf // 2), min(n, bounds[k + 1] + xf // 2)
        tt = t[a:b]
        seg = np.zeros(b - a, np.float32)
        for nn in notes:
            f = NOTE[nn]
            seg += np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * f * 2 * tt + 0.5)
            seg += 0.5 * np.sin(2 * np.pi * f * 1.003 * tt)
        w = np.ones(b - a, np.float32)
        r = np.linspace(0, 1, min(xf, b - a))
        w[:len(r)] = np.minimum(w[:len(r)], r)
        w[-len(r):] = np.minimum(w[-len(r):], r[::-1])
        out[a:b] += seg * w
    out *= 0.8 + 0.2 * np.sin(2 * np.pi * 0.15 * t)
    return out / np.abs(out).max()


def pluck(f, d=1.6):
    """Müzik kutusu / keçeli piyano benzeri yumuşak nota."""
    n = int(d * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 6)
    return x * env(n, 0.006, d / 4)


def soft_plucks(n, bpm=76):
    out = np.zeros(n, np.float32)
    step = 60 / bpm
    k = 0
    while k * step * SR < n:
        t0 = k * step
        notes = SOFT_CHORDS[0][1]
        for c0, nn in SOFT_CHORDS:
            if t0 >= c0:
                notes = nn
        f = NOTE[notes[k % len(notes)]] * 2
        add(out, pluck(f), t0, 0.5 if k % 2 == 0 else 0.3)
        k += 1
    return out


def soft_whoosh(d=0.7):
    return onepole_lp(whoosh(d).astype(np.float32), 0.25)


def build_mix_soft(audio, dur, fps, words, out_path):
    v, duck = prep_voice(audio, dur, depth=0.6)
    n = len(v)
    wt = word_finder(words)

    music = soft_pad(n) * 0.09 + soft_plucks(n) * 0.05
    music = fade_edges(music, 0.8, 1.5) * duck

    fx = np.zeros(n, np.float32)
    add(fx, pop(500, 750, 0.12), 0.05, 0.14)
    add(fx, pop(450, 650, 0.12), 0.4, 0.12)
    for k in range(40):
        add(fx, click(), 0.75 + k * (1.85 / 40), 0.04)
    add(fx, ding(1046, 0.8), 2.85, 0.10)
    add(fx, pop(420, 300, 0.16), 4.4, 0.16)
    add(fx, ding(784, 0.8), 4.85, 0.08)
    for tb in (5.55, 11.35, 25.45, 31.0, 39.4):
        add(fx, soft_whoosh(0.7), tb - 0.4, 0.22)
    sc = wt("sana")
    add(fx, pop(500, 700, 0.12), sc - 0.1, 0.14)
    add(fx, ding(1318, 0.5), wt("basit"), 0.07)
    add(fx, ding(1568, 0.5), wt("etkili"), 0.07)
    add(fx, pop(500, 750, 0.12), wt("cümleyi") - 0.1, 0.14)
    for x in words:
        if 5 <= x["seg"] <= 8:
            L = len(x["w"])
            for c in range(L):
                add(fx, click(), x["s"] + (x["e"] - x["s"]) * 0.8 * c / L, 0.025)
    for k in range(3):
        add(fx, pop(500 + k * 120, 700 + k * 120, 0.12), 25.8 + k * 0.6, 0.12)
    add(fx, pop(380, 300, 0.2), 31.05, 0.18)
    oz = wt("özellikle")
    for i, cue in enumerate(("güvenilir", "kaynaklardan", "kontrol")):
        add(fx, ding(1046 * (1.125 ** i), 0.7), wt(cue, oz), 0.08)
    add(fx, ding(1046, 1.2), wt("gelmez", 40), 0.10)
    add(fx, ding(1568, 1.4), wt("gelmez", 40) + 0.12, 0.06)
    return finish(v, music, fx, out_path, dur, fps)
