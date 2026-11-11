"""Koneksi database dan skema (SQLAlchemy Core).

- Bila ``DATABASE_URL`` diisi (variabel lingkungan atau ``st.secrets``), dipakai
  PostgreSQL (mis. Supabase / Neon). Data bertahan walau aplikasi di-restart.
- Bila tidak diisi, dipakai SQLite lokal ``auth_data/ria.db`` (cocok untuk
  pengembangan; di hosting dengan disk sementara datanya hilang saat restart).
- Untuk pengujian, ``RIA_AUTH_DB`` dapat menunjuk berkas SQLite lain.
"""

from __future__ import annotations

import os
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


def _buat_engine(url: str) -> sa.Engine:
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
