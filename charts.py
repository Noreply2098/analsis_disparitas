"""Pembuat grafik Altair yang dipakai bersama oleh halaman Visualisasi dan Analisis."""

import altair as alt
import pandas as pd
import textwrap

from utils import (
    COL_WILAYAH,
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

HIJAU_PITA, KUNING_PITA, MERAH_PITA = "#2e9e5b", "#e6a817", "#d64545"

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


def _bungkus_nama(nama):
    return textwrap.fill(str(nama), LEBAR_NAMA, break_long_words=False)


def _sumbu_nama():
    return alt.Axis(
        labelLimit=0, labelPadding=10, labelOverlap=False,
        labelColor=TEKS, labelFontSize=13, labelExpr=LABEL_WILAYAH,
    )


# ==============================
# BATANG HORIZONTAL TERURUT
# ==============================
def grafik_batang(data, kolom, judul_nilai, warna_akhir, rata_rata=None,
                  label_fn=None, format_tooltip=",.0f", langkah=48):
    """Batang horizontal terurut, dengan label nilai langsung di ujung batang.

    label_fn: fungsi nilai -> teks label (default: singkatan rb/jt/M/T).
    rata_rata: bila diisi, digambar garis putus-putus oranye pada nilai tersebut.
    """
    d = data[[COL_WILAYAH, kolom]].copy()
    d["Nama"] = d[COL_WILAYAH].apply(_bungkus_nama)

    if label_fn is None:
        pembagi, sufiks = satuan(d[kolom].max())
        label_fn = lambda v: singkat(v, pembagi, sufiks)  # noqa: E731
    d["Label"] = d[kolom].apply(label_fn)

    if rata_rata is not None:
        d["Rata"] = rata_rata

    batas = d[kolom].max() * 1.3
    skala_x = alt.Scale(domain=[0, batas if batas > 0 else 1], nice=False)

    dasar = alt.Chart(d).encode(
        y=alt.Y("Nama:N", sort="-x", title=None, axis=_sumbu_nama()),
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
            alt.Tooltip(f"{kolom}:Q", title=judul_nilai, format=format_tooltip),
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

    return gaya(alt.layer(*lapisan).properties(height=alt.Step(langkah)))


# ==============================
# PERBANDINGAN ANTARWILAYAH (tertinggi / terendah ditandai)
# ==============================
def grafik_perbandingan(tabel, judul_nilai, urut="nilai", rata_rata=None, langkah=48):
    """Batang horizontal perbandingan wilayah dari tabel_perbandingan().

    Hanya wilayah dengan nilai tersedia yang digambar (data tidak tersedia tidak pernah
    digambar sebagai nol). Nilai tertinggi dan terendah diberi warna berbeda.
    """
    d = tabel[tabel["Nilai"].notna()].copy()
    if urut == "nama":
        d = d.sort_values("Wilayah", key=lambda x: x.str.lower(), kind="stable")
    else:
        d = d.sort_values(["Nilai", "Wilayah"], ascending=[False, True], kind="stable")
    d["Nama"] = d["Wilayah"].apply(_bungkus_nama)
    urutan = d["Nama"].tolist()

    pembagi, sufiks = satuan(d["Nilai"].abs().max())
    d["Label"] = d["Nilai"].apply(lambda v: singkat(v, pembagi, sufiks))
    d["Penanda"] = d["Keterangan"].where(d["Keterangan"].isin(["Tertinggi", "Terendah"]), "Lainnya")
    if rata_rata is not None:
        d["Rata"] = rata_rata

    batas = d["Nilai"].max() * 1.3
    skala_x = alt.Scale(domain=[0, batas if batas > 0 else 1], nice=False)
    dasar = alt.Chart(d).encode(
        y=alt.Y("Nama:N", sort=urutan, title=None, axis=_sumbu_nama()),
        x=alt.X("Nilai:Q", title=None, axis=None, stack=None, scale=skala_x),
    )

    ada = [k for k in ("Tertinggi", "Terendah", "Lainnya") if k in set(d["Penanda"])]
    warna = {"Tertinggi": BIRU_TUA, "Terendah": ORANYE, "Lainnya": BIRU_MUDA}
    batang = dasar.mark_bar(cornerRadiusEnd=6, size=24).encode(
        color=alt.Color(
            "Penanda:N",
            scale=alt.Scale(domain=ada, range=[warna[k] for k in ada]),
            legend=alt.Legend(title=None, orient="top", labelFontSize=12,
                              symbolType="square", labelColor=TEKS_PUDAR),
        ),
        tooltip=[
            alt.Tooltip("Wilayah:N", title="Wilayah"),
            alt.Tooltip("Nilai:Q", title=judul_nilai, format=",.0f"),
            alt.Tooltip("Tahun:Q", title="Tahun", format="d"),
        ],
    )
    label = dasar.mark_text(
        align="left", dx=7, fontSize=13, fontWeight=600, color=TEKS
    ).encode(text="Label:N")

    lapisan = [batang]
    if rata_rata is not None:
        lapisan.append(
            alt.Chart(d).mark_rule(strokeDash=[6, 4], color=ORANYE, strokeWidth=2)
            .encode(x=alt.X("Rata:Q", scale=skala_x, axis=None, stack=None))
        )
    lapisan.append(label)
    return gaya(alt.layer(*lapisan).properties(height=alt.Step(langkah)))


# ==============================
# BATANG BERDIVERGENSI (selisih terhadap rata-rata)
# ==============================
def grafik_selisih(data, kolom_selisih="Selisih", kolom_posisi="Posisi", langkah=48):
    """Selisih PDRB tiap wilayah terhadap rata-rata: biru di atas, oranye di bawah."""
    d = data[[COL_WILAYAH, kolom_selisih, kolom_posisi]].copy()
    d["Nama"] = d[COL_WILAYAH].apply(_bungkus_nama)

    pembagi, sufiks = satuan(d[kolom_selisih].abs().max())

    def tanda(v):
        if v > 0:
            return "+" + singkat(v, pembagi, sufiks)
        if v < 0:
            return "−" + singkat(-v, pembagi, sufiks)
        return "0"

    d["Label"] = d[kolom_selisih].apply(tanda)
    d["Nol"] = 0

    m = d[kolom_selisih].abs().max() * 1.5
    skala_x = alt.Scale(domain=[-m if m > 0 else -1, m if m > 0 else 1], nice=False)

    urutan = ["Di atas rata-rata", "Di bawah rata-rata", "Sama dengan rata-rata"]
    warna = {"Di atas rata-rata": BIRU, "Di bawah rata-rata": ORANYE,
             "Sama dengan rata-rata": "#9aa7b6"}
    ada = [p for p in urutan if p in set(d[kolom_posisi])]

    dasar = alt.Chart(d).encode(
        y=alt.Y("Nama:N", sort="-x", title=None, axis=_sumbu_nama()),
        x=alt.X(f"{kolom_selisih}:Q", title=None, axis=None, stack=None, scale=skala_x),
    )

    batang = dasar.mark_bar(cornerRadiusEnd=6, size=24).encode(
        color=alt.Color(
            f"{kolom_posisi}:N",
            scale=alt.Scale(domain=ada, range=[warna[p] for p in ada]),
            legend=alt.Legend(title=None, orient="top", labelFontSize=12,
                              symbolType="square", labelColor=TEKS_PUDAR),
        ),
        tooltip=[
            alt.Tooltip(f"{COL_WILAYAH}:N", title="Wilayah"),
            alt.Tooltip(f"{kolom_selisih}:Q", title="Selisih dari rata-rata", format=",.0f"),
        ],
    )

    nol = (
        alt.Chart(d)
        .mark_rule(color="#9aa7b6", strokeWidth=1.5)
        .encode(x=alt.X("Nol:Q", scale=skala_x, axis=None, stack=None))
    )

    teks_pos = dasar.mark_text(
        align="left", dx=7, fontSize=13, fontWeight=600, color=TEKS
    ).encode(text="Label:N").transform_filter(alt.datum[kolom_selisih] >= 0)
    teks_neg = dasar.mark_text(
        align="right", dx=-7, fontSize=13, fontWeight=600, color=TEKS
    ).encode(text="Label:N").transform_filter(alt.datum[kolom_selisih] < 0)

    return gaya(
        alt.layer(batang, nol, teks_pos, teks_neg).properties(height=alt.Step(langkah))
    )


# ==============================
# INDIKATOR POSISI INDEKS (gauge horizontal)
# ==============================
def grafik_indikator(indeks):
    """Pita kategori rendah/sedang/tinggi dengan penanda posisi nilai indeks."""
    xmax = max(0.6, float(indeks) * 1.15)
    skala = alt.Scale(domain=[0, xmax], nice=False)

    pita = pd.DataFrame({
        "awal": [0, 0.3, 0.5],
        "akhir": [0.3, 0.5, xmax],
        "tengah": [0.15, 0.4, (0.5 + xmax) / 2],
        "Kategori": ["Rendah", "Sedang", "Tinggi"],
    })
    kategori = ["Rendah", "Sedang", "Tinggi"]
    skala_warna = alt.Scale(
        domain=kategori, range=["#a8dcbc", "#f6dc93", "#f2aaaa"]
    )

    rect = (
        alt.Chart(pita)
        .mark_rect(cornerRadius=4)
        .encode(
            x=alt.X("awal:Q", scale=skala, axis=None),
            x2="akhir:Q",
            y=alt.value(34), y2=alt.value(70),
            color=alt.Color("Kategori:N", scale=skala_warna, legend=None),
        )
    )
    nama = (
        alt.Chart(pita)
        .mark_text(fontSize=12, fontWeight=600, color="#3d4b5c")
        .encode(
            x=alt.X("tengah:Q", scale=skala, axis=None),
            y=alt.value(52), text="Kategori:N",
        )
    )

    pos = indeks / xmax
    rata = "left" if pos < 0.08 else "right" if pos > 0.92 else "center"
    penanda = pd.DataFrame({"iw": [float(indeks)]})

    garis = (
        alt.Chart(penanda)
        .mark_rule(color=TEKS, strokeWidth=3)
        .encode(x=alt.X("iw:Q", scale=skala, axis=None), y=alt.value(28), y2=alt.value(76))
    )
    segitiga = (
        alt.Chart(penanda)
        .mark_point(shape="triangle-down", filled=True, color=TEKS, size=110)
        .encode(x=alt.X("iw:Q", scale=skala, axis=None), y=alt.value(22))
    )
    nilai = (
        alt.Chart(penanda)
        .mark_text(fontSize=14, fontWeight=700, color=TEKS, align=rata, baseline="bottom", dy=-2)
        .encode(
            x=alt.X("iw:Q", scale=skala, axis=None),
            y=alt.value(12),
            text=alt.Text("iw:Q", format=".4f"),
        )
    )

    return gaya(alt.layer(rect, nama, garis, segitiga, nilai).properties(height=84))


# ==============================
# TREN INDEKS WILLIAMSON
# ==============================
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
                                range=[HIJAU_PITA, KUNING_PITA, MERAH_PITA]),
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
