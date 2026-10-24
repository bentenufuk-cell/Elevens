# elevens1 — dikey Shorts/Reels videosu

İki tema, aynı seslendirme:

| Dosya | Tema | Betik |
|---|---|---|
| `out/elevens1_shorts.mp4` | Koyu, enerjik: neon vurgular, glitch/whip/flaş geçişler, ritimli müzik | `render.py` |
| `out/elevens1_shorts_soft.mp4` | Yumuşak, sade: krem kâğıt zemin, pastel tonlar, beyaz kartlar, yavaş solmalar, müzik kutusu | `render_soft.py` |
| `out/elevens1_shorts_doodle.mp4` | **Bambaşka kurgu** — defter/karalama anlatımı: tek dev sayfa, kamera sayfada gezer, her şey elle çiziliyor, robot karakter, finalde tüm sayfa açılır; marimba + kalem sesleri | `render_doodle.py` + `sound_doodle.py` |

Her ikisi de 1080x1920, 30 fps, 47 sn, H.264 + AAC.

Tüm görseller kod ile üretilir (stok görsel yok). Akış:

1. `align.py` — Whisper (turbo) ile çıkarılıp elle düzeltilmiş metni, ses enerjisine göre kelime kelime zamanlar → `words.json`
2. `sound.py` — seslendirme + sentez ambiyans pad, hafif ritim, geçiş/pop/daktilo/boom efektleri, sese göre müzik kısma (sidechain)
3. `render.py` — 6 sahne, geçişler (glitch, whip-pan, zoom-through, kırmızı flaş), karaoke altyazı, kareleri ffmpeg'e borular

```bash
pip install numpy pillow
python3 align.py                    # words.json
python3 render.py                   # out/elevens1_shorts.mp4
python3 render_soft.py              # out/elevens1_shorts_soft.mp4
python3 render_doodle.py            # out/elevens1_shorts_doodle.mp4
python3 render.py --preview 4.5 20  # tek kare PNG önizleme
```

Defter temasındaki fontlar (`assets/fonts/`): Kalam, Caveat Brush, Shantell Sans — SIL Open Font License (lisans metinleri aynı klasörde).
