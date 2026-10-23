# elevens1 — dikey Shorts/Reels videosu

`out/elevens1_shorts.mp4` — 1080x1920, 30 fps, 47 sn, H.264 + AAC (-15 LUFS).

Tüm görseller kod ile üretilir (stok görsel yok). Akış:

1. `align.py` — Whisper (turbo) ile çıkarılıp elle düzeltilmiş metni, ses enerjisine göre kelime kelime zamanlar → `words.json`
2. `sound.py` — seslendirme + sentez ambiyans pad, hafif ritim, geçiş/pop/daktilo/boom efektleri, sese göre müzik kısma (sidechain)
3. `render.py` — 6 sahne, geçişler (glitch, whip-pan, zoom-through, kırmızı flaş), karaoke altyazı, kareleri ffmpeg'e borular

```bash
pip install numpy pillow
python3 align.py                    # words.json
python3 render.py                   # out/elevens1_shorts.mp4
python3 render.py --preview 4.5 20  # tek kare PNG önizleme
```
