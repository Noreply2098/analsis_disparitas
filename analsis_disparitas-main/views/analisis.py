import streamlit as st

from laporan import blok_cetak
from utils import (
    COL_PDRB,
    COL_PENDUDUK,
    COL_WILAYAH,
    baca_metadata,
    aktifkan_konsisten,
    daftar_tahun,
    duplikat_tahun,
    format_antarperiode,
    format_lintas_tahun,
    format_perbandingan,
    hitung_antarperiode,
    kemungkinan_duplikat_tahun,
    ke_csv_bytes,
    ke_excel_dengan_metadata,
    keterangan_batas_kategori,
    load_dataset,
    nama_file_ekspor,
    narasi_antarperiode,
    narasi_perbandingan,
    narasi_ringkasan,
    page_header,
    pilih_pembanding,
    ringkasan_ekspor,
    satuan_indikator,
    susun_analisis,
    tabel_lintas_tahun,
    tabel_perbandingan,
    tampilkan_filter,
)
import pandas as pd

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

page_header(
    "Analisis Disparitas Pendapatan",
    "Analisis tingkat ketimpangan pendapatan antarwilayah "
    "menggunakan metode Indeks Williamson.",
)

df, pesan = load_dataset()

if df is None or not daftar_tahun(df):
    with st.container(border=True):
        st.subheader("Pengaturan Analisis")
        st.info(
            "**Dataset Belum Tersedia.** Silakan import atau input data "
            "pendapatan terlebih dahulu sebelum melakukan analisis."
        )
    st.stop()

# ---- Filter bersama (sama dengan halaman Data Pendapatan dan Visualisasi) ----
f, df_f, info = tampilkan_filter(df)
if df_f.empty:
    st.stop()

tahun_list = daftar_tahun(df_f)
if not tahun_list:
    st.info("Tidak ada baris bertahun valid pada filter ini.")
    st.stop()

meta = baca_metadata()

pengaturan = st.container(border=True)  # tombol cetak diisi di akhir halaman
with pengaturan:
    st.subheader("Pengaturan Analisis")
    st.write("Pilih tahun pengamatan dari tahun yang tersedia pada filter.")
    tahun = st.selectbox("Tahun Pengamatan", tahun_list, index=len(tahun_list) - 1)

dup = duplikat_tahun(df_f, tahun)
if not dup.empty:
    st.warning(
        f"Data tahun {tahun} memiliki **{len(dup)} baris duplikat** (wilayah sama), "
        "sehingga hasil perhitungan dapat tidak akurat. "
        "Rapikan di halaman Data Pendapatan."
    )

mungkin = kemungkinan_duplikat_tahun(df_f, tahun)
if not mungkin.empty:
    st.warning(
        f"Data tahun {tahun} memiliki **{len(mungkin)} baris kemungkinan duplikat** "
        "(identitas wilayah tidak lengkap), sehingga hasil perhitungan dapat tidak akurat. "
        "Periksa di halaman Data Pendapatan."
    )

a, pesan_analisis = susun_analisis(df_f, tahun)
ap = hitung_antarperiode(df_f)  # satu sumber untuk tabel antarperiode dan perubahan di bawah

# ==============================
# HASIL UTAMA
# ==============================
with st.container(border=True):
    st.subheader("Hasil Analisis Indeks Williamson")
    if a is None:
        st.warning(f"Indeks Williamson tahun {tahun} belum dapat dihitung: {pesan_analisis}")
    else:
        hasil = a.hasil
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

        baris_tahun = ap.tabel[ap.tabel["Tahun"] == tahun]
        if len(baris_tahun) and "Cakupan berbeda" in baris_tahun["Catatan"].iloc[0]:
            st.caption("⚠ " + baris_tahun["Catatan"].iloc[0])

        pesan_kategori = f"**{a.kategori}** pada tahun {tahun}."
        if a.kategori == "Ketimpangan rendah":
            st.success(pesan_kategori)
        elif a.kategori == "Ketimpangan sedang":
            st.warning(pesan_kategori)
        else:
            st.error(pesan_kategori)

        st.caption(
            keterangan_batas_kategori()
            + " Semakin besar nilai indeks, semakin timpang PDRB per kapita antarwilayah."
        )
        st.write(narasi_ringkasan(a))
        st.caption("Grafik posisi, kontribusi, dan perkembangan indeks tersedia di halaman Visualisasi.")

# ==============================
# RINGKASAN PERHITUNGAN
# ==============================
if a is not None:
    hasil, tertinggi, terendah = a.hasil, a.tertinggi, a.terendah
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
# PERKEMBANGAN INDEKS ANTARPERIODE
# ==============================
with st.container(border=True):
    st.subheader("Perkembangan Indeks Williamson Antarperiode")
    if len(ap.tabel) < 2:
        st.info(
            "Perbandingan antarperiode memerlukan minimal dua tahun. "
            "Perluas rentang tahun pada filter."
        )
    else:
        st.write(narasi_antarperiode(ap.tabel))
    for peringatan in ap.peringatan:
        st.warning(peringatan)
    if not f.konsisten and not ap.perubahan_cakupan.empty:
        st.button("Aktifkan cakupan wilayah konsisten", on_click=aktifkan_konsisten, key="btn_konsisten_analisis")

    st.dataframe(
        format_antarperiode(ap.tabel), hide_index=True,
        column_config={"Catatan": st.column_config.Column(width="large")},
    )
    st.caption(
        keterangan_batas_kategori()
        + " Indeks dihitung terpisah untuk setiap tahun dari wilayah yang punya data valid "
        "pada tahun itu. Perubahan dihitung terhadap tahun terdekat sebelumnya yang memiliki indeks; "
        "perubahan di bawah 0,005 disebut relatif stabil (ketetapan aplikasi, bukan standar baku). "
        "Perubahan indeks saja tidak menjelaskan penyebab perubahan disparitas."
    )
    if not ap.perubahan_cakupan.empty:
        with st.expander("Rincian perubahan cakupan wilayah"):
            st.dataframe(ap.perubahan_cakupan.fillna(""), hide_index=True)

    ringkas = ringkasan_ekspor(ap.tabel, len(df), f, info["opsi"], meta,
                               judul="Indeks Williamson antarperiode")
    unduh = st.columns(2)
    unduh[0].download_button(
        "Unduh Tabel Antarperiode (CSV)", ke_csv_bytes(ap.tabel),
        file_name=nama_file_ekspor(ap.tabel, f, "csv", "ria_indeks_williamson"),
        mime="text/csv", key="unduh_ap_csv",
    )
    unduh[1].download_button(
        "Unduh Tabel Antarperiode (Excel)",
        ke_excel_dengan_metadata(ap.tabel, ringkas, nama_data="Antarperiode"),
        file_name=nama_file_ekspor(ap.tabel, f, "xlsx", "ria_indeks_williamson"),
        mime=EXCEL_MIME, key="unduh_ap_xlsx",
    )

# ==============================
# PERBANDINGAN ANTARWILAYAH
# ==============================
with st.container(border=True):
    st.subheader("Perbandingan Antarwilayah")
    indikator, urut = pilih_pembanding()
    satuan = satuan_indikator(indikator, meta)
    tabel_p, catatan_p = tabel_perbandingan(df_f, tahun, indikator, urut, satuan, list(f.wilayah))

    st.write(narasi_perbandingan(tabel_p, indikator))
    for c in catatan_p:
        st.warning(c)
    st.dataframe(format_perbandingan(tabel_p), hide_index=True)
    st.caption(
        f"Tahun {tahun} · Satuan: {satuan}. Wilayah yang datanya tidak tersedia tidak diberi nilai nol. "
        "Bandingkan hanya data dengan definisi dan jenis harga yang sama."
    )
    if a is not None:
        st.info(
            f"Indeks Williamson untuk kumpulan wilayah ini pada tahun {tahun}: **{a.hasil.indeks:.4f}**. "
            "Indeks merupakan ukuran agregat cakupan wilayah, bukan nilai individual tiap wilayah."
        )
    with st.expander("Lihat indikator lintas tahun (wilayah × tahun)"):
        st.dataframe(format_lintas_tahun(tabel_lintas_tahun(df_f, indikator)))

    ringkas_p = ringkasan_ekspor(tabel_p, len(df), f, info["opsi"], meta,
                                 judul=f"Perbandingan {indikator} tahun {tahun}", tahun_ekspor=[tahun])
    unduh_p = st.columns(2)
    unduh_p[0].download_button(
        "Unduh Perbandingan (CSV)", ke_csv_bytes(tabel_p),
        file_name=nama_file_ekspor(pd.DataFrame({"Tahun": [tahun]}), f, "csv", "ria_perbandingan"),
        mime="text/csv", key="unduh_pb_csv",
    )
    unduh_p[1].download_button(
        "Unduh Perbandingan (Excel)",
        ke_excel_dengan_metadata(tabel_p, ringkas_p, nama_data="Perbandingan"),
        file_name=nama_file_ekspor(pd.DataFrame({"Tahun": [tahun]}), f, "xlsx", "ria_perbandingan"),
        mime=EXCEL_MIME, key="unduh_pb_xlsx",
    )

# ==============================
# ANALISIS PER WILAYAH (TAB)
# ==============================
if a is not None:
    detail = a.detail
    with st.container(border=True):
        st.subheader("Analisis Per Wilayah")
        tab_rincian, tab_langkah = st.tabs(["Rincian", "Langkah"])

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

            ringkas_r = ringkasan_ekspor(detail, len(df), f, info["opsi"], meta,
                                         judul=f"Rincian perhitungan Indeks Williamson tahun {tahun}",
                                         tahun_ekspor=[tahun])
            unduh_r = st.columns(2)
            unduh_r[0].download_button(
                "Unduh Rincian (CSV)", ke_csv_bytes(detail),
                file_name=nama_file_ekspor(pd.DataFrame({"Tahun": [tahun]}), f, "csv", "ria_rincian_williamson"),
                mime="text/csv", key="unduh_rc_csv",
            )
            unduh_r[1].download_button(
                "Unduh Rincian (Excel)",
                ke_excel_dengan_metadata(detail, ringkas_r, nama_data="Rincian"),
                file_name=nama_file_ekspor(pd.DataFrame({"Tahun": [tahun]}), f, "xlsx", "ria_rincian_williamson"),
                mime=EXCEL_MIME, key="unduh_rc_xlsx",
            )

        with tab_langkah:
            st.caption(f"Langkah perhitungan Indeks Williamson tahun {tahun} dengan angka sebenarnya.")
            hasil = a.hasil
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

# ---- Cetak (mengikuti filter, tahun, dan indikator perbandingan di atas) ----
with pengaturan:
    st.markdown("**Cetak Laporan**")
    blok_cetak(tahun, "analisis", f, indikator, urut)
