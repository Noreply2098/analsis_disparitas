"""Autentikasi pengguna: registrasi, login, sesi tetap, ubah password, dan administrasi.

- Data disimpan lewat ``db.py`` (PostgreSQL bila ``DATABASE_URL`` diisi, selain itu SQLite).
- Password TIDAK pernah disimpan apa adanya: hanya hash bcrypt (salt acak).
- Username dan email unik tanpa membedakan huruf besar/kecil.
- Akun dikunci sementara setelah beberapa kali salah password berturut-turut.
- Sesi bertahan saat halaman di-refresh lewat token acak di cookie browser; server hanya
  menyimpan hash token (sha256), sehingga isi database tidak bisa dipakai untuk menyamar.
- Pendaftaran: akun pertama menjadi admin; sesudahnya wajib kode undangan sekali pakai
  (dibuat admin), kecuali ``REGISTRASI_TERBUKA=true``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import bcrypt
import sqlalchemy as sa
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError

import db
import mailer
from db import reset_password, sesi, undangan, users

# ======================================================================
# KONFIGURASI
# ======================================================================

NAMA_MIN, NAMA_MAX = 2, 100
USERNAME_MIN, USERNAME_MAX = 3, 30
EMAIL_MAX = 254
PASSWORD_MIN = 8
PASSWORD_MAX_BYTE = 72  # batas bcrypt: byte di atas ini diabaikan, jadi ditolak

BCRYPT_ROUNDS = 12
MAKS_GAGAL = 5  # percobaan salah berturut-turut sebelum akun dikunci
DURASI_KUNCI_MENIT = 5

MASA_SESI_HARI = 7
COOKIE_NAMA = "ria_sesi"
UNDANGAN_HARI_BAWAAN = 7
UNDANGAN_HARI_MAKS = 30
_ALFABET_KODE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # tanpa 0/O/1/I agar mudah dibaca
PANJANG_KODE = 12
PANJANG_KODE_RESET = 8

RESET_MASA_MENIT = 15           # kode reset yang diminta lewat email
RESET_MASA_ADMIN_MENIT = 60     # kode reset yang dibuat administrator
RESET_MAKS_GAGAL = 5            # tebakan salah sebelum kode hangus
RESET_MAKS_PERMINTAAN_JAM = 3   # permintaan kode per akun per jam

PERAN_ADMIN, PERAN_USER = "admin", "user"

SESSION_KEY = "auth_user"
TOAST_KEY = "_auth_toast"
TOKEN_KEY = "_auth_token"
COOKIE_TULIS_KEY = "_cookie_tulis"
COOKIE_HAPUS_KEY = "_cookie_hapus"
PULIH_KEY = "_pulih_dicoba"

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
        errors.append("Format username tidak valid. " + PETUNJUK_USERNAME)
    if not password:
        errors.append("Password tidak boleh kosong.")
    elif len(password) < PASSWORD_MIN:
        errors.append(f"Password minimal {PASSWORD_MIN} karakter.")
    elif len(password.encode("utf-8")) > PASSWORD_MAX_BYTE:
        errors.append(f"Password terlalu panjang (maksimal {PASSWORD_MAX_BYTE} byte).")
    return errors


# ======================================================================
# HASH (bcrypt untuk password, sha256 untuk token dan kode acak)
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


def _sha256(teks: str) -> str:
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


# ======================================================================
# UTILITAS DATABASE
# ======================================================================

def _sekarang() -> datetime:
    """Waktu UTC tanpa zona (kolom DateTime database disimpan sebagai UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _profil(row) -> dict:
    """Data pengguna yang aman ditampung di sesi (tanpa hash password)."""
    return {
        "id": row["id"],
        "nama": row["nama_lengkap"],
        "username": row["username"],
        "email": row["email"],
        "peran": row["peran"],
        "aktif": bool(row["aktif"]),
        "dibuat_pada": row["dibuat_pada"].strftime("%Y-%m-%d"),
    }


def ambil_pengguna(user_id: int) -> dict | None:
    with db.engine().connect() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).mappings().first()
    return _profil(row) if row else None


def jumlah_pengguna() -> int:
    with db.engine().connect() as conn:
        return conn.execute(select(func.count()).select_from(users)).scalar_one()


# ======================================================================
# KEBIJAKAN REGISTRASI
# ======================================================================

MODE_PERTAMA = "pertama"      # belum ada pengguna: pendaftar pertama menjadi admin
MODE_TERBUKA = "terbuka"      # siapa pun boleh mendaftar
MODE_UNDANGAN = "undangan"    # wajib kode undangan dari admin


def registrasi_terbuka() -> bool:
    return str(db.config("REGISTRASI_TERBUKA", "")).strip().lower() in ("1", "true", "ya", "yes")


def mode_registrasi() -> str:
    if jumlah_pengguna() == 0:
        return MODE_PERTAMA
    return MODE_TERBUKA if registrasi_terbuka() else MODE_UNDANGAN


def normalisasi_kode(kode: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", kode or "").upper()


def _format_kode(kode: str) -> str:
    return "-".join(kode[i:i + 4] for i in range(0, len(kode), 4))


def _cek_undangan(conn, kode: str) -> tuple[int | None, str | None]:
    """Periksa kode undangan. Mengembalikan (id_undangan, None) atau (None, pesan)."""
    kode = normalisasi_kode(kode)
    if not kode:
        return None, "Kode undangan wajib diisi. Minta kode kepada administrator."
    row = conn.execute(
        select(undangan).where(undangan.c.kode_hash == _sha256(kode))
    ).mappings().first()
    if row is None:
        return None, "Kode undangan tidak valid."
    if row["dipakai_oleh"] is not None:
        return None, "Kode undangan sudah dipakai. Minta kode baru kepada administrator."
    if row["kedaluwarsa"] <= _sekarang():
        return None, "Kode undangan sudah kedaluwarsa. Minta kode baru kepada administrator."
    return row["id"], None


class _UndanganGagal(Exception):
    pass


# ======================================================================
# REGISTRASI
# ======================================================================

def registrasi(
    nama: str,
    username: str,
    email: str,
    password: str,
    konfirmasi: str,
    kode_undangan: str = "",
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

    # Kebijakan undangan diperiksa dulu agar pesannya muncul bersama error lain.
    mode = mode_registrasi()
    if mode == MODE_UNDANGAN and not normalisasi_kode(kode_undangan):
        errors.append("Kode undangan wajib diisi. Minta kode kepada administrator.")
    if errors:
        return errors

    hash_baru = hash_password(password)
    try:
        with db.engine().begin() as conn:
            pertama = conn.execute(select(func.count()).select_from(users)).scalar_one() == 0
            id_undangan = None
            if not pertama and not registrasi_terbuka():
                id_undangan, galat = _cek_undangan(conn, kode_undangan)
                if galat:
                    errors.append(galat)

            ada = conn.execute(
                select(users.c.username_lc, users.c.email_lc).where(
                    or_(users.c.username_lc == username.lower(), users.c.email_lc == email)
                )
            ).all()
            for uname, mail in ada:
                if uname == username.lower():
                    errors.append(f"Username '{username}' sudah terdaftar. Pilih username lain.")
                if mail == email:
                    errors.append(
                        f"Email '{email}' sudah terdaftar. Gunakan email lain atau masuk."
                    )
            errors = list(dict.fromkeys(errors))
            if errors:
                return errors

            hasil = conn.execute(
                insert(users).values(
                    nama_lengkap=nama,
                    username=username,
                    username_lc=username.lower(),
                    email=email,
                    email_lc=email,
                    password_hash=hash_baru,
                    peran=PERAN_ADMIN if pertama else PERAN_USER,
                    aktif=True,
                    dibuat_pada=_sekarang(),
                )
            )
            if id_undangan is not None:
                # Syarat "belum dipakai" diulang di UPDATE agar dua pendaftar bersamaan
                # tidak bisa memakai kode yang sama.
                dipakai = conn.execute(
                    update(undangan)
                    .where(and_(undangan.c.id == id_undangan, undangan.c.dipakai_oleh.is_(None)))
                    .values(dipakai_oleh=hasil.inserted_primary_key[0], dipakai_pada=_sekarang())
                )
                if dipakai.rowcount != 1:
                    raise _UndanganGagal()
    except _UndanganGagal:
        return ["Kode undangan sudah dipakai. Minta kode baru kepada administrator."]
    except IntegrityError:
        # Dua pendaftaran bersamaan dengan data sama: batasan UNIQUE jadi penjaga terakhir.
        return ["Username atau email sudah terdaftar. Gunakan data lain."]
    return []


# ======================================================================
# LOGIN
# ======================================================================

PESAN_LOGIN_GAGAL = "Username atau password salah."
PESAN_NONAKTIF = "Akun Anda dinonaktifkan. Hubungi administrator."


def login(username: str, password: str) -> tuple[dict | None, str | None]:
    """Cek kredensial. Mengembalikan (profil, None) bila berhasil, atau (None, pesan)."""
    username = (username or "").strip()
    with db.engine().begin() as conn:
        row = conn.execute(
            select(users).where(users.c.username_lc == username.lower())
        ).mappings().first()

        if row is None:
            cocok_password(password, _hash_palsu())
            return None, PESAN_LOGIN_GAGAL

        if row["terkunci_sampai"] is not None:
            sisa = row["terkunci_sampai"] - _sekarang()
            if sisa.total_seconds() > 0:
                menit = max(1, int(sisa.total_seconds() // 60) + 1)
                return None, (
                    "Terlalu banyak percobaan login yang gagal. "
                    f"Akun dikunci sementara, coba lagi dalam {menit} menit."
                )

        if cocok_password(password, row["password_hash"]):
            conn.execute(
                update(users)
                .where(users.c.id == row["id"])
                .values(gagal_login=0, terkunci_sampai=None)
            )
            if not row["aktif"]:
                return None, PESAN_NONAKTIF
            return _profil(row), None

        gagal = (row["gagal_login"] or 0) + 1
        if gagal >= MAKS_GAGAL:
            conn.execute(
                update(users)
                .where(users.c.id == row["id"])
                .values(
                    gagal_login=0,
                    terkunci_sampai=_sekarang() + timedelta(minutes=DURASI_KUNCI_MENIT),
                )
            )
        else:
            conn.execute(
                update(users)
                .where(users.c.id == row["id"])
                .values(gagal_login=gagal, terkunci_sampai=None)
            )
        return None, PESAN_LOGIN_GAGAL


# ======================================================================
# SESI TETAP (token di cookie)
# ======================================================================

def buat_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    sekarang = _sekarang()
    with db.engine().begin() as conn:
        conn.execute(delete(sesi).where(sesi.c.kedaluwarsa < sekarang))  # bersih-bersih
        conn.execute(
            insert(sesi).values(
                user_id=user_id,
                token_hash=_sha256(token),
                dibuat_pada=sekarang,
                kedaluwarsa=sekarang + timedelta(days=MASA_SESI_HARI),
            )
        )
    return token


def pulihkan_dari_token(token: str | None) -> dict | None:
    """Profil pengguna untuk token yang valid, belum kedaluwarsa, dan akunnya aktif."""
    if not token or len(token) > 100:
        return None
    with db.engine().connect() as conn:
        row = conn.execute(
            select(users)
            .join(sesi, sesi.c.user_id == users.c.id)
            .where(
                sesi.c.token_hash == _sha256(token),
                sesi.c.kedaluwarsa > _sekarang(),
                users.c.aktif.is_(True),
            )
        ).mappings().first()
    return _profil(row) if row else None


def hapus_token(token: str | None) -> None:
    if token:
        with db.engine().begin() as conn:
            conn.execute(delete(sesi).where(sesi.c.token_hash == _sha256(token)))


def hapus_semua_token(user_id: int) -> None:
    with db.engine().begin() as conn:
        conn.execute(delete(sesi).where(sesi.c.user_id == user_id))


# ======================================================================
# SESI STREAMLIT
# ======================================================================

def pengguna_aktif() -> dict | None:
    return st.session_state.get(SESSION_KEY)


def adalah_admin() -> bool:
    pengguna = pengguna_aktif()
    return bool(pengguna and pengguna.get("peran") == PERAN_ADMIN)


def _cookie_browser() -> str | None:
    try:
        nilai = st.context.cookies.get(COOKIE_NAMA)
    except Exception:  # st.context tidak tersedia (mis. saat pengujian)
        return None
    return nilai if isinstance(nilai, str) else None


def terbitkan_cookie(user_id: int) -> None:
    """Buat token baru dan jadwalkan penulisan cookie pada tampilan berikutnya."""
    token = buat_token(user_id)
    st.session_state[TOKEN_KEY] = token
    st.session_state[COOKIE_TULIS_KEY] = (token, MASA_SESI_HARI * 86400)


def masuk(profil: dict) -> None:
    st.session_state[SESSION_KEY] = profil
    terbitkan_cookie(profil["id"])
    st.session_state[PULIH_KEY] = True
    antri_toast(f"Selamat datang, {profil['nama']}!", ":material/waving_hand:")


def pulihkan_sesi() -> None:
    """Masuk otomatis dari cookie saat sesi baru (mis. setelah halaman di-refresh)."""
    if pengguna_aktif() or st.session_state.get(PULIH_KEY):
        return
    st.session_state[PULIH_KEY] = True
    token = _cookie_browser()
    profil = pulihkan_dari_token(token)
    if profil:
        st.session_state[SESSION_KEY] = profil
        st.session_state[TOKEN_KEY] = token


def segarkan_sesi() -> None:
    """Sinkronkan profil sesi dengan database; keluarkan bila akun dinonaktifkan/dihapus."""
    pengguna = pengguna_aktif()
    if not pengguna:
        return
    terbaru = ambil_pengguna(pengguna["id"])
    if terbaru is None or not terbaru["aktif"]:
        keluar("Akun Anda tidak aktif lagi. Hubungi administrator.")
        st.rerun()
    st.session_state[SESSION_KEY] = terbaru


def keluar(pesan: str = "Anda telah keluar.") -> None:
    """Akhiri sesi: cabut token di server, hapus cookie, dan kosongkan seluruh sesi."""
    for token in {st.session_state.get(TOKEN_KEY), _cookie_browser()}:
        try:
            hapus_token(token)
        except sa.exc.SQLAlchemyError:
            pass
    st.session_state.clear()
    st.session_state[PULIH_KEY] = True  # jangan pulihkan lagi dari cookie lama
    st.session_state[COOKIE_HAPUS_KEY] = True
    antri_toast(pesan, ":material/logout:")


def terapkan_cookie() -> None:
    """Tulis/hapus cookie di browser bila ada yang tertunda (dipanggil dari app.py)."""
    tulis = st.session_state.pop(COOKIE_TULIS_KEY, None)
    hapus = st.session_state.pop(COOKIE_HAPUS_KEY, False)
    if tulis:
        token, umur = tulis
        nilai = f"{COOKIE_NAMA}=' + {json.dumps(token)} + '; Path=/; Max-Age={int(umur)}"
    elif hapus:
        nilai = f"{COOKIE_NAMA}=; Path=/; Max-Age=0"
    else:
        return
    skrip = (
        "<script>(function(){try{"
        "var p=window.parent;"
        "var s=p.location.protocol==='https:'?'; Secure':'';"
        f"p.document.cookie='{nilai}; SameSite=Lax'+s;"
        "}catch(e){}})();</script>"
    )
    components.html(skrip, height=0)


def antri_toast(pesan: str, ikon: str = ":material/info:") -> None:
    st.session_state.setdefault(TOAST_KEY, []).append((pesan, ikon))


def tampilkan_toast() -> None:
    for pesan, ikon in st.session_state.pop(TOAST_KEY, []):
        st.toast(pesan, icon=ikon)


def escape_markdown(teks: str) -> str:
    """Netralkan karakter markdown pada teks buatan pengguna sebelum ditampilkan."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$&:])", r"\\\1", teks or "")


# ======================================================================
# UBAH PASSWORD
# ======================================================================

def ubah_password(
    user_id: int, password_lama: str, password_baru: str, konfirmasi: str
) -> list[str]:
    """Ganti password setelah memastikan password lama benar. Sesi lain dicabut."""
    errors = []
    if not password_lama:
        errors.append("Password lama tidak boleh kosong.")
    if not konfirmasi:
        errors.append("Konfirmasi password baru tidak boleh kosong.")

    with db.engine().begin() as conn:
        row = conn.execute(select(users).where(users.c.id == user_id)).mappings().first()
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
            update(users)
            .where(users.c.id == user_id)
            .values(
                password_hash=hash_password(password_baru),
                gagal_login=0,
                terkunci_sampai=None,
            )
        )
        # Perangkat lain yang masih memakai password lama harus masuk ulang.
        conn.execute(delete(sesi).where(sesi.c.user_id == user_id))
    return []


# ======================================================================
# LUPA PASSWORD (kode reset sekali pakai)
# ======================================================================

PESAN_RESET_GAGAL = "Kode reset tidak valid atau sudah kedaluwarsa. Minta kode baru bila perlu."


def email_reset_tersedia() -> bool:
    """True bila aplikasi dapat mengirim email (SMTP dikonfigurasi)."""
    return mailer.terkonfigurasi()


def _terbitkan_reset(conn, user_id: int, menit: int, dibuat_oleh: int | None = None) -> str:
    """Buat kode reset baru; kode lama yang belum dipakai otomatis tidak berlaku lagi."""
    kode = "".join(secrets.choice(_ALFABET_KODE) for _ in range(PANJANG_KODE_RESET))
    sekarang = _sekarang()
    conn.execute(
        update(reset_password)
        .where(
            reset_password.c.user_id == user_id,
            reset_password.c.dipakai_pada.is_(None),
            reset_password.c.kedaluwarsa > sekarang,
        )
        .values(kedaluwarsa=sekarang)
    )
    conn.execute(
        insert(reset_password).values(
            user_id=user_id,
            kode_hash=_sha256(kode),
            dibuat_pada=sekarang,
            kedaluwarsa=sekarang + timedelta(minutes=menit),
            dibuat_oleh=dibuat_oleh,
        )
    )
    return kode


def minta_reset(email: str) -> list[str]:
    """Kirim kode reset ke ``email`` bila akun aktif ada.

    Hanya kesalahan FORMAT email yang dikembalikan. Selain itu hasilnya selalu sama
    (akun ada/tidak ada, kena batas permintaan, atau email gagal terkirim) sehingga
    halaman ini tidak bisa dipakai untuk menebak email yang terdaftar.
    """
    email = (email or "").strip().lower()
    errors = validasi_email(email)
    if errors:
        return errors
    if not mailer.terkonfigurasi():
        return []

    kirim = None
    with db.engine().begin() as conn:
        row = conn.execute(
            select(users).where(users.c.email_lc == email, users.c.aktif.is_(True))
        ).mappings().first()
        if row is not None:
            sejam_lalu = _sekarang() - timedelta(hours=1)
            jumlah = conn.execute(
                select(func.count())
                .select_from(reset_password)
                .where(
                    reset_password.c.user_id == row["id"],
                    reset_password.c.dibuat_oleh.is_(None),
                    reset_password.c.dibuat_pada > sejam_lalu,
                )
            ).scalar_one()
            if jumlah < RESET_MAKS_PERMINTAAN_JAM:
                kode = _terbitkan_reset(conn, row["id"], RESET_MASA_MENIT)
                kirim = (row["email"], row["nama_lengkap"], row["username"], kode)

    if kirim:  # dikirim setelah transaksi tersimpan
        tujuan, nama, username, kode = kirim
        mailer.kirim_di_latar(
            tujuan,
            f"Kode reset password - {mailer.JUDUL_APLIKASI}",
            (
                f"Halo {nama},\n\n"
                f"Kami menerima permintaan reset password untuk akun Anda di "
                f"{mailer.JUDUL_APLIKASI}.\n\n"
                f"Username : {username}\n"
                f"Kode reset: {_format_kode(kode)}\n\n"
                f"Kode berlaku {RESET_MASA_MENIT} menit dan hanya dapat dipakai sekali. "
                "Masukkan kode ini di halaman Lupa Password.\n\n"
                "Jika Anda tidak merasa meminta reset password, abaikan email ini. "
                "Password Anda tidak berubah."
            ),
        )
    return []


def reset_password_dengan_kode(
    email: str, kode: str, password_baru: str, konfirmasi: str
) -> list[str]:
    """Atur password baru memakai kode reset. Mengembalikan daftar error (kosong = berhasil)."""
    email = (email or "").strip().lower()
    kode_bersih = normalisasi_kode(kode)

    errors = validasi_email(email)
    if not kode_bersih:
        errors.append("Kode reset tidak boleh kosong.")
    errors += validasi_password(password_baru)
    if not konfirmasi:
        errors.append("Konfirmasi password baru tidak boleh kosong.")
    elif password_baru and konfirmasi != password_baru:
        errors.append("Konfirmasi password baru tidak sama dengan password baru.")
    if errors:
        return errors

    hash_kode = _sha256(kode_bersih)
    hash_baru = hash_password(password_baru)
    with db.engine().begin() as conn:
        user = conn.execute(
            select(users).where(users.c.email_lc == email, users.c.aktif.is_(True))
        ).mappings().first()
        if user is None:
            return [PESAN_RESET_GAGAL]

        aktif = conn.execute(
            select(reset_password).where(
                reset_password.c.user_id == user["id"],
                reset_password.c.dipakai_pada.is_(None),
                reset_password.c.kedaluwarsa > _sekarang(),
                reset_password.c.gagal < RESET_MAKS_GAGAL,
            )
        ).mappings().all()
        cocok = next((r for r in aktif if hmac.compare_digest(r["kode_hash"], hash_kode)), None)
        if cocok is None:
            if aktif:  # tebakan salah dihitung; setelah batas, kode hangus
                conn.execute(
                    update(reset_password)
                    .where(reset_password.c.id.in_([r["id"] for r in aktif]))
                    .values(gagal=reset_password.c.gagal + 1)
                )
            return [PESAN_RESET_GAGAL]

        if password_baru.lower() == user["username"].lower():
            return ["Password tidak boleh sama dengan username."]  # kode belum terpakai

        conn.execute(
            update(users)
            .where(users.c.id == user["id"])
            .values(password_hash=hash_baru, gagal_login=0, terkunci_sampai=None)
        )
        conn.execute(
            update(reset_password)
            .where(reset_password.c.id == cocok["id"])
            .values(dipakai_pada=_sekarang())
        )
        conn.execute(delete(sesi).where(sesi.c.user_id == user["id"]))  # semua perangkat keluar
    return []


def buat_kode_reset_admin(admin_id: int, target_id: int) -> tuple[str | None, str | None]:
    """Administrator membuat kode reset untuk pengguna (cara lain bila email tidak tersedia).
    Mengembalikan (kode, None) atau (None, pesan)."""
    with db.engine().begin() as conn:
        if not _wajib_admin(conn, admin_id):
            return None, "Hanya administrator yang boleh membuat kode reset."
        ada = conn.execute(
            select(users.c.id).where(users.c.id == target_id, users.c.aktif.is_(True))
        ).scalar_one_or_none()
        if ada is None:
            return None, "Akun tidak ditemukan atau tidak aktif."
        kode = _terbitkan_reset(conn, target_id, RESET_MASA_ADMIN_MENIT, dibuat_oleh=admin_id)
    return _format_kode(kode), None


# ======================================================================
# ADMINISTRASI
# ======================================================================

def _wajib_admin(conn, admin_id: int) -> bool:
    peran = conn.execute(
        select(users.c.peran).where(users.c.id == admin_id, users.c.aktif.is_(True))
    ).scalar_one_or_none()
    return peran == PERAN_ADMIN


def daftar_pengguna(admin_id: int) -> list[dict]:
    with db.engine().connect() as conn:
        if not _wajib_admin(conn, admin_id):
            return []
        rows = conn.execute(select(users).order_by(users.c.id)).mappings().all()
    return [_profil(r) for r in rows]


def ubah_status(admin_id: int, target_id: int, aktif: bool) -> str | None:
    """Aktifkan/nonaktifkan akun. Mengembalikan pesan error atau None bila berhasil."""
    with db.engine().begin() as conn:
        if not _wajib_admin(conn, admin_id):
            return "Hanya administrator yang boleh mengubah status akun."
        if admin_id == target_id:
            return "Anda tidak dapat menonaktifkan akun Anda sendiri."
        hasil = conn.execute(update(users).where(users.c.id == target_id).values(aktif=aktif))
        if hasil.rowcount != 1:
            return "Akun tidak ditemukan."
        if not aktif:
            conn.execute(delete(sesi).where(sesi.c.user_id == target_id))
    return None


def ubah_peran(admin_id: int, target_id: int, peran: str) -> str | None:
    if peran not in (PERAN_ADMIN, PERAN_USER):
        return "Peran tidak dikenal."
    with db.engine().begin() as conn:
        if not _wajib_admin(conn, admin_id):
            return "Hanya administrator yang boleh mengubah peran."
        if admin_id == target_id:
            return "Anda tidak dapat mengubah peran akun Anda sendiri."
        hasil = conn.execute(update(users).where(users.c.id == target_id).values(peran=peran))
        if hasil.rowcount != 1:
            return "Akun tidak ditemukan."
    return None


def buat_undangan(admin_id: int, hari: int = UNDANGAN_HARI_BAWAAN) -> tuple[str | None, str | None]:
    """Buat kode undangan sekali pakai. Mengembalikan (kode, None) atau (None, pesan)."""
    if not 1 <= int(hari) <= UNDANGAN_HARI_MAKS:
        return None, f"Masa berlaku harus 1-{UNDANGAN_HARI_MAKS} hari."
    kode = "".join(secrets.choice(_ALFABET_KODE) for _ in range(PANJANG_KODE))
    with db.engine().begin() as conn:
        if not _wajib_admin(conn, admin_id):
            return None, "Hanya administrator yang boleh membuat kode undangan."
        sekarang = _sekarang()
        conn.execute(
            insert(undangan).values(
                kode_hash=_sha256(kode),
                dibuat_oleh=admin_id,
                dibuat_pada=sekarang,
                kedaluwarsa=sekarang + timedelta(days=int(hari)),
            )
        )
    return _format_kode(kode), None


def daftar_undangan(admin_id: int) -> list[dict]:
    pemakai = users.alias("pemakai")
    with db.engine().connect() as conn:
        if not _wajib_admin(conn, admin_id):
            return []
        rows = conn.execute(
            select(
                undangan.c.id,
                undangan.c.dibuat_pada,
                undangan.c.kedaluwarsa,
                undangan.c.dipakai_pada,
                pemakai.c.username.label("dipakai_oleh"),
            )
            .select_from(undangan.outerjoin(pemakai, pemakai.c.id == undangan.c.dipakai_oleh))
            .order_by(undangan.c.id.desc())
        ).mappings().all()
    sekarang = _sekarang()
    hasil = []
    for r in rows:
        if r["dipakai_oleh"]:
            status = f"Dipakai oleh {r['dipakai_oleh']}"
        elif r["kedaluwarsa"] <= sekarang:
            status = "Kedaluwarsa"
        else:
            status = "Aktif"
        hasil.append(
            {
                "Dibuat": r["dibuat_pada"].strftime("%Y-%m-%d %H:%M"),
                "Berlaku sampai": r["kedaluwarsa"].strftime("%Y-%m-%d %H:%M"),
                "Status": status,
            }
        )
    return hasil
