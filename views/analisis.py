import streamlit as st

from utils import (
    COL_PENDUDUK, COL_PDRB, COL_WILAYAH,
    daftar_tahun, hitung_williamson, interpretasi, load_dataset, page_header,
)

page_header(
    "Analisis Disparitas Pendapatan",
    "Analisis tingkat ketimpangan pendapatan antarwilayah "
    "menggunakan metode Indeks Williamson.",
)

df, pesan = load_dataset()
tahun_list = daftar_tahun(df) if df is not None else []

with st.container(border=True):
    st.subheader("Pengaturan Analisis")
    st.write("Pilih tahun pengamatan untuk melakukan perhitungan ketimpangan pendapatan.")

    if not tahun_list:
        st.info(
            "**Dataset Belum Tersedia.** Silakan import atau input data "
            "pendapatan terlebih dahulu sebelum melakukan analisis."
        )
        st.stop()

    tahun = st.selectbox(
        "Tahun Pengamatan", tahun_list, index=len(tahun_list) - 1
    )

hasil, pesan = hitung_williamson(df, tahun)

if hasil is None:
    with st.container(border=True):
        st.subheader("Informasi Analisis")
        st.warning(pesan)
    st.stop()

# ---- Hasil ----
with st.container(border=True):
    st.subheader("Hasil Analisis Indeks Williamson")
    st.metric("Nilai Indeks Williamson", f"{hasil.indeks:.4f}")
    st.caption(f"{interpretasi(hasil.indeks)} (relatif).")

# ---- Ringkasan ----
with st.container(border=True):
    st.subheader("Ringkasan Perhitungan")
    kolom = st.columns(3)
    kolom[0].metric("Tahun Pengamatan", tahun)
    kolom[1].metric("Total Penduduk", f"{hasil.total_penduduk:,.0f}")
    kolom[2].metric("Rata-rata PDRB Per Kapita", f"{hasil.rata_rata:,.2f}")

# ---- Rincian ----
with st.container(border=True):
    st.subheader("Rincian Perhitungan Indeks Williamson")
    st.caption(
        "Detail perhitungan ketimpangan PDRB per kapita berdasarkan masing-masing wilayah."
    )

    rincian = hasil.detail.drop(columns=["Tahun"]).reset_index(drop=True)
    rincian.index = rincian.index + 1
    rincian.index.name = "No."

    st.dataframe(
        rincian.style.format({
            COL_PDRB: "{:,.2f}",
            COL_PENDUDUK: "{:,.0f}",
            "Proporsi Penduduk": "{:.2%}",
            "Selisih": "{:,.2f}",
            "Selisih Kuadrat": "{:,.2f}",
            "Kontribusi": "{:,.2f}",
        }),
    )
