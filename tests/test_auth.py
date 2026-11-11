"""Pengujian autentikasi, sesi, undangan, administrasi, dan data per pengguna.

Jalankan:  pytest tests -q
Pengujian logika dijalankan di SQLite dan (bila paket ``pgserver`` terpasang) di
PostgreSQL sungguhan.
"""

import io
import os
import re
import socket
import sys
import time
import types
import zipfile
from datetime import timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import auth  # noqa: E402
import db  # noqa: E402
import mailer  # noqa: E402
import storage  # noqa: E402

TABEL = "users, sesi, undangan, berkas_pengguna, reset_password"


# ======================================================================
# FIXTURE
# ======================================================================

@pytest.fixture(scope="session")
def server_pg(tmp_path_factory):
    pgserver = pytest.importorskip("pgserver")
    srv = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    yield srv.get_uri()
    srv.cleanup()


def _siapkan(backend, tmp_path, monkeypatch, request):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REGISTRASI_TERBUKA", raising=False)
    for kunci in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_SECURITY"):
        monkeypatch.delenv(kunci, raising=False)
    monkeypatch.setattr(auth, "BCRYPT_ROUNDS", 4)  # cepat; bcrypt tetap dipakai
    monkeypatch.setenv("RIA_DATA_DIR", str(tmp_path / "data"))
    db.tutup_semua()
    if backend == "postgres":
        monkeypatch.setenv("DATABASE_URL", request.getfixturevalue("server_pg"))
        with db.engine().begin() as conn:
            conn.execute(sa.text(f"TRUNCATE {TABEL} RESTART IDENTITY CASCADE"))
    else:
        monkeypatch.setenv("RIA_AUTH_DB", str(tmp_path / "ria.db"))


@pytest.fixture(params=["sqlite", "postgres"])
def backend(request, tmp_path, monkeypatch):
    _siapkan(request.param, tmp_path, monkeypatch, request)
    yield request.param
    db.tutup_semua()


@pytest.fixture
def db_sqlite(tmp_path, monkeypatch, request):
    _siapkan("sqlite", tmp_path, monkeypatch, request)
    yield
    db.tutup_semua()


def daftar(nama="Budi Santoso", username="budi", email="budi@contoh.com",
           password="rahasia123", konfirmasi=None, kode=""):
    return auth.registrasi(nama, username, email, password,
                           password if konfirmasi is None else konfirmasi, kode)


def admin_dan_user(backend=None):
    """Admin 'admin' (akun pertama) dan pengguna 'budi' yang masuk dengan kode undangan."""
    assert daftar("Admin Utama", "admin", "admin@contoh.com") == []
    admin = auth.login("admin", "rahasia123")[0]
    kode, _ = auth.buat_undangan(admin["id"])
    assert daftar(kode=kode) == []
    return admin, auth.login("budi", "rahasia123")[0]


# ======================================================================
# VALIDASI (tanpa database)
# ======================================================================

def test_validasi_username():
    assert auth.validasi_username("") == ["Username tidak boleh kosong."]
    assert "minimal" in auth.validasi_username("ab")[0]
    assert "maksimal" in auth.validasi_username("a" * 31)[0]
    assert auth.validasi_username("budi santoso")
    assert auth.validasi_username(".budi")
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


def test_validasi_login_format():
    assert len(auth.validasi_login("", "")) == 2
    assert "Format username tidak valid" in auth.validasi_login("a b", "rahasia123")[0]
    assert any("minimal 8" in e for e in auth.validasi_login("budi", "123"))


# ======================================================================
# REGISTRASI, KEBIJAKAN, UNDANGAN
# ======================================================================

def test_akun_pertama_jadi_admin_tanpa_kode_dan_password_di_hash(backend):
    assert auth.mode_registrasi() == auth.MODE_PERTAMA
    assert daftar() == []
    with db.engine().connect() as c:
        row = c.execute(sa.text("SELECT password_hash, email, peran FROM users")).first()
    assert row.peran == "admin" and row.email == "budi@contoh.com"
    assert row.password_hash.startswith("$2b$") and "rahasia123" not in row.password_hash
    assert auth.cocok_password("rahasia123", row.password_hash)
    assert auth.mode_registrasi() == auth.MODE_UNDANGAN


def test_pendaftar_berikutnya_wajib_kode_undangan(backend):
    assert daftar("Admin", "admin", "admin@contoh.com") == []
    e = daftar()
    assert any("Kode undangan wajib" in x for x in e)
    e = daftar(kode="ABCD-EFGH-JKLM")
    assert "Kode undangan tidak valid." in e
    assert jumlah() == 1


def jumlah():
    return auth.jumlah_pengguna()


def test_kode_undangan_sekali_pakai_dan_hanya_hash_tersimpan(backend):
    admin = (daftar("Admin", "admin", "admin@contoh.com"), auth.login("admin", "rahasia123")[0])[1]
    kode, err = auth.buat_undangan(admin["id"], 7)
    assert err is None and len(auth.normalisasi_kode(kode)) == auth.PANJANG_KODE
    with db.engine().connect() as c:
        kolom = c.execute(sa.text("SELECT kode_hash FROM undangan")).scalar_one()
    assert auth.normalisasi_kode(kode) not in kolom and len(kolom) == 64

    assert daftar(kode=kode.lower().replace("-", " ")) == []  # format longgar diterima
    assert auth.login("budi", "rahasia123")[0]["peran"] == "user"
    e = daftar("Siti", "siti", "siti@contoh.com", kode=kode)
    assert "Kode undangan sudah dipakai. Minta kode baru kepada administrator." in e


def test_kode_undangan_kedaluwarsa(backend):
    admin = (daftar("Admin", "admin", "admin@contoh.com"), auth.login("admin", "rahasia123")[0])[1]
    kode, _ = auth.buat_undangan(admin["id"], 1)
    with db.engine().begin() as c:
        c.execute(sa.text("UPDATE undangan SET kedaluwarsa = :t"),
                  {"t": auth._sekarang() - timedelta(minutes=1)})
    assert any("kedaluwarsa" in x for x in daftar(kode=kode))
    assert auth.daftar_undangan(admin["id"])[0]["Status"] == "Kedaluwarsa"


def test_registrasi_terbuka_lewat_konfigurasi(backend, monkeypatch):
    assert daftar("Admin", "admin", "admin@contoh.com") == []
    monkeypatch.setenv("REGISTRASI_TERBUKA", "true")
    assert auth.mode_registrasi() == auth.MODE_TERBUKA
    assert daftar() == []


def test_registrasi_duplikat_username_dan_email(backend, monkeypatch):
    monkeypatch.setenv("REGISTRASI_TERBUKA", "true")
    assert daftar() == []
    e = daftar(email="lain@contoh.com", username="BUDI")
    assert any("Username 'BUDI' sudah terdaftar" in x for x in e)
    e = daftar(username="budi2", email="Budi@Contoh.com")
    assert any("sudah terdaftar" in x and "Email" in x for x in e)
    assert len(daftar()) == 2


def test_registrasi_input_tidak_valid_menampilkan_semua_error(backend):
    e = auth.registrasi("", "a", "salah", "abc", "xyz")
    assert len(e) >= 5 and any("Konfirmasi password tidak sama" in x for x in e)
    assert daftar(konfirmasi="beda12345") == ["Konfirmasi password tidak sama dengan password."]


def test_kode_undangan_tidak_terpakai_bila_registrasi_gagal(backend):
    admin = (daftar("Admin", "admin", "admin@contoh.com"), auth.login("admin", "rahasia123")[0])[1]
    kode, _ = auth.buat_undangan(admin["id"])
    assert daftar(email="admin@contoh.com", kode=kode)  # email duplikat -> gagal
    assert auth.daftar_undangan(admin["id"])[0]["Status"] == "Aktif"
    assert daftar(kode=kode) == []


# ======================================================================
# LOGIN
# ======================================================================

def test_login_sukses_gagal_dan_pesan_seragam(backend):
    daftar()
    user, err = auth.login("budi", "rahasia123")
    assert err is None and user["username"] == "budi" and "password_hash" not in user
    assert auth.login("BUDI", "rahasia123")[0] is not None
    assert auth.login("budi", "salah12345") == (None, "Username atau password salah.")
    assert auth.login("tidakada", "rahasia123") == (None, "Username atau password salah.")


def test_akun_terkunci_setelah_gagal_berulang_dan_reset_saat_berhasil(backend):
    daftar()
    for _ in range(auth.MAKS_GAGAL - 1):
        auth.login("budi", "salah12345")
    assert auth.login("budi", "rahasia123")[0] is not None  # counter direset
    for _ in range(auth.MAKS_GAGAL):
        assert auth.login("budi", "salah12345")[1] == "Username atau password salah."
    user, err = auth.login("budi", "rahasia123")
    assert user is None and "dikunci sementara" in err


def test_akun_nonaktif_tidak_bisa_login(backend):
    admin, budi = admin_dan_user()
    assert auth.ubah_status(admin["id"], budi["id"], False) is None
    assert auth.login("budi", "rahasia123") == (None, auth.PESAN_NONAKTIF)
    assert auth.ubah_status(admin["id"], budi["id"], True) is None
    assert auth.login("budi", "rahasia123")[0] is not None


# ======================================================================
# SESI TETAP (cookie)
# ======================================================================

def test_sesi_token_pulih_kedaluwarsa_dan_hanya_hash_tersimpan(backend):
    daftar()
    uid = auth.login("budi", "rahasia123")[0]["id"]
    token = auth.buat_token(uid)
    with db.engine().connect() as c:
        tersimpan = c.execute(sa.text("SELECT token_hash FROM sesi")).scalar_one()
    assert token not in tersimpan and len(tersimpan) == 64

    assert auth.pulihkan_dari_token(token)["username"] == "budi"
    assert auth.pulihkan_dari_token("token-ngawur") is None
    assert auth.pulihkan_dari_token("") is None and auth.pulihkan_dari_token(None) is None

    with db.engine().begin() as c:
        c.execute(sa.text("UPDATE sesi SET kedaluwarsa = :t"),
                  {"t": auth._sekarang() - timedelta(seconds=1)})
    assert auth.pulihkan_dari_token(token) is None


def test_token_dicabut_saat_logout_nonaktif_dan_ganti_password(backend):
    admin, budi = admin_dan_user()
    t1, t2 = auth.buat_token(budi["id"]), auth.buat_token(budi["id"])
    auth.hapus_token(t1)
    assert auth.pulihkan_dari_token(t1) is None and auth.pulihkan_dari_token(t2)

    assert auth.ubah_password(budi["id"], "rahasia123", "baru12345", "baru12345") == []
    assert auth.pulihkan_dari_token(t2) is None  # semua sesi dicabut

    t3 = auth.buat_token(budi["id"])
    assert auth.ubah_status(admin["id"], budi["id"], False) is None
    assert auth.pulihkan_dari_token(t3) is None


# ======================================================================
# UBAH PASSWORD
# ======================================================================

def test_ubah_password(backend):
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
    assert auth.ubah_password(999, "x", "baru12345", "baru12345")


# ======================================================================
# ADMINISTRASI
# ======================================================================

def test_hanya_admin_yang_boleh_mengelola(backend):
    admin, budi = admin_dan_user()
    assert auth.daftar_pengguna(budi["id"]) == []
    assert auth.daftar_undangan(budi["id"]) == []
    assert auth.buat_undangan(budi["id"])[0] is None
    assert auth.ubah_status(budi["id"], admin["id"], False)
    assert auth.ubah_peran(budi["id"], admin["id"], "user")
    assert len(auth.daftar_pengguna(admin["id"])) == 2


def test_admin_tidak_bisa_menonaktifkan_atau_menurunkan_diri_sendiri(backend):
    admin, budi = admin_dan_user()
    assert "sendiri" in auth.ubah_status(admin["id"], admin["id"], False)
    assert "sendiri" in auth.ubah_peran(admin["id"], admin["id"], "user")
    assert auth.ubah_peran(admin["id"], budi["id"], "admin") is None
    assert auth.ambil_pengguna(budi["id"])["peran"] == "admin"
    assert auth.ubah_peran(admin["id"], budi["id"], "superuser")
    assert auth.buat_undangan(admin["id"], 0)[0] is None
    assert auth.buat_undangan(admin["id"], 99)[0] is None


def test_status_undangan_dipakai(backend):
    admin, _ = admin_dan_user()
    status = auth.daftar_undangan(admin["id"])[0]["Status"]
    assert status == "Dipakai oleh budi"


# ======================================================================
# DATA PER PENGGUNA
# ======================================================================

@pytest.fixture
def sesi_palsu(monkeypatch, tmp_path):
    """Ganti session_state/pengguna aktif dengan versi sederhana untuk menguji storage."""
    state = {}
    monkeypatch.setenv("RIA_DATA_DIR", str(tmp_path / "data"))  # jangan menulis ke folder proyek
    monkeypatch.setattr(storage, "st", types.SimpleNamespace(session_state=state))
    monkeypatch.setattr(auth, "st", types.SimpleNamespace(session_state=state))

    pengguna = {"id": 1}
    monkeypatch.setattr(auth, "pengguna_aktif", lambda: pengguna)
    return state, pengguna


def tulis_data(isi="Nama Wilayah,Tahun\nA,2023\n"):
    storage.path_dataset().write_text(isi, encoding="utf-8")
    storage.path_metadata().write_text('{"sumber": "uji"}', encoding="utf-8")
    storage.dir_cadangan().mkdir(exist_ok=True)
    (storage.dir_cadangan() / "dataset_20240101_impor.csv").write_text(isi, encoding="utf-8")


def test_data_tiap_pengguna_terpisah(backend, sesi_palsu):
    _, pengguna = sesi_palsu
    tulis_data("Nama Wilayah,Tahun\nMILIK-1,2023\n")
    pengguna["id"] = 2
    assert not storage.path_dataset().exists()
    assert storage.dir_data() != storage._akar_data() / "1"
    tulis_data("Nama Wilayah,Tahun\nMILIK-2,2023\n")
    pengguna["id"] = 1
    assert "MILIK-1" in storage.path_dataset().read_text()
    assert "MILIK-2" not in storage.path_dataset().read_text()


def test_data_bertahan_setelah_server_restart(backend, sesi_palsu, tmp_path):
    state, _ = sesi_palsu
    daftar()  # pengguna id 1 (kunci asing berkas_pengguna)
    storage.siapkan_data()
    tulis_data()
    storage.sinkronkan_data()
    with db.engine().connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM berkas_pengguna")).scalar_one() == 1

    # "Restart": disk hosting kosong dan sesi baru.
    import shutil
    shutil.rmtree(tmp_path / "data" / "pengguna")
    state.clear()
    storage.siapkan_data()
    assert storage.path_dataset().read_text() == "Nama Wilayah,Tahun\nA,2023\n"
    assert storage.path_metadata().read_text() == '{"sumber": "uji"}'
    assert (storage.dir_cadangan() / "dataset_20240101_impor.csv").exists()

    # Setelah dipulihkan tidak ada unggah ulang yang tidak perlu.
    with db.engine().connect() as c:
        sidik = c.execute(sa.text("SELECT sidik FROM berkas_pengguna")).scalar_one()
    assert sidik == storage.sidik_folder(storage.dir_data())


def test_sinkron_hanya_saat_ada_perubahan(backend, sesi_palsu, monkeypatch):
    daftar()
    storage.siapkan_data()
    tulis_data()
    panggilan = []
    asli = storage.simpan_arsip
    monkeypatch.setattr(storage, "simpan_arsip", lambda *a: (panggilan.append(1), asli(*a)))
    storage.sinkronkan_data()
    storage.sinkronkan_data()
    storage.sinkronkan_data()
    assert len(panggilan) == 1


def test_arsip_berbahaya_tidak_bisa_menulis_di_luar_folder(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "x")
        zf.writestr("/abs.txt", "x")
        zf.writestr("cadangan/../x.csv", "x")
        zf.writestr("cadangan/sub/y.csv", "x")
        zf.writestr("rahasia.py", "x")
        zf.writestr("dataset.csv", "aman")
    folder = tmp_path / "u"
    folder.mkdir()
    assert storage.ekstrak_arsip(buf.getvalue(), folder) == 1
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["dataset.csv"]


def test_arsip_terlalu_besar_ditolak_dengan_peringatan(backend, sesi_palsu, monkeypatch):
    state, _ = sesi_palsu
    daftar()
    storage.siapkan_data()
    monkeypatch.setattr(storage, "MAKS_ARSIP_MB", 0)
    tulis_data()
    storage.sinkronkan_data()
    assert "melebihi" in state[storage.PERINGATAN_KEY]
    with db.engine().connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM berkas_pengguna")).scalar_one() == 0


def test_kunci_cache_cetak_memuat_id_pengguna(sesi_palsu):
    import laporan
    _, pengguna = sesi_palsu
    k1 = laporan._versi_data()
    pengguna["id"] = 2
    k2 = laporan._versi_data()
    assert k1[0] == "u1" and k2[0] == "u2" and k1 != k2


# ======================================================================
# LUPA PASSWORD
# ======================================================================

@pytest.fixture
def surat(monkeypatch):
    """SMTP 'aktif' dengan pengiriman dicatat ke daftar (tanpa jaringan)."""
    kotak = []
    monkeypatch.setenv("SMTP_HOST", "smtp.contoh.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@contoh.test")
    monkeypatch.setattr(mailer, "SINKRON", True)
    monkeypatch.setattr(mailer, "kirim_email", lambda tujuan, subjek, isi: kotak.append((tujuan, subjek, isi)))
    return kotak


def kode_dari(kotak) -> str:
    return re.search(r"Kode reset: ([A-Z2-9]{4}-[A-Z2-9]{4})", kotak[-1][2]).group(1)


def test_konfigurasi_smtp(monkeypatch):
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_SECURITY"):
        monkeypatch.delenv(k, raising=False)
    assert mailer.konfigurasi() is None and not mailer.terkonfigurasi()
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    assert mailer.konfigurasi() is None  # pengirim belum ada
    monkeypatch.setenv("SMTP_USER", "saya@gmail.com")
    cfg = mailer.konfigurasi()
    assert cfg["port"] == 587 and cfg["keamanan"] == "starttls" and cfg["dari"] == "saya@gmail.com"
    monkeypatch.setenv("SMTP_PORT", "abc")
    assert mailer.konfigurasi() is None
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    assert mailer.konfigurasi()["keamanan"] == "ssl"
    monkeypatch.setenv("SMTP_SECURITY", "ngawur")
    assert mailer.konfigurasi()["keamanan"] == "starttls"


def test_minta_reset_kirim_email_dan_respons_seragam(backend, surat):
    daftar()
    assert auth.minta_reset("BUDI@contoh.com") == []
    assert len(surat) == 1
    tujuan, subjek, isi = surat[0]
    assert tujuan == "budi@contoh.com" and "Kode reset password" in subjek
    assert "Username : budi" in isi and "15 menit" in isi
    assert auth.minta_reset("tidak@ada.com") == []   # respons sama, tanpa email
    assert len(surat) == 1
    assert auth.minta_reset("salah")                  # hanya error format yang dibedakan
    assert auth.minta_reset("") == ["Email tidak boleh kosong."]


def test_minta_reset_tanpa_smtp_tidak_mengirim_apa_apa(backend, monkeypatch):
    daftar()
    assert not auth.email_reset_tersedia()
    assert auth.minta_reset("budi@contoh.com") == []
    with db.engine().connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM reset_password")).scalar_one() == 0


def test_reset_password_sukses_kode_sekali_pakai(backend, surat):
    admin, budi = admin_dan_user()
    token = auth.buat_token(budi["id"])
    for _ in range(auth.MAKS_GAGAL):
        auth.login("budi", "salah12345")  # akun terkunci
    auth.minta_reset("budi@contoh.com")
    kode = kode_dari(surat)

    assert auth.reset_password_dengan_kode("budi@contoh.com", kode.lower(), "baru12345", "baru12345") == []
    assert auth.login("budi", "rahasia123")[0] is None
    assert auth.login("budi", "baru12345")[0] is not None     # kunci akun ikut dibuka
    assert auth.pulihkan_dari_token(token) is None            # semua sesi dicabut
    assert auth.reset_password_dengan_kode(
        "budi@contoh.com", kode, "lain12345", "lain12345") == [auth.PESAN_RESET_GAGAL]


def test_kode_hangus_setelah_tebakan_salah_berulang(backend, surat):
    daftar()
    auth.minta_reset("budi@contoh.com")
    kode = kode_dari(surat)
    for _ in range(auth.RESET_MAKS_GAGAL):
        assert auth.reset_password_dengan_kode(
            "budi@contoh.com", "AAAA-BBBB", "baru12345", "baru12345") == [auth.PESAN_RESET_GAGAL]
    assert auth.reset_password_dengan_kode(
        "budi@contoh.com", kode, "baru12345", "baru12345") == [auth.PESAN_RESET_GAGAL]
    assert auth.login("budi", "rahasia123")[0] is not None


def test_kode_kedaluwarsa_dan_kode_baru_membatalkan_yang_lama(backend, surat):
    daftar()
    auth.minta_reset("budi@contoh.com")
    kode1 = kode_dari(surat)
    auth.minta_reset("budi@contoh.com")
    kode2 = kode_dari(surat)
    assert kode1 != kode2
    assert auth.reset_password_dengan_kode(
        "budi@contoh.com", kode1, "baru12345", "baru12345") == [auth.PESAN_RESET_GAGAL]
    with db.engine().begin() as c:
        c.execute(sa.text("UPDATE reset_password SET kedaluwarsa = :t"),
                  {"t": auth._sekarang() - timedelta(seconds=1)})
    assert auth.reset_password_dengan_kode(
        "budi@contoh.com", kode2, "baru12345", "baru12345") == [auth.PESAN_RESET_GAGAL]


def test_batas_permintaan_kode_per_jam(backend, surat):
    daftar()
    for _ in range(auth.RESET_MAKS_PERMINTAAN_JAM + 2):
        assert auth.minta_reset("budi@contoh.com") == []
    assert len(surat) == auth.RESET_MAKS_PERMINTAAN_JAM


def test_validasi_password_baru_tidak_membakar_kode(backend, surat):
    daftar()
    auth.minta_reset("budi@contoh.com")
    kode = kode_dari(surat)
    assert any("minimal 8" in e for e in auth.reset_password_dengan_kode("budi@contoh.com", kode, "abc1", "abc1"))
    assert any("tidak sama" in e for e in auth.reset_password_dengan_kode("budi@contoh.com", kode, "baru12345", "x"))
    assert any("Kode reset tidak boleh kosong" in e
               for e in auth.reset_password_dengan_kode("budi@contoh.com", "", "baru12345", "baru12345"))
    assert auth.reset_password_dengan_kode("budi@contoh.com", kode, "budi", "budi")  # password lemah
    assert auth.reset_password_dengan_kode("budi@contoh.com", kode, "baru12345", "baru12345") == []


def test_email_tidak_dikenal_dan_akun_nonaktif_mendapat_pesan_sama(backend, surat):
    admin, budi = admin_dan_user()
    auth.minta_reset("budi@contoh.com")
    kode = kode_dari(surat)
    assert auth.ubah_status(admin["id"], budi["id"], False) is None
    for email in ("budi@contoh.com", "tidak@ada.com"):
        assert auth.reset_password_dengan_kode(email, kode, "baru12345", "baru12345") == [auth.PESAN_RESET_GAGAL]
    n = len(surat)
    auth.minta_reset("budi@contoh.com")  # nonaktif: tidak ada email baru
    assert len(surat) == n


def test_kode_reset_dari_admin(backend):
    admin, budi = admin_dan_user()
    assert auth.buat_kode_reset_admin(budi["id"], admin["id"])[0] is None  # bukan admin
    assert auth.buat_kode_reset_admin(admin["id"], 999)[0] is None
    kode, err = auth.buat_kode_reset_admin(admin["id"], budi["id"])
    assert err is None and re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", kode)
    with db.engine().connect() as c:
        rp = db.reset_password
        row = c.execute(sa.select(rp.c.kode_hash, rp.c.dibuat_oleh, rp.c.kedaluwarsa, rp.c.dibuat_pada)).first()
    assert auth.normalisasi_kode(kode) not in row.kode_hash and len(row.kode_hash) == 64
    assert row.dibuat_oleh == admin["id"]
    assert 59 <= (row.kedaluwarsa - row.dibuat_pada).total_seconds() / 60 <= 61

    assert auth.reset_password_dengan_kode("budi@contoh.com", kode, "baru12345", "baru12345") == []
    assert auth.login("budi", "baru12345")[0] is not None
    assert auth.ubah_status(admin["id"], budi["id"], False) is None
    assert auth.buat_kode_reset_admin(admin["id"], budi["id"])[0] is None   # nonaktif


def test_smtp_sungguhan_lewat_server_palsu(backend, monkeypatch):
    """Pengiriman nyata lewat protokol SMTP (server palsu lokal, tanpa TLS)."""
    pytest.importorskip("aiosmtpd")
    from aiosmtpd.controller import Controller

    class Tangkap:
        def __init__(self):
            self.surat = []

        async def handle_DATA(self, server, session, envelope):
            self.surat.append(envelope)
            return "250 OK"

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    tangkap = Tangkap()
    ctrl = Controller(tangkap, hostname="127.0.0.1", port=port)
    ctrl.start()
    try:
        monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
        monkeypatch.setenv("SMTP_PORT", str(port))
        monkeypatch.setenv("SMTP_SECURITY", "none")
        monkeypatch.setenv("SMTP_FROM", "noreply@contoh.test")
        monkeypatch.setattr(mailer, "SINKRON", True)
        daftar()
        assert auth.minta_reset("budi@contoh.com") == []
        assert len(tangkap.surat) == 1
        env = tangkap.surat[0]
        assert env.mail_from == "noreply@contoh.test" and env.rcpt_tos == ["budi@contoh.com"]
        isi = env.content.decode("utf-8", "replace")
        assert "Kode reset password" in isi and re.search(r"Kode reset: [A-Z2-9]{4}-[A-Z2-9]{4}", isi)
    finally:
        ctrl.stop()


def test_kegagalan_smtp_tidak_membocorkan_apa_pun(backend, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1")  # tidak ada server
    monkeypatch.setenv("SMTP_SECURITY", "none")
    monkeypatch.setenv("SMTP_FROM", "noreply@contoh.test")
    monkeypatch.setattr(mailer, "SINKRON", True)
    daftar()
    assert auth.minta_reset("budi@contoh.com") == []  # galat dicatat di log, respons tetap sama


# ======================================================================
# MODE TAMU: data tidak disimpan permanen
# ======================================================================

def test_tamu_memakai_folder_sementara_dan_tidak_menyentuh_database(backend, sesi_palsu, monkeypatch, tmp_path):
    state, _ = sesi_palsu
    monkeypatch.setattr(auth, "pengguna_aktif", lambda: None)
    tulis_data()
    folder = storage.dir_data()
    assert str(folder).startswith(str(tmp_path / "data" / "tamu"))
    assert storage.path_dataset().exists()
    assert not (tmp_path / "data" / "pengguna").exists()  # tidak ada folder permanen
    storage.siapkan_data()
    storage.sinkronkan_data()
    with db.engine().connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM berkas_pengguna")).scalar_one() == 0


def test_tamu_tiap_sesi_terpisah_dan_data_hilang_saat_sesi_baru(backend, sesi_palsu, monkeypatch):
    state, _ = sesi_palsu
    monkeypatch.setattr(auth, "pengguna_aktif", lambda: None)
    tulis_data("Nama Wilayah,Tahun\nTAMU-A,2023\n")
    folder_a, kunci_a = storage.dir_data(), storage.kunci_pemilik()
    state.clear()  # refresh/tab baru = sesi baru
    assert storage.dir_data() != folder_a and storage.kunci_pemilik() != kunci_a
    assert not storage.path_dataset().exists()  # data tamu sebelumnya tidak terlihat


def test_folder_tamu_lama_dibersihkan(sesi_palsu, monkeypatch, tmp_path):
    akar = storage._akar_tamu()
    lama, baru = akar / "lama", akar / "baru"
    for d in (lama, baru):
        (d / "cadangan").mkdir(parents=True)
        (d / "dataset.csv").write_text("x")
    usang = time.time() - (storage.MASA_TAMU_JAM + 1) * 3600
    os.utime(lama, (usang, usang))
    storage.bersihkan_tamu_lama()
    assert not lama.exists() and baru.exists()


def test_data_tamu_dibawa_ke_akun_kosong_saat_masuk(backend, sesi_palsu, monkeypatch):
    state, pengguna = sesi_palsu
    daftar()  # akun id 1
    monkeypatch.setattr(auth, "pengguna_aktif", lambda: None)
    tulis_data("Nama Wilayah,Tahun\nTAMU,2023\n")
    folder_tamu = storage.dir_data()

    monkeypatch.setattr(auth, "pengguna_aktif", lambda: pengguna)  # tamu masuk
    storage.siapkan_data()
    assert "TAMU" in storage.path_dataset().read_text()
    assert not folder_tamu.exists() and storage.TAMU_KEY not in state
    assert any("tersimpan di akun" in p for p, _ in state[auth.TOAST_KEY])
    with db.engine().connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM berkas_pengguna")).scalar_one() == 1


def test_data_tamu_tidak_menimpa_data_akun(backend, sesi_palsu, monkeypatch):
    state, pengguna = sesi_palsu
    daftar()
    storage.siapkan_data()
    tulis_data("Nama Wilayah,Tahun\nMILIK-AKUN,2023\n")
    storage.sinkronkan_data()

    state.clear()  # keluar -> tamu
    monkeypatch.setattr(auth, "pengguna_aktif", lambda: None)
    tulis_data("Nama Wilayah,Tahun\nTAMU,2023\n")
    folder_tamu = storage.dir_data()
    monkeypatch.setattr(auth, "pengguna_aktif", lambda: pengguna)
    storage.siapkan_data()
    teks = storage.path_dataset().read_text()
    assert "MILIK-AKUN" in teks and "TAMU" not in teks
    assert not folder_tamu.exists()
    assert any("sudah memiliki data" in p for p, _ in state[auth.TOAST_KEY])


# ======================================================================
# ALUR UI (AppTest)
# ======================================================================

def isi(at, nilai):
    for i, v in enumerate(nilai):
        at.text_input[i].input(v)


def per_label(at):
    return {t.label: t for t in at.text_input}


def test_alur_ui_lengkap(db_sqlite):
    from streamlit.testing.v1 import AppTest

    # ---- Tamu: langsung ke aplikasi (bukan panel login), dengan banner mode tamu
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    assert not at.exception
    assert "Dashboard" in at.title[0].value
    assert any("Mode tamu" in i.value for i in at.info)
    for halaman in ("views/data_pendapatan.py", "views/analisis.py", "views/visualisasi.py",
                    "views/import_data.py"):
        at.switch_page(halaman).run()
        assert not at.exception and any("Mode tamu" in i.value for i in at.info), halaman
    with pytest.raises(ValueError):
        at.switch_page("views/akun.py")        # halaman akun/admin tidak ada untuk tamu
    with pytest.raises(ValueError):
        at.switch_page("views/kelola_pengguna.py")

    # ---- Halaman Masuk: tanpa banner; validasi dan pesan seragam
    at.switch_page("views/login.py").run()
    assert at.title[0].value == "Masuk" and not any("Mode tamu" in i.value for i in at.info)
    at.button[0].click().run()
    assert any("Username tidak boleh kosong" in e.value for e in at.error)
    isi(at, ["budi", "rahasia123"])
    at.button[0].click().run()
    assert [e.value for e in at.error] == ["Username atau password salah."]

    # ---- Registrasi akun pertama -> admin
    at.switch_page("views/register.py").run()
    assert len(at.text_input) == 5 and any("Administrator" in i.value for i in at.info)
    isi(at, ["Admin Utama", "admin", "admin@contoh.com", "rahasia123", "rahasia123"])
    at.button[0].click().run()
    assert any("berhasil dibuat" in s.value for s in at.success)

    # ---- Login admin: kembali ke Dashboard (sebagai pengguna), tanpa banner tamu
    at.switch_page("views/login.py").run()
    isi(at, ["admin", "rahasia123"])
    at.button[0].click().run()
    assert at.session_state["auth_user"]["peran"] == "admin"
    assert "Dashboard" in at.title[0].value and not any("Mode tamu" in i.value for i in at.info)

    # ---- Admin membuat kode undangan, lalu keluar -> kembali ke mode tamu
    at.switch_page("views/kelola_pengguna.py").run()
    [b for b in at.button if b.label == "Buat kode undangan"][0].click().run()
    kode_undangan = at.code[0].value
    at.switch_page("views/akun.py").run()
    [b for b in at.button if b.key == "btn_keluar_akun"][0].click().run()
    assert "auth_user" not in at.session_state
    assert "Dashboard" in at.title[0].value and any("Mode tamu" in i.value for i in at.info)

    # ---- Pendaftar kedua wajib kode undangan
    at.switch_page("views/register.py").run()
    assert len(at.text_input) == 6
    isi(at, ["Budi Santoso", "budi", "budi@contoh.com", "rahasia123", "rahasia123", ""])
    at.button[0].click().run()
    assert any("Kode undangan wajib" in e.value for e in at.error)
    at.text_input[5].input(kode_undangan)
    at.button[0].click().run()
    assert any("berhasil dibuat" in s.value for s in at.success)

    # ---- Lupa password tanpa SMTP: ada petunjuk ke administrator
    at.switch_page("views/lupa_password.py").run()
    assert not at.exception and any("belum diaktifkan" in i.value for i in at.info)
    assert "Email terdaftar" not in per_label(at)

    # ---- Admin membuat kode reset untuk Budi
    at.switch_page("views/login.py").run()
    isi(at, ["admin", "rahasia123"])
    at.button[0].click().run()
    at.switch_page("views/kelola_pengguna.py").run()
    [b for b in at.button if b.label == "Buat kode reset password"][0].click().run()
    assert not at.error, [e.value for e in at.error]
    kode_reset = at.code[0].value
    assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", kode_reset)
    at.switch_page("views/akun.py").run()
    [b for b in at.button if b.key == "btn_keluar_akun"][0].click().run()

    # ---- Budi (tamu) memakai kode: salah dulu, lalu benar
    at.switch_page("views/lupa_password.py").run()
    ti = per_label(at)
    ti["Email akun"].input("budi@contoh.com"); ti["Kode reset"].input("AAAA-BBBB")
    ti["Password baru"].input("baru12345"); ti["Konfirmasi password baru"].input("baru12345")
    at.button[0].click().run()
    assert any("Kode reset tidak valid" in e.value for e in at.error)
    ti = per_label(at)
    ti["Email akun"].input("budi@contoh.com"); ti["Kode reset"].input(kode_reset)
    ti["Password baru"].input("baru12345"); ti["Konfirmasi password baru"].input("baru12345")
    at.button[0].click().run()
    assert any("Password berhasil diubah" in s.value for s in at.success)

    # ---- Login: password lama ditolak, baru diterima; pengguna biasa tak punya menu admin
    at.switch_page("views/login.py").run()
    isi(at, ["budi", "rahasia123"])
    at.button[0].click().run()
    assert [e.value for e in at.error] == ["Username atau password salah."]
    isi(at, ["budi", "baru12345"])
    at.button[0].click().run()
    assert at.session_state["auth_user"]["username"] == "budi"
    with pytest.raises(ValueError):
        at.switch_page("views/kelola_pengguna.py")

    # ---- Ubah password dari halaman Akun
    at.switch_page("views/akun.py").run()
    ti = per_label(at)
    ti["Password lama"].input("salahsalah1"); ti["Password baru"].input("lagi12345")
    ti["Konfirmasi password baru"].input("lagi12345")
    at.button[0].click().run()
    assert any("Password lama salah" in e.value for e in at.error)
    ti = per_label(at)
    ti["Password lama"].input("baru12345"); ti["Password baru"].input("lagi12345")
    ti["Konfirmasi password baru"].input("lagi12345")
    at.button[0].click().run()
    assert any("berhasil diubah" in s.value for s in at.success)


def test_ui_lupa_password_dengan_email(db_sqlite, monkeypatch):
    from streamlit.testing.v1 import AppTest

    assert daftar("Admin", "admin", "admin@contoh.com") == []
    monkeypatch.setenv("SMTP_HOST", "smtp.contoh.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@contoh.test")
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    at.switch_page("views/lupa_password.py").run()
    assert not at.exception and "Email terdaftar" in per_label(at)
    per_label(at)["Email terdaftar"].input("salah")
    at.button[0].click().run()
    assert any("Format email tidak valid" in e.value for e in at.error)


def test_tamu_tetap_bisa_memakai_aplikasi_saat_database_mati(db_sqlite, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DATABASE_URL", "postgresql://x:y@127.0.0.1:1/tidak_ada")  # tidak ada server
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=60).run()
    assert not at.exception and "Dashboard" in at.title[0].value
    for halaman in ("views/data_pendapatan.py", "views/analisis.py", "views/visualisasi.py"):
        at.switch_page(halaman).run()
        assert not at.exception, halaman
    at.switch_page("views/register.py").run()  # butuh database: pesan ramah, bukan traceback
    assert any("Tidak dapat terhubung ke database" in e.value for e in at.error)


def test_cli_kode_reset(backend, capsys):
    import kelola_akun
    admin, budi = admin_dan_user()
    assert kelola_akun.kode_reset("BUDI") == 0
    kode = re.search(r"([A-Z2-9]{4}-[A-Z2-9]{4})", capsys.readouterr().out).group(1)
    assert auth.reset_password_dengan_kode("budi@contoh.com", kode, "baru12345", "baru12345") == []
    assert kelola_akun.kode_reset("tidak_ada") == 1
