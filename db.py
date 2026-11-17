"""Koneksi database dan skema (SQLAlchemy Core).

- Bila ``DATABASE_URL`` diisi (variabel lingkungan atau ``st.secrets``), dipakai
  PostgreSQL (mis. Supabase / Neon). Data bertahan walau aplikasi di-restart.
- Bila tidak diisi, dipakai SQLite lokal ``auth_data/ria.db`` (cocok untuk
  pengembangan; di hosting dengan disk sementara datanya hilang saat restart).
- Untuk pengujian, ``RIA_AUTH_DB`` dapat menunjuk berkas SQLite lain.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import event

BASE_DIR = Path(__file__).resolve().parent
SQLITE_BAWAAN = BASE_DIR / "auth_data" / "ria.db"

metadata = sa.MetaData()

users = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("nama_lengkap", sa.String(100), nullable=False),
    sa.Column("username", sa.String(30), nullable=False),
    # Kolom *_lc menyimpan versi huruf kecil agar keunikan tidak peka huruf besar/kecil
    # dan berlaku sama di SQLite maupun PostgreSQL.
    sa.Column("username_lc", sa.String(30), nullable=False, unique=True),
    sa.Column("email", sa.String(254), nullable=False),
    sa.Column("email_lc", sa.String(254), nullable=False, unique=True),
    sa.Column("password_hash", sa.String(100), nullable=False),
    sa.Column("peran", sa.String(10), nullable=False, server_default="user"),
    sa.Column("aktif", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("dibuat_pada", sa.DateTime, nullable=False),
    sa.Column("gagal_login", sa.Integer, nullable=False, server_default="0"),
    sa.Column("terkunci_sampai", sa.DateTime),
)

sesi = sa.Table(
    "sesi",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
              nullable=False, index=True),
    # Hanya hash token yang disimpan; token asli hanya ada di cookie browser.
    sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
    sa.Column("dibuat_pada", sa.DateTime, nullable=False),
    sa.Column("kedaluwarsa", sa.DateTime, nullable=False),
)

undangan = sa.Table(
    "undangan",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("kode_hash", sa.String(64), nullable=False, unique=True),
    sa.Column("dibuat_oleh", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("dibuat_pada", sa.DateTime, nullable=False),
    sa.Column("kedaluwarsa", sa.DateTime, nullable=False),
    sa.Column("dipakai_oleh", sa.Integer, sa.ForeignKey("users.id")),
    sa.Column("dipakai_pada", sa.DateTime),
)

reset_password = sa.Table(
    "reset_password",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
              nullable=False, index=True),
    sa.Column("kode_hash", sa.String(64), nullable=False),
    sa.Column("dibuat_pada", sa.DateTime, nullable=False),
    sa.Column("kedaluwarsa", sa.DateTime, nullable=False),
    sa.Column("gagal", sa.Integer, nullable=False, server_default="0"),
    sa.Column("dipakai_pada", sa.DateTime),
    # Kosong bila diminta sendiri lewat email; terisi bila dibuat oleh administrator.
    sa.Column("dibuat_oleh", sa.Integer, sa.ForeignKey("users.id")),
)

berkas_pengguna = sa.Table(
    "berkas_pengguna",
    metadata,
    sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
              primary_key=True),
    sa.Column("arsip", sa.LargeBinary, nullable=False),
    sa.Column("sidik", sa.String(64), nullable=False, server_default=""),
    sa.Column("diubah", sa.DateTime, nullable=False),
)


def config(kunci: str, bawaan: str | None = None) -> str | None:
    """Baca pengaturan dari variabel lingkungan, lalu ``st.secrets``."""
    nilai = os.environ.get(kunci)
    if nilai:
        return nilai
    try:
        import streamlit as st

        if kunci in st.secrets:
            return str(st.secrets[kunci])
    except Exception:
        pass
    return bawaan


def url_database() -> str:
    url = config("DATABASE_URL")
    if url:
        url = url.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url
    path = Path(os.environ.get("RIA_AUTH_DB") or SQLITE_BAWAAN)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def pakai_postgres() -> bool:
    return not url_database().startswith("sqlite")


_ENGINES: dict[str, sa.Engine] = {}


class GalatDatabase(sa.exc.SQLAlchemyError):
    """Galat konfigurasi database (mis. driver belum terpasang)."""


def _buat_engine(url: str) -> sa.Engine:
    try:
        return _buat_engine_inti(url)
    except ModuleNotFoundError as e:
        raise GalatDatabase(f"Driver database belum terpasang: {e}") from e


def _buat_engine_inti(url: str) -> sa.Engine:
    if url.startswith("sqlite"):
        eng = sa.create_engine(url, connect_args={"timeout": 10})

        @event.listens_for(eng, "connect")
        def _aktifkan_fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    else:
        eng = sa.create_engine(
            url, pool_pre_ping=True, pool_recycle=300, pool_size=3, max_overflow=2
        )
    metadata.create_all(eng)
    return eng


def engine() -> sa.Engine:
    url = url_database()
    if url not in _ENGINES:
        _ENGINES[url] = _buat_engine(url)
    return _ENGINES[url]


def tutup_semua() -> None:
    """Tutup semua koneksi (dipanggil sebelum modul ini dimuat ulang dan di pengujian)."""
    for eng in _ENGINES.values():
        eng.dispose()
    _ENGINES.clear()


# ======================================================================
# DIAGNOSIS GALAT KONEKSI
# ======================================================================

def samarkan(teks: str) -> str:
    """Hilangkan password DATABASE_URL dari teks (log dan layar tidak boleh membocorkannya).

    Password yang mengandung karakter khusus (@ # / ...) bisa terbelah saat URL diurai
    sehingga sebagian terbaca sebagai nama host; karena itu potongan akhirnya juga disamarkan."""
    hasil = str(teks)
    url = config("DATABASE_URL") or ""
    if "://" in url and "@" in url:
        info = url.split("://", 1)[1].rsplit("@", 1)[0]
        sandi = info.split(":", 1)[1] if ":" in info else ""
        for awal in range(len(sandi)):  # dari password utuh sampai potongan akhir >= 3 karakter
            potongan = sandi[awal:]
            if len(potongan) < 3:
                break
            hasil = hasil.replace(potongan, "***")
    # Nama host yang berisi karakter khusus pasti hasil salah urai (bagian dari password).
    hasil = re.sub(r'(host name )"[^"]*[@#/?%:][^"]*"', r'\1"***"', hasil)
    return re.sub(r"(://[^:/@\s]+:)[^@\s'\"]+@", r"\1***@", hasil)


def petunjuk_galat(exc: BaseException) -> str:
    """Penjelasan singkat (Indonesia) penyebab paling mungkin dari galat koneksi database."""
    teks = str(exc)
    rendah = teks.lower()
    host = re.search(r'could not translate host name "([^"]*)"', teks)

    if "driver database belum terpasang" in rendah:
        return ("Paket driver PostgreSQL belum terpasang. Pastikan requirements.txt di GitHub "
                "berisi `sqlalchemy` dan `psycopg2-binary`, lalu Reboot aplikasi.")
    if isinstance(exc, sa.exc.ArgumentError) or "could not parse" in rendah:
        return ("Format DATABASE_URL tidak valid. Bentuk yang benar: "
                "`postgresql://USER:PASSWORD@HOST:5432/NAMA_DB` dan nilainya diapit tanda kutip.")
    if host and re.search(r"[@#/?%:]", host.group(1)):
        return ("Password di DATABASE_URL kemungkinan mengandung karakter khusus (@ # / ? % :) "
                "sehingga URL terbaca salah. Ganti password database dengan huruf dan angka saja, "
                "atau tulis karakter khusus dalam bentuk URL-encoded (mis. @ menjadi %40).")
    if host:
        return (f"Alamat server database ('{host.group(1)}') tidak ditemukan. Pastikan bagian HOST "
                "diisi alamat asli dari penyedia database, bukan tulisan contoh, dan ejaannya benar.")
    if "network is unreachable" in rendah or "cannot assign requested address" in rendah:
        return ("Server database tidak terjangkau dari Streamlit Cloud. Pada Supabase, koneksi langsung "
                "(db.xxxx.supabase.co) hanya IPv6; pakai connection string **Session pooler** "
                "(host *.pooler.supabase.com) atau database Neon.")
    if "tenant or user not found" in rendah:
        return "Pada pooler Supabase, username harus berbentuk `postgres.KODE_PROYEK`, bukan `postgres` saja."
    if "password authentication failed" in rendah:
        return ("Username atau password database salah. Pastikan password asli sudah menggantikan "
                "tulisan [YOUR-PASSWORD] (termasuk tanda kurungnya).")
    if "database" in rendah and "does not exist" in rendah:
        return "Nama database di akhir URL tidak ada (pada Supabase biasanya `postgres`)."
    if "ssl" in rendah:
        return "Server mewajibkan SSL: tambahkan `?sslmode=require` di akhir DATABASE_URL."
    if "timeout" in rendah or "timed out" in rendah:
        return ("Koneksi ke database habis waktu. Database gratis bisa sedang 'tidur' (coba muat ulang) "
                "atau diblokir pembatasan IP di penyedia database.")
    if "connection refused" in rendah:
        return "Server menolak koneksi: periksa HOST dan PORT (umumnya 5432; pooler transaksi 6543)."
    return "Periksa kembali nilai DATABASE_URL di Secrets, lalu lihat log aplikasi (Manage app) untuk detailnya."
