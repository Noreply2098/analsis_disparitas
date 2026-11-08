import numpy as np
import streamlit as st

from utils import (
    COL_KODE,
    COL_PDRB,
    COL_PENDUDUK,
    COL_PROVINSI,
    COL_TAHUN,
    COL_WILAYAH,
    MAKS_CADANGAN,
    baca_metadata,
    buat_cadangan,
    daftar_cadangan,
    delete_dataset,
    duplikat,
    flash,
    hapus_duplikat,
    identitas_tidak_lengkap,
    info_dataset,
    ke_csv_bytes,
    ke_excel_bytes,
    kemungkinan_duplikat,
    kolom_dataset,
    load_dataset,
    page_header,
    periksa_baris,
    pulihkan,
    save_dataset,
    show_flash,
    simpan_metadata,
    validasi_baris,
)

page_header(
    "Data Pendapatan",
    "Lihat, ubah, tambah, hapus, dan kelola data pendapatan regional.",
)

show_flash()

df, pesan = load_dataset()

tab_tabel, tab_kelola = st.tabs(["Tabel Data", "Kelola Dataset"])

# ==============================
# TABEL DATA
# ==============================
with tab_tabel:
    if df is None:
        st.info(pesan)
    else:
        # ---- Ringkasan ----
        kolom = st.columns(3)
        kolom[0].metric("Total Wilayah", df[COL_WILAYAH].nunique())
        kolom[1].metric("Tahun Pengamatan", df[COL_TAHUN].nunique())
        kolom[2].metric("Total Data", len(df))

        # ---- Peringatan data bermasalah / duplikat ----
        periksa = periksa_baris(df)
        if not periksa.bermasalah.empty:
            st.error(
                f"Dataset memiliki **{len(periksa.bermasalah)} baris bermasalah** "
                "(nilai kosong atau tidak valid). Perbaiki pada tabel di bawah."
            )
            with st.expander("Lihat baris bermasalah"):
                st.dataframe(
                    periksa.bermasalah.fillna(""), hide_index=True,
                    column_config={"Masalah": st.column_config.Column(width="large")},
                )

        dup = duplikat(periksa.valid)
        if not dup.empty:
            st.warning(
                f"Ditemukan **{len(dup)} baris duplikat** (nama wilayah dan tahun sama). "
                "Duplikat dapat menggandakan bobot wilayah pada perhitungan indeks."
            )
            with st.expander("Lihat baris duplikat"):
                st.dataframe(dup, hide_index=True)
            if periksa.bermasalah.empty:
                setuju = st.checkbox(
                    "Saya setuju baris duplikat dihapus (cadangan dibuat otomatis)", key="setuju_dup"
                )
                aksi = st.columns(2)
                for kol_aksi, simpan, label_aksi in (
                    (aksi[0], "pertama", "Hapus duplikat (simpan baris pertama)"),
                    (aksi[1], "terakhir", "Hapus duplikat (simpan baris terakhir)"),
                ):
                    if kol_aksi.button(label_aksi, disabled=not setuju):
                        try:
                            save_dataset(hapus_duplikat(periksa.valid, simpan), alasan="hapus-duplikat")
                        except ValueError as e:
                            st.error(str(e))
                        else:
                            st.session_state.pop("editor_data", None)
                            flash(f"Duplikat dihapus, baris {simpan} dipertahankan.")
                            st.rerun()

        # ---- Identitas wilayah tidak lengkap (hanya peringatan; tidak ada yang diubah otomatis) ----
        mungkin = kemungkinan_duplikat(periksa.valid)
        if not mungkin.empty:
            st.warning(
                f"**{len(mungkin)} baris kemungkinan duplikat:** nama wilayah dan tahun sama, tetapi "
                "identitas (kode/provinsi) kosong pada sebagian baris. Periksa dan lengkapi pada "
                "tabel di bawah; tidak ada data yang digabung atau dihapus otomatis."
            )
            with st.expander("Lihat kemungkinan duplikat"):
                st.dataframe(
                    mungkin.fillna(""), hide_index=True,
                    column_config={"Alasan": st.column_config.Column(width="large")},
                )
        lengkap = identitas_tidak_lengkap(periksa.valid)
        if not lengkap.empty:
            st.info(
                f"{len(lengkap)} baris memiliki identitas wilayah tidak lengkap "
                "(Kode Wilayah/Provinsi kosong)."
            )
            with st.expander("Lihat baris dengan identitas tidak lengkap"):
                st.dataframe(lengkap.fillna(""), hide_index=True)

        # ---- Tabel (edit / tambah / hapus langsung di tabel) ----
        with st.container(border=True):
            st.subheader("Tabel Data Pendapatan")
            st.caption(
                "Klik sel untuk mengubah nilai. Tambah baris lewat baris paling bawah; "
                "hapus baris dengan memilihnya lalu menekan ikon tempat sampah / tombol Delete. "
                "Perubahan baru tersimpan setelah menekan **Simpan Perubahan**. "
                "Di HP, geser tabel ke samping untuk melihat semua kolom."
            )

            tabel = df[[c for c in df.columns if c in kolom_dataset(df) or c in (COL_KODE, COL_PROVINSI)]].copy()
            for kolom_id in (COL_KODE, COL_PROVINSI):
                if kolom_id in tabel.columns:
                    tabel[kolom_id] = tabel[kolom_id].fillna("").astype(str)  # editor teks
            tabel.index = np.arange(len(tabel)) + 1
            tabel.index.name = "No."

            config_kolom = {
                COL_WILAYAH: st.column_config.TextColumn("Nama Wilayah", required=True, width="medium"),
                COL_TAHUN: st.column_config.NumberColumn("Tahun", step=1, format="%d", width="small"),
                COL_PDRB: st.column_config.NumberColumn(
                    "PDRB Per Kapita", min_value=0, format="%d", width="medium"
                ),
                COL_PENDUDUK: st.column_config.NumberColumn(
                    "Jumlah Penduduk", min_value=1, step=1, format="%d", width="medium"
                ),
                COL_KODE: st.column_config.TextColumn("Kode Wilayah", width="small"),
                COL_PROVINSI: st.column_config.TextColumn("Provinsi", width="medium"),
            }
            hasil_edit = st.data_editor(
                tabel, num_rows="dynamic", key="editor_data", column_config=config_kolom,
            )

            # PDRB nol memerlukan konfirmasi sebelum disimpan
            konfirmasi_nol = True
            try:
                nol = periksa_baris(hasil_edit).peringatan
            except Exception:
                nol = None
            if nol is not None and not nol.empty and nol["Perlu konfirmasi"].any():
                st.warning("Ada baris dengan **PDRB bernilai nol**. Periksa definisi data sebelum menyimpan.")
                konfirmasi_nol = st.checkbox(
                    "Saya sudah memeriksa baris dengan PDRB nol dan tetap ingin menyimpannya",
                    key="konfirmasi_nol_edit",
                )

            if st.button("Simpan Perubahan", type="primary", disabled=not konfirmasi_nol):
                try:
                    meta = save_dataset(
                        validasi_baris(hasil_edit, konfirmasi_nol=True), alasan="edit"
                    )
                    st.session_state.pop("editor_data", None)
                    flash(f"Perubahan disimpan dan diverifikasi: {meta['jumlah_baris']} baris.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

# ==============================
# KELOLA DATASET
# ==============================
with tab_kelola:
    # ---- Informasi dataset aktif ----
    with st.container(border=True):
        st.subheader("Informasi Dataset Aktif")
        if df is None:
            st.info(pesan)
        else:
            info = info_dataset(df)
            meta = info["metadata"]

            baris1 = st.columns(3)
            baris1[0].metric("Jumlah Baris", f"{info['baris']:,}")
            baris1[1].metric("Jumlah Wilayah", f"{info['wilayah']:,}")
            if info["tahun_awal"] is not None:
                rentang = (
                    str(info["tahun_awal"]) if info["tahun_awal"] == info["tahun_akhir"]
                    else f"{info['tahun_awal']}–{info['tahun_akhir']}"
                )
                baris1[2].metric("Rentang Tahun", rentang)

            rincian = []
            if meta.get("nama_berkas"):
                rincian.append(f"**Berkas terakhir diimpor:** {meta['nama_berkas']}")
            if meta.get("waktu_import"):
                rincian.append(f"**Waktu impor:** {meta['waktu_import'].replace('T', ' ')}")
            for kunci, label in (("sumber", "Sumber"), ("tautan", "Tautan"),
                                 ("tanggal_pengambilan", "Tanggal pengambilan"),
                                 ("satuan", "Satuan PDRB"), ("catatan_revisi", "Catatan revisi")):
                if meta.get(kunci):
                    rincian.append(f"**{label}:** {meta[kunci]}")
            if rincian:
                st.markdown("  \n".join(rincian))
            else:
                st.caption("Belum ada catatan sumber data.")

            if meta.get("jumlah_baris") not in (None, info["baris"]):
                st.warning(
                    f"Jumlah baris pada catatan ({meta['jumlah_baris']}) berbeda dari berkas "
                    f"saat ini ({info['baris']}). Periksa apakah berkas diubah di luar aplikasi."
                )
            st.caption(
                f"Ukuran berkas {info['ukuran_kb']:.1f} KB · terakhir diubah "
                f"{info['diubah']:%d-%m-%Y %H:%M}"
            )

            with st.expander("Ubah catatan sumber data"):
                sumber = st.text_input("Sumber data", value=meta.get("sumber", ""), key="m_sumber")
                tautan = st.text_input("Tautan sumber", value=meta.get("tautan", ""), key="m_tautan")
                tanggal = st.text_input("Tanggal pengambilan (YYYY-MM-DD)",
                                        value=meta.get("tanggal_pengambilan", ""), key="m_tanggal")
                satuan = st.text_input("Satuan PDRB", value=meta.get("satuan", ""), key="m_satuan")
                revisi = st.text_area("Catatan revisi", value=meta.get("catatan_revisi", ""), key="m_revisi")
                if st.button("Simpan catatan sumber"):
                    baru = dict(meta)
                    baru.update(sumber=sumber.strip(), tautan=tautan.strip(),
                                tanggal_pengambilan=tanggal.strip(), satuan=satuan.strip(),
                                catatan_revisi=revisi.strip())
                    simpan_metadata(baru)
                    flash("Catatan sumber data disimpan.")
                    st.rerun()

    # ---- Unduh ----
    if df is not None:
        with st.container(border=True):
            st.subheader("Unduh Dataset")
            st.caption("Simpan salinan dataset saat ini ke perangkat.")
            salinan = df[kolom_dataset(df)]
            unduh = st.columns(2)
            unduh[0].download_button(
                "Unduh CSV", ke_csv_bytes(salinan),
                file_name="dataset_pendapatan.csv", mime="text/csv",
            )
            unduh[1].download_button(
                "Unduh Excel", ke_excel_bytes(salinan),
                file_name="dataset_pendapatan.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    # ---- Cadangan ----
    with st.container(border=True):
        st.subheader("Cadangan")
        st.caption(
            f"Cadangan dibuat otomatis sebelum dataset diganti, diedit, atau dihapus. "
            f"Disimpan {MAKS_CADANGAN} cadangan terbaru, lengkap dengan catatan sumbernya."
        )
        if df is not None and st.button("Buat cadangan sekarang"):
            buat_cadangan("manual")
            flash("Cadangan manual dibuat.")
            st.rerun()

        cadangan = daftar_cadangan()
        if not cadangan:
            st.info("Belum ada cadangan.")
        else:
            def label(c):
                baris = f"{c['baris']} baris" if c["baris"] is not None else "tidak terbaca"
                alasan = c["alasan"].replace("-", " ")
                if alasan != "manual" and not alasan.startswith("sebelum"):
                    alasan = "sebelum " + alasan  # cadangan = kondisi sebelum perubahan
                return f"{c['waktu']:%d-%m-%Y %H:%M:%S} · {alasan} · {baris}"

            pilihan = st.selectbox("Pilih cadangan", cadangan, format_func=label)
            yakin = st.checkbox(
                "Saya mengerti dataset aktif akan diganti dengan cadangan ini "
                "(kondisi saat ini dicadangkan lebih dulu)", key="yakin_pulih",
            )
            if st.button("Pulihkan cadangan ini", disabled=not yakin):
                try:
                    pulihkan(pilihan["nama"])
                    st.session_state.pop("editor_data", None)
                    flash("Dataset dipulihkan dari cadangan.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    # ---- Hapus semua ----
    if df is not None:
        with st.expander("Hapus semua data"):
            st.warning(
                "Seluruh dataset akan dihapus. Cadangan dibuat otomatis, "
                "sehingga data masih bisa dipulihkan dari bagian Cadangan."
            )
            if st.checkbox("Saya yakin ingin menghapus seluruh data"):
                if st.button("Hapus Semua Data"):
                    delete_dataset()
                    st.session_state.pop("editor_data", None)
                    flash("Seluruh data dihapus. Cadangan tersimpan dan bisa dipulihkan.", "info")
                    st.rerun()
