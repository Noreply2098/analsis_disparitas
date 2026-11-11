"""Penyimpanan data per pengguna.

Setiap pengguna punya folder sendiri: ``uploads/pengguna/<id>/`` berisi ``dataset.csv``,
``metadata.json``, dan ``cadangan/``. Pengguna A tidak pernah membaca folder pengguna B.

TAMU (belum masuk) memakai folder SEMENTARA milik sesinya di direktori temp sistem. Folder itu
tidak pernah disalin ke database maupun ke ``uploads/``, tidak terbaca sesi lain, dan dihapus
otomatis bila sudah lama tidak dipakai. Data tamu hilang saat halaman dimuat ulang atau ditutup.

Agar data bertahan saat server restart (disk hosting bersifat sementara), isi folder
disalin sebagai satu arsip zip ke tabel ``berkas_pengguna`` di database:

- ``siapkan_data()``  : di awal sesi, mengembalikan folder dari database bila folder lokal kosong.
- ``sinkronkan_data()``: di akhir setiap eksekusi halaman, menyimpan arsip bila isi folder berubah.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import secrets
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
import streamlit as st
from sqlalchemy import insert, select, update

import auth
import db
from db import berkas_pengguna

BASE_DIR = Path(__file__).resolve().parent

def _akar_data() -> Path:
    """Folder induk data pengguna. ``RIA_DATA_DIR`` (opsional) memindahkannya, mis. untuk uji."""
    dasar = os.environ.get("RIA_DATA_DIR")
    return Path(dasar) / "pengguna" if dasar else BASE_DIR / "uploads" / "pengguna"


def _akar_tamu() -> Path:
    dasar = os.environ.get("RIA_DATA_DIR")
    return Path(dasar) / "tamu" if dasar else Path(tempfile.gettempdir()) / "ria_tamu"


MASA_TAMU_JAM = 6  # folder tamu yang tak disentuh selama ini dihapus
TAMU_KEY = "_id_tamu"

MAKS_ARSIP_MB = 30
SIDIK_KEY = "_sidik_data"
SIAP_KEY = "_data_siap"
PERINGATAN_KEY = "_peringatan_data"

_NAMA_AMAN = re.compile(r"[A-Za-z0-9_.\-]+")


# ======================================================================
# PATH PER PENGGUNA
# ======================================================================

def bersihkan_tamu_lama() -> None:
    """Hapus folder tamu yang sudah lama tidak dipakai (sesinya pasti sudah berakhir)."""
    if not _akar_tamu().is_dir():
        return
    batas = time.time() - MASA_TAMU_JAM * 3600
    for anak in _akar_tamu().iterdir():
        try:
            if anak.is_dir() and anak.stat().st_mtime < batas:
                shutil.rmtree(anak, ignore_errors=True)
        except OSError:
            pass


def _id_tamu() -> str:
    if TAMU_KEY not in st.session_state:
        bersihkan_tamu_lama()
        st.session_state[TAMU_KEY] = secrets.token_hex(8)
    return st.session_state[TAMU_KEY]


def kunci_pemilik() -> str:
    """Identitas pemilik data saat ini (pengguna atau sesi tamu), untuk kunci cache."""
    pengguna = auth.pengguna_aktif()
    return f"u{int(pengguna['id'])}" if pengguna else f"t{_id_tamu()}"


def dir_data() -> Path:
    pengguna = auth.pengguna_aktif()
    if pengguna:
        folder = _akar_data() / str(int(pengguna["id"]))
        folder.mkdir(parents=True, exist_ok=True)
    else:
        folder = _akar_tamu() / _id_tamu()
        folder.mkdir(parents=True, exist_ok=True)
        os.utime(folder)  # tandai masih dipakai agar tidak ikut dibersihkan
    return folder


def path_dataset() -> Path:
    return dir_data() / "dataset.csv"


def path_metadata() -> Path:
    return dir_data() / "metadata.json"


def dir_cadangan() -> Path:
    return dir_data() / "cadangan"


# ======================================================================
# ARSIP <-> DATABASE
# ======================================================================

def _berkas_data(folder: Path) -> list[Path]:
    """Berkas yang termasuk data pengguna (daftar putih), terurut."""
    hasil = []
    for nama in ("dataset.csv", "metadata.json"):
        if (folder / nama).is_file():
            hasil.append(folder / nama)
    cadangan = folder / "cadangan"
    if cadangan.is_dir():
        hasil += sorted(
            p for p in cadangan.iterdir()
            if p.is_file() and p.suffix in (".csv", ".json") and _NAMA_AMAN.fullmatch(p.name)
        )
    return hasil


def sidik_folder(folder: Path) -> str:
    """Sidik jari ringan (nama, ukuran, waktu ubah) untuk mendeteksi perubahan."""
    bagian = []
    for p in _berkas_data(folder):
        st_ = p.stat()
        bagian.append(f"{p.relative_to(folder).as_posix()}:{st_.st_size}:{st_.st_mtime_ns}")
    return hashlib.sha256("|".join(bagian).encode("utf-8")).hexdigest() if bagian else ""


def buat_arsip(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in _berkas_data(folder):
            zf.write(p, p.relative_to(folder).as_posix())
    return buf.getvalue()


def _nama_diizinkan(nama: str) -> bool:
    if nama in ("dataset.csv", "metadata.json"):
        return True
    induk, _, anak = nama.partition("/")
    return (
        induk == "cadangan"
        and bool(anak)
        and "/" not in anak
        and bool(_NAMA_AMAN.fullmatch(anak))
        and anak.endswith((".csv", ".json"))
    )


def ekstrak_arsip(data: bytes, folder: Path) -> int:
    """Pulihkan arsip ke folder. Hanya nama berkas yang diizinkan yang ditulis
    (mencegah path traversal dari arsip yang dimanipulasi). Mengembalikan jumlah berkas."""
    jumlah = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir() or not _nama_diizinkan(info.filename):
                continue
            if info.file_size > MAKS_ARSIP_MB * 1024 * 1024:
                continue
            tujuan = folder / info.filename
            tujuan.parent.mkdir(parents=True, exist_ok=True)
            tujuan.write_bytes(zf.read(info))
            jumlah += 1
    return jumlah


def _sekarang() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def simpan_arsip(user_id: int, arsip: bytes, sidik: str) -> None:
    with db.engine().begin() as conn:
        hasil = conn.execute(
            update(berkas_pengguna)
            .where(berkas_pengguna.c.user_id == user_id)
            .values(arsip=arsip, sidik=sidik, diubah=_sekarang())
        )
        if hasil.rowcount == 0:
            conn.execute(
                insert(berkas_pengguna).values(
                    user_id=user_id, arsip=arsip, sidik=sidik, diubah=_sekarang()
                )
            )


def _baca_baris(user_id: int):
    with db.engine().connect() as conn:
        return conn.execute(
            select(berkas_pengguna.c.arsip, berkas_pengguna.c.sidik).where(
                berkas_pengguna.c.user_id == user_id
            )
        ).first()


# ======================================================================
# DIPANGGIL DARI app.py
# ======================================================================

def _punya_data(folder: Path) -> bool:
    return bool(_berkas_data(folder))


def _pindahkan_data_tamu(folder_akun: Path) -> None:
    """Saat tamu masuk: bawa data tamu ke akun bila akun belum punya data (tidak pernah
    menimpa data akun). Folder tamu selalu dihapus sesudahnya."""
    id_tamu = st.session_state.pop(TAMU_KEY, None)
    if not id_tamu:
        return
    tamu = _akar_tamu() / id_tamu
    if tamu.is_dir() and _punya_data(tamu):
        if _punya_data(folder_akun):
            auth.antri_toast(
                "Data tamu tidak dipindahkan karena akun Anda sudah memiliki data.",
                ":material/info:",
            )
        else:
            for p in _berkas_data(tamu):
                tujuan = folder_akun / p.relative_to(tamu)
                tujuan.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, tujuan)
            auth.antri_toast(
                "Data yang Anda impor sebagai tamu sekarang tersimpan di akun Anda.",
                ":material/cloud_done:",
            )
    shutil.rmtree(tamu, ignore_errors=True)


def siapkan_data() -> None:
    """Awal sesi pengguna: pulihkan data dari database bila folder lokal kosong, bawa data
    tamu (bila ada), lalu pastikan salinan di database mutakhir."""
    pengguna = auth.pengguna_aktif()
    if not pengguna or st.session_state.get(SIAP_KEY) == pengguna["id"]:
        return
    folder = dir_data()
    baris = _baca_baris(pengguna["id"])
    sidik = sidik_folder(folder)
    sidik_db = baris.sidik if baris is not None else None

    if not sidik and baris is not None and baris.arsip:
        ekstrak_arsip(baris.arsip, folder)
        sidik = sidik_folder(folder)
        # Waktu ubah berkas berganti saat dipulihkan: catat sidik baru agar tidak diunggah ulang.
        simpan_arsip(pengguna["id"], baris.arsip, sidik)
        sidik_db = sidik

    _pindahkan_data_tamu(folder)
    sidik = sidik_folder(folder)
    if sidik and sidik != sidik_db:
        _unggah(pengguna["id"], folder, sidik)

    st.session_state[SIDIK_KEY] = sidik
    st.session_state[SIAP_KEY] = pengguna["id"]


def _unggah(user_id: int, folder: Path, sidik: str) -> bool:
    arsip = buat_arsip(folder)
    if len(arsip) > MAKS_ARSIP_MB * 1024 * 1024:
        st.session_state[PERINGATAN_KEY] = (
            f"Data Anda melebihi {MAKS_ARSIP_MB} MB (setelah dikompres) sehingga tidak "
            "dapat disimpan permanen di database. Hapus cadangan lama atau perkecil data."
        )
        return False
    st.session_state.pop(PERINGATAN_KEY, None)
    simpan_arsip(user_id, arsip, sidik)
    return True


def sinkronkan_data() -> None:
    """Akhir eksekusi halaman: simpan ke database bila isi folder pengguna berubah."""
    pengguna = auth.pengguna_aktif()
    if not pengguna or st.session_state.get(SIAP_KEY) != pengguna["id"]:
        return
    folder = dir_data()
    sidik = sidik_folder(folder)
    if sidik != st.session_state.get(SIDIK_KEY):
        _unggah(pengguna["id"], folder, sidik)
        st.session_state[SIDIK_KEY] = sidik  # juga bila ditolak, agar tidak dicoba ulang tiap rerun
