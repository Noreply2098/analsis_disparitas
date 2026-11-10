import streamlit as st

from charts import (
    BIRU_TUA,
    grafik_batang,
    grafik_indikator,
    grafik_perbandingan,
    grafik_selisih,
    grafik_tren,
)
from laporan import blok_cetak
from utils import (
    baca_metadata,
    aktifkan_konsisten,
    daftar_tahun,
    duplikat_tahun,
    format_antarperiode,
    hitung_antarperiode,
    kemungkinan_duplikat_tahun,
    keterangan_batas_kategori,
    load_dataset,
    narasi_perbandingan,
    page_header,
    pilih_pembanding,
    satuan_indikator,
    susun_analisis,
    tabel_perbandingan,
    tampilkan_filter,
)

page_header(
    "Visualisasi",
    "Grafik perbandingan antarwilayah, posisi dan kontribusi tiap wilayah, "
    "serta perkembangan Indeks Williamson.",
)

df, pesan = load_dataset()

if df is None:
    st.info(pesan)
    st.stop()

if not daftar_tahun(df):
    st.info("Tidak ada data tahun yang valid untuk ditampilkan.")
    st.stop()

# ---- Filter bersama (sama dengan halaman Data Pendapatan dan Analisis) ----
f, df_f, info = tampilkan_filter(df)
if df_f.empty:
    st.stop()

tahun_list = daftar_tahun(df_f)
if not tahun_list:
    st.info("Tidak ada baris bertahun valid pada filter ini.")
    st.stop()

tahun = st.selectbox("Tahun Pengamatan", tahun_list, index=len(tahun_list) - 1)
meta = baca_metadata()

dup = duplikat_tahun(df_f, tahun)
if not dup.empty:
    st.warning(
        f"Data tahun {tahun} memiliki **{len(dup)} baris duplikat** (wilayah sama), "
        "sehingga grafik dapat tidak akurat. Rapikan di halaman Data Pendapatan."
    )

mungkin = kemungkinan_duplikat_tahun(df_f, tahun)
if not mungkin.empty:
    st.warning(
        f"Data tahun {tahun} memiliki **{len(mungkin)} baris kemungkinan duplikat** "
        "(identitas wilayah tidak lengkap), sehingga grafik dapat tidak akurat. "
        "Periksa di halaman Data Pendapatan."
    )

cetak = st.container(border=True)  # tombol cetak diisi setelah indikator dipilih

a, pesan_analisis = susun_analisis(df_f, tahun)

# ==============================
# PERBANDINGAN ANTARWILAYAH
# ==============================
with st.container(border=True):
    st.subheader(f"Perbandingan Antarwilayah Tahun {tahun}")
    indikator, urut = pilih_pembanding()
    satuan = satuan_indikator(indikator, meta)
    tabel_p, catatan_p = tabel_perbandingan(df_f, tahun, indikator, urut, satuan, list(f.wilayah))

    for c in catatan_p:
        st.warning(c)
    if tabel_p["Nilai"].notna().any():
        rata = a.hasil.rata_rata if (a is not None and indikator == "PDRB per kapita") else None
        st.altair_chart(grafik_perbandingan(tabel_p, indikator, urut, rata_rata=rata))
        keterangan = (
            f"Satuan: {satuan}. Label disingkat: rb = ribu, jt = juta, M = miliar. "
            "Warna gelap menandai nilai tertinggi dan oranye nilai terendah."
        )
        if rata is not None:
            keterangan += (
                f" Garis putus-putus oranye: rata-rata PDRB per kapita dibobot penduduk ({rata:,.2f})."
            )
        st.caption(keterangan)
    else:
        st.info(f"Tidak ada wilayah dengan data {indikator} yang tersedia pada tahun {tahun}.")
    kosong = tabel_p.loc[tabel_p["Nilai"].isna(), "Wilayah"].tolist()
    if kosong:
        st.caption(
            "Data tidak tersedia (tidak digambar, bukan bernilai nol): " + ", ".join(kosong) + "."
        )
    st.write(narasi_perbandingan(tabel_p, indikator))

# ==============================
# GRAFIK HASIL ANALISIS (posisi, kontribusi, indikator)
# ==============================
if a is None:
    with st.container(border=True):
        st.subheader("Grafik Hasil Analisis")
        st.info(f"Grafik posisi, kontribusi, dan indikator belum tersedia: {pesan_analisis}")
else:
    with st.container(border=True):
        st.subheader(f"Posisi Terhadap Rata-rata Tahun {tahun}")
        st.altair_chart(grafik_selisih(a.detail))
        st.caption(
            f"Selisih PDRB per kapita setiap wilayah terhadap rata-rata "
            f"({a.hasil.rata_rata:,.2f}). Biru berarti di atas rata-rata, "
            f"oranye di bawah rata-rata."
        )

    with st.container(border=True):
        st.subheader(f"Kontribusi Terhadap Ketimpangan Tahun {tahun}")
        st.altair_chart(grafik_batang(
            a.detail, "Porsi Kontribusi", "Porsi Kontribusi", BIRU_TUA,
            label_fn=lambda v: f"{v:.1%}", format_tooltip=".2%",
        ))
        st.caption(
            "Porsi tiap wilayah terhadap total ketimpangan, dihitung dari "
            "proporsi penduduk × selisih kuadrat terhadap rata-rata. Wilayah "
            "yang jauh dari rata-rata dan berpenduduk besar menyumbang lebih banyak."
        )

    with st.container(border=True):
        st.subheader(f"Posisi Indeks Williamson Tahun {tahun}")
        st.altair_chart(grafik_indikator(a.hasil.indeks))
        st.caption(f"{a.kategori}. {keterangan_batas_kategori()}")

# ==============================
# TREN ANTARPERIODE (sumber sama dengan tabel di halaman Analisis)
# ==============================
ap = hitung_antarperiode(df_f)
tren = ap.untuk_grafik()
with st.container(border=True):
    st.subheader("Perkembangan Indeks Williamson Antarperiode")
    if tren.empty:
        st.info("Indeks belum dapat dihitung untuk tahun mana pun pada filter ini.")
    else:
        st.altair_chart(grafik_tren(tren))
        st.caption(
            keterangan_batas_kategori() + " Pita warna menunjukkan kategori ketimpangan."
        )
    for peringatan in ap.peringatan:
        st.warning(peringatan)
    if not f.konsisten and not ap.perubahan_cakupan.empty:
        st.button("Aktifkan cakupan wilayah konsisten", on_click=aktifkan_konsisten, key="btn_konsisten_visual")
    with st.expander("Lihat tabel nilai (sama dengan tabel di halaman Analisis)"):
        st.dataframe(
            format_antarperiode(ap.tabel), hide_index=True,
            column_config={"Catatan": st.column_config.Column(width="large")},
        )

# ---- Cetak (mengikuti filter, tahun, dan indikator di atas) ----
with cetak:
    st.markdown("**Cetak Laporan**")
    blok_cetak(tahun, "grafik", f, indikator, urut)
