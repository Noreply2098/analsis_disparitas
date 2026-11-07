"""Fungsi bersama aplikasi RIA: konfigurasi, tampilan, validasi, dataset, dan Indeks Williamson."""

import io
import json
import numpy as np
import os
import pandas as pd
import re
import shutil
import streamlit as st
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# ======================================================================
# KONFIGURASI
# ======================================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "uploads"
BACKUP_DIR = DATA_DIR / "cadangan"
DATASET_PATH = DATA_DIR / "dataset.csv"
METADATA_PATH = DATA_DIR / "metadata.json"

DATA_DIR.mkdir(exist_ok=True)

COL_WILAYAH = "Nama Wilayah"
COL_TAHUN = "Tahun"
COL_PDRB = "PDRB Per Kapita"
COL_PENDUDUK = "Jumlah Penduduk"

COL_KODE = "Kode Wilayah"
COL_PROVINSI = "Provinsi"

REQUIRED_COLUMNS = [COL_WILAYAH, COL_TAHUN, COL_PDRB, COL_PENDUDUK]
NUMERIC_COLUMNS = [COL_TAHUN, COL_PDRB, COL_PENDUDUK]
# Kolom identitas opsional: bila ada, ikut menentukan apakah dua baris dianggap duplikat
# (nama kabupaten yang sama di provinsi berbeda bukan duplikat).
OPTIONAL_COLUMNS = [COL_KODE, COL_PROVINSI]

TAHUN_MIN, TAHUN_MAX = 1900, 2100

MAKS_UKURAN_MB = 10        # batas ukuran berkas impor
MAKS_BARIS_IMPOR = 50_000  # batas jumlah baris berkas impor
MAKS_CADANGAN = 10         # jumlah cadangan otomatis yang disimpan
PENCILAN_MIN_WILAYAH = 5   # pemeriksaan pencilan hanya bila ada cukup wilayah per tahun
PENCILAN_FAKTOR = 3.0      # pagar Tukey (kali IQR) untuk menandai nilai yang tidak biasa


# ======================================================================
# ELEMEN TAMPILAN
# ======================================================================

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


# ======================================================================
# VALIDASI & DUPLIKAT
# ======================================================================

# ==============================
# PEMBERSIHAN NILAI
# ==============================

# Hanya pola yang tidak ambigu (minimal dua kelompok ribuan) yang dikonversi otomatis.
_POLA_TITIK = re.compile(r"^-?\d{1,3}(\.\d{3}){2,}(,\d+)?$")  # 29.000.000 / 1.234.567,89
_POLA_KOMA = re.compile(r"^-?\d{1,3}(,\d{3}){2,}(\.\d+)?$")   # 29,000,000 / 1,234,567.89
# Satu kelompok tepat 3 digit ("104.000" / "104,000") ambigu: bisa ribuan, bisa desimal.
_POLA_AMBIGU = re.compile(r"^-?\d{1,3}[.,]\d{3}$")


def normalisasi_nama(seri: pd.Series) -> pd.Series:
    """Rapikan spasi pada teks (hapus spasi ganda dan spasi tepi)."""
    return seri.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()


def _teks_bersih(nilai) -> str | None:
    if pd.isna(nilai):
        return None
    teks = str(nilai).strip()
    teks = re.sub(r"(?i)^rp\.?\s*", "", teks).replace("\u00a0", "").replace(" ", "")
    return teks or None


def _bersihkan_angka(nilai):
    teks = _teks_bersih(nilai)
    if teks is None:
        return np.nan
    if _POLA_AMBIGU.match(teks):
        return np.nan  # jangan menebak; dilaporkan sebagai format ambigu
    if _POLA_TITIK.match(teks):
        teks = teks.replace(".", "").replace(",", ".")
    elif _POLA_KOMA.match(teks):
        teks = teks.replace(",", "")
    return teks


def angka_ambigu(seri: pd.Series) -> np.ndarray:
    """True untuk sel teks berformat ambigu seperti "104.000" (ribuan atau desimal?)."""
    if pd.api.types.is_numeric_dtype(seri):
        return np.zeros(len(seri), dtype=bool)
    return seri.map(lambda v: bool(_POLA_AMBIGU.match(_teks_bersih(v) or ""))).to_numpy()


def ke_angka(seri: pd.Series) -> pd.Series:
    """Ubah kolom menjadi angka; nilai tidak valid atau ambigu menjadi NaN."""
    if pd.api.types.is_numeric_dtype(seri):
        return pd.to_numeric(seri, errors="coerce")
    return pd.to_numeric(seri.map(_bersihkan_angka), errors="coerce")


def to_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in NUMERIC_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def kolom_identitas(df: pd.DataFrame) -> list[str]:
    """Kolom identitas opsional (Kode Wilayah, Provinsi) yang ada dan berisi."""
    return [
        c for c in OPTIONAL_COLUMNS
        if c in df.columns and normalisasi_nama(df[c]).ne("").any()
    ]


def kolom_dataset(df: pd.DataFrame) -> list[str]:
    """Kolom yang disimpan: kolom wajib + identitas opsional yang berisi."""
    return REQUIRED_COLUMNS + kolom_identitas(df)


# ==============================
# PEMERIKSAAN PER BARIS
# ==============================

@dataclass
class HasilPeriksa:
    valid: pd.DataFrame        # kolom dataset (bertipe benar) + "Baris"
    bermasalah: pd.DataFrame   # "Baris", "Masalah" + nilai asli
    peringatan: pd.DataFrame   # baris valid yang perlu diperiksa (PDRB nol, pencilan)
    jumlah_kosong: int         # baris yang sepenuhnya kosong (diabaikan)


_KOLOM_PERINGATAN = ["Baris", "Peringatan", COL_WILAYAH, COL_TAHUN, COL_PDRB, COL_PENDUDUK, "Perlu konfirmasi"]


def _periksa_peringatan(valid: pd.DataFrame) -> pd.DataFrame:
    """Tandai nilai yang tidak biasa pada baris valid (tanpa menolaknya)."""
    if valid.empty:
        return pd.DataFrame(columns=_KOLOM_PERINGATAN)

    catatan: dict[int, list[str]] = {}
    konfirmasi: set[int] = set()

    # PDRB nol: tidak otomatis dianggap valid; pengguna harus memeriksa definisi datanya.
    for i in valid.index[valid[COL_PDRB] == 0]:
        catatan.setdefault(i, []).append("PDRB per kapita bernilai nol — periksa definisi data")
        konfirmasi.add(i)

    # Pencilan ekstrem terhadap wilayah lain pada tahun yang sama (hanya bila cukup data).
    for tahun, g in valid.groupby(COL_TAHUN):
        if len(g) < PENCILAN_MIN_WILAYAH:
            continue
        for kolom, label in ((COL_PDRB, "PDRB per kapita"), (COL_PENDUDUK, "Jumlah penduduk")):
            q1, q3 = g[kolom].quantile(0.25), g[kolom].quantile(0.75)
            iqr = q3 - q1
            if iqr <= 0:
                continue
            batas_bawah, batas_atas = q1 - PENCILAN_FAKTOR * iqr, q3 + PENCILAN_FAKTOR * iqr
            for i in g.index[(g[kolom] < batas_bawah) | (g[kolom] > batas_atas)]:
                if kolom == COL_PDRB and valid.at[i, COL_PDRB] == 0:
                    continue  # sudah ditandai sebagai nol
                catatan.setdefault(i, []).append(
                    f"{label} jauh di luar sebaran wilayah lain pada tahun {tahun} "
                    "— periksa satuan atau kemungkinan pencilan"
                )

    if not catatan:
        return pd.DataFrame(columns=_KOLOM_PERINGATAN)

    d = valid.loc[list(catatan)].copy()
    d["Peringatan"] = ["; ".join(catatan[i]) for i in d.index]
    d["Perlu konfirmasi"] = [i in konfirmasi for i in d.index]
    return d[_KOLOM_PERINGATAN].sort_values("Baris").reset_index(drop=True)


def periksa_baris(df: pd.DataFrame, offset: int = 1) -> HasilPeriksa:
    """Periksa setiap baris dan catat semua masalahnya.

    offset: nomor baris pertama pada sumber data (1 untuk tabel editor,
    2 untuk berkas dengan baris judul).
    """
    ident_cols = [c for c in OPTIONAL_COLUMNS if c in df.columns]
    mentah = df[REQUIRED_COLUMNS + ident_cols].copy()
    n = len(mentah)
    nomor = np.arange(n) + offset

    nama = normalisasi_nama(mentah[COL_WILAYAH])
    kosong_mentah = {
        c: (mentah[c].isna() | mentah[c].astype(str).str.strip().eq("")).to_numpy()
        for c in NUMERIC_COLUMNS
    }
    angka = {c: ke_angka(mentah[c]) for c in NUMERIC_COLUMNS}
    ambigu = {c: angka_ambigu(mentah[c]) for c in NUMERIC_COLUMNS}
    contoh = "tulis tanpa pemisah ribuan, mis. 104000"

    baris_kosong = (
        nama.eq("").to_numpy()
        & kosong_mentah[COL_TAHUN] & kosong_mentah[COL_PDRB] & kosong_mentah[COL_PENDUDUK]
    )

    masalah: list[list[str]] = [[] for _ in range(n)]

    def tandai(mask, teks):
        for i in np.flatnonzero(np.asarray(mask)):
            masalah[i].append(teks)

    tahun, pdrb, pend = angka[COL_TAHUN], angka[COL_PDRB], angka[COL_PENDUDUK]

    tandai(nama.eq("").to_numpy(), "Nama wilayah kosong")

    tandai(kosong_mentah[COL_TAHUN], "Tahun kosong")
    tandai(ambigu[COL_TAHUN], f"Tahun berformat ambigu ({contoh})")
    tandai(~kosong_mentah[COL_TAHUN] & ~ambigu[COL_TAHUN] & tahun.isna().to_numpy(), "Tahun bukan angka")
    ada = tahun.notna().to_numpy()
    tandai(ada & ((tahun % 1) != 0).to_numpy(), "Tahun harus bilangan bulat")
    tandai(ada & ((tahun < TAHUN_MIN) | (tahun > TAHUN_MAX)).to_numpy(),
           f"Tahun di luar {TAHUN_MIN}–{TAHUN_MAX}")

    tandai(kosong_mentah[COL_PDRB], "PDRB per kapita kosong")
    tandai(ambigu[COL_PDRB], f"PDRB per kapita berformat ambigu ({contoh})")
    tandai(~kosong_mentah[COL_PDRB] & ~ambigu[COL_PDRB] & pdrb.isna().to_numpy(), "PDRB per kapita bukan angka")
    tandai(pdrb.notna().to_numpy() & (pdrb < 0).to_numpy(), "PDRB per kapita negatif")

    tandai(kosong_mentah[COL_PENDUDUK], "Jumlah penduduk kosong")
    tandai(ambigu[COL_PENDUDUK], f"Jumlah penduduk berformat ambigu ({contoh})")
    tandai(~kosong_mentah[COL_PENDUDUK] & ~ambigu[COL_PENDUDUK] & pend.isna().to_numpy(), "Jumlah penduduk bukan angka")
    ada = pend.notna().to_numpy()
    tandai(ada & (pend <= 0).to_numpy(), "Jumlah penduduk harus lebih dari 0")
    tandai(ada & (pend > 0).to_numpy() & ((pend % 1) != 0).to_numpy(),
           "Jumlah penduduk harus bilangan bulat")

    teks_masalah = pd.Series(["; ".join(m) for m in masalah], index=mentah.index)
    bermasalah_mask = teks_masalah.ne("").to_numpy() & ~baris_kosong
    valid_mask = teks_masalah.eq("").to_numpy() & ~baris_kosong

    pdrb_valid = pdrb[valid_mask]
    if len(pdrb_valid) and (pdrb_valid % 1 == 0).all():
        pdrb_valid = pdrb_valid.astype(int)  # PDRB bulat disimpan sebagai bilangan bulat

    data = {
        COL_WILAYAH: nama[valid_mask].to_numpy(),
        COL_TAHUN: tahun[valid_mask].astype(int).to_numpy(),
        COL_PDRB: pdrb_valid.to_numpy(),
        COL_PENDUDUK: pend[valid_mask].astype(int).to_numpy(),
    }
    for c in ident_cols:
        data[c] = normalisasi_nama(mentah[c])[valid_mask].to_numpy()
    data["Baris"] = nomor[valid_mask]
    valid = pd.DataFrame(data)

    bermasalah = mentah[bermasalah_mask].copy()
    bermasalah.insert(0, "Baris", nomor[bermasalah_mask])
    bermasalah.insert(1, "Masalah", teks_masalah[bermasalah_mask].to_numpy())  # dekat nomor baris agar terlihat di HP

    return HasilPeriksa(
        valid, bermasalah.reset_index(drop=True), _periksa_peringatan(valid), int(baris_kosong.sum())
    )


# ==============================
# DUPLIKAT (wilayah + tahun [+ kode/provinsi] yang sama)
# ==============================

def kunci_baris(df: pd.DataFrame) -> pd.Series:
    """Kunci pembanding baris: nama (huruf kecil, spasi dirapikan) + tahun + identitas opsional."""
    kunci = normalisasi_nama(df[COL_WILAYAH]).str.lower()
    kunci = kunci + "|" + pd.to_numeric(df[COL_TAHUN], errors="coerce").astype("Int64").astype(str)
    for c in kolom_identitas(df):
        kunci = kunci + "|" + normalisasi_nama(df[c]).str.lower()
    return kunci


def duplikat(df: pd.DataFrame) -> pd.DataFrame:
    """Semua baris yang berbagi kunci yang sama, lengkap dengan jenisnya.

    Jenis: "Persis sama" (semua nilai sama) atau "Nilai berbeda" (nilai saling bertentangan).
    Bila ada kolom "Baris" / "Asal", ikut ditampilkan.
    """
    ident = kolom_identitas(df)
    kolom_tampil = (
        ["Baris"] + (["Asal"] if "Asal" in df.columns else [])
        + REQUIRED_COLUMNS + ident + ["Jenis"]
    )
    if df.empty:
        return pd.DataFrame(columns=kolom_tampil)

    d = df.copy()
    if "Baris" not in d.columns:
        d["Baris"] = np.arange(len(d)) + 1
    d["_k"] = kunci_baris(d)
    d = d[d["_k"].duplicated(keep=False)].copy()
    if d.empty:
        return pd.DataFrame(columns=kolom_tampil)

    d["_v"] = d[COL_PDRB].astype(str) + "|" + d[COL_PENDUDUK].astype(str)
    n_unik = d.groupby("_k")["_v"].nunique()
    d["Jenis"] = d["_k"].map(lambda k: "Persis sama" if n_unik[k] == 1 else "Nilai berbeda")
    d = d.sort_values(["_k", "Baris"], kind="stable")
    return d[kolom_tampil].reset_index(drop=True)


def hapus_duplikat(df: pd.DataFrame, simpan: str = "pertama") -> pd.DataFrame:
    """Hapus duplikat dan simpan kemunculan "pertama" atau "terakhir"."""
    keep = "first" if simpan == "pertama" else "last"
    return df[~kunci_baris(df).duplicated(keep=keep)].reset_index(drop=True)


def terapkan_pilihan_duplikat(gabungan: pd.DataFrame, pilihan: pd.DataFrame):
    """Terapkan pilihan manual: tepat satu baris "Simpan" untuk setiap kelompok duplikat.

    pilihan: tabel duplikat (hasil duplikat()) dengan kolom bool "Simpan".
    Mengembalikan (data tanpa baris yang dibuang, None) atau (None, pesan galat).
    """
    per_kelompok = pilihan["Simpan"].groupby(kunci_baris(pilihan).to_numpy()).sum()
    if (per_kelompok != 1).any():
        return None, "pada pilihan manual, centang tepat satu baris untuk setiap kelompok duplikat"

    buang = pilihan[~pilihan["Simpan"]]
    dibuang = set(zip(buang["Asal"], buang["Baris"]))
    simpan = [(a, b) not in dibuang for a, b in zip(gabungan["Asal"], gabungan["Baris"])]
    return gabungan[simpan].reset_index(drop=True), None


def duplikat_tahun(df: pd.DataFrame, tahun: int) -> pd.DataFrame:
    """Duplikat pada satu tahun pengamatan (untuk peringatan di halaman analisis)."""
    data = to_numeric_frame(df)
    return duplikat(data[data[COL_TAHUN] == tahun])


def beri_label_unik(df: pd.DataFrame) -> pd.DataFrame:
    """Samakan nama wilayah yang kembar (provinsi/kode berbeda) agar tampil unik di grafik.

    Contoh: "Kabupaten Bogor (Jawa Barat)". Baris yang benar-benar duplikat dibiarkan.
    """
    d = df.copy()
    nama = normalisasi_nama(d[COL_WILAYAH])
    kembar = nama.str.lower().duplicated(keep=False)
    if not kembar.any():
        return d
    penanda = pd.Series("", index=d.index)
    for c in (COL_PROVINSI, COL_KODE):
        if c in d.columns:
            teks = normalisasi_nama(d[c])
            penanda = penanda.where(penanda != "", teks)
    d.loc[kembar, COL_WILAYAH] = nama[kembar] + np.where(
        penanda[kembar] != "", " (" + penanda[kembar] + ")", ""
    )
    return d


# ==============================
# VALIDASI KETAT (editor tabel & input manual)
# ==============================

def validasi_baris(
    df: pd.DataFrame, offset: int = 1,
    izinkan_duplikat: bool = False, konfirmasi_nol: bool = False,
) -> pd.DataFrame:
    """Validasi baris dari tabel. Melempar ValueError dengan nomor baris bermasalah."""
    hasil = periksa_baris(df, offset)

    if hasil.valid.empty and hasil.bermasalah.empty:
        raise ValueError("Silakan masukkan minimal satu baris data.")

    if not hasil.bermasalah.empty:
        b = hasil.bermasalah
        pesan = "; ".join(f"Baris {r.Baris}: {r.Masalah}" for r in b.head(5).itertuples())
        if len(b) > 5:
            pesan += f" (dan {len(b) - 5} baris lain bermasalah)"
        raise ValueError(pesan)

    nol = hasil.peringatan[hasil.peringatan["Perlu konfirmasi"]] if not hasil.peringatan.empty else hasil.peringatan
    if not konfirmasi_nol and not nol.empty:
        raise ValueError(
            "PDRB per kapita bernilai nol pada baris " + ", ".join(map(str, nol["Baris"].head(5)))
            + ". Periksa definisi data, lalu konfirmasi bila nilai nol memang benar."
        )

    if not izinkan_duplikat:
        dup = duplikat(hasil.valid)
        if not dup.empty:
            grup = []
            for _, g in dup.groupby(kunci_baris(dup), sort=False):
                grup.append(
                    f"{g[COL_WILAYAH].iloc[0]} ({g[COL_TAHUN].iloc[0]}) "
                    f"pada baris {', '.join(map(str, g['Baris']))}"
                )
            pesan = "Data duplikat (wilayah dan tahun sama): " + "; ".join(grup[:3])
            if len(grup) > 3:
                pesan += f" (dan {len(grup) - 3} duplikat lain)"
            raise ValueError(pesan)

    return hasil.valid[kolom_dataset(hasil.valid)].reset_index(drop=True)


# ======================================================================
# MEMBACA BERKAS IMPOR
# ======================================================================

def _kunci_kolom(nama) -> str:
    return re.sub(r"\s+", " ", str(nama).replace("_", " ").strip()).lower()


def daftar_sheet(isi: bytes) -> list[str]:
    try:
        return pd.ExcelFile(io.BytesIO(isi)).sheet_names
    except Exception as e:
        raise ValueError(f"File Excel tidak dapat dibuka: {e}") from e


def baca_berkas(nama_berkas: str, isi: bytes, sheet: str | None = None) -> pd.DataFrame:
    """Baca CSV/Excel sebagai teks mentah (agar format angka dapat diperiksa sendiri)."""
    if len(isi) > MAKS_UKURAN_MB * 1024 * 1024:
        raise ValueError(f"Ukuran berkas melebihi {MAKS_UKURAN_MB} MB.")
    if len(isi) == 0:
        raise ValueError("Berkas kosong.")

    nama = nama_berkas.lower()
    try:
        if nama.endswith(".csv"):
            teks = None
            for encoding in ("utf-8-sig", "cp1252"):
                try:
                    teks = isi.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if teks is None:
                raise ValueError("Encoding berkas CSV tidak dikenali. Simpan ulang sebagai CSV UTF-8.")
            df = pd.read_csv(io.StringIO(teks), sep=None, engine="python", dtype=str)
        elif nama.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(io.BytesIO(isi), sheet_name=sheet or 0, dtype=str)
        else:
            raise ValueError("Format berkas tidak didukung. Gunakan .csv atau .xlsx.")
    except ValueError:
        raise
    except pd.errors.EmptyDataError as e:
        raise ValueError("Berkas kosong atau tidak memiliki baris judul.") from e
    except Exception as e:
        raise ValueError(f"Gagal membaca berkas: {e}") from e

    if df.empty:
        raise ValueError("Berkas tidak memiliki baris data.")
    if len(df) > MAKS_BARIS_IMPOR:
        raise ValueError(f"Jumlah baris melebihi batas {MAKS_BARIS_IMPOR:,} baris.")
    return df


# Variasi penulisan yang diterima (sengaja konservatif: "PDRB" saja tidak dipetakan
# karena bisa berarti PDRB total, bukan per kapita).
ALIAS_KOLOM = {
    COL_WILAYAH: ["wilayah", "nama daerah", "daerah", "kabupaten/kota", "kab/kota", "kabupaten kota"],
    COL_TAHUN: ["tahun pengamatan", "periode"],
    COL_PDRB: ["pdrb perkapita", "pdrb/kapita", "pdrb per-kapita", "pdrb per kapita (rp)",
               "pdrb per kapita (rupiah)"],
    COL_PENDUDUK: ["penduduk", "jumlah penduduk (jiwa)", "populasi", "jumlah populasi"],
    COL_KODE: ["kode daerah", "kode bps", "kode kab/kota"],
    COL_PROVINSI: ["nama provinsi"],
}


def cocokkan_kolom(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str], list[str]]:
    """Samakan nama kolom berkas dengan nama baku.

    Mengabaikan huruf besar/kecil, spasi, dan garis bawah, serta menerima variasi
    penulisan pada ALIAS_KOLOM. Kolom identitas opsional (Kode Wilayah, Provinsi)
    ikut dibawa bila ada.

    Mengembalikan (df kolom baku, kolom wajib yang hilang, kolom tambahan yang
    diabaikan, catatan pemetaan nama kolom).
    """
    peta = {}
    for baku in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
        peta[_kunci_kolom(baku)] = baku
        for alias in ALIAS_KOLOM.get(baku, []):
            peta[_kunci_kolom(alias)] = baku

    ganti, dipakai, catatan = {}, set(), []
    for kolom in df.columns:
        baku = peta.get(_kunci_kolom(kolom))
        if baku and baku not in dipakai:
            ganti[kolom] = baku
            dipakai.add(baku)
            if _kunci_kolom(kolom) != _kunci_kolom(baku):
                catatan.append(f"Kolom \"{kolom}\" dibaca sebagai \"{baku}\"")

    hilang = [k for k in REQUIRED_COLUMNS if k not in dipakai]
    ekstra = [str(k) for k in df.columns if k not in ganti]
    hasil = df.rename(columns=ganti)
    if not hilang:
        hasil = hasil[REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS if c in dipakai]]
    return hasil, hilang, ekstra, catatan


# ======================================================================
# PENYIMPANAN DATASET
# ======================================================================

# Isian metadata sumber data (semua opsional).
KOLOM_METADATA = ["sumber", "tautan", "tanggal_pengambilan", "satuan", "catatan_revisi"]

# ==============================
# METADATA
# ==============================

def baca_metadata() -> dict:
    if not METADATA_PATH.exists():
        return {}
    try:
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def simpan_metadata(metadata: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    sementara = METADATA_PATH.with_suffix(".tmp")
    sementara.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(sementara, METADATA_PATH)


# ==============================
# BACA / SIMPAN
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


def save_dataset(df: pd.DataFrame, alasan: str = "simpan", metadata: dict | None = None) -> dict:
    """Simpan dataset dengan aman lalu verifikasi.

    Langkah: cadangan dataset lama -> tulis berkas sementara -> ganti secara atomik ->
    baca ulang dan cocokkan jumlah baris & kolom -> catat metadata.
    Mengembalikan metadata yang tersimpan. Melempar ValueError bila verifikasi gagal.
    """
    DATA_DIR.mkdir(exist_ok=True)
    buat_cadangan(alasan)

    kolom = kolom_dataset(df)
    sementara = DATASET_PATH.with_suffix(".tmp")
    df[kolom].to_csv(sementara, index=False, encoding="utf-8-sig")
    os.replace(sementara, DATASET_PATH)

    # Verifikasi: baca ulang dan pastikan isinya sesuai.
    ulang, galat = load_dataset()
    if ulang is None or len(ulang) != len(df) or list(ulang.columns) != kolom:
        raise ValueError(
            "Verifikasi setelah menyimpan gagal: isi dataset tidak sesuai. "
            "Pulihkan dari cadangan terbaru di tab Kelola Dataset."
        )

    meta = baca_metadata()
    if metadata:
        meta.update(metadata)
    meta["jumlah_baris"] = len(ulang)
    meta["terakhir_diubah"] = datetime.now().isoformat(timespec="seconds")
    simpan_metadata(meta)
    return meta


def delete_dataset() -> None:
    """Hapus dataset (cadangan dibuat lebih dulu sehingga bisa dipulihkan)."""
    if DATASET_PATH.exists():
        buat_cadangan("hapus")
        DATASET_PATH.unlink()
    METADATA_PATH.unlink(missing_ok=True)


# ==============================
# CADANGAN
# ==============================

def buat_cadangan(alasan: str) -> str | None:
    """Salin dataset aktif (dan metadatanya) ke folder cadangan. Mengembalikan nama berkas."""
    if not DATASET_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    tujuan = BACKUP_DIR / f"dataset_{stempel}_{alasan}.csv"
    shutil.copy2(DATASET_PATH, tujuan)
    if METADATA_PATH.exists():
        shutil.copy2(METADATA_PATH, tujuan.with_suffix(".json"))
    _pangkas_cadangan()
    return tujuan.name


def _pangkas_cadangan() -> None:
    berkas = sorted(BACKUP_DIR.glob("dataset_*.csv"), reverse=True)
    for lama in berkas[MAKS_CADANGAN:]:
        lama.unlink(missing_ok=True)
        lama.with_suffix(".json").unlink(missing_ok=True)


def daftar_cadangan() -> list[dict]:
    """Cadangan terbaru lebih dulu: nama berkas, waktu, alasan, dan jumlah baris."""
    if not BACKUP_DIR.exists():
        return []
    hasil = []
    for path in sorted(BACKUP_DIR.glob("dataset_*.csv"), reverse=True):
        bagian = path.stem.split("_")  # dataset, tanggal, jam, mikrodetik, alasan
        try:
            waktu = datetime.strptime("_".join(bagian[1:4]), "%Y%m%d_%H%M%S_%f")
        except ValueError:
            continue
        try:
            baris = len(pd.read_csv(path))
        except Exception:
            baris = None
        hasil.append({
            "nama": path.name, "waktu": waktu,
            "alasan": "_".join(bagian[4:]) or "simpan", "baris": baris,
        })
    return hasil


def pulihkan(nama_berkas: str) -> None:
    """Pulihkan dataset dan metadata dari cadangan (kondisi saat ini dicadangkan lebih dulu)."""
    sumber = BACKUP_DIR / os.path.basename(nama_berkas)
    if not sumber.exists():
        raise ValueError("Cadangan tidak ditemukan.")
    buat_cadangan("sebelum-pulih")
    DATA_DIR.mkdir(exist_ok=True)
    sementara = DATASET_PATH.with_suffix(".tmp")
    shutil.copyfile(sumber, sementara)
    os.replace(sementara, DATASET_PATH)

    meta_cadangan = sumber.with_suffix(".json")
    if meta_cadangan.exists():
        shutil.copyfile(meta_cadangan, METADATA_PATH)
    else:
        METADATA_PATH.unlink(missing_ok=True)


# ==============================
# INFORMASI
# ==============================

def info_dataset(df: pd.DataFrame) -> dict:
    tahun = pd.to_numeric(df[COL_TAHUN], errors="coerce").dropna().astype(int)
    stat = DATASET_PATH.stat()
    return {
        "baris": len(df),
        "wilayah": df[COL_WILAYAH].nunique(),
        "tahun_awal": int(tahun.min()) if len(tahun) else None,
        "tahun_akhir": int(tahun.max()) if len(tahun) else None,
        "ukuran_kb": stat.st_size / 1024,
        "diubah": datetime.fromtimestamp(stat.st_mtime),
        "metadata": baca_metadata(),
    }


# ==============================
# EKSPOR & TEMPLAT
# ==============================

def ke_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def ke_excel_bytes(df: pd.DataFrame, sheet: str = "Data") -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as penulis:
        df.to_excel(penulis, index=False, sheet_name=sheet)
    return buf.getvalue()


def template_kosong() -> pd.DataFrame:
    """Templat impor: hanya baris judul, tanpa data contoh."""
    return pd.DataFrame(columns=REQUIRED_COLUMNS)


# ======================================================================
# INDEKS WILLIAMSON
# ======================================================================

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
    data = data[(data[COL_PDRB] >= 0) & (data[COL_PENDUDUK] > 0)].copy()
    return beri_label_unik(data)  # nama kembar (provinsi/kode berbeda) dibuat unik untuk tampilan


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
