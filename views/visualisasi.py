import streamlit as st

from utils import (
    COL_PDRB,
    COL_PENDUDUK,
    beri_label_unik,
    daftar_tahun,
    duplikat_tahun,
    kemungkinan_duplikat_tahun,
    load_dataset,
    page_header,
    susun_analisis,
    to_numeric_frame,
    tren_williamson,
)
from charts import (
    BIRU,
    BIRU_TUA,
    grafik_batang,
    grafik_indikator,
    grafik_selisih,
    grafik_tren,
)
from laporan import (
    blok_cetak,
)

page_header(
    "Visualisasi",
    "Grafik PDRB per kapita, jumlah penduduk, posisi dan kontribusi tiap wilayah, "
    "serta perkembangan Indeks Williamson.",
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
data = beri_label_unik(data[data["Tahun"] == tahun])

df_pdrb = data.dropna(subset=[COL_PDRB])
df_penduduk = data.dropna(subset=[COL_PENDUDUK])
df_penduduk = df_penduduk[df_penduduk[COL_PENDUDUK] > 0]

if df_pdrb.empty and df_penduduk.empty:
    st.warning("Tidak ada data valid untuk ditampilkan.")
    st.stop()

dup = duplikat_tahun(df, tahun)
if not dup.empty:
    st.warning(
        f"Data tahun {tahun} memiliki **{len(dup)} baris duplikat** (wilayah sama), "
        "sehingga grafik dapat tidak akurat. Rapikan di halaman Data Pendapatan."
    )

mungkin = kemungkinan_duplikat_tahun(df, tahun)
if not mungkin.empty:
    st.warning(
        f"Data tahun {tahun} memiliki **{len(mungkin)} baris kemungkinan duplikat** "
        "(identitas wilayah tidak lengkap), sehingga grafik dapat tidak akurat. "
        "Periksa di halaman Data Pendapatan."
    )

with st.container(border=True):
    st.markdown("**Cetak Laporan**")
    blok_cetak(tahun, "grafik")

a, pesan_analisis = susun_analisis(df, tahun)

# ---- PDRB per kapita ----
if not df_pdrb.empty:
    with st.container(border=True):
        st.subheader(f"PDRB Per Kapita Antarwilayah Tahun {tahun}")
        st.altair_chart(grafik_batang(
            df_pdrb, COL_PDRB, "PDRB Per Kapita", BIRU_TUA,
            rata_rata=a.hasil.rata_rata if a else None,
        ))
        keterangan = "Label disingkat: rb = ribu, jt = juta, M = miliar. "
        if a:
            keterangan += (
                f"Garis putus-putus oranye menunjukkan rata-rata PDRB per kapita "
                f"(dibobot jumlah penduduk): {a.hasil.rata_rata:,.2f}."
            )
        st.caption(keterangan)

# ---- Jumlah penduduk ----
if not df_penduduk.empty:
    with st.container(border=True):
        st.subheader(f"Jumlah Penduduk Antarwilayah Tahun {tahun}")
        st.altair_chart(grafik_batang(
            df_penduduk, COL_PENDUDUK, "Jumlah Penduduk (Jiwa)", BIRU,
        ))
        st.caption("Label disingkat: rb = ribu, jt = juta, M = miliar.")

# ---- Grafik hasil analisis (posisi, kontribusi, indikator) ----
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
        st.caption(
            f"{a.kategori}. Kategori pada aplikasi ini: rendah (< 0,3), sedang "
            f"(0,3 – 0,5), tinggi (> 0,5)."
        )

# ---- Tren ----
tren = tren_williamson(df)
if not tren.empty:
    with st.container(border=True):
        st.subheader("Perkembangan Indeks Williamson Antarwaktu")
        st.altair_chart(grafik_tren(tren))
        st.caption(
            "Pita warna menunjukkan kategori ketimpangan: hijau (< 0,3) rendah, "
            "kuning (0,3 – 0,5) sedang, merah (> 0,5) tinggi."
        )
