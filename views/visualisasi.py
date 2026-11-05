import streamlit as st

from charts import BIRU, BIRU_TUA, grafik_batang, grafik_tren
from utils import (
    COL_PENDUDUK, COL_PDRB, COL_WILAYAH,
    daftar_tahun, hitung_williamson, load_dataset, page_header,
    to_numeric_frame, tren_williamson,
)

page_header(
    "Visualisasi",
    "Grafik PDRB per kapita, jumlah penduduk, dan perkembangan Indeks Williamson.",
)

# ==============================
# HALAMAN
# ==============================
df, pesan = load_dataset()

if df is None:
    st.info(pesan)
    st.stop()

tahun_list = daftar_tahun(df)
if not tahun_list:
    st.info("Tidak ada data tahun yang valid untuk ditampilkan.")
    st.stop()

tahun = st.selectbox("Tahun Pengamatan", tahun_list, index=len(tahun_list) - 1)

data = to_numeric_frame(df)
data = data[data["Tahun"] == tahun]

df_pdrb = data.dropna(subset=[COL_PDRB])
df_penduduk = data.dropna(subset=[COL_PENDUDUK])
df_penduduk = df_penduduk[df_penduduk[COL_PENDUDUK] > 0]

if df_pdrb.empty and df_penduduk.empty:
    st.warning("Tidak ada data valid untuk ditampilkan.")
    st.stop()

hasil, _ = hitung_williamson(df, tahun)

if not df_pdrb.empty:
    with st.container(border=True):
        st.subheader(f"PDRB Per Kapita Antarwilayah Tahun {tahun}")
        st.altair_chart(grafik_batang(
            df_pdrb, COL_PDRB, "PDRB Per Kapita", BIRU_TUA,
            rata_rata=hasil.rata_rata if hasil else None,
        ))
        keterangan = "Label disingkat: rb = ribu, jt = juta, M = miliar. "
        if hasil:
            keterangan += (
                f"Garis putus-putus oranye menunjukkan rata-rata PDRB per kapita "
                f"(dibobot jumlah penduduk): {hasil.rata_rata:,.2f}."
            )
        st.caption(keterangan)

if not df_penduduk.empty:
    with st.container(border=True):
        st.subheader(f"Jumlah Penduduk Antarwilayah Tahun {tahun}")
        st.altair_chart(grafik_batang(
            df_penduduk, COL_PENDUDUK, "Jumlah Penduduk (Jiwa)", BIRU,
        ))
        st.caption("Label disingkat: rb = ribu, jt = juta, M = miliar.")

tren = tren_williamson(df)
if not tren.empty:
    with st.container(border=True):
        st.subheader("Perkembangan Indeks Williamson Antarwaktu")
        st.altair_chart(grafik_tren(tren))
        st.caption(
            "Pita warna menunjukkan kategori ketimpangan: hijau (< 0,3) rendah, "
            "kuning (0,3 – 0,5) sedang, merah (> 0,5) tinggi."
        )
