# Build APK PULSE ARENA 3.0

1. Instal Android Studio versi terbaru beserta Android SDK Platform 35 + SDK Build Tools.
2. File → Open → folder `android/PulseArenaAndroid`.
3. Selesaikan Gradle Sync. Android Gradle Plugin 8.7.3 memerlukan JDK 17 dan Gradle 8.9.
4. Build → Build APK(s) (Debug).
5. Ambil APK dari `app/build/outputs/apk/debug/app-debug.apk`.
6. Salin ke gawai Android; izinkan instalasi dari sumber terpercaya jika diperlukan. Buka PULSE ARENA, masukkan IP private PC Windows bridge (mis. 192.168.1.10), lalu PIN pairing dari jendela server.
7. Pastikan Android dan Windows pada Wi-Fi/LAN yang sama. Aplikasi ini memakai WebView private LAN (bukan aplikasi langsung UDP OSC tanpa server).

Alternatif build: unggah source project ke repo GitHub, aktifkan Actions, jalankan workflow `Build PULSE ARENA Android APK`, lalu unduh artifacts `PULSE_ARENA_v3_debug_APK` setelah job sukses.

**Tidak ada binary APK yang sudah dikompilasi dalam distribusi ini.** Hindari memasang APK dari pihak tak dikenal yang mengatasnamakan PULSE ARENA.
