"""Pengiriman email lewat SMTP (dipakai untuk kode reset password).

Pengaturan dibaca dari variabel lingkungan atau ``st.secrets``:

    SMTP_HOST      mis. smtp.gmail.com              (wajib; kosong = email dinonaktifkan)
    SMTP_PORT      587 (bawaan) atau 465
    SMTP_USER      akun SMTP
    SMTP_PASSWORD  password / "App Password"
    SMTP_FROM      alamat pengirim (bawaan: SMTP_USER)
    SMTP_SECURITY  starttls (bawaan) | ssl | none
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage

import db

log = logging.getLogger("ria.mailer")

# Untuk pengujian: True = kirim langsung (tanpa thread) agar hasilnya bisa diperiksa.
SINKRON = False

JUDUL_APLIKASI = "Regional Income Analysis"


def konfigurasi() -> dict | None:
    host = (db.config("SMTP_HOST") or "").strip()
    if not host:
        return None
    pengguna = (db.config("SMTP_USER") or "").strip()
    pengirim = (db.config("SMTP_FROM") or pengguna).strip()
    if not pengirim:
        return None
    try:
        port = int(db.config("SMTP_PORT", "587"))
    except ValueError:
        return None
    keamanan = (db.config("SMTP_SECURITY", "starttls") or "starttls").strip().lower()
    if keamanan not in ("starttls", "ssl", "none"):
        keamanan = "starttls"
    return {
        "host": host,
        "port": port,
        "user": pengguna,
        "password": db.config("SMTP_PASSWORD") or "",
        "dari": pengirim,
        "keamanan": keamanan,
    }


def terkonfigurasi() -> bool:
    return konfigurasi() is not None


def kirim_email(tujuan: str, subjek: str, isi: str) -> None:
    """Kirim satu email teks biasa. Melempar exception bila gagal."""
    cfg = konfigurasi()
    if cfg is None:
        raise RuntimeError("SMTP belum dikonfigurasi.")
    pesan = EmailMessage()  # menolak karakter baris baru di header (anti header injection)
    pesan["From"] = cfg["dari"]
    pesan["To"] = tujuan
    pesan["Subject"] = subjek
    pesan.set_content(isi)

    konteks = ssl.create_default_context()
    if cfg["keamanan"] == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15, context=konteks)
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
    with server:
        if cfg["keamanan"] == "starttls":
            server.starttls(context=konteks)
        if cfg["user"]:
            server.login(cfg["user"], cfg["password"])
        server.send_message(pesan)


def _samarkan(email: str) -> str:
    nama, _, domain = email.partition("@")
    return f"{nama[:1]}***@{domain}"


def kirim_di_latar(tujuan: str, subjek: str, isi: str) -> None:
    """Kirim di thread terpisah agar waktu respons halaman sama, apa pun hasilnya
    (mencegah penebakan email terdaftar lewat lamanya respons)."""

    def kerja():
        try:
            kirim_email(tujuan, subjek, isi)
        except Exception:
            log.exception("Gagal mengirim email ke %s", _samarkan(tujuan))

    if SINKRON:
        kerja()
    else:
        threading.Thread(target=kerja, daemon=True).start()
