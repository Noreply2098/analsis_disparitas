import numpy as np
import pandas as pd
import streamlit as st

from utils import (
    COL_PENDUDUK, COL_PDRB, COL_TAHUN, COL_WILAYAH, DATASET_PATH,
    REQUIRED_COLUMNS, flash, load_dataset, page_header, save_dataset,
    show_flash, validasi_baris,
)

page_header(
    "Import Data BPS",
    "Import data pendapatan regional dari file Excel atau CSV, "
    "atau masukkan data secara manual.",
)

show_flash()

tab_upload, tab_manual = st.tabs(["Unggah Dataset", "Input Data Manual"])

# ==============================
# UNGGAH FILE
# ==============================
with tab_upload:
    st.write(
        "Silakan pilih file dataset yang akan digunakan dalam penelitian "
        "analisis disparitas pendapatan regional."
    )
    st.caption("Kolom wajib: " + ", ".join(REQUIRED_COLUMNS))

    file = st.file_uploader(
        "Pilih File Dataset",
        type=["csv", "xlsx"],
        help="Format yang didukung: Excel (.xlsx) dan CSV (.csv)",
    )

    if file is not None:
        try:
            if file.name.lower().endswith(".csv"):
                df_upload = pd.read_csv(file)
            else:
                df_upload = pd.read_excel(file)
        except Exception as e:
            st.error(f"Gagal membaca file: {e}")
        else:
            if not all(col in df_upload.columns for col in REQUIRED_COLUMNS):
                st.error(
                    "Kolom wajib: Nama Wilayah, Tahun, PDRB Per Kapita, Jumlah Penduduk."
                )
            else:
                st.success(f"Berhasil membaca {len(df_upload)} baris data.")
                st.dataframe(df_upload, hide_index=True)

                if DATASET_PATH.exists():
                    st.caption("Dataset yang sudah ada akan diganti dengan file ini.")

                if st.button("Simpan sebagai Dataset", type="primary"):
                    save_dataset(df_upload)
                    flash(f"{len(df_upload)} baris data berhasil disimpan sebagai dataset.")
                    st.rerun()

# ==============================
# INPUT MANUAL
# ==============================
with tab_manual:
    st.write(
        "Masukkan informasi setiap wilayah berdasarkan tahun pengamatan. "
        "Data baru akan ditambahkan ke dataset yang sudah ada."
    )

    versi = st.session_state.setdefault("manual_versi", 0)

    template = pd.DataFrame({
        COL_WILAYAH: [""],
        COL_TAHUN: [np.nan],
        COL_PDRB: [np.nan],
        COL_PENDUDUK: [np.nan],
    })

    input_df = st.data_editor(
        template,
        num_rows="dynamic",
        hide_index=True,
        key=f"editor_manual_{versi}",
        column_config={
            COL_WILAYAH: st.column_config.TextColumn("Nama Wilayah", required=True),
            COL_TAHUN: st.column_config.NumberColumn("Tahun", step=1, format="%d"),
            COL_PDRB: st.column_config.NumberColumn(
                "PDRB Per Kapita (Rp)", min_value=0, format="%d"
            ),
            COL_PENDUDUK: st.column_config.NumberColumn(
                "Jumlah Penduduk", min_value=1, step=1, format="%d"
            ),
        },
    )
    st.caption("Gunakan baris paling bawah untuk menambah baris baru.")

    if st.button("Simpan Data", type="primary"):
        try:
            df_baru = validasi_baris(input_df)

            df_lama, _ = load_dataset()
            if DATASET_PATH.exists() and df_lama is None:
                raise ValueError(
                    "Format dataset lama tidak sesuai. "
                    "Periksa dataset sebelum menambahkan data."
                )

            hasil = (
                pd.concat([df_lama, df_baru], ignore_index=True)
                if df_lama is not None else df_baru
            )
            save_dataset(hasil)

            st.session_state["manual_versi"] = versi + 1  # kosongkan formulir
            flash(f"Berhasil! {len(df_baru)} baris data berhasil disimpan.")
            st.rerun()
        except ValueError as e:
            st.error(f"Gagal menyimpan data: {e}")
