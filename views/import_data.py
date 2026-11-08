from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from utils import (
    COL_PDRB,
    COL_PENDUDUK,
    COL_TAHUN,
    COL_WILAYAH,
    DATASET_PATH,
    MAKS_UKURAN_MB,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
    baca_berkas,
    cocokkan_kolom,
    daftar_sheet,
    duplikat,
    flash,
    hapus_duplikat,
    identitas_tidak_lengkap,
    ke_csv_bytes,
    ke_excel_bytes,
    kemungkinan_duplikat,
    kolom_dataset,
    kunci_baris,
    load_dataset,
    page_header,
    periksa_baris,
    save_dataset,
    show_flash,
    template_kosong,
    terapkan_pilihan_duplikat,
    validasi_baris,
)

page_header(
    "Import Data BPS",
    "Import data pendapatan regional dari file Excel atau CSV, "
    "atau masukkan data secara manual.",
)

show_flash()

PILIHAN_DUPLIKAT = {
    "Batalkan — perbaiki berkas/sumber data terlebih dahulu": "batal",
    "Simpan yang pertama (data lama / baris paling atas)": "pertama",
    "Simpan yang terakhir (data baru / baris paling bawah)": "terakhir",
    "Pilih sendiri baris yang disimpan": "manual",
}


def data_lama_bersih():
    """Dataset yang sudah ada dalam bentuk bersih, atau (None, pesan) bila bermasalah."""
    df_lama, _ = load_dataset()
    if df_lama is None:
        return None, "Dataset yang ada tidak dapat dibaca."
    hasil = periksa_baris(df_lama)
    if not hasil.bermasalah.empty:
        return None, (
            f"Dataset yang ada memiliki {len(hasil.bermasalah)} baris bermasalah. "
            "Perbaiki di halaman Data Pendapatan terlebih dahulu."
        )
    lama = hasil.valid.copy()
    lama["Baris"] = np.arange(len(lama)) + 1
    lama["Asal"] = "Data lama"
    return lama, None


def tangani_duplikat(gabungan: pd.DataFrame, prefix: str):
    """Tampilkan duplikat dan pilihan penanganannya.

    Mengembalikan (data tanpa duplikat, None) bila sudah ditangani, atau
    (None, pesan) bila pengguna belum memutuskan. Tidak ada data yang dihapus
    tanpa pilihan eksplisit dari pengguna.
    """
    dup = duplikat(gabungan)
    if dup.empty:
        return gabungan, None

    n_berbeda = int((dup["Jenis"] == "Nilai berbeda").sum())
    st.warning(
        f"Ditemukan **{len(dup)} baris duplikat** (wilayah dan tahun sama)"
        + (f", {n_berbeda} baris di antaranya memiliki nilai yang berbeda." if n_berbeda else ".")
        + " Tentukan cara menanganinya."
    )
    with st.expander("Lihat baris duplikat", expanded=True):
        st.dataframe(dup, hide_index=True)

    pilihan = PILIHAN_DUPLIKAT[
        st.radio("Penanganan duplikat", list(PILIHAN_DUPLIKAT), key=f"{prefix}_dup")
    ]

    if pilihan == "batal":
        return None, "pilih cara menangani duplikat, atau perbaiki berkas sumber lalu unggah ulang"
    if pilihan in ("pertama", "terakhir"):
        return hapus_duplikat(gabungan, pilihan), None

    # Pilih sendiri: tepat satu baris yang dipertahankan untuk setiap kelompok duplikat
    editor = dup.reset_index(drop=True)
    editor.insert(0, "Simpan", False)
    edit = st.data_editor(
        editor, hide_index=True, key=f"{prefix}_pilih",
        disabled=[c for c in editor.columns if c != "Simpan"],
        column_config={"Simpan": st.column_config.CheckboxColumn("Simpan", default=False)},
    )
    st.caption("Centang tepat satu baris untuk setiap kelompok duplikat; baris lain tidak disimpan.")
    return terapkan_pilihan_duplikat(gabungan, edit)


def tampilkan_peringatan(peringatan: pd.DataFrame, kunci: str):
    """Tampilkan nilai yang perlu diperiksa. Mengembalikan True bila ada yang perlu konfirmasi
    dan belum dikonfirmasi."""
    if peringatan.empty:
        return False
    perlu = bool(peringatan["Perlu konfirmasi"].any())
    st.warning(
        f"**{len(peringatan)} baris perlu diperiksa.** Baris ini valid secara format, "
        "tetapi nilainya tidak biasa. Baris tidak dihapus otomatis."
    )
    with st.expander("Lihat baris yang perlu diperiksa", expanded=perlu):
        st.dataframe(peringatan.drop(columns=["Perlu konfirmasi"]), hide_index=True,
                     column_config={"Peringatan": st.column_config.Column(width="large")})
    if perlu:
        ok = st.checkbox(
            "Saya sudah memeriksa baris dengan PDRB bernilai nol dan tetap ingin menggunakannya",
            key=kunci,
        )
        return not ok
    return False


def tampilkan_identitas(df: pd.DataFrame, kunci: str) -> bool:
    """Peringatan identitas wilayah tidak lengkap.

    Mengembalikan True bila ada kemungkinan duplikat yang belum dikonfirmasi pengguna.
    Tidak ada data yang digabung atau dihapus otomatis.
    """
    kemungkinan = kemungkinan_duplikat(df)
    tidak_lengkap = identitas_tidak_lengkap(df)
    perlu_konfirmasi = False

    if not kemungkinan.empty:
        st.warning(
            f"**{len(kemungkinan)} baris kemungkinan duplikat.** Nama wilayah dan tahun sama, "
            "tetapi identitas (kode/provinsi) kosong pada sebagian baris sehingga belum pasti "
            "wilayah yang sama. Tidak ada data yang digabung atau dihapus otomatis."
        )
        with st.expander("Lihat kemungkinan duplikat", expanded=True):
            st.dataframe(
                kemungkinan.fillna(""), hide_index=True,
                column_config={"Alasan": st.column_config.Column(width="large")},
            )
        sudah = st.checkbox(
            "Saya sudah memeriksa kemungkinan duplikat dan tetap ingin menyimpan", key=kunci
        )
        perlu_konfirmasi = not sudah

    if not tidak_lengkap.empty:
        st.info(
            f"{len(tidak_lengkap)} baris memiliki identitas wilayah tidak lengkap "
            "(Kode Wilayah/Provinsi kosong). Lengkapi agar wilayah bernama sama tidak tertukar."
        )
        with st.expander("Lihat baris dengan identitas tidak lengkap"):
            st.dataframe(tidak_lengkap.fillna(""), hide_index=True)
    return perlu_konfirmasi


tab_upload, tab_manual = st.tabs(["Unggah Dataset", "Input Data Manual"])

# ==============================
# UNGGAH FILE
# ==============================
with tab_upload:
    st.write(
        "Silakan pilih file dataset yang akan digunakan dalam penelitian "
        "analisis disparitas pendapatan regional."
    )
    st.caption(
        "Kolom wajib: " + ", ".join(REQUIRED_COLUMNS)
        + ". Kolom opsional: " + ", ".join(OPTIONAL_COLUMNS)
        + " (dipakai membedakan wilayah yang namanya sama)."
    )

    with st.expander("Unduh templat kosong"):
        st.caption("Templat hanya berisi baris judul kolom, tanpa data contoh.")
        kolom_unduh = st.columns(2)
        kolom_unduh[0].download_button(
            "Templat CSV", ke_csv_bytes(template_kosong()),
            file_name="templat_dataset.csv", mime="text/csv",
        )
        kolom_unduh[1].download_button(
            "Templat Excel", ke_excel_bytes(template_kosong()),
            file_name="templat_dataset.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    file = st.file_uploader(
        "Pilih File Dataset",
        type=["csv", "xlsx"],
        help=f"Format: CSV (.csv) atau Excel (.xlsx). Maksimal {MAKS_UKURAN_MB} MB.",
    )

    if file is not None:
        sig = f"{file.name}_{file.size}"  # konfirmasi berlaku per berkas
        isi = file.getvalue()

        sheet = None
        if file.name.lower().endswith(".xlsx"):
            try:
                daftar = daftar_sheet(isi)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            if len(daftar) > 1:
                sheet = st.selectbox("Sheet yang dibaca", daftar)

        try:
            mentah = baca_berkas(file.name, isi, sheet)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        with st.expander(f"Pratinjau berkas ({min(10, len(mentah))} dari {len(mentah)} baris)"):
            st.dataframe(mentah.head(10), hide_index=True)

        df_file, hilang, ekstra, catatan = cocokkan_kolom(mentah)
        if hilang:
            st.error(
                "Kolom wajib tidak ditemukan: **" + ", ".join(hilang) + "**. "
                "Kolom yang terbaca pada berkas: " + ", ".join(map(str, mentah.columns)) + "."
            )
            st.stop()
        if catatan:
            st.info("Penyesuaian nama kolom: " + "; ".join(catatan) + ".")
        if ekstra:
            st.info("Kolom tambahan berikut diabaikan: " + ", ".join(ekstra) + ".")

        # ---- Validasi per baris (baris 1 pada berkas adalah judul kolom) ----
        hasil = periksa_baris(df_file, offset=2)
        valid, bermasalah = hasil.valid, hasil.bermasalah

        ringkas = st.columns(3)
        ringkas[0].metric("Baris terbaca", len(valid) + len(bermasalah))
        ringkas[1].metric("Baris valid", len(valid))
        ringkas[2].metric("Baris bermasalah", len(bermasalah))
        if hasil.jumlah_kosong:
            st.caption(f"{hasil.jumlah_kosong} baris kosong diabaikan.")

        if len(bermasalah):
            st.error(f"**{len(bermasalah)} baris bermasalah.** Nomor baris sesuai urutan pada berkas.")
            tabel_masalah = bermasalah.fillna("")
            tabel_masalah.insert(2, "Tindakan", "Tidak diimpor — perbaiki di berkas sumber")
            with st.expander("Lihat baris bermasalah", expanded=True):
                st.dataframe(
                    tabel_masalah, hide_index=True,
                    column_config={"Masalah": st.column_config.Column(width="large"),
                                   "Tindakan": st.column_config.Column(width="medium")},
                )
            lewati = st.checkbox(
                "Lewati baris bermasalah dan impor baris yang valid saja", key=f"lewati_{sig}"
            )
        else:
            lewati = True

        if valid.empty:
            st.error("Tidak ada baris valid yang dapat diimpor.")
            st.stop()

        # ---- Nilai yang perlu diperiksa (PDRB nol, pencilan) ----
        butuh_konfirmasi_nol = tampilkan_peringatan(hasil.peringatan, f"nol_{sig}")

        # ---- Mode simpan ----
        mode = "Ganti seluruh dataset"
        data_lama = None
        konfirmasi_ganti = True
        if DATASET_PATH.exists():
            mode = st.radio(
                "Cara menyimpan",
                ["Ganti seluruh dataset", "Tambahkan ke dataset yang ada"],
                help="Dataset yang lama otomatis dicadangkan sebelum diubah.",
                key=f"mode_{sig}",
            )
            if mode == "Tambahkan ke dataset yang ada":
                data_lama, galat = data_lama_bersih()
                if galat:
                    st.error(galat)
                    st.stop()
            else:
                konfirmasi_ganti = st.checkbox(
                    "Saya mengerti dataset aktif akan diganti (cadangan dibuat otomatis)",
                    key=f"ganti_{sig}",
                )

        baru = valid.copy()
        baru["Asal"] = "File baru"
        gabungan = pd.concat([data_lama, baru], ignore_index=True) if data_lama is not None else baru

        # ---- Duplikat ----
        tanpa_duplikat, galat_duplikat = tangani_duplikat(gabungan, f"file_{sig}")
        butuh_cek_identitas = (
            tampilkan_identitas(tanpa_duplikat, f"identitas_{sig}")
            if tanpa_duplikat is not None else False
        )

        # ---- Metadata sumber (opsional) ----
        with st.expander("Catatan sumber data (opsional)"):
            st.caption("Dicatat bersama dataset agar asal-usul data dapat ditelusuri.")
            sumber = st.text_input("Sumber data", placeholder="mis. BPS Provinsi ...", key=f"sumber_{sig}")
            tautan = st.text_input("Tautan sumber", key=f"tautan_{sig}")
            tanggal = st.date_input("Tanggal pengambilan data", value=None,
                                    format="DD/MM/YYYY", key=f"tanggal_{sig}")
            satuan = st.text_input("Satuan PDRB", placeholder="mis. Rupiah per kapita", key=f"satuan_{sig}")
            revisi = st.text_area("Catatan revisi", placeholder="mis. angka sementara / angka revisi ...",
                                  key=f"revisi_{sig}")

        # ---- Ringkasan & simpan ----
        syarat = []
        if len(bermasalah) and not lewati:
            syarat.append("centang opsi melewati baris bermasalah, atau perbaiki berkas")
        if butuh_konfirmasi_nol:
            syarat.append("konfirmasi baris dengan PDRB bernilai nol")
        if not konfirmasi_ganti:
            syarat.append("konfirmasi penggantian dataset")
        if galat_duplikat:
            syarat.append(galat_duplikat)
        if butuh_cek_identitas:
            syarat.append("konfirmasi pemeriksaan kemungkinan duplikat")

        if tanpa_duplikat is not None:
            hasil_akhir = tanpa_duplikat[kolom_dataset(tanpa_duplikat)]
            dihapus = len(gabungan) - len(hasil_akhir)
            st.success(
                f"Siap disimpan: **{len(hasil_akhir)} baris**"
                + (f" ({dihapus} baris duplikat tidak disimpan)." if dihapus else ".")
            )
            with st.expander("Pratinjau data yang akan disimpan"):
                st.dataframe(hasil_akhir.head(100), hide_index=True)
                if len(hasil_akhir) > 100:
                    st.caption(f"Menampilkan 100 dari {len(hasil_akhir)} baris.")

        if st.button("Simpan Dataset", type="primary", disabled=bool(syarat)):
            metadata = {
                "nama_berkas": file.name,
                "waktu_import": datetime.now().isoformat(timespec="seconds"),
                "sumber": sumber.strip(), "tautan": tautan.strip(),
                "tanggal_pengambilan": tanggal.isoformat() if tanggal else "",
                "satuan": satuan.strip(), "catatan_revisi": revisi.strip(),
            }
            if mode == "Tambahkan ke dataset yang ada":  # isian kosong tidak menghapus catatan lama
                metadata = {k: v for k, v in metadata.items() if v != ""}
            try:
                meta = save_dataset(hasil_akhir, alasan="impor", metadata=metadata)
            except ValueError as e:
                st.error(str(e))
            else:
                flash(f"Dataset disimpan dan diverifikasi: {meta['jumlah_baris']} baris.")
                st.rerun()
        if syarat:
            st.caption("Untuk menyimpan: " + "; ".join(syarat) + ".")

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

    # Deteksi masalah secara langsung (hanya bila isian sudah valid)
    try:
        df_baru = validasi_baris(input_df, izinkan_duplikat=True, konfirmasi_nol=True)
    except ValueError:
        df_baru = None

    syarat_manual = []
    tanpa_dup_manual, galat_lama = None, None
    if df_baru is not None:
        butuh_nol = tampilkan_peringatan(
            periksa_baris(input_df).peringatan, f"nol_manual_{versi}"
        )
        if butuh_nol:
            syarat_manual.append("konfirmasi baris dengan PDRB bernilai nol")

        baru = df_baru.copy()
        baru["Baris"] = np.arange(len(baru)) + 1
        baru["Asal"] = "Input baru"
        data_lama, galat_lama = (data_lama_bersih() if DATASET_PATH.exists() else (None, None))
        if galat_lama:
            st.error(galat_lama)
            syarat_manual.append("perbaiki dataset yang ada")
        else:
            gabungan_manual = (
                pd.concat([data_lama, baru], ignore_index=True) if data_lama is not None else baru
            )
            tanpa_dup_manual, galat_dup = tangani_duplikat(gabungan_manual, f"manual_{versi}")
            if galat_dup:
                syarat_manual.append(galat_dup)
            elif tampilkan_identitas(tanpa_dup_manual, f"identitas_manual_{versi}"):
                syarat_manual.append("konfirmasi pemeriksaan kemungkinan duplikat")

    if st.button("Simpan Data", type="primary", disabled=bool(syarat_manual)):
        try:
            df_baru = validasi_baris(input_df, izinkan_duplikat=True, konfirmasi_nol=True)
            if tanpa_dup_manual is None:
                raise ValueError(galat_lama or "Data belum dapat disimpan.")
            final = tanpa_dup_manual[kolom_dataset(tanpa_dup_manual)]
            meta = save_dataset(final, alasan="input-manual")
            st.session_state["manual_versi"] = versi + 1  # kosongkan formulir
            flash(f"Berhasil! Dataset diverifikasi: {meta['jumlah_baris']} baris.")
            st.rerun()
        except ValueError as e:
            st.error(f"Gagal menyimpan data: {e}")
    if syarat_manual:
        st.caption("Untuk menyimpan: " + "; ".join(syarat_manual) + ".")
