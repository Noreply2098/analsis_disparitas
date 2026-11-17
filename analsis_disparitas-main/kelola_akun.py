"""Alat baris perintah untuk pengelola aplikasi (mis. admin satu-satunya lupa password
dan email belum dikonfigurasi).

    python kelola_akun.py cek-db                  uji koneksi DATABASE_URL dan jelaskan galatnya
    python kelola_akun.py kode-reset USERNAME

`cek-db` berguna sebelum menempel DATABASE_URL ke Secrets Streamlit Cloud.

`kode-reset` membuat kode reset password (berlaku 60 menit) untuk akun USERNAME. Pengguna memasukkan kode
itu di halaman Lupa Password bersama email akunnya. Jalankan dengan DATABASE_URL yang sama
dengan aplikasi, misalnya:

    DATABASE_URL="postgresql://..." python kelola_akun.py kode-reset admin
"""

import sys

from sqlalchemy import select

import auth
import db


def cek_db() -> int:
    """Uji koneksi ke database yang dipakai aplikasi dan tampilkan penyebab bila gagal."""
    import sqlalchemy as sa

    url = db.samarkan(db.url_database())
    print(f"Database: {'PostgreSQL' if db.pakai_postgres() else 'SQLite lokal'}  ->  {url}")
    try:
        with db.engine().connect() as conn:
            conn.execute(sa.text("SELECT 1"))
            jumlah = conn.execute(sa.select(sa.func.count()).select_from(db.users)).scalar_one()
    except Exception as exc:
        print("GAGAL terhubung.")
        print("Galat   :", db.samarkan(f"{type(exc).__name__}: {exc}").splitlines()[0][:300])
        print("Petunjuk:", db.petunjuk_galat(exc))
        return 1
    print(f"BERHASIL terhubung. Tabel siap; jumlah akun saat ini: {jumlah}.")
    return 0


def kode_reset(username: str) -> int:
    with db.engine().begin() as conn:
        user_id = conn.execute(
            select(db.users.c.id).where(
                db.users.c.username_lc == username.strip().lower(),
                db.users.c.aktif.is_(True),
            )
        ).scalar_one_or_none()
        if user_id is None:
            print(f"Akun aktif dengan username '{username}' tidak ditemukan.", file=sys.stderr)
            return 1
        kode = auth._terbitkan_reset(conn, user_id, auth.RESET_MASA_ADMIN_MENIT)
    print(f"Kode reset untuk '{username}': {auth._format_kode(kode)}")
    print(f"Berlaku {auth.RESET_MASA_ADMIN_MENIT} menit, sekali pakai. Masukkan di halaman Lupa Password.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "cek-db":
        sys.exit(cek_db())
    if len(sys.argv) == 3 and sys.argv[1] == "kode-reset":
        sys.exit(kode_reset(sys.argv[2]))
    print(__doc__)
    sys.exit(2)
