import streamlit as st

from utils import (
    COL_PENDUDUK, COL_PDRB, COL_TAHUN, COL_WILAYAH,
    daftar_tahun, hitung_williamson, interpretasi, load_dataset, page_header,
)

page_header(
    "Dashboard Regional Income Analysis",
    "Sistem otomatisasi pengolahan data dan analisis disparitas "
    "pendapatan regional berbasis Python.",
)

total_wilayah = total_tahun = total_data = 0
tahun_terbaru = None
hasil = None

df, _ = load_dataset()

if df is not None:
    total_wilayah = df[COL_WILAYAH].nunique()
    total_data = len(df)
    tahun_list = daftar_tahun(df)
    total_tahun = len(tahun_list)

    if tahun_list:
        tahun_terbaru = tahun_list[-1]
        hasil, _ = hitung_williamson(df, tahun_terbaru)

# ---- Statistik ----
kolom = st.columns(4)

with kolom[0].container(border=True):
    st.metric("Total Wilayah", total_wilayah)
    st.caption("Wilayah dalam dataset")

with kolom[1].container(border=True):
    st.metric("Tahun Pengamatan", total_tahun)
    st.caption(f"Data terbaru tahun {tahun_terbaru}" if tahun_terbaru else "Belum ada data")

with kolom[2].container(border=True):
    st.metric("Total Data", total_data)
    st.caption("Seluruh catatan data regional")

with kolom[3].container(border=True):
    st.metric("Indeks Williamson", f"{hasil.indeks:.4f}" if hasil else "—")
    st.caption(interpretasi(hasil.indeks) if hasil else "Belum tersedia")

# ---- Status analisis ----
with st.container(border=True):
    st.subheader("Status Analisis Regional")
    if hasil:
        st.success(
            f"**Analisis tersedia.** Indeks Williamson berhasil dihitung "
            f"berdasarkan data tahun {tahun_terbaru}."
        )
    else:
        st.warning(
            "**Analisis belum tersedia.** Silakan tambahkan data regional "
            "yang valid untuk melakukan analisis."
        )

# ---- Informasi penelitian ----
with st.container(border=True):
    st.subheader("Informasi Penelitian")
    st.write(
        "Aplikasi Regional Income Analysis (RIA) digunakan untuk membantu "
        "proses pengolahan data PDRB per kapita dan jumlah penduduk serta "
        "analisis disparitas antarwilayah menggunakan metode Indeks Williamson."
    )
    st.write(
        "Data dapat dimasukkan melalui fitur import dataset atau input manual. "
        "Pastikan sumber data dan satuan yang digunakan dicantumkan dalam penelitian."
    )

# ---- Alur proses ----
with st.container(border=True):
    st.subheader("Alur Proses Analisis")
    langkah = ["Import Data Regional", "Pengolahan Data",
               "Analisis Disparitas", "Hasil Visualisasi"]
    for kol, (no, teks) in zip(st.columns(4), enumerate(langkah, start=1)):
        kol.markdown(f"### {no:02d}")
        kol.write(teks)
