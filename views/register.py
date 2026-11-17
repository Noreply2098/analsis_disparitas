import streamlit as st

import auth

_, tengah, _ = st.columns([1, 2, 1])

with tengah:
    st.title("Daftar Akun")
    st.caption("Buat akun baru untuk menggunakan Regional Income Analysis.")

    if st.session_state.pop("_reg_sukses", False):
        st.success("Akun berhasil dibuat. Silakan masuk dengan username dan password Anda.")
        st.page_link("views/login.py", label="Ke halaman masuk", icon=":material/login:")
        st.stop()

    mode = auth.mode_registrasi()
    if mode == auth.MODE_PERTAMA:
        st.info(
            "Belum ada akun di aplikasi ini. Akun pertama yang dibuat akan menjadi "
            "**Administrator** yang mengelola pengguna dan kode undangan."
        )

    with st.container(border=True):
        with st.form("form_registrasi"):
            nama = st.text_input("Nama lengkap", max_chars=auth.NAMA_MAX)
            username = st.text_input(
                "Username",
                max_chars=auth.USERNAME_MAX,
                help=auth.PETUNJUK_USERNAME,
            )
            email = st.text_input("Email", max_chars=auth.EMAIL_MAX)
            password = st.text_input(
                "Password", type="password", help=auth.PETUNJUK_PASSWORD
            )
            konfirmasi = st.text_input("Konfirmasi password", type="password")
            st.caption(auth.PETUNJUK_PASSWORD)
            kode = ""
            if mode == auth.MODE_UNDANGAN:
                kode = st.text_input(
                    "Kode undangan",
                    max_chars=20,
                    placeholder="XXXX-XXXX-XXXX",
                    help="Kode sekali pakai dari administrator.",
                )
            kirim = st.form_submit_button("Daftar", type="primary")

    if kirim:
        with st.spinner("Membuat akun..."):
            errors = auth.registrasi(nama, username, email, password, konfirmasi, kode)
        if errors:
            for pesan in errors:
                st.error(pesan)
        else:
            st.session_state["_reg_sukses"] = True
            st.rerun()

    st.page_link(
        "views/login.py",
        label="Sudah punya akun? Masuk di sini",
        icon=":material/login:",
    )
