import streamlit as st

import auth

pengguna = auth.pengguna_aktif()
data = auth.ambil_pengguna(pengguna["id"]) if pengguna else None
if data is None:
    # Akun terhapus atau sesi tidak valid: paksa masuk ulang.
    auth.keluar()
    st.rerun()

st.title("Akun Saya")
st.caption("Kelola informasi akun dan keamanan password Anda.")

with st.container(border=True):
    st.subheader("Profil")
    kiri, kanan = st.columns(2)
    kiri.text_input("Nama lengkap", value=data["nama"], disabled=True)
    kanan.text_input("Username", value=data["username"], disabled=True)
    kiri.text_input("Email", value=data["email"], disabled=True)
    kanan.text_input("Terdaftar sejak", value=data["dibuat_pada"], disabled=True)
    st.text_input(
        "Peran",
        value="Administrator" if data["peran"] == auth.PERAN_ADMIN else "Pengguna",
        disabled=True,
    )

# Nomor pada key diganti setelah sukses agar isian form kembali kosong.
nomor = st.session_state.get("_pw_form_no", 0)

with st.container(border=True):
    st.subheader("Ubah Password")
    if st.session_state.pop("_pw_sukses", False):
        st.success("Password berhasil diubah. Gunakan password baru saat masuk berikutnya.")

    with st.form(f"form_ubah_password_{nomor}"):
        lama = st.text_input("Password lama", type="password")
        baru = st.text_input("Password baru", type="password", help=auth.PETUNJUK_PASSWORD)
        konfirmasi = st.text_input("Konfirmasi password baru", type="password")
        st.caption(auth.PETUNJUK_PASSWORD)
        kirim = st.form_submit_button("Ubah password", type="primary")

    if kirim:
        with st.spinner("Memproses..."):
            errors = auth.ubah_password(data["id"], lama, baru, konfirmasi)
        if errors:
            for pesan in errors:
                st.error(pesan)
        else:
            # Perubahan password mencabut semua sesi tetap; perangkat ini diberi sesi baru.
            auth.terbitkan_cookie(data["id"])
            st.session_state["_pw_sukses"] = True
            st.session_state["_pw_form_no"] = nomor + 1
            st.rerun()

with st.container(border=True):
    st.subheader("Keluar")
    st.caption("Akhiri sesi Anda di perangkat ini.")
    if st.button("Keluar dari akun", icon=":material/logout:", key="btn_keluar_akun"):
        auth.keluar()
        st.rerun()
