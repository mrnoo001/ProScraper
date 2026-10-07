# ProScraper

Aplikasi desktop untuk mengambil data dari halaman web secara visual. Pilih elemen langsung di browser, tinjau hasil, lalu ekspor ke Excel, CSV, atau JSON.

## Fitur

- Browser Chromium terlihat dengan sesi login lokal yang dapat digunakan kembali.
- Pemilih elemen visual dan selector yang dapat disunting.
- Pagination berupa tombol Next, pola URL, atau infinite scroll.
- Simpan progres dan data secara bertahap di SQLite, dengan jeda dan deduplikasi.
- Jeda, lanjutkan, dan ekspor hasil ke Excel, CSV, atau JSON.
- UI desktop menggunakan PySide6.

## Persyaratan

- Python 3.12 atau lebih baru.
- macOS atau Windows dengan sesi desktop grafis.
- Chromium untuk Playwright. Instalasi browser diperlukan satu kali per environment.

## Instalasi dan menjalankan

Pastikan Git sudah terpasang. Jalankan perintah berikut satu per satu di Terminal (macOS) atau PowerShell (Windows). Clone hanya perlu dilakukan sekali.

### macOS

```bash
git clone https://github.com/mrnoo001/ProScraper.git
cd ProScraper
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
proscraper
```

### Windows (PowerShell)

```powershell
git clone https://github.com/mrnoo001/ProScraper.git
cd ProScraper
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
proscraper
```

Untuk kebutuhan pengembangan (tes, lint, dan membuat bundle macOS), pasang juga dependensi pengembangan:

```bash
python -m pip install -e ".[dev]"
```

Alternatifnya, `requirements.txt` berisi dependensi runtime aplikasi. Untuk menjalankan dari source tanpa memasang paket editable, setelah menginstal requirements gunakan `PYTHONPATH=src python -m scraper_app.main` (macOS/Linux) atau `$env:PYTHONPATH="src"; python -m scraper_app.main` (PowerShell).

## Cara menggunakan

1. Buat proyek baru, masukkan nama proyek dan URL situs, lalu pilih **Buka browser**.
2. Jika situs meminta login atau verifikasi, selesaikan sendiri di jendela browser.
3. Pilih **Pilih elemen**, lalu klik contoh data di browser. Selector kontainer berulang dan field akan disarankan otomatis.
4. Ulangi untuk field lain. Periksa atau ubah nama kolom dan selector di aplikasi.
5. Pilih tipe **Angka** untuk nilai numerik. Untuk mengambil link/gambar, isi atribut dengan `href` atau `src`.
6. Pilih kunci deduplikasi bila ada kolom unik. Atur pagination dan jeda permintaan.
7. Pilih **Jalankan scraper**. Data disimpan bertahap; gunakan jeda dan lanjutkan bila dibutuhkan.
8. Ekspor hasil ke Excel, CSV, atau JSON.

Untuk pagination URL, pola harus mengandung `{page}`, misalnya `https://contoh.com/halaman/{page}`. Infinite scroll berhenti saat halaman tidak lagi bertambah atau mencapai batas halaman. Pratinjau menampilkan hingga 100 baris; seluruh hasil tetap disimpan di database.

## Penyimpanan dan privasi

Database, profil browser (termasuk cookies/login), dan log rotasi disimpan di direktori data aplikasi lokal:

- macOS: `~/Library/Application Support/ProScraper`
- Windows: `%APPDATA%\ProScraper`

Data tidak dikirim ke layanan ProScraper. ProScraper tidak memeriksa `robots.txt`; pengguna bertanggung jawab mematuhi ketentuan situs dan hukum yang berlaku. Aplikasi memberi jeda permintaan yang dapat diatur. CAPTCHA/verifikasi tidak dilewati otomatis dan harus diselesaikan sendiri di browser.

## Tes dan lint

```bash
python -m pytest
ruff check .
```

Tes integrasi browser menggunakan Chromium. Pastikan `python -m playwright install chromium` telah dijalankan.

## Membuat aplikasi macOS

Jalankan pada Mac setelah menginstal dependensi pengembangan dan Chromium:

```bash
python -m pip install -e ".[dev]"
python -m playwright install chromium
./packaging/build_macos.sh
```

Bundle tersedia di `dist/ProScraper.app`. Skrip ini menyertakan browser Chromium sehingga ukuran aplikasi menjadi besar. Penandatanganan, notarization, dan validasi untuk distribusi resmi harus dilakukan terpisah.

## Batasan saat ini

- Selector dibuat secara heuristik; periksa pratinjau dan sesuaikan selector pada situs dinamis.
- Browser dan pagination berjalan berurutan. Antrean halaman detail, banyak tab paralel, serta penjadwalan belum tersedia.
- Gambar disimpan sebagai URL/teks, bukan thumbnail yang ditanam ke Excel.
- Bundle macOS belum ditandatangani atau dinotariskan.

## Dependensi

Metadata paket, rentang versi, dan dependensi opsional pengembangan dikelola di [`pyproject.toml`](pyproject.toml). `requirements.txt` menyediakan dependensi runtime untuk instalasi berbasis pip.
