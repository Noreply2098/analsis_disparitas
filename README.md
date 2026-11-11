# Regional Income Analysis (RIA)

Aplikasi Streamlit untuk mengolah data PDRB per kapita dan jumlah penduduk serta
menganalisis disparitas pendapatan antarwilayah dengan Indeks Williamson.
Dikembangkan oleh Kelompok 2.

## Menjalankan

```
pip install -r requirements.txt
streamlit run app.py
```

## Struktur folder

```
app.py                  Pintu masuk aplikasi dan menu navigasi
auth.py                 Login, registrasi, sesi cookie, undangan, administrasi (bcrypt)
mailer.py               Pengiriman email SMTP (kode reset password)
kelola_akun.py          Alat CLI pengelola: buat kode reset dari terminal
db.py                   Koneksi database + skema (PostgreSQL via DATABASE_URL, atau SQLite)
storage.py              Folder data per pengguna + salinan ke database
utils.py                Konfigurasi, validasi, duplikat, dataset, cadangan, filter, ekspor, Indeks Williamson
charts.py               Grafik (Altair)
laporan.py              Dokumen dan tombol cetak
requirements.txt        Daftar library
Procfile                Perintah menjalankan aplikasi saat di-deploy
README.md               Dokumen ini
.gitignore              Berkas yang tidak ikut di-commit (cache, rahasia, data pengguna)
.streamlit/config.toml  Tema (light, putih + biru)

views/                  Satu file per halaman
  dashboard.py            Ringkasan data dan status analisis
  import_data.py          Import CSV/Excel (validasi, duplikat) dan input manual
  data_pendapatan.py      Tabel data (edit), filter & ekspor, dan pengelolaan dataset (sumber, cadangan)
  analisis.py             Indeks Williamson, antarperiode, perbandingan wilayah, rincian, langkah
  visualisasi.py          Seluruh grafik (perbandingan wilayah, posisi, kontribusi, tren)
  tentang.py              Informasi aplikasi
  login.py                Halaman masuk
  register.py             Halaman pendaftaran akun
  akun.py                 Profil, ubah password, dan keluar
  lupa_password.py        Minta kode reset dan atur password baru
  kelola_pengguna.py      Khusus admin: pengguna, kode undangan, kode reset

tests/test_auth.py      Pengujian (pip install -r requirements-dev.txt; pytest tests -q)

auth_data/              Dibuat otomatis bila tanpa DATABASE_URL: ria.db (SQLite lokal)
uploads/pengguna/<id>/   Dibuat otomatis: data pengguna yang masuk (tamu: folder temp sementara) saat aplikasi berjalan (kosong saat pertama kali dibuka)
  dataset.csv             Dataset aktif
  metadata.json           Catatan sumber data dan riwayat impor terakhir
  cadangan/               Cadangan otomatis (10 terbaru, beserta catatan sumbernya)
```

## Autentikasi, Akun, dan Data Pengguna

### Fitur
- **Masuk / Daftar / Keluar / Ubah password / Lupa password.** Akun bersifat opsional: aplikasi
  bisa langsung dipakai tanpa login (mode tamu, lihat di bawah). Halaman Akun Saya dan Kelola
  Pengguna hanya ada untuk pengguna yang masuk (dan admin), sehingga tidak bisa dibuka lewat URL.
- **Validasi dan pesan error spesifik** pada semua form. Login gagal selalu menampilkan
  `Username atau password salah.` (tidak membedakan username yang tidak ada). Setelah 5 kali
  salah berturut-turut akun dikunci 5 menit. Tombol tampilkan/sembunyikan password adalah ikon
  mata bawaan Streamlit di kolom password.
- **Password** hanya disimpan sebagai hash bcrypt (12 putaran, salt acak). Aturan password baru:
  minimal 8 karakter, ada huruf dan angka, maksimal 72 byte, tidak sama dengan username.
- **Username dan email unik** tanpa membedakan huruf besar/kecil (dijaga juga oleh batasan UNIQUE
  database terhadap pendaftaran bersamaan).

### Akun bertahan saat server restart (database)
Aplikasi memakai SQLAlchemy. Bila `DATABASE_URL` diisi, data akun, sesi, kode undangan, dan data
pengguna disimpan di **PostgreSQL** (Supabase, Neon, dsb.) sehingga tidak hilang saat restart.
Bila tidak diisi, dipakai SQLite lokal `auth_data/ria.db` (hanya untuk pengembangan; di hosting
dengan disk sementara, isinya hilang saat restart). Tabel dibuat otomatis.

Langkah di Streamlit Community Cloud:
1. Buat database PostgreSQL gratis (mis. Supabase atau Neon) dan salin connection string-nya.
   Bila koneksi langsung ditolak (Supabase memakai IPv6 untuk koneksi langsung), pakai
   connection string **Session pooler**.
2. Di *App settings -> Secrets* tempel (lihat `.streamlit/secrets.toml.example`):
   `DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DBNAME?sslmode=require"`
3. Reboot aplikasi, lalu **segera daftarkan akun pertama**: akun pertama otomatis menjadi
   Administrator.

### Sesi bertahan saat halaman di-refresh (cookie)
Setelah masuk, server membuat token acak dan menyimpannya di cookie `ria_sesi` (berlaku 7 hari,
`SameSite=Lax`, plus `Secure` di HTTPS). Database hanya menyimpan **hash sha256** token, jadi
isi database tidak bisa dipakai untuk menyamar. Token dicabut saat Keluar, saat password diubah
(semua perangkat), saat akun dinonaktifkan, dan otomatis saat kedaluwarsa. Catatan: cookie ini
diatur lewat JavaScript sehingga tidak bisa ber-flag `HttpOnly`; itu batasan Streamlit.

### Pendaftaran tidak lagi terbuka
- Akun pertama menjadi **Administrator**. Sesudahnya pendaftar wajib memasukkan **kode undangan
  sekali pakai** yang dibuat Administrator di halaman *Kelola Pengguna* (masa berlaku 1-30 hari;
  database hanya menyimpan hash kode, jadi kode hanya terlihat saat dibuat).
- Administrator dapat mengaktifkan/menonaktifkan akun (sesinya langsung diakhiri) dan mengubah
  peran. Administrator tidak dapat menonaktifkan atau menurunkan dirinya sendiri.
- Untuk pendaftaran bebas tanpa kode, isi secret `REGISTRASI_TERBUKA = "true"`.

### Data dipisah per pengguna
Setiap pengguna punya dataset, metadata, dan cadangan sendiri di `uploads/pengguna/<id>/`;
pengguna lain tidak pernah membacanya (kunci cache dokumen cetak juga memuat ID pengguna).
Isi folder disalin sebagai satu arsip zip ke tabel `berkas_pengguna` setiap kali berubah dan
dipulihkan otomatis saat folder lokal kosong (mis. setelah restart). Batas: 30 MB per pengguna
setelah dikompres; bila terlampaui, muncul peringatan di sidebar.

### Mode tamu: bisa dipakai tanpa login, data tidak disimpan
Membuka link langsung menampilkan aplikasi (Dashboard), bukan halaman login. Menu **Masuk**,
**Daftar**, dan **Lupa Password** tersedia di sidebar (bagian AKUN) tetapi opsional.

- Tamu bisa mengimpor data, menganalisis, dan membuat visualisasi. Banner "Mode tamu" di setiap
  halaman menjelaskan bahwa data dan cadangan hanya sementara.
- Data tamu hanya ada di **folder sementara milik sesi itu** (direktori temp server). Data itu
  tidak pernah masuk ke database maupun folder `uploads/`, tidak terbaca sesi lain, hilang saat
  halaman di-refresh atau ditutup, dan folder yang lama tidak dipakai (6 jam) dihapus otomatis.
- Tamu tidak memerlukan database: aplikasi tetap bisa dipakai tamu walau database sedang
  tidak terjangkau.
- Bila tamu **mendaftar lalu masuk di sesi yang sama**, data tamunya otomatis dipindahkan ke akun
  **hanya jika akun itu belum punya data** (data akun tidak pernah ditimpa); sesudahnya data
  tersimpan permanen.

### Lupa password
Halaman **Lupa Password** memakai kode reset sekali pakai (format `XXXX-XXXX`) dalam dua langkah:
1. **Minta kode.** Masukkan email akun; kode dikirim lewat email (berlaku 15 menit, maksimal
   3 permintaan per jam per akun). Pesan di layar selalu sama baik email terdaftar maupun tidak,
   sehingga halaman ini tidak bisa dipakai menebak email yang terdaftar.
2. **Buat password baru.** Masukkan email, kode, dan password baru (aturan sama seperti
   registrasi). Setelah berhasil, kode hangus, kunci akun dibuka, dan semua sesi di semua
   perangkat diakhiri.

Keamanan kode: hanya hash sha256 yang disimpan; setelah 5 tebakan salah kode hangus; meminta
kode baru membatalkan kode lama; akun nonaktif tidak bisa direset.

**Pengiriman email (SMTP)** diatur lewat secrets (lihat `.streamlit/secrets.toml.example`):
`SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, dan `SMTP_SECURITY`
(`starttls`, `ssl`, atau `none`). Contoh Gmail: host `smtp.gmail.com`, port 587, `starttls`,
dan **App Password** (bukan password Gmail biasa; perlu verifikasi 2 langkah). Email dikirim di
latar belakang; bila gagal, galatnya dicatat di log server.

**Tanpa SMTP**, halaman Lupa Password memberi tahu pengguna untuk meminta kode kepada
administrator: admin membuka *Kelola Pengguna*, memilih pengguna, lalu menekan **Buat kode reset
password** (berlaku 60 menit, hanya tampil sekali) dan mengirimkannya lewat jalur aman.

**Admin satu-satunya lupa password dan SMTP belum aktif?** Jalankan dari komputer Anda dengan
`DATABASE_URL` yang sama dengan aplikasi:

```
DATABASE_URL="postgresql://..." python kelola_akun.py kode-reset NAMA_ADMIN
```

### Yang belum ada
- **Data lama** yang sebelumnya tersimpan langsung di `uploads/dataset.csv` (sebelum fitur akun)
  tidak dipindahkan otomatis ke pengguna mana pun.
- **Verifikasi email saat registrasi.** Alamat email diperiksa formatnya dan keunikannya, tetapi
  belum dibuktikan milik pendaftar (pendaftaran sudah dibatasi kode undangan).

## Aturan data

- **Kolom wajib:** Nama Wilayah, Tahun, PDRB Per Kapita, Jumlah Penduduk.
  **Kolom opsional:** Kode Wilayah, Provinsi (membedakan wilayah yang namanya sama).
- Nama kolom boleh berbeda huruf besar/kecil atau spasi. Beberapa variasi dikenali
  (mis. `Wilayah`, `Periode`, `Penduduk`, `PDRB Perkapita`) dan dilaporkan saat import.
  `PDRB` saja sengaja tidak dipetakan karena bisa berarti PDRB total.
- **Tahun:** bilangan bulat 1900–2100. **Jumlah penduduk:** bilangan bulat lebih dari 0.
  **PDRB per kapita:** tidak boleh negatif atau kosong.
- **PDRB bernilai nol** tidak otomatis dianggap valid: baris ditandai dan perlu
  konfirmasi pengguna. Nilai yang jauh di luar sebaran wilayah lain (bila ada minimal 5
  wilayah pada tahun yang sama) ditandai untuk diperiksa, tidak dihapus.
- Angka `29.000.000` / `29,000,000` / `Rp 29.000.000` dikenali otomatis. Angka dengan
  satu pemisah ribuan seperti `104.000` ambigu (ribuan atau desimal) dan dilaporkan
  sebagai error; tulis `104000`.
- **Duplikat** = wilayah + tahun yang sama. Bila **Kode Wilayah** terisi, kode resmi itu
  menjadi identitas utama (kode + tahun); selain itu dipakai nama (tanpa membedakan
  huruf besar/kecil atau spasi ganda) + tahun + Provinsi (bila ada). Isi Kode Wilayah dengan
  kode lengkap (provinsi + kabupaten/kota) agar wilayah bernama sama tidak tertukar.
  Tidak ada data yang dihapus otomatis: pengguna memilih batalkan, simpan yang pertama,
  simpan yang terakhir, atau memilih baris sendiri.
- **Identitas tidak lengkap:** bila kolom Kode Wilayah/Provinsi dipakai tetapi kosong pada
  sebagian baris, baris itu ditandai. Dua baris dengan nama + tahun sama yang identitasnya
  kosong pada salah satunya ditampilkan sebagai **kemungkinan duplikat** dan perlu
  konfirmasi sebelum disimpan. Wilayah bernama sama dengan provinsi/kode berbeda dan
  terisi lengkap tidak dianggap sama.

## Pengelolaan dataset

- Mengganti dataset dan memulihkan cadangan memerlukan konfirmasi.
- **Simpan terverifikasi:** cadangan dataset lama, tulis berkas sementara, ganti secara
  atomik, lalu baca ulang dan bandingkan ISI dengan data yang dimaksud (urutan kolom,
  jumlah baris, nilai kosong, tipe angka, presisi, teks). Bila gagal, penyimpanan tidak
  dilaporkan berhasil dan dataset sebelumnya dikembalikan dari cadangan.
- **Pulihkan terverifikasi:** cadangan diperiksa dulu (terbaca dan memiliki kolom wajib);
  cadangan rusak ditolak tanpa mengubah apa pun. Setelah dipulihkan, dataset aktif
  dibandingkan dengan cadangan yang dipilih. Cadangan tidak pernah dihapus, termasuk saat
  pemangkasan, dan kondisi sebelum pemulihan ikut dicadangkan.
- Catatan sumber (sumber, tautan, tanggal pengambilan, satuan, catatan revisi) disimpan
  di `metadata.json` dan ikut dicadangkan/dipulihkan.

## Filter, ekspor, perbandingan, dan antarperiode (Tahap 2)

- **Filter bersama** (tahun awal/akhir, wilayah, provinsi bila ada lebih dari satu) muncul di
  halaman Data Pendapatan (tab Filter & Ekspor), Analisis, dan Visualisasi. Pilihannya sama di
  ketiga halaman selama sesi berjalan. Opsi diambil dari data yang ada, filter tidak mengubah
  dataset, dan hasil kosong ditampilkan sebagai pesan (bukan angka nol). Tombol Reset filter
  mengembalikan seluruh data. Tab Tabel Data (untuk mengedit) selalu menampilkan seluruh
  dataset agar menyimpan hasil edit tidak menimpa dataset dengan data terfilter.
- **Ekspor:** CSV dan Excel untuk seluruh dataset atau data sesuai filter, dengan jumlah baris
  ditampilkan sebelum diunduh dan nama berkas informatif (mis. `ria_data_2023_2025.xlsx`).
  Berkas Excel berisi lembar Data dan lembar Metadata (tanggal ekspor, filter, periode, jumlah
  baris, sumber, satuan, catatan revisi). Tabel antarperiode, perbandingan, dan rincian
  perhitungan di halaman Analisis juga dapat diunduh.
- **Perbandingan antarwilayah:** indikator PDRB per kapita, jumlah penduduk, dan PDRB (turunan)
  untuk satu tahun. *PDRB (turunan)* = PDRB per kapita × jumlah penduduk; ini bukan angka PDRB
  resmi dari sumber dan dapat berbeda karena pembulatan atau definisi penduduk. Wilayah tanpa
  data pada tahun itu ditulis "Data tidak tersedia" (tidak digambar dan tidak bernilai nol).
  Indeks Williamson bukan indikator per wilayah: ia ukuran agregat untuk kumpulan wilayah.
- **Indeks Williamson antarperiode:** dihitung terpisah untuk setiap tahun dengan rumus yang
  sama seperti halaman Analisis. Tabel (selisih absolut, persentase, arah) dan grafik tren
  berasal dari satu hasil hitung yang sama. Aturan yang dipakai:
  - Tahun yang punya kurang dari dua wilayah dengan data valid ditandai "Data tidak memadai"
    dan tidak dipaksakan menghasilkan indeks.
  - Perubahan dihitung terhadap tahun terdekat sebelumnya yang memiliki indeks; bila ada
    tahun yang dilewati, hal itu dicatat.
  - Bila kumpulan wilayah berbeda antartahun, tabel mencatat wilayah yang bertambah/hilang
    dan memperingatkan bahwa indeks tidak sepenuhnya sebanding. Opsi **Cakupan wilayah
    konsisten** (satu klik dari peringatan) hanya memakai wilayah dengan data valid di semua
    tahun terpilih dan menjelaskan wilayah yang dikecualikan. Opsi ini nonaktif secara
    bawaan agar Reset filter benar-benar menampilkan seluruh data.
  - Perubahan di bawah 0,005 disebut "relatif stabil". Ambang ini ketetapan aplikasi
    (`AMBANG_STABIL` di `utils.py`), bukan standar baku.
- **Batas kategori** (rendah < 0,3, sedang 0,3–0,5, tinggi > 0,5) adalah ketetapan aplikasi.
  Sumber rujukannya belum dicantumkan; isi `SUMBER_BATAS_KATEGORI` di `utils.py` dengan
  literatur yang dipakai penelitian agar tercantum di seluruh tampilan dan dokumen cetak.
- Dokumen cetak mengikuti filter, tahun, dan indikator yang sedang aktif, dan mencantumkan
  ringkasan filternya.

## Catatan repository dan deployment

- `.gitignore` sudah disertakan: cache Python, lingkungan virtual, `.env`,
  `.streamlit/secrets.toml`, berkas sementara, dan folder `uploads/` (data pengguna dan
  cadangan lokal) tidak ikut di-commit. `.streamlit/config.toml` (tema) tetap di-commit.
- `.gitignore` tidak menghapus berkas yang **sudah** dilacak Git. Bila `__pycache__/` atau
  `uploads/` pernah ter-commit, lepaskan dari pelacakan (berkas di komputer tidak terhapus):

  ```
  git rm -r --cached __pycache__ views/__pycache__ uploads
  git commit -m "Lepaskan cache dan data dari repository"
  ```
- Jangan pernah memasukkan token atau kredensial ke commit. Simpan di
  `.streamlit/secrets.toml` (sudah di-ignore) atau pengaturan Secrets platform deployment.
- Pada layanan hosting yang sistem berkasnya sementara (mis. Streamlit Community Cloud), folder
  `uploads/` hilang saat aplikasi di-restart. Dengan `DATABASE_URL` terisi, data pengguna
  disalin ke database dan dipulihkan otomatis (lihat bagian Autentikasi); tanpa itu, datanya
  hilang. Cadangan tetap tidak menggantikan unduhan berkala atau cadangan database.
- Data contoh hanya untuk menguji fungsi. Untuk analisis dan kesimpulan penelitian,
  gunakan data dengan sumber, satuan, periode, dan cakupan wilayah yang dapat diverifikasi.
