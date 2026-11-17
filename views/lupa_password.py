import streamlit as st

import auth

_, tengah, _ = st.columns([1, 2, 1])

with tengah:
    st.title("Lupa Password")

    if st.session_state.pop("_reset_sukses", False):
        st.success("Password berhasil diubah. Silakan masuk dengan password baru Anda.")
        st.page_link("views/login.py", label="Ke halaman masuk", icon=":material/login:")
        st.stop()

    st.caption("Atur ulang password dengan kode reset sekali pakai.")

    with st.container(border=True):
        st.subheader("1. Minta kode reset")
        if auth.email_reset_tersedia():
            st.caption(
                f"Kode dikirim ke email akun Anda dan berlaku {auth.RESET_MASA_MENIT} menit. "
                f"Maksimal {auth.RESET_MAKS_PERMINTAAN_JAM} permintaan per jam."
            )
            with st.form("form_minta_reset"):
                email_minta = st.text_input("Email terdaftar", max_chars=auth.EMAIL_MAX)
                kirim_minta = st.form_submit_button("Kirim kode reset")
            if kirim_minta:
                errors = auth.minta_reset(email_minta)
                if errors:
                    for pesan in errors:
                        st.error(pesan)
                else:
                    st.success(
                        "Jika email tersebut terdaftar, kode reset sudah dikirim. "
                        "Periksa kotak masuk dan folder spam, lalu lanjutkan ke langkah 2."
                    )
        else:
            st.info(
                "Pengiriman email belum diaktifkan di aplikasi ini. Minta kode reset "
                "kepada administrator, lalu lanjutkan ke langkah 2."
            )

    with st.container(border=True):
        st.subheader("2. Buat password baru")
        with st.form("form_reset_password"):
            email = st.text_input("Email akun", max_chars=auth.EMAIL_MAX)
            kode = st.text_input("Kode reset", max_chars=20, placeholder="XXXX-XXXX")
            baru = st.text_input("Password baru", type="password", help=auth.PETUNJUK_PASSWORD)
            konfirmasi = st.text_input("Konfirmasi password baru", type="password")
            st.caption(auth.PETUNJUK_PASSWORD)
            kirim = st.form_submit_button("Ubah password", type="primary")
        if kirim:
            with st.spinner("Memproses..."):
                errors = auth.reset_password_dengan_kode(email, kode, baru, konfirmasi)
            if errors:
                for pesan in errors:
                    st.error(pesan)
            else:
                st.session_state["_reset_sukses"] = True
                st.rerun()

    st.page_link("views/login.py", label="Kembali ke halaman masuk", icon=":material/login:")
