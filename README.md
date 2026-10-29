# PULSE ARENA v3.0.1 — Patch pada v3.0

**Basis proyek: PULSE ARENA v3.0 (bukan v3.1).** Perbaikan hanya mengikuti enam catatan terbaru pengguna. Aplikasi tidak resmi dari Resolume.

## Perbaikan

1. **Blackout** kini menggunakan OSC `/composition/video/opacity` untuk mengatur *master video opacity* ke `0` (hitam), dan mengembalikan opacity ke nilai sebelum blackout pada perintah Restore. Tekan/tahan tombol ±750 ms untuk blackout, sentuh untuk restore. Ini menghindari ketergantungan pada toggle master bypass dan tidak mengubah opasitas tiap layer. Tetap harus diuji pada rig Resolume asli.
2. **Quick FX/Macro Editor** di STUDIO: pilih FX 1–4, ubah label, warna, OSC address, mode (Toggle / Momentary / Pulse), nilai ON, nilai OFF. Perubahan disimpan dalam `data/preset.json`. Klik ikon pensil pada panel FX atau tombol **EDIT FX** di bar STUDIO.
3. **FX ON/OFF**: Toggle mengirim ON pada sentuhan pertama dan OFF pada sentuhan berikutnya. Momentary ON selama ditahan dan OFF ketika dilepas. Pulse ON lalu OFF otomatis. Tombol punya indikator lokal ketika ON; jika Resolume mengirim OSC Output terkait, status diperbarui dari feedback tersebut. **Alamat OSC harus benar-benar mengarah ke parameter efek di Resolume**; alamat bawaan `/composition/dashboard/linkN` hanya berguna bila parameter telah dihubungkan ke Dashboard Link N.
4. **BPM lebih responsif**: bridge mendengar OSC Output Resolume di port UDP `7700`, lalu mengirim perubahan BPM melalui SSE (Server-Sent Events) ke browser gawai tanpa menunggu polling. Bila OSC Output belum diaktifkan, REST polling tetap menjadi fallback (default 1,2 detik pada bridge dan sekitar 650 ms di UI). Tidak ada angka BPM palsu saat REST offline.
5. **HEX input & copy**: STUDIO → PAD INSPECTOR → input `#RRGGBB` bisa diketik/paste; tombol COPY menyalin warna, juga tersedia color picker visual. Format warna diperiksa sebelum disimpan.
6. **Glow selama clip aktif**: warna solid pad tetap, tetapi `glow` menyala sepanjang status `connected=true` dari snapshot REST atau OSC Output `/composition/layers/{L}/clips/{C}/connected`. Glow mati setelah status `false`; ini **bukan** animasi sentuh sesaat. OSC feedback dari Resolume membantu mempercepat perubahan.

## Cara upgrade dari v3.0

1. **Tutup bridge v3.0**, backup seluruh folder v3 lama.
2. Ekstrak v3.0.1 ke folder baru. Jangan menimpa source v3 lama dahulu.
3. Jika perlu mempertahankan pad dan preset: salin **hanya** file `data/preset.json` dari folder v3 lama ke `data/preset.json` versi baru (buat folder `data` bila belum ada). Format preset v3 kompatibel; Macro mendapatkan opsi tambahan dengan default yang aman.
4. **Tidak perlu menyalin `data/settings.json`** dari versi lama; khususnya interval polling lama 2 detik berpotensi membuat BPM terlihat terlambat. Isi kembali pengaturan host/port melalui Settings jika sebelumnya diubah.
5. Jalankan `run_windows.bat`, masukkan PIN baru di browser HP/tablet atau aplikasi WebView Android lama, pada LAN yang sama.
6. Aktifkan **Preferences → Webserver → Enable Webserver & REST API** (default TCP `8080`) dan **Preferences → OSC → OSC Input** (default UDP `7000`) di Resolume.
7. Untuk feedback realtime: di Resolume **Preferences → OSC → OSC Output**, aktifkan, atur tujuan **localhost `127.0.0.1`** dan **UDP port `7700`** (bridge berjalan di PC yang sama). Di **Shortcuts → Edit OSC**, pilih preset **Output All OSC Messages** untuk pengujian; untuk produksi lebih baik buat preset output selektif untuk **tempo**, **connected** clip, serta macro yang digunakan agar lalu lintas minimal. Jika pengaturan feedback port di PULSE diubah, **restart bridge** agar listener pindah port.
8. Uji blackout dan restore pada **konten latihan**, kemudian uji masing-masing Quick FX terhadap parameter OSC target aslinya.

## Routing

| Koneksi | Arah | Port bawaan |
|---|---|---|
| HTTP browser / Android WebView → bridge | HP ke PC | TCP `8787` |
| REST bridge → Resolume | internal PC | TCP `8080` |
| OSC bridge → Resolume | internal PC | UDP `7000` |
| OSC Output Resolume → bridge | internal PC | UDP `7700` |
| SSE browser → bridge | HP ke PC, koneksi HTTP `GET /api/events` | TCP `8787` |

**Penting:** Buka port TCP `8787` pada Windows Firewall khusus *Private Network*. UDP `7000` dan `7700` tetap menggunakan localhost bila bridge dan Resolume berjalan di komputer yang sama; jangan expose akses controller ke internet. Di venue, gunakan LAN privat yang stabil.

## Pengoperasian FX

- Pilih **STUDIO**, klik ikon pensil di judul **QUICK FX / MACRO** atau tombol **EDIT FX**.
- Pilih salah satu FX; isi label, target OSC (gunakan **Resolume → Shortcuts → Edit OSC** untuk mengonfirmasi alamat), mode, warna, ON/OFF value.
- Contoh bila **FX bypass** menggunakan parameter boolean: pastikan arah ON/OFF sesuai keadaan *bypassed* (untuk mematikan bypass biasanya kirim `0`, untuk menyalakannya `1`). Tombol FX mengikuti **nilai parameter yang dikirim**, bukan mengetahui apakah efek terlihat atau tidak. Bila nilai boolean terbalik, atur ON/OFF terbalik.
- Klik **SAVE** di STUDIO. Kembali ke LIVE. Tekan FX untuk ON, tekan lagi untuk OFF.

## Batasan dan status pengujian

- 16 pengujian backend lulus, termasuk OSC parser, stream SSE, preservasi master opacity, validasi FX, normalisasi BPM dan status clip. Browser smoke test lulus pada Chromium untuk UI dan interaksi dengan data Resolume simulasi.
- Perbaikan **belum** diverifikasi pada instalasi Resolume Arena nyata. Pada rig sebenarnya, pengiriman OSC tidak sama dengan konfirmasi perubahan output. Status glow dan FX yang benar memerlukan REST API berjalan dan/atau OSC Output diaktifkan.
- Mekanisme blackout yang dipilih **mengubah master video opacity**, bukan komposisi layer. Saat blackout aktif, tidak boleh dipakai sekaligus dengan kontrol master opacity lain yang sedang mengubah nilainya, karena pemulihan akan mengembalikan nilai sebelum blackout.
- SSE membutuhkan koneksi browser ke bridge tetap terjaga; apabila stream tidak tersedia, REST polling tetap berfungsi.
- Port feedback dapat diubah di Settings, tetapi **listener baru menggunakan port tersebut setelah bridge restart**.
- Bila paket sudah berisi Android Studio project, **tidak** berarti APK installer telah dibangun. Aplikasi Android WebView yang menunjuk ke bridge versi baru akan memakai UI terbaru dari bridge yang diperbarui.

## Pengujian ulang

```powershell
python -m unittest discover -s tests -v
python tests/browser_smoke_v32.py
```

Test browser opsional membutuhkan paket `playwright` dan Chromium. `browser_smoke_v32.py` mensimulasikan REST di dalam browser; tidak melakukan koneksi perangkat Resolume nyata.

Referensi: https://resolume.com/support/en/osc · https://resolume.com/docs/restapi/ · https://resolume.com/support/en/websocket-api
