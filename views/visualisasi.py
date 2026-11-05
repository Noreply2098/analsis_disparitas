import textwrap

import altair as alt
import pandas as pd
import streamlit as st

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
# GAYA GRAFIK
# ==============================
BIRU_TUA = "#1F5F9E"
BIRU = "#2874B8"
BIRU_MUDA = "#6FB1EC"
TEKS = "#26364a"
TEKS_PUDAR = "#5b6b7f"
ORANYE = "#E07A1F"

# Nama panjang dipecah ke beberapa baris (pemisah \n) agar tidak terpotong di layar kecil
LABEL_WILAYAH = "split(datum.label, '\\n')"
LEBAR_NAMA = 16  # jumlah karakter per baris pada label wilayah


def gaya(grafik):
    """Terapkan tampilan seragam: bersih, tanpa bingkai, teks mudah dibaca."""
    return (
        grafik
        .configure_view(stroke=None)
        .configure_axis(
            domain=False,
            ticks=False,
            labelColor=TEKS_PUDAR,
            titleColor=TEKS_PUDAR,
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight="normal",
            gridColor="#e6ecf3",
        )
    )


def satuan(nilai_maks):
    """Pilih satuan singkatan (rb, jt, M, T) sesuai besar nilai."""
    for pembagi, sufiks in ((1e12, "T"), (1e9, "M"), (1e6, "jt"), (1e3, "rb")):
        if nilai_maks >= pembagi:
            return pembagi, sufiks
    return 1, ""


def singkat(nilai, pembagi, sufiks):
    teks = f"{nilai / pembagi:.1f}"
    if teks.endswith(".0"):
        teks = teks[:-2]
    return f"{teks} {sufiks}".strip()


# ==============================
# GRAFIK
# ==============================
def grafik_batang(data, kolom, judul_nilai, warna_akhir, rata_rata=None):
    """Batang horizontal terurut, dengan label nilai langsung di ujung batang."""
    d = data[[COL_WILAYAH, kolom]].copy()
    d["Nama"] = d[COL_WILAYAH].astype(str).apply(
        lambda n: textwrap.fill(n, LEBAR_NAMA, break_long_words=False)
    )
    pembagi, sufiks = satuan(d[kolom].max())
    d["Label"] = d[kolom].apply(lambda v: singkat(v, pembagi, sufiks))

    if rata_rata is not None:
        d["Rata"] = rata_rata

    batas = d[kolom].max() * 1.3
    skala_x = alt.Scale(domain=[0, batas], nice=False)

    dasar = alt.Chart(d).encode(
        y=alt.Y(
            "Nama:N", sort="-x", title=None,
            axis=alt.Axis(labelLimit=0, labelPadding=10, labelOverlap=False,
                          labelColor=TEKS, labelFontSize=13,
                          labelExpr=LABEL_WILAYAH),
        ),
        x=alt.X(f"{kolom}:Q", title=None, axis=None, stack=None, scale=skala_x),
    )

    warna = alt.Gradient(
        gradient="linear",
        stops=[alt.GradientStop(color=BIRU_MUDA, offset=0),
               alt.GradientStop(color=warna_akhir, offset=1)],
        x1=0, x2=1, y1=0, y2=0,
    )

    batang = dasar.mark_bar(cornerRadiusEnd=6, size=24, color=warna).encode(
        tooltip=[
            alt.Tooltip(f"{COL_WILAYAH}:N", title="Wilayah"),
            alt.Tooltip(f"{kolom}:Q", title=judul_nilai, format=",.0f"),
        ]
    )
    label = dasar.mark_text(
        align="left", dx=7, fontSize=13, fontWeight=600, color=TEKS
    ).encode(text="Label:N")

    lapisan = [batang]
    if rata_rata is not None:
        # axis=None harus sama dengan lapisan batang agar sumbu bisa digabung
        garis = (
            alt.Chart(d)
            .mark_rule(strokeDash=[6, 4], color=ORANYE, strokeWidth=2)
            .encode(x=alt.X("Rata:Q", scale=skala_x, axis=None, stack=None))
        )
        lapisan.append(garis)
    lapisan.append(label)  # label di lapisan teratas agar tidak tertimpa garis

    return gaya(alt.layer(*lapisan).properties(height=alt.Step(48)))


def grafik_tren(tren):
    """Tren Indeks Williamson dengan pita warna kategori ketimpangan."""
    ymax = max(0.6, float(tren["Indeks Williamson"].max()) * 1.2)
    skala_y = alt.Scale(domain=[0, ymax], nice=False)

    kategori = ["Rendah", "Sedang", "Tinggi"]
    pita = (
        alt.Chart(pd.DataFrame({
            "bawah": [0, 0.3, 0.5],
            "atas": [0.3, 0.5, ymax],
            "Kategori": kategori,
        }))
        .mark_rect(opacity=0.13)
        .encode(
            y=alt.Y("bawah:Q", scale=skala_y),
            y2="atas:Q",
            color=alt.Color(
                "Kategori:N", legend=None,
                scale=alt.Scale(domain=kategori,
                                range=["#2e9e5b", "#e6a817", "#d64545"]),
            ),
        )
    )

    dasar = alt.Chart(tren).encode(
        x=alt.X("Tahun:O", title=None,
                axis=alt.Axis(labelAngle=0, labelColor=TEKS, labelFontSize=13)),
        y=alt.Y("Indeks Williamson:Q", scale=skala_y, title="Indeks Williamson",
                axis=alt.Axis(grid=False, tickCount=6, format=".1f")),
    )

    isi = alt.Gradient(
        gradient="linear",
        stops=[alt.GradientStop(color="rgba(40,116,184,0.35)", offset=0),
               alt.GradientStop(color="rgba(40,116,184,0.03)", offset=1)],
        x1=1, x2=1, y1=0, y2=1,
    )
    area = dasar.mark_area(color=isi)
    garis = dasar.mark_line(color=BIRU, strokeWidth=3)
    titik = dasar.mark_point(
        filled=True, color=BIRU, size=130, stroke="white", strokeWidth=2,
        opacity=1,
    ).encode(
        tooltip=[
            alt.Tooltip("Tahun:O", title="Tahun"),
            alt.Tooltip("Indeks Williamson:Q", format=".4f"),
        ]
    )
    nilai = dasar.mark_text(
        dy=-18, fontSize=13, fontWeight=600, color=TEKS
    ).encode(text=alt.Text("Indeks Williamson:Q", format=".4f"))

    return gaya(alt.layer(pita, area, garis, titik, nilai).properties(height=320))


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
