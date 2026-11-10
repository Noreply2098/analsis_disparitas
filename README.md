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
auth.py                 Login, registrasi, ubah password, sesi (bcrypt + SQLite)
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

tests/test_auth.py      Pengujian autentikasi (pytest tests -q)

auth_data/              Dibuat otomatis: users.db (akun pengguna, hanya berisi hash password)
uploads/                Dibuat otomatis saat aplikasi berjalan (kosong saat pertama kali dibuka)
  dataset.csv             Dataset aktif
  metadata.json           Catatan sumber data dan riwayat impor terakhir
  cadangan/               Cadangan otomatis (10 terbaru, beserta catatan sumbernya)
```

## Autentikasi (Login, Registrasi, Ubah Password, Logout)

- Pengguna yang belum masuk hanya melihat halaman **Masuk** dan **Daftar**. Halaman data
  tidak didaftarkan untuk mereka, sehingga tidak bisa dibuka lewat URL langsung.
- **Registrasi:** nama lengkap, username, email, password, dan konfirmasi password. Semua
  kesalahan ditampilkan sekaligus dengan pesan spesifik. Username dan email harus unik
  (tidak peka huruf besar/kecil); duplikat ditolak, termasuk bila dua pendaftaran terjadi
  bersamaan (batasan UNIQUE di database).
- **Aturan:** username 3-30 karakter (huruf, angka, titik, garis bawah); email berformat
  benar; password minimal 8 karakter, mengandung huruf dan angka, maksimal 72 byte (batas
  bcrypt), dan tidak sama dengan username.
- **Login:** username dan password divalidasi (tidak kosong, format benar). Bila gagal,
  pesannya selalu `Username atau password salah.` tanpa membedakan username yang tidak
  ada. Setelah 5 kali salah berturut-turut, akun dikunci 5 menit
  (`MAKS_GAGAL`, `DURASI_KUNCI_MENIT` di `auth.py`). Tombol tampilkan/sembunyikan password
  adalah ikon mata bawaan Streamlit pada kolom password.
- **Ubah password** (halaman Akun Saya): wajib memasukkan password lama yang benar; password
  baru harus memenuhi aturan di atas dan berbeda dari yang lama.
- **Logout:** tombol Keluar di sidebar dan halaman Akun Saya. Seluruh isi sesi dihapus,
  termasuk filter data.
- **Penyimpanan password:** hanya hash bcrypt (salt acak, 12 putaran) di `auth_data/users.db`.
  Password asli tidak pernah disimpan atau dicatat.
- **Batasan:** (1) Sesi hilang saat halaman di-refresh penuh atau tab ditutup (Streamlit
  tidak menyimpan cookie sendiri). (2) Seperti `uploads/`, `auth_data/` berada di sistem
  berkas sementara pada Streamlit Community Cloud: akun hilang saat aplikasi restart. Untuk
  penggunaan jangka panjang, pindahkan ke database persisten (mis. PostgreSQL/Supabase).
  (3) Dataset bersifat bersama: semua pengguna yang masuk melihat data yang sama.
  (4) Pendaftaran terbuka untuk siapa saja yang mengetahui URL aplikasi.

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
- Cadangan lokal tidak melindungi dari semua risiko kehilangan. Pada layanan hosting yang
  sistem berkasnya sementara (mis. Streamlit Community Cloud), isi `uploads/` hilang saat
  aplikasi di-restart. Unduh dataset secara berkala, atau gunakan penyimpanan persisten.
- Data contoh hanya untuk menguji fungsi. Untuk analisis dan kesimpulan penelitian,
  gunakan data dengan sumber, satuan, periode, dan cakupan wilayah yang dapat diverifikasi.
