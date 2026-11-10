import streamlit as st

from utils import (
    REQUIRED_COLUMNS,
    page_header,
)

page_header(
    "Tentang Regional Income Analysis",
    "Sistem otomatisasi pengolahan data dan analisis disparitas "
    "pendapatan regional berbasis Python.",
)

# ---- Profil ----
with st.container(border=True):
    st.subheader("Profil Aplikasi")
    st.write(
        "Regional Income Analysis (RIA) merupakan aplikasi berbasis web yang "
        "dikembangkan untuk membantu proses pengolahan data ekonomi regional "
        "dan menganalisis tingkat ketimpangan pendapatan antarwilayah."
    )
    st.write(
        "Aplikasi ini menggunakan Python sebagai bahasa pemrograman utama, "
        "dengan metode Indeks Williamson untuk mengukur tingkat disparitas "
        "pendapatan regional."
    )
    ringkas = [
        ("Versi", "1.0"),
        ("Platform", "Web"),
        ("Bidang", "Ekonomi Regional"),
        ("Metode", "Indeks Williamson"),
    ]
    for kol, (label, nilai) in zip(st.columns(4), ringkas):
        kol.caption(label)
        kol.markdown(f"#### {nilai}")

# ---- Tujuan ----
with st.container(border=True):
    st.subheader("Tujuan Pengembangan")
    st.markdown(
        "- Mempermudah proses pengolahan data ekonomi regional.\n"
        "- Menyediakan fitur import dan input data secara manual.\n"
        "- Menghitung tingkat disparitas menggunakan Indeks Williamson.\n"
        "- Menyajikan hasil analisis dalam bentuk tabel dan visualisasi.\n"
        "- Mendukung kebutuhan penelitian dan pembelajaran akademik."
    )

# ---- Fitur ----
with st.container(border=True):
    st.subheader("Fitur Utama")
    fitur = [
        (":material/upload_file:", "Import Data",
         "Unggah CSV/Excel dengan validasi per baris dan deteksi duplikat."),
        (":material/edit_note:", "Input Manual",
         "Tambahkan data wilayah langsung melalui tabel isian."),
        (":material/table_chart:", "Kelola Data",
         "Ubah data, filter, unduh CSV/Excel, cadangkan, dan pulihkan dataset."),
        (":material/calculate:", "Analisis Disparitas",
         "Indeks Williamson per tahun, perkembangannya antarperiode, dan perbandingan antarwilayah."),
        (":material/bar_chart:", "Visualisasi",
         "Grafik PDRB, penduduk, posisi dan kontribusi wilayah, serta tren indeks."),
        (":material/dashboard:", "Dashboard",
         "Ringkasan data dan status analisis tahun terbaru."),
    ]
    for baris in (fitur[:3], fitur[3:]):
        for kol, (ikon, judul, deskripsi) in zip(st.columns(3), baris):
            with kol.container(border=True):
                st.markdown(f"**{ikon} {judul}**")
                st.caption(deskripsi)

# ---- Metode ----
with st.container(border=True):
    st.subheader("Metode Analisis")
    st.write(
        "Indeks Williamson mengukur tingkat ketimpangan pembangunan atau "
        "pendapatan antarwilayah dengan mempertimbangkan jumlah penduduk. "
        "Semakin besar nilainya, semakin tinggi ketimpangan antarwilayah."
    )
    st.latex(
        r"IW = \frac{\sqrt{\sum_{i=1}^{n} (Y_i - \bar{Y})^2 \cdot \frac{f_i}{N}}}{\bar{Y}}"
    )
    st.markdown(
        "- **Yᵢ**: PDRB per kapita wilayah ke-*i*\n"
        "- **Ȳ**: rata-rata PDRB per kapita, dibobot jumlah penduduk\n"
        "- **fᵢ**: jumlah penduduk wilayah ke-*i*\n"
        "- **N**: total penduduk seluruh wilayah"
    )

    st.markdown("**Kategori hasil pada aplikasi ini:**")
    kat = st.columns(3)
    kat[0].success("**< 0,3**  \nKetimpangan rendah")
    kat[1].warning("**0,3 – 0,5**  \nKetimpangan sedang")
    kat[2].error("**> 0,5**  \nKetimpangan tinggi")

# ---- Data ----
with st.container(border=True):
    st.subheader("Kebutuhan Data")
    st.write("Dataset harus memiliki kolom berikut:")
    st.markdown("\n".join(f"- {kol}" for kol in REQUIRED_COLUMNS))
    st.caption(
        "Perhitungan per tahun memerlukan minimal dua wilayah dengan data yang "
        "valid. Pastikan sumber data dan satuan yang digunakan dicantumkan "
        "dalam penelitian."
    )

# ---- Alur ----
with st.container(border=True):
    st.subheader("Alur Penggunaan")
    langkah = [
        ("Import Data", "Unggah file atau input manual"),
        ("Periksa Data", "Rapikan data di halaman Data Pendapatan"),
        ("Analisis", "Pilih tahun dan lihat Indeks Williamson"),
        ("Visualisasi", "Lihat grafik hasil analisis"),
    ]
    for kol, (no, (judul, ket)) in zip(st.columns(4), enumerate(langkah, start=1)):
        kol.markdown(f"### {no:02d}")
        kol.markdown(f"**{judul}**")
        kol.caption(ket)

# ---- Teknologi ----
with st.container(border=True):
    st.subheader("Teknologi yang Digunakan")
    teknologi = [
        ("Python", "Bahasa pemrograman utama"),
        ("Streamlit", "Antarmuka web"),
        ("Pandas", "Pengolahan data"),
        ("Altair", "Pembuatan grafik interaktif"),
    ]
    for kol, (nama, ket) in zip(st.columns(4), teknologi):
        kol.markdown(f"**{nama}**")
        kol.caption(ket)

# ---- Tim ----
with st.container(border=True):
    st.subheader("Tim Pengembang")
    st.write("Dikembangkan oleh **Kelompok 2**:")
    anggota = ["Koko Bonardo Hasibuan", "Novri Aldy", "Siti Aisah Lingga", "Salsabila"]
    for kol, nama in zip(st.columns(4), anggota):
        with kol.container(border=True):
            st.markdown(f"#### :material/person:  \n**{nama}**")

# ---- Informasi pengembangan ----
with st.container(border=True):
    st.subheader("Informasi Pengembangan")
    st.markdown(
        "**Nama Aplikasi:** Regional Income Analysis (RIA)  \n"
        "**Versi:** 1.0  \n"
        "**Dikembangkan oleh:** Kelompok 2  \n"
        "**Lisensi dan Hak Cipta:** Informasi perlindungan program komputer "
        "menjadi bagian dari dokumentasi pengembangan aplikasi."
    )
