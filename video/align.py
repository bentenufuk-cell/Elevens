"""Kelime zamanlaması: VAD segmentleri + Türkçe hece (ünlü) sayısına göre dağıtım,
sınırları ses enerjisindeki en yakın çukura yaslar. Çıktı: words.json"""
import json, subprocess, sys
import numpy as np

AUDIO = sys.argv[1] if len(sys.argv) > 1 else "assets/elevens1.mp3"

# (başlangıç, bitiş, metin) — VAD + Whisper turbo çıktısı, elle düzeltilmiş
SEGMENTS = [
    (0.12, 3.14, "ChatGPT bazen öyle bir yanlış cevap veriyor ki,"),
    (3.36, 5.29, "doğru olduğundan hiç şüphe etmiyorsun."),
    (5.76, 7.98, "Peki bunu azaltmak için ne yapabilirsin?"),
    (8.41, 11.14, "Sana basit ama etkili bir yöntem göstereyim."),
    (11.52, 15.37, "ChatGPT'ye önemli bir soru sorduktan sonra şu cümleyi ekle:"),
    (15.84, 17.42, "Kesin bildiğin bilgileri,"),
    (17.60, 21.64, "tahminlerini ve doğrulanması gereken iddiaları ayrı ayrı belirt."),
    (22.08, 23.53, "Emin olmadığın konularda"),
    (23.64, 25.13, "“bilmiyorum” demekten çekinme."),
    (25.69, 30.73, "Bu sayede yapay zekanın hangi noktalarda emin olmadığını daha kolay fark edebilirsin."),
    (31.13, 31.91, "Ama dikkat!"),
    (32.28, 35.02, "Bu yöntem bütün yanlışları ortadan kaldırmaz."),
    (35.29, 39.18, "Özellikle önemli bilgileri güvenilir kaynaklardan kontrol etmelisin."),
    (39.55, 40.04, "Unutma,"),
    (40.35, 42.92, "yapay zekanın kendinden emin konuşması,"),
    (43.16, 45.63, "her zaman doğru konuştuğu anlamına gelmez."),
]

SPECIAL = {"chatgpt": 4, "chatgpt'ye": 5}
VOWELS = set("aeıioöuüAEIİOÖUÜ")


def syllables(word):
    key = "".join(c for c in word.lower() if c.isalpha() or c == "'")
    if key in SPECIAL:
        return SPECIAL[key]
    return max(1, sum(c in VOWELS for c in word))


def main():
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", AUDIO, "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 160  # 10 ms
    rms = np.sqrt(np.convolve(a ** 2, np.ones(400) / 400, "same")[::hop] + 1e-9)

    out = []
    for si, (t0, t1, text) in enumerate(SEGMENTS):
        words = text.split()
        # ağırlık: hece sayısı + kelime arası küçük sabit + virgül sonrası duraksama
        w = np.array([syllables(x) + 0.35 + (0.8 if x.endswith(",") else 0) for x in words], float)
        edges = t0 + np.concatenate([[0], np.cumsum(w)]) / w.sum() * (t1 - t0)
        # iç sınırları ±90 ms içindeki en düşük enerjiye yasla
        for k in range(1, len(edges) - 1):
            c = int(edges[k] * 100)
            lo, hi = max(c - 6, 0), min(c + 7, len(rms))
            edges[k] = (lo + int(np.argmin(rms[lo:hi]))) / 100
        for k in range(1, len(edges)):  # en az 0.1 sn kelime süresi
            edges[k] = max(edges[k], edges[k - 1] + 0.1)
        edges[-1] = max(edges[-1], t1)
        for k, x in enumerate(words):
            out.append({"w": x, "s": round(float(edges[k]), 3), "e": round(float(edges[k + 1]), 3), "seg": si})
    json.dump(out, open("words.json", "w"), ensure_ascii=False, indent=1)
    for x in out:
        print(f'{x["s"]:6.2f} {x["e"]:6.2f} {x["w"]}')


if __name__ == "__main__":
    main()
