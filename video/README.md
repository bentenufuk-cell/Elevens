# elevens1 — dikey Shorts/Reels videosu

İki tema, aynı seslendirme:

| Dosya | Tema | Betik |
|---|---|---|
| `out/elevens1_shorts.mp4` | Koyu, enerjik: neon vurgular, glitch/whip/flaş geçişler, ritimli müzik | `render.py` |
| `out/elevens1_shorts_soft.mp4` | Yumuşak, sade: krem kâğıt zemin, pastel tonlar, beyaz kartlar, yavaş solmalar, müzik kutusu | `render_soft.py` |
| `out/elevens1_shorts_doodle.mp4` | **Bambaşka kurgu** — defter/karalama anlatımı: tek dev sayfa, kamera sayfada gezer, her şey elle çiziliyor, robot karakter, finalde tüm sayfa açılır; marimba + kalem sesleri | `render_doodle.py` + `sound_doodle.py` |
| `out/elevens1_shorts_noir.mp4` | **Kara film (noir) dedektif hikâyesi** — "Sorgu Odası": siyah-beyaz film dokusu + kırmızı vurgu, lamba ışığı/panjur gölgeleri, daktilo belgeler, lastik damgalar, delil panosu, yalan makinesi şeridi; caz kontrbas + piyano | `render_noir.py` + `sound_noir.py` |
| `out/elevens1_shorts_pixel.mp4` | **8-bit retro oyun** — "Hata Avcısı": 216x384 piksel sanatı (5x büyütme), RPG diyalog kutuları, can/skor göstergesi, soru blokları ve sandık, büyü parşömeni, envanter, boss savaşı, görev listesi, kayıt ekranı; chiptune müzik ve oyun bipleri | `render_pixel.py` + `sound_pixel.py` |
| `out/elevens1_shorts_screen.mp4` | **YouTube yapay zekâ ipucu formatı** — üstte sabit kanca başlığı, ortada ekran kaydı (koyu temalı, logosuz temsili sohbet uygulaması) + otomatik zoom, dokunuş göstergesi, açılan klavye, akan yanıtlar, vurgu kutuları ve çıkartmalar; kalın kelime kelime altyazı; önce/sonra kurgusu ve tarayıcıda kaynak kontrolü; lo-fi ritim | `render_screen.py` + `sound_screen.py` |

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
python3 render_noir.py              # out/elevens1_shorts_noir.mp4
python3 render_pixel.py             # out/elevens1_shorts_pixel.mp4
python3 render_screen.py            # out/elevens1_shorts_screen.mp4
python3 render.py --preview 4.5 20  # tek kare PNG önizleme
```

Fontlar (`assets/fonts/`): Kalam, Caveat Brush, Shantell Sans, Bebas Neue, Anton, Press Start 2P, Jersey 10, Montserrat (SIL Open Font License) ve Special Elite (Apache 2.0); lisans metinleri aynı klasörde.

Ses dengesi: `sound.finish` her miksi ölçer; efektler konuşmanın 20 LU, müzik 17 LU altına otomatik çekilir, sonra sabit kazançla -14 LUFS'a getirilir.
