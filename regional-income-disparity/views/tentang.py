import streamlit as st

from utils import page_header

page_header(
    "Tentang Regional Income Analysis",
    "Sistem otomatisasi pengolahan data dan analisis disparitas "
    "pendapatan regional berbasis Python.",
)

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

with st.container(border=True):
    st.subheader("Tujuan Pengembangan")
    st.markdown(
        "- Mempermudah proses pengolahan data ekonomi regional.\n"
        "- Menyediakan fitur import dan input data secara manual.\n"
        "- Menghitung tingkat disparitas menggunakan Indeks Williamson.\n"
        "- Menyajikan hasil analisis dalam bentuk tabel dan visualisasi.\n"
        "- Mendukung kebutuhan penelitian dan pembelajaran akademik."
    )

with st.container(border=True):
    st.subheader("Metode Analisis")
    st.write(
        "Metode yang digunakan dalam aplikasi ini adalah Indeks Williamson, "
        "yaitu metode untuk mengukur tingkat ketimpangan pembangunan atau "
        "pendapatan antarwilayah dengan mempertimbangkan jumlah penduduk."
    )
    st.markdown("**Indikator yang digunakan:**")
    st.markdown(
        "- Nama Wilayah\n- Tahun Pengamatan\n- PDRB Per Kapita\n- Jumlah Penduduk"
    )

with st.container(border=True):
    st.subheader("Teknologi yang Digunakan")
    teknologi = ["Python", "Streamlit", "Pandas", "Matplotlib"]
    for kol, (no, nama) in zip(st.columns(4), enumerate(teknologi, start=1)):
        kol.markdown(f"### {no:02d}")
        kol.write(nama)

with st.container(border=True):
    st.subheader("Informasi Pengembangan")
    st.markdown(
        "**Nama Aplikasi:** Regional Income Analysis (RIA)  \n"
        "**Versi:** 1.0  \n"
        "**Platform:** Web Application  \n"
        "**Bidang:** Analisis Ekonomi Regional  \n"
        "**Metode:** Indeks Williamson  \n"
        "**Lisensi dan Hak Cipta:** Informasi perlindungan program komputer "
        "menjadi bagian dari dokumentasi pengembangan aplikasi."
    )
