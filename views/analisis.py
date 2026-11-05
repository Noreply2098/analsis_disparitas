import numpy as np
import streamlit as st

from charts import (
    BIRU_TUA, grafik_batang, grafik_indikator, grafik_selisih,
)
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

# ==============================
# TURUNAN DATA
# ==============================
detail = hasil.detail.drop(columns=["Tahun"]).reset_index(drop=True)

total_kontribusi = detail["Kontribusi"].sum()
detail["Porsi Kontribusi"] = (
    detail["Kontribusi"] / total_kontribusi if total_kontribusi > 0 else 0.0
)
detail["Posisi"] = np.select(
    [detail["Selisih"] > 0, detail["Selisih"] < 0],
    ["Di atas rata-rata", "Di bawah rata-rata"],
    default="Sama dengan rata-rata",
)

kategori = interpretasi(hasil.indeks)
jumlah_wilayah = len(detail)

tertinggi = detail.loc[detail[COL_PDRB].idxmax()]
terendah = detail.loc[detail[COL_PDRB].idxmin()]
rasio = tertinggi[COL_PDRB] / terendah[COL_PDRB] if terendah[COL_PDRB] > 0 else None
pendorong = detail.loc[detail["Porsi Kontribusi"].idxmax()]

# Indeks tahun sebelumnya (tahun terdekat yang datanya memenuhi syarat)
sebelumnya = None
for t in reversed([t for t in tahun_list if t < tahun]):
    h, _ = hitung_williamson(df, t)
    if h is not None:
        sebelumnya = (t, h.indeks)
        break

# ==============================
# HASIL UTAMA
# ==============================
with st.container(border=True):
    st.subheader("Hasil Analisis Indeks Williamson")

    if sebelumnya:
        selisih_iw = hasil.indeks - sebelumnya[1]
        st.metric(
            "Nilai Indeks Williamson",
            f"{hasil.indeks:.4f}",
            delta=f"{selisih_iw:+.4f} dibanding {sebelumnya[0]}",
            delta_color="inverse",
            help="Panah merah = ketimpangan naik, hijau = ketimpangan turun.",
        )
    else:
        st.metric("Nilai Indeks Williamson", f"{hasil.indeks:.4f}")

    pesan_kategori = f"**{kategori}** pada tahun {tahun}."
    if kategori == "Ketimpangan rendah":
        st.success(pesan_kategori)
    elif kategori == "Ketimpangan sedang":
        st.warning(pesan_kategori)
    else:
        st.error(pesan_kategori)

    st.altair_chart(grafik_indikator(hasil.indeks))
    st.caption(
        "Kategori pada aplikasi ini: rendah (< 0,3), sedang (0,3 – 0,5), "
        "tinggi (> 0,5). Semakin besar nilai indeks, semakin timpang PDRB per "
        "kapita antarwilayah."
    )

    ringkasan = (
        f"Pada tahun {tahun}, PDRB per kapita tertinggi dimiliki **{tertinggi[COL_WILAYAH]}** "
        f"({tertinggi[COL_PDRB]:,.0f}) dan terendah **{terendah[COL_WILAYAH]}** "
        f"({terendah[COL_PDRB]:,.0f})"
    )
    if rasio:
        ringkasan += f", atau selisih {rasio:.2f} kali lipat"
    ringkasan += "."
    if jumlah_wilayah > 1 and total_kontribusi > 0:
        ringkasan += (
            f" Wilayah yang paling besar menyumbang ketimpangan adalah "
            f"**{pendorong[COL_WILAYAH]}** ({pendorong['Porsi Kontribusi']:.1%} "
            f"dari total kontribusi)."
        )
    st.write(ringkasan)

# ==============================
# RINGKASAN PERHITUNGAN
# ==============================
with st.container(border=True):
    st.subheader("Ringkasan Perhitungan")

    baris1 = st.columns(3)
    baris1[0].metric("Tahun Pengamatan", tahun)
    baris1[1].metric("Jumlah Wilayah", jumlah_wilayah)
    baris1[2].metric("Total Penduduk", f"{hasil.total_penduduk:,.0f}")

    baris2 = st.columns(3)
    baris2[0].metric("Rata-rata PDRB Per Kapita", f"{hasil.rata_rata:,.2f}",
                     help="Rata-rata dibobot jumlah penduduk.")
    with baris2[1]:
        st.metric("PDRB Tertinggi", f"{tertinggi[COL_PDRB]:,.0f}")
        st.caption(tertinggi[COL_WILAYAH])
    with baris2[2]:
        st.metric("PDRB Terendah", f"{terendah[COL_PDRB]:,.0f}")
        st.caption(terendah[COL_WILAYAH])

    baris3 = st.columns(3)
    baris3[0].metric(
        "Selisih Tertinggi–Terendah",
        f"{tertinggi[COL_PDRB] - terendah[COL_PDRB]:,.0f}",
    )
    baris3[1].metric("Rasio Tertinggi/Terendah", f"{rasio:.2f}×" if rasio else "—")

# ==============================
# ANALISIS LANJUTAN (TAB)
# ==============================
with st.container(border=True):
    st.subheader("Analisis Per Wilayah")
    tab_posisi, tab_kontribusi, tab_rincian, tab_langkah = st.tabs(
        ["Posisi", "Kontribusi", "Rincian", "Langkah"]
    )

    # ---- Posisi terhadap rata-rata ----
    with tab_posisi:
        st.caption(
            f"Selisih PDRB per kapita setiap wilayah terhadap rata-rata "
            f"({hasil.rata_rata:,.2f}). Biru berarti di atas rata-rata, "
            f"oranye di bawah rata-rata."
        )
        st.altair_chart(grafik_selisih(detail))

    # ---- Kontribusi terhadap ketimpangan ----
    with tab_kontribusi:
        st.caption(
            "Porsi tiap wilayah terhadap total ketimpangan, dihitung dari "
            "proporsi penduduk × selisih kuadrat terhadap rata-rata. Wilayah "
            "yang jauh dari rata-rata dan berpenduduk besar menyumbang lebih banyak."
        )
        st.altair_chart(grafik_batang(
            detail, "Porsi Kontribusi", "Porsi Kontribusi", BIRU_TUA,
            label_fn=lambda v: f"{v:.1%}", format_tooltip=".2%",
        ))

    # ---- Rincian tabel ----
    with tab_rincian:
        st.caption(
            "Detail perhitungan per wilayah. Geser tabel ke samping untuk "
            "melihat semua kolom."
        )

        tampil = detail[[
            COL_WILAYAH, COL_PDRB, COL_PENDUDUK, "Proporsi Penduduk",
            "Selisih", "Selisih Kuadrat", "Kontribusi", "Porsi Kontribusi", "Posisi",
        ]].copy()
        tampil.index = range(1, jumlah_wilayah + 1)
        tampil.index.name = "No."

        st.dataframe(
            tampil.style.format({
                COL_PDRB: "{:,.2f}",
                COL_PENDUDUK: "{:,.0f}",
                "Proporsi Penduduk": "{:.2%}",
                "Selisih": "{:,.2f}",
                "Selisih Kuadrat": "{:,.2f}",
                "Kontribusi": "{:,.2f}",
                "Porsi Kontribusi": "{:.2%}",
            }),
            column_config={
                kol: st.column_config.Column(width="medium") for kol in tampil.columns
            },
        )
        st.caption(
            f"Total: penduduk {tampil[COL_PENDUDUK].sum():,.0f} · "
            f"proporsi penduduk {tampil['Proporsi Penduduk'].sum():.2%} · "
            f"kontribusi {total_kontribusi:,.2f} · "
            f"porsi kontribusi {tampil['Porsi Kontribusi'].sum():.2%}"
        )

        st.download_button(
            "Unduh Rincian (CSV)",
            data=detail.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"rincian_williamson_{tahun}.csv",
            mime="text/csv",
        )

    # ---- Langkah perhitungan ----
    with tab_langkah:
        st.caption(f"Langkah perhitungan Indeks Williamson tahun {tahun} dengan angka sebenarnya.")
        akar = total_kontribusi ** 0.5
        st.markdown(
            f"**1. Total penduduk (N)**  \n"
            f"N = Σ fᵢ = **{hasil.total_penduduk:,.0f}**\n\n"
            f"**2. Rata-rata PDRB per kapita dibobot penduduk (Ȳ)**  \n"
            f"Ȳ = Σ (Yᵢ × fᵢ) / N = **{hasil.rata_rata:,.2f}**\n\n"
            f"**3. Jumlah kontribusi seluruh wilayah**  \n"
            f"Σ (Yᵢ − Ȳ)² × (fᵢ / N) = **{total_kontribusi:,.2f}**\n\n"
            f"**4. Akar dari jumlah kontribusi**  \n"
            f"√ {total_kontribusi:,.2f} = **{akar:,.2f}**\n\n"
            f"**5. Indeks Williamson**  \n"
            f"IW = {akar:,.2f} / {hasil.rata_rata:,.2f} = **{hasil.indeks:.4f}**"
        )
