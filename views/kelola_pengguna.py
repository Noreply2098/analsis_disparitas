import pandas as pd
import streamlit as st

import auth

pengguna = auth.pengguna_aktif()
if not pengguna or pengguna.get("peran") != auth.PERAN_ADMIN:
    st.error("Halaman ini hanya untuk administrator.")
    st.stop()

admin_id = pengguna["id"]

st.title("Kelola Pengguna")
st.caption("Atur akun pengguna dan buat kode undangan untuk pendaftaran.")

tab_pengguna, tab_undangan = st.tabs(["Pengguna", "Kode Undangan"])

# ----------------------------------------------------------------------
with tab_pengguna:
    pesan = st.session_state.pop("_admin_pesan", None)
    if pesan:
        st.success(pesan)

    daftar = auth.daftar_pengguna(admin_id)
    tabel = pd.DataFrame(
        [
            {
                "Nama": u["nama"],
                "Username": u["username"],
                "Email": u["email"],
                "Peran": "Administrator" if u["peran"] == auth.PERAN_ADMIN else "Pengguna",
                "Status": "Aktif" if u["aktif"] else "Nonaktif",
                "Terdaftar": u["dibuat_pada"],
            }
            for u in daftar
        ]
    )
    st.dataframe(tabel, hide_index=True)

    lain = [u for u in daftar if u["id"] != admin_id]
    if not lain:
        st.info("Belum ada pengguna lain. Buat kode undangan di tab sebelah.")
    else:
        with st.container(border=True):
            st.subheader("Ubah akun")
            terpilih = st.selectbox(
                "Pilih pengguna",
                lain,
                format_func=lambda u: f"{u['nama']} (@{u['username']})",
            )
            kiri, kanan = st.columns(2)
            if terpilih["aktif"]:
                if kiri.button("Nonaktifkan akun", icon=":material/block:"):
                    galat = auth.ubah_status(admin_id, terpilih["id"], False)
                    if galat:
                        st.error(galat)
                    else:
                        st.session_state["_admin_pesan"] = (
                            f"Akun @{terpilih['username']} dinonaktifkan dan semua sesinya diakhiri."
                        )
                        st.rerun()
            else:
                if kiri.button("Aktifkan akun", icon=":material/check_circle:"):
                    galat = auth.ubah_status(admin_id, terpilih["id"], True)
                    if galat:
                        st.error(galat)
                    else:
                        st.session_state["_admin_pesan"] = f"Akun @{terpilih['username']} diaktifkan."
                        st.rerun()

            jadi_admin = terpilih["peran"] != auth.PERAN_ADMIN
            label = "Jadikan administrator" if jadi_admin else "Jadikan pengguna biasa"
            if kanan.button(label, icon=":material/admin_panel_settings:"):
                galat = auth.ubah_peran(
                    admin_id,
                    terpilih["id"],
                    auth.PERAN_ADMIN if jadi_admin else auth.PERAN_USER,
                )
                if galat:
                    st.error(galat)
                else:
                    st.session_state["_admin_pesan"] = (
                        f"Peran @{terpilih['username']} diubah."
                    )
                    st.rerun()

            if st.button("Buat kode reset password", icon=":material/key:"):
                kode_reset, galat = auth.buat_kode_reset_admin(admin_id, terpilih["id"])
                if galat:
                    st.error(galat)
                else:
                    st.success(
                        f"Kode reset untuk @{terpilih['username']} berlaku "
                        f"{auth.RESET_MASA_ADMIN_MENIT} menit."
                    )
                    st.code(kode_reset, language=None)
                    st.warning(
                        "Kirim kode ini ke pengguna lewat jalur yang aman. Pengguna memasukkannya "
                        "di halaman Lupa Password bersama email akunnya. Kode tidak dapat "
                        "dilihat lagi (hanya hash-nya yang disimpan)."
                    )

# ----------------------------------------------------------------------
with tab_undangan:
    st.write(
        "Pendaftar baru wajib memasukkan kode undangan. Setiap kode hanya bisa dipakai "
        "satu kali dan punya masa berlaku."
    )
    with st.form("form_undangan"):
        hari = st.number_input(
            "Masa berlaku (hari)",
            min_value=1,
            max_value=auth.UNDANGAN_HARI_MAKS,
            value=auth.UNDANGAN_HARI_BAWAAN,
            step=1,
        )
        buat = st.form_submit_button("Buat kode undangan", type="primary")

    if buat:
        kode, galat = auth.buat_undangan(admin_id, int(hari))
        if galat:
            st.error(galat)
        else:
            st.success("Kode undangan dibuat. Salin dan kirim ke calon pengguna.")
            st.code(kode, language=None)
            st.warning(
                "Kode ini hanya ditampilkan sekarang dan tidak dapat dilihat lagi "
                "(sistem hanya menyimpan hash-nya)."
            )

    riwayat = auth.daftar_undangan(admin_id)
    if riwayat:
        st.subheader("Riwayat kode")
        st.dataframe(pd.DataFrame(riwayat), hide_index=True)
    else:
        st.caption("Belum ada kode undangan.")
