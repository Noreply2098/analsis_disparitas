import streamlit as st

from utils import (
    COL_PENDUDUK, COL_PDRB, COL_TAHUN, COL_WILAYAH,
    delete_dataset, flash, load_dataset, page_header, save_dataset,
    show_flash, validasi_baris,
)

page_header(
    "Data Pendapatan",
    "Lihat, ubah, tambah, dan hapus data pendapatan regional.",
)

show_flash()

df, pesan = load_dataset()

if df is None:
    st.info(pesan)
    st.stop()

# ---- Ringkasan ----
kolom = st.columns(3)
kolom[0].metric("Total Wilayah", df[COL_WILAYAH].nunique())
kolom[1].metric("Tahun Pengamatan", df[COL_TAHUN].nunique())
kolom[2].metric("Total Data", len(df))

# ---- Tabel (edit / tambah / hapus langsung di tabel) ----
with st.container(border=True):
    st.subheader("Tabel Data Pendapatan")
    st.caption(
        "Klik sel untuk mengubah nilai. Tambah baris lewat baris paling bawah; "
        "hapus baris dengan memilihnya lalu menekan ikon tempat sampah / tombol Delete. "
        "Perubahan baru tersimpan setelah menekan **Simpan Perubahan**."
    )

    hasil_edit = st.data_editor(
        df,
        num_rows="dynamic",
        key="editor_data",
        column_config={
            COL_WILAYAH: st.column_config.TextColumn("Nama Wilayah", required=True),
            COL_TAHUN: st.column_config.NumberColumn("Tahun", step=1, format="%d"),
            COL_PDRB: st.column_config.NumberColumn("PDRB Per Kapita", min_value=0, format="%d"),
            COL_PENDUDUK: st.column_config.NumberColumn(
                "Jumlah Penduduk", min_value=1, step=1, format="%d"
            ),
        },
    )

    if st.button("Simpan Perubahan", type="primary"):
        try:
            save_dataset(validasi_baris(hasil_edit))
            st.session_state.pop("editor_data", None)
            flash("Perubahan data berhasil disimpan.")
            st.rerun()
        except ValueError as e:
            st.error(str(e))

# ---- Hapus semua ----
with st.expander("Hapus semua data"):
    st.warning("Seluruh dataset akan dihapus dan tidak dapat dikembalikan.")
    if st.checkbox("Saya yakin ingin menghapus seluruh data"):
        if st.button("Hapus Semua Data"):
            delete_dataset()
            st.session_state.pop("editor_data", None)
            flash("Seluruh data berhasil dihapus.", "info")
            st.rerun()
