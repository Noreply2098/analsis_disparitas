"""Fungsi bersama: akses dataset, validasi, dan perhitungan Indeks Williamson."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

# ==============================
# KONFIGURASI DATASET
# ==============================

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DATASET_PATH = UPLOAD_DIR / "dataset.csv"

COL_WILAYAH = "Nama Wilayah"
COL_TAHUN = "Tahun"
COL_PDRB = "PDRB Per Kapita"
COL_PENDUDUK = "Jumlah Penduduk"

REQUIRED_COLUMNS = [COL_WILAYAH, COL_TAHUN, COL_PDRB, COL_PENDUDUK]
NUMERIC_COLUMNS = [COL_TAHUN, COL_PDRB, COL_PENDUDUK]


# ==============================
# TAMPILAN BERSAMA
# ==============================

def page_header(judul: str, deskripsi: str) -> None:
    st.title(judul)
    st.caption(deskripsi)


def flash(pesan: str, jenis: str = "success") -> None:
    """Simpan pesan agar tetap tampil setelah halaman dimuat ulang."""
    st.session_state["_flash"] = (jenis, pesan)


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if item:
        jenis, pesan = item
        getattr(st, jenis)(pesan)


# ==============================
# AKSES DATASET
# ==============================

def load_dataset() -> tuple[pd.DataFrame | None, str | None]:
    """Baca dataset. Mengembalikan (DataFrame, None) atau (None, pesan_alasan)."""
    if not DATASET_PATH.exists():
        return None, "Dataset belum tersedia. Silakan masukkan data terlebih dahulu."

    try:
        df = pd.read_csv(DATASET_PATH)
    except Exception:
        return None, "Dataset tidak dapat dibaca. Silakan import ulang data."

    if not all(col in df.columns for col in REQUIRED_COLUMNS):
        return None, "Format kolom dataset tidak sesuai."

    return df, None


def save_dataset(df: pd.DataFrame) -> None:
    df.to_csv(DATASET_PATH, index=False, encoding="utf-8-sig")


def delete_dataset() -> None:
    if DATASET_PATH.exists():
        DATASET_PATH.unlink()


# ==============================
# VALIDASI INPUT
# ==============================

def to_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def validasi_baris(df: pd.DataFrame) -> pd.DataFrame:
    """Validasi baris input/edit. Melempar ValueError jika ada yang tidak sesuai."""
    df = df[REQUIRED_COLUMNS].copy()

    nama = df[COL_WILAYAH].fillna("").astype(str).str.strip()
    angka = to_numeric_frame(df.assign(**{COL_WILAYAH: nama}))

    # Baris yang benar-benar kosong diabaikan
    kosong = (nama == "") & angka[NUMERIC_COLUMNS].isnull().all(axis=1)
    nama, angka = nama[~kosong], angka[~kosong]

    if len(angka) == 0:
        raise ValueError("Silakan masukkan minimal satu baris data.")

    if (nama == "").any():
        raise ValueError("Nama wilayah tidak boleh kosong.")

    angka[COL_WILAYAH] = nama

    if angka[NUMERIC_COLUMNS].isnull().any().any():
        raise ValueError("Pastikan semua kolom angka diisi dengan benar.")

    if (angka[COL_TAHUN] % 1 != 0).any():
        raise ValueError("Tahun harus berupa bilangan bulat.")

    if ((angka[COL_TAHUN] < 1900) | (angka[COL_TAHUN] > 2100)).any():
        raise ValueError("Tahun tidak valid (harus antara 1900 dan 2100).")

    if (angka[COL_PDRB] < 0).any():
        raise ValueError("PDRB Per Kapita tidak boleh negatif.")

    if (angka[COL_PENDUDUK] <= 0).any():
        raise ValueError("Jumlah penduduk harus lebih dari 0.")

    if (angka[COL_PENDUDUK] % 1 != 0).any():
        raise ValueError("Jumlah penduduk harus berupa bilangan bulat.")

    angka[COL_TAHUN] = angka[COL_TAHUN].astype(int)
    angka[COL_PENDUDUK] = angka[COL_PENDUDUK].astype(int)

    return angka[REQUIRED_COLUMNS].reset_index(drop=True)


# ==============================
# INDEKS WILLIAMSON
# ==============================

@dataclass
class HasilWilliamson:
    indeks: float
    rata_rata: float
    total_penduduk: float
    detail: pd.DataFrame


def daftar_tahun(df: pd.DataFrame) -> list[int]:
    tahun = pd.to_numeric(df[COL_TAHUN], errors="coerce").dropna()
    return sorted(tahun.astype(int).unique().tolist())


def interpretasi(indeks: float) -> str:
    if indeks < 0.3:
        return "Ketimpangan rendah"
    if indeks <= 0.5:
        return "Ketimpangan sedang"
    return "Ketimpangan tinggi"


def data_valid_tahun(df: pd.DataFrame, tahun: int) -> pd.DataFrame:
    """Ambil data satu tahun yang valid (angka lengkap, PDRB >= 0, penduduk > 0)."""
    data = to_numeric_frame(df)
    data = data[data[COL_TAHUN] == tahun].dropna(subset=[COL_PDRB, COL_PENDUDUK])
    return data[(data[COL_PDRB] >= 0) & (data[COL_PENDUDUK] > 0)].copy()


def hitung_williamson(
    df: pd.DataFrame, tahun: int
) -> tuple[HasilWilliamson | None, str | None]:
    """Hitung Indeks Williamson untuk satu tahun.

    Mengembalikan (hasil, None) bila berhasil, atau (None, pesan) bila gagal.
    """
    data = data_valid_tahun(df, tahun)

    if len(data) < 2:
        return None, "Minimal diperlukan dua wilayah dengan data valid."

    total_penduduk = data[COL_PENDUDUK].sum()
    rata_rata = (data[COL_PDRB] * data[COL_PENDUDUK]).sum() / total_penduduk

    if rata_rata <= 0:
        return None, "Rata-rata PDRB per kapita harus lebih dari nol."

    data["Proporsi Penduduk"] = data[COL_PENDUDUK] / total_penduduk
    data["Selisih"] = data[COL_PDRB] - rata_rata
    data["Selisih Kuadrat"] = data["Selisih"] ** 2
    data["Kontribusi"] = data["Proporsi Penduduk"] * data["Selisih Kuadrat"]

    indeks = (data["Kontribusi"].sum() ** 0.5) / rata_rata

    return HasilWilliamson(indeks, rata_rata, total_penduduk, data), None


def tren_williamson(df: pd.DataFrame) -> pd.DataFrame:
    """Indeks Williamson untuk setiap tahun yang datanya memenuhi syarat."""
    baris = []
    for tahun in daftar_tahun(df):
        hasil, _ = hitung_williamson(df, tahun)
        if hasil is not None:
            baris.append({"Tahun": tahun, "Indeks Williamson": hasil.indeks})
    return pd.DataFrame(baris, columns=["Tahun", "Indeks Williamson"])


# ==============================
# RINGKASAN ANALISIS LENGKAP (dipakai halaman Analisis & dokumen cetak)
# ==============================

@dataclass
class HasilAnalisis:
    tahun: int
    hasil: HasilWilliamson
    detail: pd.DataFrame
    kategori: str
    total_kontribusi: float
    tertinggi: pd.Series
    terendah: pd.Series
    rasio: float | None
    pendorong: pd.Series
    sebelumnya: tuple[int, float] | None

    @property
    def jumlah_wilayah(self) -> int:
        return len(self.detail)


def susun_analisis(
    df: pd.DataFrame, tahun: int
) -> tuple[HasilAnalisis | None, str | None]:
    """Hitung Indeks Williamson beserta turunan yang dipakai untuk tampilan dan cetak."""
    hasil, pesan = hitung_williamson(df, tahun)
    if hasil is None:
        return None, pesan

    detail = hasil.detail.drop(columns=["Tahun"]).reset_index(drop=True)

    total_kontribusi = float(detail["Kontribusi"].sum())
    detail["Porsi Kontribusi"] = (
        detail["Kontribusi"] / total_kontribusi if total_kontribusi > 0 else 0.0
    )
    detail["Posisi"] = np.select(
        [detail["Selisih"] > 0, detail["Selisih"] < 0],
        ["Di atas rata-rata", "Di bawah rata-rata"],
        default="Sama dengan rata-rata",
    )

    tertinggi = detail.loc[detail[COL_PDRB].idxmax()]
    terendah = detail.loc[detail[COL_PDRB].idxmin()]
    rasio = tertinggi[COL_PDRB] / terendah[COL_PDRB] if terendah[COL_PDRB] > 0 else None
    pendorong = detail.loc[detail["Porsi Kontribusi"].idxmax()]

    sebelumnya = None
    for t in reversed([t for t in daftar_tahun(df) if t < tahun]):
        h, _ = hitung_williamson(df, t)
        if h is not None:
            sebelumnya = (t, h.indeks)
            break

    return HasilAnalisis(
        tahun=tahun, hasil=hasil, detail=detail,
        kategori=interpretasi(hasil.indeks),
        total_kontribusi=total_kontribusi,
        tertinggi=tertinggi, terendah=terendah, rasio=rasio,
        pendorong=pendorong, sebelumnya=sebelumnya,
    ), None


def narasi_ringkasan(a: HasilAnalisis) -> str:
    """Kalimat ringkasan otomatis (teks tebal ditandai dengan **...**)."""
    teks = (
        f"Pada tahun {a.tahun}, PDRB per kapita tertinggi dimiliki **{a.tertinggi[COL_WILAYAH]}** "
        f"({a.tertinggi[COL_PDRB]:,.0f}) dan terendah **{a.terendah[COL_WILAYAH]}** "
        f"({a.terendah[COL_PDRB]:,.0f})"
    )
    if a.rasio:
        teks += f", atau selisih {a.rasio:.2f} kali lipat"
    teks += "."
    if a.jumlah_wilayah > 1 and a.total_kontribusi > 0:
        teks += (
            f" Wilayah yang paling besar menyumbang ketimpangan adalah "
            f"**{a.pendorong[COL_WILAYAH]}** ({a.pendorong['Porsi Kontribusi']:.1%} "
            f"dari total kontribusi)."
        )
    return teks
