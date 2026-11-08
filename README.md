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
utils.py                Konfigurasi, validasi, duplikat, dataset, cadangan, Indeks Williamson
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
  data_pendapatan.py      Tabel data (edit) dan pengelolaan dataset (catatan sumber, unduh, cadangan)
  analisis.py             Hasil Indeks Williamson, ringkasan, rincian, langkah
  visualisasi.py          Seluruh grafik
  tentang.py              Informasi aplikasi

uploads/                Dibuat otomatis saat aplikasi berjalan (kosong saat pertama kali dibuka)
  dataset.csv             Dataset aktif
  metadata.json           Catatan sumber data dan riwayat impor terakhir
  cadangan/               Cadangan otomatis (10 terbaru, beserta catatan sumbernya)
```

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
