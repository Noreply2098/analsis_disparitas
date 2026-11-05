import altair as alt
import streamlit as st

from utils import (
    COL_PENDUDUK, COL_PDRB, COL_WILAYAH,
    daftar_tahun, load_dataset, page_header, to_numeric_frame, tren_williamson,
)

page_header(
    "Visualisasi",
    "Grafik PDRB per kapita, jumlah penduduk, dan perkembangan Indeks Williamson.",
)

TINGGI = 340


def grafik_batang(data, kolom, label_y, warna):
    return (
        alt.Chart(data[[COL_WILAYAH, kolom]])
        .mark_bar(color=warna)
        .encode(
            x=alt.X(
                f"{COL_WILAYAH}:N", sort=None, title="Nama Wilayah",
                axis=alt.Axis(labelAngle=-45, labelLimit=160),
            ),
            y=alt.Y(f"{kolom}:Q", title=label_y, axis=alt.Axis(format="~s")),
            tooltip=[
                alt.Tooltip(f"{COL_WILAYAH}:N", title="Wilayah"),
                alt.Tooltip(f"{kolom}:Q", title=label_y, format=",.0f"),
            ],
        )
        .properties(height=TINGGI)
    )


def grafik_tren(tren):
    return (
        alt.Chart(tren)
        .mark_line(point=alt.OverlayMarkDef(size=90), color="#2874B8", strokeWidth=3)
        .encode(
            x=alt.X("Tahun:O", title="Tahun", axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Indeks Williamson:Q", title="Indeks Williamson"),
            tooltip=[
                alt.Tooltip("Tahun:O", title="Tahun"),
                alt.Tooltip("Indeks Williamson:Q", format=".4f"),
            ],
        )
        .properties(height=TINGGI)
    )


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
        st.subheader(f"PDRB Per Kapita Antarwilayah Tahun {tahun}")
        st.altair_chart(grafik_batang(df_pdrb, COL_PDRB, "PDRB Per Kapita", "#2874B8"))

if not df_penduduk.empty:
    with st.container(border=True):
        st.subheader(f"Jumlah Penduduk Antarwilayah Tahun {tahun}")
        st.altair_chart(
            grafik_batang(df_penduduk, COL_PENDUDUK, "Jumlah Penduduk (Jiwa)", "#4C9BE8")
        )

tren = tren_williamson(df)
if not tren.empty:
    with st.container(border=True):
        st.subheader("Perkembangan Indeks Williamson Antarwaktu")
        st.altair_chart(grafik_tren(tren))
