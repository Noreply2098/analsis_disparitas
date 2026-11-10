"""Autentikasi pengguna: registrasi, login, ubah password, dan sesi.

- Data pengguna disimpan di SQLite (``auth_data/users.db``, di-ignore oleh Git).
- Password TIDAK pernah disimpan apa adanya: hanya hash bcrypt (dengan salt acak).
- Username dan email tidak peka huruf besar/kecil dan harus unik.
- Akun dikunci sementara setelah beberapa kali salah password berturut-turut.

Lokasi database dapat diganti lewat variabel lingkungan ``RIA_AUTH_DB``
(dipakai oleh pengujian).
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import bcrypt
import streamlit as st

# ======================================================================
# KONFIGURASI
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent
DB_BAWAAN = BASE_DIR / "auth_data" / "users.db"

NAMA_MIN, NAMA_MAX = 2, 100
USERNAME_MIN, USERNAME_MAX = 3, 30
EMAIL_MAX = 254
PASSWORD_MIN = 8
PASSWORD_MAX_BYTE = 72  # batas bcrypt: byte di atas ini diabaikan, jadi ditolak

BCRYPT_ROUNDS = 12
MAKS_GAGAL = 5  # percobaan salah berturut-turut sebelum akun dikunci
DURASI_KUNCI_MENIT = 5

SESSION_KEY = "auth_user"
TOAST_KEY = "_auth_toast"

_RE_USERNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._]*[A-Za-z0-9])?")
_RE_EMAIL = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"
)
_RE_NAMA = re.compile(r"[^\W\d_](?:[^\W\d_]|[ .'\-])*")

PETUNJUK_USERNAME = (
    f"{USERNAME_MIN}-{USERNAME_MAX} karakter: huruf, angka, titik, atau garis bawah."
)
PETUNJUK_PASSWORD = f"Minimal {PASSWORD_MIN} karakter, mengandung huruf dan angka."


# ======================================================================
# VALIDASI INPUT (setiap fungsi mengembalikan daftar pesan error)
# ======================================================================

def bersihkan_nama(nama: str) -> str:
    return re.sub(r"\s+", " ", (nama or "").strip())


def validasi_nama(nama: str) -> list[str]:
    nama = bersihkan_nama(nama)
    if not nama:
        return ["Nama lengkap tidak boleh kosong."]
    if len(nama) < NAMA_MIN:
        return [f"Nama lengkap minimal {NAMA_MIN} karakter."]
    if len(nama) > NAMA_MAX:
        return [f"Nama lengkap maksimal {NAMA_MAX} karakter."]
    if not _RE_NAMA.fullmatch(nama):
        return [
            "Nama lengkap hanya boleh berisi huruf, spasi, titik, apostrof, "
            "dan tanda hubung (tanpa angka)."
        ]
    return []


def validasi_username(username: str) -> list[str]:
    username = (username or "").strip()
    if not username:
        return ["Username tidak boleh kosong."]
    if len(username) < USERNAME_MIN:
        return [f"Username minimal {USERNAME_MIN} karakter."]
    if len(username) > USERNAME_MAX:
        return [f"Username maksimal {USERNAME_MAX} karakter."]
    if not _RE_USERNAME.fullmatch(username):
        return [
            "Username hanya boleh berisi huruf, angka, titik, dan garis bawah "
            "(tanpa spasi), serta harus diawali dan diakhiri huruf atau angka."
        ]
    return []


def validasi_email(email: str) -> list[str]:
    email = (email or "").strip()
    if not email:
        return ["Email tidak boleh kosong."]
    if len(email) > EMAIL_MAX:
        return [f"Email maksimal {EMAIL_MAX} karakter."]
    if ".." in email or not _RE_EMAIL.fullmatch(email):
        return ["Format email tidak valid (contoh: nama@contoh.com)."]
    return []


def validasi_password(password: str, username: str = "") -> list[str]:
    """Aturan password baru (registrasi dan ubah password)."""
    if not password:
        return ["Password tidak boleh kosong."]
    errors = []
    if len(password) < PASSWORD_MIN:
        errors.append(f"Password minimal {PASSWORD_MIN} karakter.")
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTE:
        errors.append(f"Password terlalu panjang (maksimal {PASSWORD_MAX_BYTE} byte).")
    if not re.search(r"[A-Za-z]", password):
        errors.append("Password harus mengandung minimal satu huruf.")
    if not re.search(r"\d", password):
        errors.append("Password harus mengandung minimal satu angka.")
    if username and password.lower() == username.strip().lower():
        errors.append("Password tidak boleh sama dengan username.")
    return errors


def validasi_login(username: str, password: str) -> list[str]:
    """Pemeriksaan format sebelum ke database (tanpa membocorkan data akun)."""
    errors = []
    username = (username or "").strip()
    if not username:
        errors.append("Username tidak boleh kosong.")
    elif not (
        USERNAME_MIN <= len(username) <= USERNAME_MAX
        and _RE_USERNAME.fullmatch(username)
    ):
        errors.append(
            "Format username tidak valid. " + PETUNJUK_USERNAME
        )
    if not password:
        errors.append("Password tidak boleh kosong.")
    elif len(password) < PASSWORD_MIN:
        errors.append(f"Password minimal {PASSWORD_MIN} karakter.")
    elif len(password.encode("utf-8")) > PASSWORD_MAX_BYTE:
        errors.append(f"Password terlalu panjang (maksimal {PASSWORD_MAX_BYTE} byte).")
    return errors


# ======================================================================
# HASH PASSWORD (bcrypt)
# ======================================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("utf-8")


def cocok_password(password: str, hash_tersimpan: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_tersimpan.encode("utf-8"))
    except (ValueError, TypeError):
        return False


@lru_cache(maxsize=1)
def _hash_palsu() -> str:
    # Dipakai saat username tidak ada, agar waktu respons tidak membedakan
    # "username tidak ada" dan "password salah".
    return hash_password("password-palsu-1")


# ======================================================================
# DATABASE
# ======================================================================

def _path_db() -> Path:
    return Path(os.environ.get("RIA_AUTH_DB") or DB_BAWAAN)


@contextmanager
def _koneksi():
    path = _path_db()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nama_lengkap    TEXT NOT NULL,
                username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email           TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash   TEXT NOT NULL,
                dibuat_pada     TEXT NOT NULL,
                gagal_login     INTEGER NOT NULL DEFAULT 0,
                terkunci_sampai TEXT
            )
            """
        )
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sekarang() -> datetime:
    return datetime.now(timezone.utc)


def _profil(row: sqlite3.Row) -> dict:
    """Data pengguna yang aman ditampung di sesi (tanpa hash)."""
    return {
        "id": row["id"],
        "nama": row["nama_lengkap"],
        "username": row["username"],
        "email": row["email"],
        "dibuat_pada": row["dibuat_pada"],
    }


def ambil_pengguna(user_id: int) -> dict | None:
    with _koneksi() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _profil(row) if row else None


# ======================================================================
# REGISTRASI
# ======================================================================

def registrasi(
    nama: str, username: str, email: str, password: str, konfirmasi: str
) -> list[str]:
    """Daftarkan pengguna baru. Mengembalikan daftar error (kosong = berhasil)."""
    nama = bersihkan_nama(nama)
    username = (username or "").strip()
    email = (email or "").strip().lower()

    errors = (
        validasi_nama(nama)
        + validasi_username(username)
        + validasi_email(email)
        + validasi_password(password, username)
    )
    if not konfirmasi:
        errors.append("Konfirmasi password tidak boleh kosong.")
    elif password and konfirmasi != password:
        errors.append("Konfirmasi password tidak sama dengan password.")
    if errors:
        return errors

    with _koneksi() as conn:
        ada = conn.execute(
            "SELECT username, email FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchall()
        for row in ada:
            if row["username"].lower() == username.lower():
                errors.append(f"Username '{username}' sudah terdaftar. Pilih username lain.")
            if row["email"].lower() == email:
                errors.append(f"Email '{email}' sudah terdaftar. Gunakan email lain atau masuk.")
        errors = list(dict.fromkeys(errors))
        if errors:
            return errors

        try:
            conn.execute(
                "INSERT INTO users (nama_lengkap, username, email, password_hash, dibuat_pada) "
                "VALUES (?, ?, ?, ?, ?)",
                (nama, username, email, hash_password(password), _sekarang().isoformat()),
            )
        except sqlite3.IntegrityError:
            # Dua pendaftaran bersamaan dengan data sama: batasan UNIQUE jadi penjaga terakhir.
            return ["Username atau email sudah terdaftar. Gunakan data lain."]
    return []


# ======================================================================
# LOGIN
# ======================================================================

PESAN_LOGIN_GAGAL = "Username atau password salah."


def login(username: str, password: str) -> tuple[dict | None, str | None]:
    """Cek kredensial. Mengembalikan (profil, None) bila berhasil, atau (None, pesan)."""
    username = (username or "").strip()
    with _koneksi() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if row is None:
            cocok_password(password, _hash_palsu())
            return None, PESAN_LOGIN_GAGAL

        if row["terkunci_sampai"]:
            sampai = datetime.fromisoformat(row["terkunci_sampai"])
            sisa = sampai - _sekarang()
            if sisa.total_seconds() > 0:
                menit = max(1, int(sisa.total_seconds() // 60) + 1)
                return None, (
                    "Terlalu banyak percobaan login yang gagal. "
                    f"Akun dikunci sementara, coba lagi dalam {menit} menit."
                )

        if cocok_password(password, row["password_hash"]):
            conn.execute(
                "UPDATE users SET gagal_login = 0, terkunci_sampai = NULL WHERE id = ?",
                (row["id"],),
            )
            return _profil(row), None

        gagal = (row["gagal_login"] or 0) + 1
        if gagal >= MAKS_GAGAL:
            kunci = (_sekarang() + timedelta(minutes=DURASI_KUNCI_MENIT)).isoformat()
            conn.execute(
                "UPDATE users SET gagal_login = 0, terkunci_sampai = ? WHERE id = ?",
                (kunci, row["id"]),
            )
        else:
            conn.execute(
                "UPDATE users SET gagal_login = ?, terkunci_sampai = NULL WHERE id = ?",
                (gagal, row["id"]),
            )
        return None, PESAN_LOGIN_GAGAL


# ======================================================================
# UBAH PASSWORD
# ======================================================================

def ubah_password(
    user_id: int, password_lama: str, password_baru: str, konfirmasi: str
) -> list[str]:
    """Ganti password setelah memastikan password lama benar."""
    errors = []
    if not password_lama:
        errors.append("Password lama tidak boleh kosong.")
    if not konfirmasi:
        errors.append("Konfirmasi password baru tidak boleh kosong.")

    with _koneksi() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return ["Akun tidak ditemukan. Silakan masuk kembali."]

        if password_lama and not cocok_password(password_lama, row["password_hash"]):
            errors.append("Password lama salah.")

        errors += validasi_password(password_baru, row["username"])
        if konfirmasi and password_baru and konfirmasi != password_baru:
            errors.append("Konfirmasi password baru tidak sama dengan password baru.")
        if password_lama and password_baru and password_lama == password_baru:
            errors.append("Password baru tidak boleh sama dengan password lama.")

        errors = list(dict.fromkeys(errors))
        if errors:
            return errors

        conn.execute(
            "UPDATE users SET password_hash = ?, gagal_login = 0, terkunci_sampai = NULL "
            "WHERE id = ?",
            (hash_password(password_baru), user_id),
        )
    return []


# ======================================================================
# SESI (Streamlit)
# ======================================================================

def pengguna_aktif() -> dict | None:
    return st.session_state.get(SESSION_KEY)


def masuk(profil: dict) -> None:
    st.session_state[SESSION_KEY] = profil
    st.session_state[TOAST_KEY] = (f"Selamat datang, {profil['nama']}!", ":material/waving_hand:")


def keluar() -> None:
    """Hapus seluruh isi sesi (termasuk filter data) agar tidak tersisa untuk pengguna berikutnya."""
    st.session_state.clear()
    st.session_state[TOAST_KEY] = ("Anda telah keluar.", ":material/logout:")


def tampilkan_toast() -> None:
    item = st.session_state.pop(TOAST_KEY, None)
    if item:
        pesan, ikon = item
        st.toast(pesan, icon=ikon)


def escape_markdown(teks: str) -> str:
    """Netralkan karakter markdown pada teks buatan pengguna sebelum ditampilkan."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$&:])", r"\\\1", teks or "")
