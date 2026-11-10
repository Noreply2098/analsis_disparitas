"""Pengujian fitur autentikasi.  Jalankan:  pytest tests -q"""

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import auth  # noqa: E402


@pytest.fixture(autouse=True)
def db_sementara(tmp_path, monkeypatch):
    monkeypatch.setenv("RIA_AUTH_DB", str(tmp_path / "users.db"))
    monkeypatch.setattr(auth, "BCRYPT_ROUNDS", 4)  # cepat; bcrypt tetap dipakai
    return tmp_path / "users.db"


def daftar(nama="Budi Santoso", username="budi", email="budi@contoh.com",
           password="rahasia123", konfirmasi=None):
    return auth.registrasi(nama, username, email, password,
                           password if konfirmasi is None else konfirmasi)


# ---------- validasi ----------

def test_validasi_username():
    assert auth.validasi_username("") == ["Username tidak boleh kosong."]
    assert "minimal" in auth.validasi_username("ab")[0]
    assert "maksimal" in auth.validasi_username("a" * 31)[0]
    assert auth.validasi_username("budi santoso")  # spasi
    assert auth.validasi_username(".budi")          # diawali titik
    assert auth.validasi_username("bud<i>")
    assert auth.validasi_username("budi.s_01") == []


def test_validasi_email():
    assert auth.validasi_email("") == ["Email tidak boleh kosong."]
    for buruk in ["budi", "budi@", "@contoh.com", "budi@contoh", "bu..di@contoh.com", "a b@c.com"]:
        assert auth.validasi_email(buruk), buruk
    assert auth.validasi_email("budi.s+x@mail.contoh.co.id") == []


def test_validasi_password():
    assert auth.validasi_password("")
    assert any("minimal 8" in e for e in auth.validasi_password("abc123"))
    assert any("angka" in e for e in auth.validasi_password("hanyahuruf"))
    assert any("huruf" in e for e in auth.validasi_password("12345678"))
    assert any("terlalu panjang" in e for e in auth.validasi_password("a1" * 40))
    assert any("username" in e for e in auth.validasi_password("budi1234", "BUDI1234"))
    assert auth.validasi_password("rahasia123") == []


def test_validasi_nama():
    assert auth.validasi_nama("") == ["Nama lengkap tidak boleh kosong."]
    assert auth.validasi_nama("B1udi")
    assert auth.validasi_nama("Budi <script>")
    assert auth.validasi_nama("Siti Nur'aini-Putri Jr.") == []


# ---------- registrasi ----------

def test_registrasi_sukses_dan_password_di_hash(db_sementara):
    assert daftar() == []
    row = sqlite3.connect(db_sementara).execute(
        "SELECT password_hash, email FROM users").fetchone()
    assert row[0] != "rahasia123" and "rahasia123" not in row[0]
    assert row[0].startswith("$2b$")
    assert auth.cocok_password("rahasia123", row[0])
    assert row[1] == "budi@contoh.com"


def test_registrasi_duplikat_username_dan_email():
    assert daftar() == []
    e = daftar(email="lain@contoh.com", username="BUDI")
    assert any("Username 'BUDI' sudah terdaftar" in x for x in e)
    e = daftar(username="budi2", email="Budi@Contoh.com")
    assert any("sudah terdaftar" in x and "Email" in x for x in e)
    e = daftar()  # keduanya
    assert len(e) == 2


def test_registrasi_input_tidak_valid_menampilkan_semua_error():
    e = auth.registrasi("", "a", "salah", "abc", "xyz")
    assert len(e) >= 5
    assert any("Konfirmasi password tidak sama" in x for x in e)


def test_registrasi_konfirmasi_beda():
    assert daftar(konfirmasi="beda12345") == ["Konfirmasi password tidak sama dengan password."]


# ---------- login ----------

def test_login_sukses_gagal_dan_pesan_seragam():
    daftar()
    user, err = auth.login("budi", "rahasia123")
    assert err is None and user["username"] == "budi" and "password_hash" not in user
    assert auth.login("BUDI", "rahasia123")[0] is not None  # tidak peka huruf besar/kecil
    assert auth.login("budi", "salah12345") == (None, "Username atau password salah.")
    assert auth.login("tidakada", "rahasia123") == (None, "Username atau password salah.")


def test_validasi_login_format():
    assert len(auth.validasi_login("", "")) == 2
    assert "Format username tidak valid" in auth.validasi_login("a b", "rahasia123")[0]
    assert any("minimal 8" in e for e in auth.validasi_login("budi", "123"))


def test_akun_terkunci_setelah_gagal_berulang():
    daftar()
    for _ in range(auth.MAKS_GAGAL):
        assert auth.login("budi", "salah12345")[1] == "Username atau password salah."
    user, err = auth.login("budi", "rahasia123")  # benar pun ditolak saat dikunci
    assert user is None and "dikunci sementara" in err


def test_gagal_login_direset_setelah_berhasil():
    daftar()
    for _ in range(auth.MAKS_GAGAL - 1):
        auth.login("budi", "salah12345")
    assert auth.login("budi", "rahasia123")[0] is not None
    for _ in range(auth.MAKS_GAGAL - 1):
        auth.login("budi", "salah12345")
    assert auth.login("budi", "rahasia123")[0] is not None


# ---------- ubah password ----------

def test_ubah_password():
    daftar()
    uid = auth.login("budi", "rahasia123")[0]["id"]
    assert "Password lama salah." in auth.ubah_password(uid, "salah", "baru12345", "baru12345")
    assert any("minimal 8" in e for e in auth.ubah_password(uid, "rahasia123", "abc1", "abc1"))
    assert any("tidak sama" in e for e in auth.ubah_password(uid, "rahasia123", "baru12345", "beda12345"))
    assert any("sama dengan password lama" in e
               for e in auth.ubah_password(uid, "rahasia123", "rahasia123", "rahasia123"))
    assert auth.ubah_password(uid, "", "baru12345", "") 
    assert auth.ubah_password(uid, "rahasia123", "baru12345", "baru12345") == []
    assert auth.login("budi", "rahasia123")[0] is None
    assert auth.login("budi", "baru12345")[0] is not None


def test_ubah_password_akun_tidak_ada():
    assert auth.ubah_password(999, "x", "baru12345", "baru12345")


# ---------- alur UI ----------

def test_alur_ui_lengkap():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Masuk"

    # login kosong -> error validasi
    at.button[0].click().run()
    assert any("Username tidak boleh kosong" in e.value for e in at.error)
    assert any("Password tidak boleh kosong" in e.value for e in at.error)

    # login akun yang belum ada -> pesan seragam
    at.text_input[0].input("budi")
    at.text_input[1].input("rahasia123")
    at.button[0].click().run()
    assert [e.value for e in at.error] == ["Username atau password salah."]

    # registrasi
    at.switch_page("views/register.py").run()
    assert at.title[0].value == "Daftar Akun"
    for i, v in enumerate(["Budi Santoso", "budi", "budi@contoh.com", "rahasia123", "rahasia123"]):
        at.text_input[i].input(v)
    at.button[0].click().run()
    assert not at.exception and any("berhasil dibuat" in s.value for s in at.success)

    # registrasi duplikat
    at.switch_page("views/register.py").run()
    for i, v in enumerate(["Budi Lain", "budi", "budi@contoh.com", "rahasia123", "rahasia123"]):
        at.text_input[i].input(v)
    at.button[0].click().run()
    teks = " ".join(e.value for e in at.error)
    assert "Username 'budi' sudah terdaftar" in teks and "Email 'budi@contoh.com' sudah terdaftar" in teks

    # login berhasil -> masuk ke Dashboard
    at.switch_page("views/login.py").run()
    at.text_input[0].input("budi")
    at.text_input[1].input("rahasia123")
    at.button[0].click().run()
    assert not at.exception
    assert at.session_state["auth_user"]["username"] == "budi"
    assert "Dashboard" in at.title[0].value

    # ubah password
    at.switch_page("views/akun.py").run()
    ti = {t.label: t for t in at.text_input}
    ti["Password lama"].input("salahsalah1")
    ti["Password baru"].input("baru12345")
    ti["Konfirmasi password baru"].input("baru12345")
    at.button[0].click().run()
    assert any("Password lama salah" in e.value for e in at.error)

    ti = {t.label: t for t in at.text_input}
    ti["Password lama"].input("rahasia123")
    ti["Password baru"].input("baru12345")
    ti["Konfirmasi password baru"].input("baru12345")
    at.button[0].click().run()
    assert any("berhasil diubah" in s.value for s in at.success)

    # logout (tombol di halaman Akun) -> kembali ke Login dan sesi kosong
    [b for b in at.button if b.key == "btn_keluar_akun"][0].click().run()
    assert "auth_user" not in at.session_state
    assert at.title[0].value == "Masuk"

    # password lama tidak berlaku, password baru berlaku
    at.text_input[0].input("budi"); at.text_input[1].input("rahasia123")
    at.button[0].click().run()
    assert [e.value for e in at.error] == ["Username atau password salah."]
    at.text_input[0].input("budi"); at.text_input[1].input("baru12345")
    at.button[0].click().run()
    assert at.session_state["auth_user"]["username"] == "budi"
