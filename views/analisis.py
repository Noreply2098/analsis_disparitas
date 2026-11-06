import numpy as np
import streamlit as st

from charts import (
    BIRU_TUA, grafik_batang, grafik_indikator, grafik_selisih,
)
from laporan import blok_cetak
from utils import (
    COL_PENDUDUK, COL_PDRB, COL_WILAYAH,
    daftar_tahun, load_dataset, narasi_ringkasan, page_header, susun_analisis,
)

page_header(
    "Analisis Disparitas Pendapatan",
    "Analisis tingkat ketimpangan pendapatan antarwilayah "
    "menggunakan metode Indeks Williamson.",
)

df, pesan = load_dataset()
tahun_list = daftar_tahun(df) if df is not None else []

pengaturan = st.container(border=True)
with pengaturan:
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

a, pesan = susun_analisis(df, tahun)

if a is None:
    with st.container(border=True):
        st.subheader("Informasi Analisis")
        st.warning(pesan)
    st.stop()

# ---- Cetak (satu bagian atau gabungan analisis + grafik) ----
with pengaturan:
    st.markdown("**Cetak Laporan**")
    blok_cetak(tahun, "analisis")

hasil, detail = a.hasil, a.detail
tertinggi, terendah = a.tertinggi, a.terendah

# ==============================
# HASIL UTAMA
# ==============================
with st.container(border=True):
    st.subheader("Hasil Analisis Indeks Williamson")

    if a.sebelumnya:
        selisih_iw = hasil.indeks - a.sebelumnya[1]
        st.metric(
            "Nilai Indeks Williamson",
            f"{hasil.indeks:.4f}",
            delta=f"{selisih_iw:+.4f} dibanding {a.sebelumnya[0]}",
            delta_color="inverse",
            help="Panah merah = ketimpangan naik, hijau = ketimpangan turun.",
        )
    else:
        st.metric("Nilai Indeks Williamson", f"{hasil.indeks:.4f}")

    pesan_kategori = f"**{a.kategori}** pada tahun {tahun}."
    if a.kategori == "Ketimpangan rendah":
        st.success(pesan_kategori)
    elif a.kategori == "Ketimpangan sedang":
        st.warning(pesan_kategori)
    else:
        st.error(pesan_kategori)

    st.altair_chart(grafik_indikator(hasil.indeks))
    st.caption(
        "Kategori pada aplikasi ini: rendah (< 0,3), sedang (0,3 – 0,5), "
        "tinggi (> 0,5). Semakin besar nilai indeks, semakin timpang PDRB per "
        "kapita antarwilayah."
    )
    st.write(narasi_ringkasan(a))

# ==============================
# RINGKASAN PERHITUNGAN
# ==============================
with st.container(border=True):
    st.subheader("Ringkasan Perhitungan")

    baris1 = st.columns(3)
    baris1[0].metric("Tahun Pengamatan", tahun)
    baris1[1].metric("Jumlah Wilayah", a.jumlah_wilayah)
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
    baris3[1].metric("Rasio Tertinggi/Terendah", f"{a.rasio:.2f}×" if a.rasio else "—")

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
        tampil.index = range(1, a.jumlah_wilayah + 1)
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
            f"kontribusi {a.total_kontribusi:,.2f} · "
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
        akar = a.total_kontribusi ** 0.5
        st.markdown(
            f"**1. Total penduduk (N)**  \n"
            f"N = Σ fᵢ = **{hasil.total_penduduk:,.0f}**\n\n"
            f"**2. Rata-rata PDRB per kapita dibobot penduduk (Ȳ)**  \n"
            f"Ȳ = Σ (Yᵢ × fᵢ) / N = **{hasil.rata_rata:,.2f}**\n\n"
            f"**3. Jumlah kontribusi seluruh wilayah**  \n"
            f"Σ (Yᵢ − Ȳ)² × (fᵢ / N) = **{a.total_kontribusi:,.2f}**\n\n"
            f"**4. Akar dari jumlah kontribusi**  \n"
            f"√ {a.total_kontribusi:,.2f} = **{akar:,.2f}**\n\n"
            f"**5. Indeks Williamson**  \n"
            f"IW = {akar:,.2f} / {hasil.rata_rata:,.2f} = **{hasil.indeks:.4f}**"
        )
