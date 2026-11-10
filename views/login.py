import streamlit as st

import auth

_, tengah, _ = st.columns([1, 2, 1])

with tengah:
    st.title("Masuk")
    st.caption("Masuk untuk mengakses Regional Income Analysis.")

    with st.container(border=True):
        with st.form("form_login"):
            username = st.text_input(
                "Username",
                max_chars=auth.USERNAME_MAX,
                placeholder="Username Anda",
            )
            # Kolom password Streamlit sudah memiliki tombol mata untuk
            # menampilkan/menyembunyikan isinya.
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Password Anda",
            )
            kirim = st.form_submit_button("Masuk", type="primary")

    if kirim:
        errors = auth.validasi_login(username, password)
        if errors:
            for pesan in errors:
                st.error(pesan)
        else:
            with st.spinner("Memeriksa akun..."):
                profil, pesan = auth.login(username, password)
            if pesan:
                st.error(pesan)
            else:
                auth.masuk(profil)
                st.rerun()

    st.page_link(
        "views/register.py",
        label="Belum punya akun? Daftar di sini",
        icon=":material/person_add:",
    )
