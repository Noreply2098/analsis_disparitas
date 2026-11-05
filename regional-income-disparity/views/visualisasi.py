import streamlit as st
from matplotlib.figure import Figure

from utils import (
    COL_PENDUDUK, COL_PDRB, COL_WILAYAH,
    daftar_tahun, load_dataset, page_header, to_numeric_frame, tren_williamson,
)

page_header(
    "Visualisasi",
    "Grafik PDRB per kapita, jumlah penduduk, dan perkembangan Indeks Williamson.",
)


def grafik_batang(data, kolom, judul, label_y, warna):
    fig = Figure(figsize=(10, 5))
    ax = fig.subplots()
    ax.bar(data[COL_WILAYAH], data[kolom], color=warna, width=0.6)
    ax.set_title(judul)
    ax.set_xlabel("Nama Wilayah")
    ax.set_ylabel(label_y)
    for label in ax.get_xticklabels():
        label.set_rotation(30)
        label.set_ha("right")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    fig.tight_layout()
    return fig


def grafik_tren(tren):
    fig = Figure(figsize=(10, 5))
    ax = fig.subplots()
    ax.plot(tren["Tahun"], tren["Indeks Williamson"], marker="o",
            color="#2874B8", linewidth=2.5, markersize=8)
    ax.set_title("Perkembangan Indeks Williamson Antarwaktu")
    ax.set_xlabel("Tahun")
    ax.set_ylabel("Indeks Williamson")
    ax.set_xticks(tren["Tahun"])
    ax.grid(linestyle="--", alpha=0.3)
    fig.tight_layout()
    return fig


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

if not df_pdrb.empty:
    with st.container(border=True):
        st.pyplot(grafik_batang(
            df_pdrb, COL_PDRB,
            f"PDRB Per Kapita Antarwilayah Tahun {tahun}",
            "PDRB Per Kapita", "#2874B8",
        ))

if not df_penduduk.empty:
    with st.container(border=True):
        st.pyplot(grafik_batang(
            df_penduduk, COL_PENDUDUK,
            f"Jumlah Penduduk Antarwilayah Tahun {tahun}",
            "Jumlah Penduduk (Jiwa)", "#4C9BE8",
        ))

tren = tren_williamson(df)
if not tren.empty:
    with st.container(border=True):
        st.pyplot(grafik_tren(tren))
