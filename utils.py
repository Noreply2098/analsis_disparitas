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

def kunci_wilayah(df: pd.DataFrame) -> pd.Series:
    """Identitas wilayah (tanpa tahun).

    - Bila Kode Wilayah terisi, kode resmi itulah identitas utama; nama yang ditulis
      berbeda tidak menjadi masalah.
    - Selain itu: nama (huruf kecil, spasi dirapikan) + provinsi (bila ada).
    """
    kunci = "nama:" + normalisasi_nama(df[COL_WILAYAH]).str.lower()
    ident = kolom_identitas(df)
    if COL_PROVINSI in ident:
        kunci = kunci + "|" + normalisasi_nama(df[COL_PROVINSI]).str.lower()
    if COL_KODE in ident:
        kode = normalisasi_nama(df[COL_KODE]).str.lower()
        kunci = kunci.where(kode == "", "kode:" + kode)
    return kunci


def kunci_baris(df: pd.DataFrame) -> pd.Series:
    """Kunci pembanding baris: identitas wilayah + tahun."""
    tahun = pd.to_numeric(df[COL_TAHUN], errors="coerce").astype("Int64").astype(str)
    return kunci_wilayah(df) + "|" + tahun


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


def _kosong(df: pd.DataFrame, kolom: str) -> pd.Series:
    return normalisasi_nama(df[kolom]).eq("")


def identitas_tidak_lengkap(df: pd.DataFrame) -> pd.DataFrame:
    """Baris yang Kode Wilayah / Provinsinya kosong padahal kolom itu dipakai pada dataset."""
    ident = kolom_identitas(df)
    kolom_tampil = ["Baris"] + (["Asal"] if "Asal" in df.columns else []) + REQUIRED_COLUMNS + ident + ["Catatan"]
    if not ident or df.empty:
        return pd.DataFrame(columns=kolom_tampil)

    d = df.copy()
    if "Baris" not in d.columns:
        d["Baris"] = np.arange(len(d)) + 1
    kurang = pd.Series([[] for _ in range(len(d))], index=d.index)
    for c in ident:
        for i in d.index[_kosong(d, c)]:
            kurang[i] = kurang[i] + [c]
    d = d[kurang.map(len) > 0].copy()
    d["Catatan"] = kurang[d.index].map(lambda k: "Kosong: " + ", ".join(k))
    return d[kolom_tampil].reset_index(drop=True)


def kemungkinan_duplikat(df: pd.DataFrame) -> pd.DataFrame:
    """Baris yang mungkin merujuk wilayah yang sama karena identitasnya tidak lengkap.

    Contoh: "Kabupaten A / 2024 / Sumatera Utara" dan "Kabupaten A / 2024 / (kosong)".
    Nama + tahun sama, kuncinya berbeda, dan sebagian identitas kosong pada salah satunya.
    Wilayah yang identitasnya terisi lengkap dan berbeda (mis. provinsi berbeda) tidak ditandai.
    Hasil hanya untuk diperiksa pengguna; tidak ada data yang digabung atau dihapus.
    """
    ident = kolom_identitas(df)
    kolom_tampil = (
        ["Baris"] + (["Asal"] if "Asal" in df.columns else [])
        + REQUIRED_COLUMNS + ident + ["Jenis", "Alasan"]
    )
    if not ident or df.empty:
        return pd.DataFrame(columns=kolom_tampil)

    d = df.copy()
    if "Baris" not in d.columns:
        d["Baris"] = np.arange(len(d)) + 1
    d["_k"] = kunci_baris(d)
    d["_g"] = normalisasi_nama(d[COL_WILAYAH]).str.lower() + "|" + pd.to_numeric(
        d[COL_TAHUN], errors="coerce"
    ).astype("Int64").astype(str)

    terpilih, alasan = [], {}
    for _, g in d.groupby("_g"):
        if len(g) < 2 or g["_k"].nunique() < 2:
            continue
        kurang = [c for c in ident if _kosong(g, c).any() and (~_kosong(g, c)).any()]
        if kurang:
            terpilih.extend(g.index)
            for i in g.index:
                alasan[i] = "Identitas tidak lengkap: " + ", ".join(kurang) + " kosong pada sebagian baris"

    if not terpilih:
        return pd.DataFrame(columns=kolom_tampil)
    hasil = d.loc[terpilih].copy()
    hasil["Jenis"] = "Kemungkinan duplikat"
    hasil["Alasan"] = pd.Series(alasan)
    return hasil.sort_values(["_g", "Baris"], kind="stable")[kolom_tampil].reset_index(drop=True)


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


def kemungkinan_duplikat_tahun(df: pd.DataFrame, tahun: int) -> pd.DataFrame:
    """Kemungkinan duplikat pada satu tahun pengamatan."""
    data = to_numeric_frame(df)
    return kemungkinan_duplikat(data[data[COL_TAHUN] == tahun])


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
        # Kode/provinsi adalah identitas (teks): "0101" tidak boleh menjadi 101 dan kolom
        # yang sebagian kosong tidak boleh berubah menjadi desimal.
        df = pd.read_csv(DATASET_PATH, dtype={c: str for c in OPTIONAL_COLUMNS})
    except Exception:
        return None, "Dataset tidak dapat dibaca. Silakan import ulang data."

    if not all(col in df.columns for col in REQUIRED_COLUMNS):
        return None, "Format kolom dataset tidak sesuai."

    return df, None


def _bandingkan_isi(maksud: pd.DataFrame, terbaca: pd.DataFrame) -> str | None:
    """Bandingkan data yang dimaksudkan dengan hasil baca ulang berkas.

    Memeriksa urutan/nama kolom, jumlah baris, nilai kosong, tipe angka (bulat vs desimal),
    presisi angka, dan isi teks. Mengembalikan pesan perbedaan pertama, atau None bila sama.
    """
    if list(terbaca.columns) != list(maksud.columns):
        return f"kolom berbeda (diharapkan {list(maksud.columns)}, terbaca {list(terbaca.columns)})"
    if len(terbaca) != len(maksud):
        return f"jumlah baris berbeda (diharapkan {len(maksud)}, terbaca {len(terbaca)})"

    for kolom in maksud.columns:
        a = maksud[kolom].reset_index(drop=True)
        b = terbaca[kolom].reset_index(drop=True)

        if pd.api.types.is_numeric_dtype(a):
            if not pd.api.types.is_numeric_dtype(b):
                return f"kolom '{kolom}' tidak lagi berupa angka"
            if pd.api.types.is_integer_dtype(a) != pd.api.types.is_integer_dtype(b):
                return f"tipe angka kolom '{kolom}' berubah (bulat/desimal)"
            if a.isna().tolist() != b.isna().tolist():
                return f"nilai kosong pada kolom '{kolom}' berubah"
            ada = a.notna().to_numpy()
            if not np.allclose(a[ada].astype(float), b[ada].astype(float), rtol=1e-12, atol=0):
                return f"presisi angka kolom '{kolom}' berubah"
        else:
            # CSV tidak membedakan teks kosong dan nilai kosong, jadi keduanya disamakan.
            if a.fillna("").astype(str).tolist() != b.fillna("").astype(str).tolist():
                return f"isi teks kolom '{kolom}' berubah"
    return None


def save_dataset(df: pd.DataFrame, alasan: str = "simpan", metadata: dict | None = None) -> dict:
    """Simpan dataset dengan aman lalu verifikasi isinya.

    Langkah: cadangan dataset lama -> tulis berkas sementara -> ganti secara atomik ->
    baca ulang dan bandingkan ISI dengan data yang dimaksud -> catat metadata.
    Bila penulisan atau verifikasi gagal, dataset sebelumnya dikembalikan dari cadangan
    dan ValueError dilempar; penyimpanan tidak pernah dilaporkan berhasil.
    """
    DATA_DIR.mkdir(exist_ok=True)
    kolom = kolom_dataset(df)
    maksud = df[kolom].reset_index(drop=True)
    ada_sebelumnya = DATASET_PATH.exists()
    meta_sebelumnya = METADATA_PATH.read_bytes() if METADATA_PATH.exists() else None
    cadangan = buat_cadangan(alasan)

    sementara = DATASET_PATH.with_suffix(".tmp")

    def kembalikan(pesan: str):
        """Kembalikan dataset dan metadata sebelumnya, lalu laporkan kegagalan."""
        sementara.unlink(missing_ok=True)
        if ada_sebelumnya and cadangan:
            shutil.copyfile(BACKUP_DIR / cadangan, DATASET_PATH)
            if meta_sebelumnya is not None:
                METADATA_PATH.write_bytes(meta_sebelumnya)
            else:
                METADATA_PATH.unlink(missing_ok=True)
            raise ValueError(f"{pesan} Dataset sebelumnya dikembalikan dari cadangan.")
        DATASET_PATH.unlink(missing_ok=True)
        raise ValueError(f"{pesan} Dataset belum tersimpan.")

    try:
        maksud.to_csv(sementara, index=False, encoding="utf-8-sig")
        os.replace(sementara, DATASET_PATH)
    except OSError as e:
        kembalikan(f"Gagal menulis dataset ({e}).")

    # Verifikasi isi: baca ulang berkas hasil penyimpanan.
    ulang, galat = load_dataset()
    if ulang is None:
        kembalikan(f"Verifikasi gagal: berkas tidak dapat dibaca ({galat}).")
    perbedaan = _bandingkan_isi(maksud, ulang)
    if perbedaan:
        kembalikan(f"Verifikasi gagal: {perbedaan}.")

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

def buat_cadangan(alasan: str, lindungi: set[str] | None = None) -> str | None:
    """Salin dataset aktif (dan metadatanya) ke folder cadangan. Mengembalikan nama berkas.

    lindungi: nama cadangan yang tidak boleh ikut dipangkas.
    """
    if not DATASET_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    tujuan = BACKUP_DIR / f"dataset_{stempel}_{alasan}.csv"
    shutil.copy2(DATASET_PATH, tujuan)
    if METADATA_PATH.exists():
        shutil.copy2(METADATA_PATH, tujuan.with_suffix(".json"))
    _pangkas_cadangan(lindungi or set())
    return tujuan.name


def _pangkas_cadangan(lindungi: set[str] | None = None) -> None:
    lindungi = lindungi or set()
    berkas = sorted(BACKUP_DIR.glob("dataset_*.csv"), reverse=True)
    for lama in berkas[MAKS_CADANGAN:]:
        if lama.name in lindungi:
            continue
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


def periksa_cadangan(nama_berkas: str) -> pd.DataFrame:
    """Pastikan cadangan dapat dibaca dan berstruktur benar. Melempar ValueError bila tidak."""
    sumber = BACKUP_DIR / os.path.basename(nama_berkas)
    if not sumber.exists():
        raise ValueError("Cadangan tidak ditemukan.")
    try:
        data = pd.read_csv(sumber, dtype={c: str for c in OPTIONAL_COLUMNS})
    except Exception as e:
        raise ValueError(f"Cadangan rusak dan tidak dapat dibaca ({type(e).__name__}).") from e
    kurang = [k for k in REQUIRED_COLUMNS if k not in data.columns]
    if kurang:
        raise ValueError("Cadangan tidak sesuai: kolom wajib hilang (" + ", ".join(kurang) + ").")
    return data


def pulihkan(nama_berkas: str) -> None:
    """Pulihkan dataset dan metadata dari cadangan, lalu verifikasi hasilnya.

    Urutan: periksa cadangan -> cadangkan kondisi saat ini -> ganti dataset secara atomik ->
    baca ulang dan cocokkan dengan cadangan -> pulihkan metadata yang sesuai.
    Cadangan tidak pernah dihapus; bila gagal, kondisi sebelumnya dikembalikan.
    """
    sumber = BACKUP_DIR / os.path.basename(nama_berkas)
    isi_cadangan = periksa_cadangan(nama_berkas)  # ditolak sebelum ada yang diubah

    ada_sebelumnya = DATASET_PATH.exists()
    meta_sebelumnya = METADATA_PATH.read_bytes() if METADATA_PATH.exists() else None
    sebelum = buat_cadangan("sebelum-pulih", lindungi={sumber.name})

    DATA_DIR.mkdir(exist_ok=True)
    sementara = DATASET_PATH.with_suffix(".tmp")

    def batalkan(pesan: str):
        sementara.unlink(missing_ok=True)
        if ada_sebelumnya and sebelum:
            shutil.copyfile(BACKUP_DIR / sebelum, DATASET_PATH)
            if meta_sebelumnya is not None:
                METADATA_PATH.write_bytes(meta_sebelumnya)
            else:
                METADATA_PATH.unlink(missing_ok=True)
            raise ValueError(f"{pesan} Dataset sebelumnya dikembalikan; cadangan tetap tersimpan.")
        DATASET_PATH.unlink(missing_ok=True)
        raise ValueError(f"{pesan} Cadangan tetap tersimpan.")

    try:
        shutil.copyfile(sumber, sementara)
        os.replace(sementara, DATASET_PATH)
    except OSError as e:
        batalkan(f"Gagal memulihkan dataset ({e}).")

    # Verifikasi: dataset aktif harus identik dengan cadangan yang dipilih.
    ulang, galat = load_dataset()
    if ulang is None:
        batalkan(f"Verifikasi gagal: dataset hasil pemulihan tidak dapat dibaca ({galat}).")
    perbedaan = _bandingkan_isi(isi_cadangan, ulang)
    if perbedaan or DATASET_PATH.read_bytes() != sumber.read_bytes():
        batalkan(f"Verifikasi gagal: isi dataset tidak sama dengan cadangan ({perbedaan or 'berkas berbeda'}).")

    # Metadata yang sesuai dengan cadangan tersebut.
    meta_cadangan = sumber.with_suffix(".json")
    meta = None
    if meta_cadangan.exists():
        try:
            meta = json.loads(meta_cadangan.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = None  # metadata cadangan rusak: dataset tetap dipulihkan tanpa catatan sumber
    if meta is None:
        METADATA_PATH.unlink(missing_ok=True)
    else:
        meta["jumlah_baris"] = len(ulang)  # selaraskan dengan isi dataset sebenarnya
        simpan_metadata(meta)


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


# Batas kategori adalah ketetapan aplikasi. SUMBER_BATAS_KATEGORI sengaja dikosongkan:
# isi dengan rujukan literatur penelitian bila kategori dipakai dalam laporan akademik.
BATAS_RENDAH, BATAS_TINGGI = 0.3, 0.5
SUMBER_BATAS_KATEGORI = ""
# Perubahan indeks di bawah ambang ini disebut "relatif stabil" (ketetapan praktis aplikasi).
AMBANG_STABIL = 0.005


def interpretasi(indeks: float) -> str:
    if indeks < BATAS_RENDAH:
        return "Ketimpangan rendah"
    if indeks <= BATAS_TINGGI:
        return "Ketimpangan sedang"
    return "Ketimpangan tinggi"


def keterangan_batas_kategori() -> str:
    """Penjelasan batas kategori, termasuk status sumbernya."""
    rendah, tinggi = (f"{x:g}".replace(".", ",") for x in (BATAS_RENDAH, BATAS_TINGGI))
    teks = f"Kategori: rendah (< {rendah}), sedang ({rendah} – {tinggi}), tinggi (> {tinggi})."
    if SUMBER_BATAS_KATEGORI:
        return teks + f" Sumber batas: {SUMBER_BATAS_KATEGORI}."
    return teks + " Batas ini ketetapan aplikasi; sumber rujukan belum dicantumkan."


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


# ======================================================================
# FILTER DATA (tahun, wilayah, provinsi) — satu sumber untuk semua halaman
# ======================================================================

@dataclass(frozen=True)
class FilterData:
    """Pilihan filter. Nilai kosong berarti "semua"."""
    tahun_awal: int | None = None
    tahun_akhir: int | None = None
    wilayah: tuple = ()
    provinsi: tuple = ()
    konsisten: bool = False  # hanya wilayah yang punya data valid di semua tahun terpilih

    def kunci(self) -> tuple:
        """Kunci yang dapat di-hash (untuk cache)."""
        return (
            self.tahun_awal, self.tahun_akhir,
            tuple(sorted(self.wilayah, key=str.lower)),
            tuple(sorted(self.provinsi, key=str.lower)),
            self.konsisten,
        )


def opsi_filter(df: pd.DataFrame) -> dict:
    """Pilihan filter yang diambil dari data yang benar-benar ada (bukan daftar permanen)."""
    nama = normalisasi_nama(df[COL_WILAYAH])
    pertama = {}
    for asli, rapi in zip(nama.str.lower(), nama):
        if asli and asli not in pertama:
            pertama[asli] = rapi
    provinsi = []
    if COL_PROVINSI in df.columns:
        provinsi = sorted({p for p in normalisasi_nama(df[COL_PROVINSI]) if p}, key=str.lower)
    return {
        "tahun": daftar_tahun(df),
        "wilayah": sorted(pertama.values(), key=str.lower),
        "provinsi": provinsi,
    }


def _data_valid_mask(d: pd.DataFrame) -> pd.Series:
    """Baris dengan angka lengkap: PDRB >= 0 dan penduduk > 0 (d sudah numerik)."""
    return (
        d[COL_PDRB].notna() & d[COL_PENDUDUK].notna()
        & (d[COL_PDRB] >= 0) & (d[COL_PENDUDUK] > 0)
    )


def batasi_cakupan_konsisten(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sisakan wilayah yang memiliki data valid pada SETIAP tahun yang punya data valid.

    Mengembalikan (data terbatasi, tabel wilayah yang dikecualikan beserta tahun yang kosong).
    """
    kolom_hasil = ["Wilayah", "Tahun tanpa data valid"]
    d = to_numeric_frame(df)
    d["_id"] = kunci_wilayah(d)
    d["_label"] = label_wilayah_unik(d)
    valid = d[_data_valid_mask(d)]
    tahun_ada = sorted(valid[COL_TAHUN].dropna().astype(int).unique())
    if not tahun_ada:
        return df.iloc[0:0].copy(), pd.DataFrame(columns=kolom_hasil)

    ada = {t: set(valid.loc[valid[COL_TAHUN] == t, "_id"]) for t in tahun_ada}
    umum = set.intersection(*ada.values())
    semua = set(d["_id"])
    label = dict(zip(d["_id"], d["_label"]))

    dikecualikan = []
    for i in sorted(semua - umum, key=lambda x: label[x].lower()):
        kosong = [str(t) for t in tahun_ada if i not in ada[t]]
        dikecualikan.append({"Wilayah": label[i], "Tahun tanpa data valid": ", ".join(kosong)})
    hasil = df[d["_id"].isin(umum).to_numpy()].copy()
    return hasil, pd.DataFrame(dikecualikan, columns=kolom_hasil)


def terapkan_filter_rinci(
    df: pd.DataFrame, f: FilterData, opsi: dict | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Terapkan filter tanpa mengubah dataset asli.

    Mengembalikan (data terfilter, wilayah yang dikecualikan oleh aturan cakupan konsisten).
    Kriteria yang mencakup seluruh pilihan tidak menyaring apa pun, sehingga baris yang
    tahunnya tidak valid tetap ikut selama filter tahun tidak mempersempit.
    """
    opsi = opsi or opsi_filter(df)
    if f.tahun_awal is not None and f.tahun_akhir is not None and f.tahun_awal > f.tahun_akhir:
        raise ValueError("Tahun awal tidak boleh lebih besar daripada tahun akhir.")

    mask = pd.Series(True, index=df.index)
    tahun = opsi["tahun"]
    if (f.tahun_awal is not None and f.tahun_akhir is not None and tahun
            and (f.tahun_awal, f.tahun_akhir) != (tahun[0], tahun[-1])):
        angka = pd.to_numeric(df[COL_TAHUN], errors="coerce")
        mask &= angka.between(f.tahun_awal, f.tahun_akhir)
    if f.wilayah:
        mask &= normalisasi_nama(df[COL_WILAYAH]).str.lower().isin({w.lower() for w in f.wilayah})
    if f.provinsi and COL_PROVINSI in df.columns:
        mask &= normalisasi_nama(df[COL_PROVINSI]).str.lower().isin({p.lower() for p in f.provinsi})

    hasil = df[mask].copy()
    if f.konsisten and not hasil.empty:
        return batasi_cakupan_konsisten(hasil)
    return hasil, pd.DataFrame(columns=["Wilayah", "Tahun tanpa data valid"])


def terapkan_filter(df: pd.DataFrame, f: FilterData, opsi: dict | None = None) -> pd.DataFrame:
    """Data hasil filter (lihat terapkan_filter_rinci)."""
    return terapkan_filter_rinci(df, f, opsi)[0]


def _daftar_singkat(nilai: list[str], maks: int = 4) -> str:
    teks = ", ".join(nilai[:maks])
    return teks + (f" (+{len(nilai) - maks} lainnya)" if len(nilai) > maks else "")


def ringkasan_filter(
    f: FilterData, opsi: dict, n_hasil: int, n_total: int, n_dikecualikan: int = 0
) -> str:
    """Satu baris ringkasan filter aktif agar pengguna tahu cakupan datanya."""
    tahun = opsi["tahun"]
    if f.tahun_awal is None or not tahun:
        bagian_tahun = "Tahun: -"
    elif (f.tahun_awal, f.tahun_akhir) == (tahun[0], tahun[-1]):
        bagian_tahun = f"Tahun: semua ({tahun[0]}" + (f"–{tahun[-1]})" if len(tahun) > 1 else ")")
    elif f.tahun_awal == f.tahun_akhir:
        bagian_tahun = f"Tahun: {f.tahun_awal}"
    else:
        bagian_tahun = f"Tahun: {f.tahun_awal}–{f.tahun_akhir}"

    if f.wilayah:
        bagian_wilayah = f"Wilayah: {len(f.wilayah)} dari {len(opsi['wilayah'])} ({_daftar_singkat(list(f.wilayah))})"
    else:
        bagian_wilayah = f"Wilayah: semua ({len(opsi['wilayah'])})"

    bagian = [bagian_tahun, bagian_wilayah]
    if opsi["provinsi"]:
        bagian.append(
            f"Provinsi: {_daftar_singkat(list(f.provinsi))}" if f.provinsi
            else f"Provinsi: semua ({len(opsi['provinsi'])})"
        )
    if f.konsisten:
        bagian.append(
            "Cakupan konsisten: aktif"
            + (f" ({n_dikecualikan} wilayah dikecualikan)" if n_dikecualikan else "")
        )
    bagian.append(f"{n_hasil:,} dari {n_total:,} baris")
    return " · ".join(bagian)


def filter_aktif(f: FilterData, opsi: dict) -> bool:
    """True bila filter mempersempit data dibanding seluruh dataset."""
    tahun = opsi["tahun"]
    sempit_tahun = bool(tahun) and f.tahun_awal is not None and (f.tahun_awal, f.tahun_akhir) != (tahun[0], tahun[-1])
    return bool(sempit_tahun or f.wilayah or f.provinsi or f.konsisten)


_KUNCI_FILTER = "_ria_filter"
_PETA_FILTER = {
    "ria_f_tahun_awal": "tahun_awal", "ria_f_tahun_akhir": "tahun_akhir",
    "ria_f_wilayah": "wilayah", "ria_f_provinsi": "provinsi", "ria_f_konsisten": "konsisten",
}


def _simpan_filter(kunci_widget: str) -> None:
    """Callback on_change: catat pilihan terbaru ke penyimpanan terpisah.

    Pilihan disimpan di luar status widget karena Streamlit membuang status widget saat
    pindah halaman; dari penyimpanan inilah widget diisi ulang pada setiap run.
    """
    tersimpan = dict(st.session_state.get(_KUNCI_FILTER, {}))
    tersimpan[_PETA_FILTER[kunci_widget]] = st.session_state[kunci_widget]
    st.session_state[_KUNCI_FILTER] = tersimpan


def aktifkan_konsisten() -> None:
    """Callback tombol: aktifkan cakupan wilayah konsisten pada filter bersama."""
    st.session_state["ria_f_konsisten"] = True
    _simpan_filter("ria_f_konsisten")


def _setel_filter_awal(opsi: dict) -> None:
    """Callback tombol Reset: kembalikan seluruh data (tanpa filter apa pun)."""
    tahun = opsi["tahun"]
    st.session_state["ria_f_tahun_awal"] = tahun[0] if tahun else None
    st.session_state["ria_f_tahun_akhir"] = tahun[-1] if tahun else None
    st.session_state["ria_f_wilayah"] = []
    st.session_state["ria_f_provinsi"] = []
    st.session_state["ria_f_konsisten"] = False
    st.session_state[_KUNCI_FILTER] = {
        "tahun_awal": st.session_state["ria_f_tahun_awal"],
        "tahun_akhir": st.session_state["ria_f_tahun_akhir"],
        "wilayah": [], "provinsi": [], "konsisten": False,
    }


def _awali_widget_filter(opsi: dict) -> None:
    """Isi kunci widget dari pilihan tersimpan pada SETIAP run (bukan hanya bila kosong).

    Nilai yang sudah tidak ada pada dataset dibuang, sehingga filter tidak pernah merujuk
    wilayah/tahun yang hilang. Aman dipanggil di awal run karena perubahan pengguna sudah
    dicatat oleh callback on_change sebelum skrip dijalankan.
    """
    tahun = opsi["tahun"]
    tersimpan = st.session_state.get(_KUNCI_FILTER, {})

    awal = tersimpan.get("tahun_awal")
    akhir = tersimpan.get("tahun_akhir")
    if awal not in tahun:
        awal = tahun[0] if tahun else None
    if akhir not in tahun:
        akhir = tahun[-1] if tahun else None
    wilayah = [w for w in tersimpan.get("wilayah", []) if w in opsi["wilayah"]]
    provinsi = [p for p in tersimpan.get("provinsi", []) if p in opsi["provinsi"]]
    konsisten = bool(tersimpan.get("konsisten", False))

    st.session_state["ria_f_tahun_awal"] = awal
    st.session_state["ria_f_tahun_akhir"] = akhir
    st.session_state["ria_f_wilayah"] = wilayah
    st.session_state["ria_f_provinsi"] = provinsi
    st.session_state["ria_f_konsisten"] = konsisten
    st.session_state[_KUNCI_FILTER] = {
        "tahun_awal": awal, "tahun_akhir": akhir, "wilayah": wilayah,
        "provinsi": provinsi, "konsisten": konsisten,
    }


def tampilkan_filter(df: pd.DataFrame) -> tuple[FilterData, pd.DataFrame, dict]:
    """Panel filter bersama. Pilihan tersimpan sehingga sama di semua halaman.

    Mengembalikan (filter, data terfilter, info) dengan info berisi opsi, ringkasan, dan
    tabel wilayah yang dikecualikan. Jika hasilnya kosong, pesan ditampilkan di sini dan
    pemanggil sebaiknya berhenti (data kosong tidak pernah dianggap nol).
    """
    opsi = opsi_filter(df)
    tahun = opsi["tahun"]
    _awali_widget_filter(opsi)

    with st.container(border=True):
        st.markdown("**Filter Data**")
        if len(tahun) >= 1:
            kolom_tahun = st.columns(2)
            awal = kolom_tahun[0].selectbox(
                "Tahun awal", tahun, key="ria_f_tahun_awal",
                on_change=_simpan_filter, args=("ria_f_tahun_awal",),
            )
            akhir = kolom_tahun[1].selectbox(
                "Tahun akhir", tahun, key="ria_f_tahun_akhir",
                on_change=_simpan_filter, args=("ria_f_tahun_akhir",),
            )
        else:
            awal = akhir = None

        wilayah = st.multiselect(
            "Wilayah", opsi["wilayah"], key="ria_f_wilayah", placeholder="Semua wilayah",
            on_change=_simpan_filter, args=("ria_f_wilayah",),
        )
        provinsi = []
        if len(opsi["provinsi"]) >= 2:  # hanya bila dataset mencakup beberapa provinsi
            provinsi = st.multiselect(
                "Provinsi", opsi["provinsi"], key="ria_f_provinsi", placeholder="Semua provinsi",
                on_change=_simpan_filter, args=("ria_f_provinsi",),
            )
        konsisten = st.checkbox(
            "Cakupan wilayah konsisten (hanya wilayah dengan data valid di semua tahun terpilih)",
            key="ria_f_konsisten",
            help="Membuat indeks antartahun dihitung dari kumpulan wilayah yang sama.",
            on_change=_simpan_filter, args=("ria_f_konsisten",),
        )
        st.button("Reset filter", on_click=_setel_filter_awal, args=(opsi,))

    f = FilterData(awal, akhir, tuple(wilayah), tuple(provinsi), bool(konsisten))
    # Pilihan tidak valid: jelaskan, jangan diam-diam menukar atau mengabaikan.
    if awal is not None and akhir is not None and awal > akhir:
        st.error(
            f"**Rentang tahun tidak valid:** tahun awal ({awal}) lebih besar daripada tahun akhir "
            f"({akhir}). Ubah salah satunya agar tahun awal ≤ tahun akhir."
        )
        return f, df.iloc[0:0].copy(), {
            "opsi": opsi, "ringkasan": "rentang tahun tidak valid",
            "dikecualikan": pd.DataFrame(columns=["Wilayah", "Tahun tanpa data valid"]),
        }

    hasil, dikecualikan = terapkan_filter_rinci(df, f, opsi)
    ringkasan = ringkasan_filter(f, opsi, len(hasil), len(df), len(dikecualikan))
    st.caption("Filter aktif: " + ringkasan)

    if f.konsisten and not dikecualikan.empty:
        st.info(
            f"**Cakupan konsisten aktif:** {len(dikecualikan)} wilayah tidak dipakai karena datanya "
            f"tidak lengkap pada sebagian tahun ({_daftar_singkat(dikecualikan['Wilayah'].tolist())}). "
            "Matikan opsi di atas untuk memakai semua wilayah."
        )
        with st.expander("Rincian wilayah yang dikecualikan"):
            st.dataframe(dikecualikan, hide_index=True)
    if hasil.empty:
        st.warning(
            "**Tidak ada data yang sesuai dengan filter.** Ubah pilihan filter atau tekan "
            "Reset filter. Data kosong tidak dianggap bernilai nol."
        )

    return f, hasil, {"opsi": opsi, "ringkasan": ringkasan, "dikecualikan": dikecualikan}


# ======================================================================
# PERBANDINGAN ANTARWILAYAH
# ======================================================================

INDIKATOR_PERBANDINGAN = ["PDRB per kapita", "Jumlah penduduk", "PDRB (turunan)"]


def satuan_indikator(indikator: str, metadata: dict | None = None) -> str:
    """Satuan indikator. Satuan PDRB diambil dari catatan sumber bila sudah dicatat."""
    satuan_pdrb = (metadata or {}).get("satuan", "").strip() or "satuan mengikuti sumber (belum dicatat)"
    if indikator == "Jumlah penduduk":
        return "jiwa"
    if indikator == "PDRB (turunan)":
        return f"PDRB per kapita × jiwa; satuan PDRB per kapita: {satuan_pdrb}"
    return satuan_pdrb


def label_wilayah_unik(df: pd.DataFrame) -> pd.Series:
    """Label wilayah yang unik: nama kembar dengan identitas berbeda diberi provinsi/kode."""
    nama = normalisasi_nama(df[COL_WILAYAH])
    unik = pd.DataFrame({"n": nama.str.lower(), "k": kunci_wilayah(df)}).drop_duplicates("k")
    kembar = set(unik.loc[unik["n"].duplicated(keep=False), "n"])
    penanda = pd.Series("", index=df.index)
    for c in (COL_PROVINSI, COL_KODE):
        if c in df.columns:
            penanda = penanda.where(penanda != "", normalisasi_nama(df[c]))
    label = nama.copy()
    m = nama.str.lower().isin(kembar) & (penanda != "")
    label[m] = nama[m] + " (" + penanda[m] + ")"
    return label


def _nilai_indikator(d: pd.DataFrame, indikator: str) -> pd.Series:
    if indikator == "Jumlah penduduk":
        return d[COL_PENDUDUK].where(d[COL_PENDUDUK] > 0)
    if indikator == "PDRB (turunan)":
        return (d[COL_PDRB] * d[COL_PENDUDUK]).where((d[COL_PDRB] >= 0) & (d[COL_PENDUDUK] > 0))
    return d[COL_PDRB].where(d[COL_PDRB] >= 0)


def tabel_perbandingan(
    df: pd.DataFrame, tahun: int, indikator: str,
    urut: str = "nilai", satuan: str = "", wilayah_dipilih: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Bandingkan wilayah pada satu tahun.

    Cakupan = semua wilayah pada data yang diberikan (tahun apa pun) ditambah
    wilayah_dipilih. Wilayah tanpa nilai valid pada tahun itu TIDAK diberi nilai nol:
    nilainya kosong (NaN) dan keterangannya "Data tidak tersedia".
    Mengembalikan (tabel, catatan).
    """
    if indikator not in INDIKATOR_PERBANDINGAN:
        raise ValueError(f"Indikator tidak dikenal: {indikator}")

    d = to_numeric_frame(df)
    d["_id"] = kunci_wilayah(d)
    d["_label"] = label_wilayah_unik(d)
    cakupan = d.drop_duplicates("_id")[["_id", "_label"]].reset_index(drop=True)

    # Wilayah yang dipilih pengguna tetapi tidak punya baris sama sekali pada data ini.
    ada = set(cakupan["_label"].str.lower())
    tambahan = [w for w in (wilayah_dipilih or []) if w.lower() not in ada]
    if tambahan:
        cakupan = pd.concat(
            [cakupan, pd.DataFrame({"_id": [f"tambahan:{w.lower()}" for w in tambahan], "_label": tambahan})],
            ignore_index=True,
        )

    catatan = []
    th = d[d[COL_TAHUN] == tahun].copy()
    th["Nilai"] = _nilai_indikator(th, indikator)
    th = th[th["Nilai"].notna()]
    n_dup = int(th["_id"].duplicated().sum())
    if n_dup:
        th = th.drop_duplicates("_id")
        catatan.append(f"{n_dup} baris duplikat diabaikan (dipakai baris pertama). Rapikan di halaman Data Pendapatan.")

    hasil = cakupan.merge(th[["_id", "Nilai"]], on="_id", how="left")
    hasil = hasil.rename(columns={"_label": "Wilayah"}).drop(columns="_id")
    hasil["Tahun"] = tahun
    hasil["Indikator"] = indikator
    hasil["Satuan"] = satuan

    tersedia = hasil["Nilai"].notna()
    hasil["Peringkat"] = hasil["Nilai"].rank(ascending=False, method="min").astype("Int64")
    if tersedia.any():
        tertinggi, terendah = hasil["Nilai"].max(), hasil["Nilai"].min()
        hasil["Selisih dari tertinggi"] = hasil["Nilai"] - tertinggi
    else:
        tertinggi = terendah = None
        hasil["Selisih dari tertinggi"] = np.nan

    def keterangan(v):
        if pd.isna(v):
            return "Data tidak tersedia"
        if tertinggi == terendah:
            return ""
        return "Tertinggi" if v == tertinggi else "Terendah" if v == terendah else ""

    hasil["Keterangan"] = hasil["Nilai"].map(keterangan)

    if urut == "nama":
        hasil = hasil.sort_values("Wilayah", key=lambda x: x.str.lower(), kind="stable")
    else:
        hasil = hasil.sort_values(["Nilai", "Wilayah"], ascending=[False, True], na_position="last", kind="stable")

    kolom = ["Wilayah", "Tahun", "Indikator", "Nilai", "Satuan", "Peringkat", "Selisih dari tertinggi", "Keterangan"]
    return hasil[kolom].reset_index(drop=True), catatan


def narasi_perbandingan(tabel: pd.DataFrame, indikator: str) -> str:
    """Penjelasan deskriptif yang hanya memuat hal yang didukung angka pada tabel."""
    ada = tabel[tabel["Nilai"].notna()]
    tahun = int(tabel["Tahun"].iloc[0]) if len(tabel) else None
    if ada.empty:
        return f"Tidak ada wilayah dengan data {indikator} yang tersedia pada tahun {tahun}."
    tinggi, rendah = ada.loc[ada["Nilai"].idxmax()], ada.loc[ada["Nilai"].idxmin()]
    teks = f"Pada tahun {tahun}, {indikator} tertinggi di **{tinggi['Wilayah']}** ({tinggi['Nilai']:,.0f})"
    if len(ada) > 1 and tinggi["Nilai"] != rendah["Nilai"]:
        teks += f" dan terendah di **{rendah['Wilayah']}** ({rendah['Nilai']:,.0f}); selisihnya {tinggi['Nilai'] - rendah['Nilai']:,.0f}"
    teks += "."
    kosong = tabel.loc[tabel["Nilai"].isna(), "Wilayah"].tolist()
    if kosong:
        teks += f" Data tidak tersedia untuk: {_daftar_singkat(kosong, 6)}."
    return teks


def tabel_lintas_tahun(df: pd.DataFrame, indikator: str) -> pd.DataFrame:
    """Indikator per wilayah (baris) dan tahun (kolom). Sel tanpa data valid dibiarkan kosong."""
    d = to_numeric_frame(df)
    d["_id"] = kunci_wilayah(d)
    d["_label"] = label_wilayah_unik(d)
    d["Nilai"] = _nilai_indikator(d, indikator)
    d = d[d[COL_TAHUN].notna()]
    d[COL_TAHUN] = d[COL_TAHUN].astype(int)
    label = d.drop_duplicates("_id").set_index("_id")["_label"]
    pivot = d.drop_duplicates(["_id", COL_TAHUN]).pivot(index="_id", columns=COL_TAHUN, values="Nilai")
    pivot.index = pivot.index.map(label)
    pivot.index.name = "Wilayah"
    return pivot.sort_index(key=lambda x: x.str.lower())


# ======================================================================
# INDEKS WILLIAMSON ANTARPERIODE
# ======================================================================

KOLOM_ANTARPERIODE = [
    "Tahun", "Indeks Williamson", "Jumlah wilayah", "Kategori",
    "Perubahan", "Perubahan (%)", "Arah", "Catatan",
]


@dataclass
class HasilAntarperiode:
    tabel: pd.DataFrame            # satu baris per tahun
    perubahan_cakupan: pd.DataFrame  # wilayah yang bertambah/hilang antar tahun
    peringatan: list[str]

    def untuk_grafik(self) -> pd.DataFrame:
        """Tahun yang memiliki indeks (sumber yang sama dengan tabel)."""
        t = self.tabel.dropna(subset=["Indeks Williamson"])
        return t[["Tahun", "Indeks Williamson"]].reset_index(drop=True)


def hitung_antarperiode(df: pd.DataFrame) -> HasilAntarperiode:
    """Hitung Indeks Williamson terpisah untuk setiap tahun pada data yang diberikan.

    Memakai hitung_williamson (sumber hasil yang sama dengan halaman Analisis). Tahun
    dengan data tidak memadai ditandai dan tidak dipaksakan menghasilkan indeks.
    Perubahan dihitung terhadap tahun terdekat sebelumnya yang memiliki indeks; bila
    kumpulan wilayahnya berbeda, hal itu dicatat dan diberi peringatan.
    """
    d = to_numeric_frame(df)
    d["_id"] = kunci_wilayah(d)
    d["_label"] = label_wilayah_unik(d)
    label = dict(zip(d["_id"], d["_label"]))

    baris, cakupan, peringatan = [], [], []
    acuan = None  # (tahun, indeks, himpunan id) terakhir yang memiliki indeks
    tahun_sebelumnya = None

    for t in daftar_tahun(d):
        dt = d[d[COL_TAHUN] == t]
        ids = set(dt.loc[_data_valid_mask(dt), "_id"])
        hasil, galat = hitung_williamson(dt, t)
        catatan = []
        iw = np.nan

        if hasil is None:
            catatan.append("Data tidak memadai: " + galat.rstrip(".") if galat else "Data tidak memadai")
        else:
            iw = float(hasil.indeks)

        perubahan = pct = np.nan
        arah = "—"
        if hasil is not None and acuan is not None:
            t_ref, iw_ref, ids_ref = acuan
            perubahan = iw - iw_ref
            pct = perubahan / iw_ref * 100 if iw_ref != 0 else np.nan
            arah = "Relatif stabil" if abs(perubahan) < AMBANG_STABIL else ("Naik" if perubahan > 0 else "Turun")
            if tahun_sebelumnya is not None and t_ref != tahun_sebelumnya:
                catatan.append(f"Dibandingkan dengan {t_ref} (tahun {tahun_sebelumnya} tidak memiliki indeks)")
            elif t - t_ref > 1:
                catatan.append(f"Dibandingkan dengan {t_ref} (tidak ada data tahun di antaranya)")
            tambah, hilang = ids - ids_ref, ids_ref - ids
            if tambah or hilang:
                catatan.append(
                    f"Cakupan berbeda dari {t_ref}: +{len(tambah)} / −{len(hilang)} wilayah, "
                    "indeks tidak sepenuhnya sebanding"
                )
                cakupan.append({
                    "Tahun": t, "Dibanding": t_ref,
                    "Wilayah bertambah": ", ".join(sorted(label[i] for i in tambah)),
                    "Wilayah hilang": ", ".join(sorted(label[i] for i in hilang)),
                })
        if hasil is not None:
            acuan = (t, iw, ids)
        tahun_sebelumnya = t

        baris.append({
            "Tahun": t, "Indeks Williamson": iw, "Jumlah wilayah": len(ids),
            "Kategori": interpretasi(iw) if hasil is not None else "—",
            "Perubahan": perubahan, "Perubahan (%)": pct, "Arah": arah,
            "Catatan": "; ".join(catatan),
        })

    tabel = pd.DataFrame(baris, columns=KOLOM_ANTARPERIODE)
    if cakupan:
        peringatan.append(
            "Kumpulan wilayah berbeda antartahun, sehingga indeks tidak sepenuhnya sebanding. "
            "Aktifkan \"Cakupan wilayah konsisten\" pada filter untuk membandingkan wilayah yang sama."
        )
    if not tabel.empty and tabel["Indeks Williamson"].isna().any():
        tahun_kosong = tabel.loc[tabel["Indeks Williamson"].isna(), "Tahun"].tolist()
        peringatan.append("Indeks tidak dapat dihitung untuk tahun: " + ", ".join(map(str, tahun_kosong)) + " (data tidak memadai).")
    return HasilAntarperiode(
        tabel, pd.DataFrame(cakupan, columns=["Tahun", "Dibanding", "Wilayah bertambah", "Wilayah hilang"]), peringatan
    )


def narasi_antarperiode(tabel: pd.DataFrame) -> str:
    """Penjelasan deskriptif perkembangan indeks (tanpa menyimpulkan penyebab)."""
    ada = tabel.dropna(subset=["Indeks Williamson"])
    if len(ada) < 2:
        return "Perbandingan antarperiode memerlukan indeks pada minimal dua tahun."
    awal, akhir = ada.iloc[0], ada.iloc[-1]
    selisih = akhir["Indeks Williamson"] - awal["Indeks Williamson"]
    arah = "relatif stabil" if abs(selisih) < AMBANG_STABIL else ("naik" if selisih > 0 else "turun")
    teks = (
        f"Dari tahun {int(awal['Tahun'])} ({awal['Indeks Williamson']:.4f}) ke tahun {int(akhir['Tahun'])} "
        f"({akhir['Indeks Williamson']:.4f}), Indeks Williamson {arah}"
    )
    if arah != "relatif stabil":
        teks += f" sebesar {abs(selisih):.4f}"
    teks += "."
    if len(ada) > 2:
        tinggi, rendah = ada.loc[ada["Indeks Williamson"].idxmax()], ada.loc[ada["Indeks Williamson"].idxmin()]
        teks += (f" Nilai tertinggi pada tahun {int(tinggi['Tahun'])} ({tinggi['Indeks Williamson']:.4f}) "
                 f"dan terendah pada tahun {int(rendah['Tahun'])} ({rendah['Indeks Williamson']:.4f}).")
    return teks + " Perubahan indeks saja tidak menjelaskan penyebab perubahan disparitas."


# ======================================================================
# EKSPOR (CSV / Excel dengan metadata)
# ======================================================================

def nama_file_ekspor(df: pd.DataFrame, f: FilterData | None, ekstensi: str, awalan: str = "ria_data") -> str:
    """Nama berkas informatif, mis. ria_data_2023_2025.xlsx atau ria_data_2024_2wilayah.csv."""
    bagian = [awalan]
    tahun = daftar_tahun(df) if len(df) else []
    if tahun:
        bagian.append(str(tahun[0]) if tahun[0] == tahun[-1] else f"{tahun[0]}_{tahun[-1]}")
    if f is not None and f.wilayah:
        bagian.append(f"{len(f.wilayah)}wilayah")
    if f is not None and f.provinsi:
        bagian.append(f"{len(f.provinsi)}provinsi")
    return "_".join(bagian) + "." + ekstensi.lstrip(".")


def ringkasan_ekspor(
    df_ekspor: pd.DataFrame, n_dataset: int, f: FilterData | None, opsi: dict | None,
    metadata: dict | None = None, judul: str = "Data pendapatan regional",
    tahun_ekspor: list[int] | None = None,
) -> pd.DataFrame:
    """Tabel Keterangan/Nilai untuk lembar Metadata pada berkas Excel."""
    meta = metadata or {}
    opsi = opsi or {"tahun": [], "wilayah": [], "provinsi": []}
    belum = "belum dicatat"
    if tahun_ekspor is not None:
        tahun = sorted(tahun_ekspor)
    else:
        tahun = daftar_tahun(df_ekspor) if len(df_ekspor) and COL_TAHUN in df_ekspor.columns else []
    aktif = f is not None and filter_aktif(f, opsi)

    def isi(kunci):
        return str(meta.get(kunci, "")).strip() or belum

    baris = [
        ("Judul", judul),
        ("Aplikasi", "Regional Income Analysis (RIA)"),
        ("Tanggal ekspor", datetime.now().strftime("%d-%m-%Y %H:%M")),
        ("Cakupan unduhan", "Data sesuai filter" if aktif else "Seluruh dataset aktif"),
        ("Filter tahun", (f"{f.tahun_awal}–{f.tahun_akhir}" if f is not None and f.tahun_awal is not None else "semua")),
        ("Filter wilayah", (", ".join(f.wilayah) if f is not None and f.wilayah else "semua")),
        ("Filter provinsi", (", ".join(f.provinsi) if f is not None and f.provinsi else "semua")),
        ("Cakupan wilayah konsisten", "ya" if f is not None and f.konsisten else "tidak"),
        ("Periode data pada berkas", (f"{tahun[0]}–{tahun[-1]}" if len(tahun) > 1 else (str(tahun[0]) if tahun else "-"))),
        ("Jumlah baris pada berkas", len(df_ekspor)),
        ("Jumlah wilayah pada berkas", int(normalisasi_nama(df_ekspor[COL_WILAYAH]).str.lower().nunique()) if len(df_ekspor) and COL_WILAYAH in df_ekspor.columns else "-"),
        ("Jumlah baris dataset aktif", n_dataset),
        ("Sumber data", isi("sumber")),
        ("Tautan sumber", isi("tautan")),
        ("Tanggal pengambilan data", isi("tanggal_pengambilan")),
        ("Satuan PDRB per kapita", isi("satuan")),
        ("Satuan jumlah penduduk", "jiwa"),
        ("Catatan revisi", isi("catatan_revisi")),
        ("Berkas terakhir diimpor", isi("nama_berkas")),
        ("Catatan", "Nilai pada lembar Data tidak diubah dari dataset aktif; nama kolom dipertahankan."),
    ]
    return pd.DataFrame(baris, columns=["Keterangan", "Nilai"])


def ke_excel_dengan_metadata(
    df: pd.DataFrame, ringkasan: pd.DataFrame, nama_data: str = "Data", nama_meta: str = "Metadata"
) -> bytes:
    """Berkas Excel dua lembar: data (header tebal, baris judul dibekukan) dan metadata."""
    from openpyxl.styles import Font

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as penulis:
        df.to_excel(penulis, index=False, sheet_name=nama_data)
        ringkasan.to_excel(penulis, index=False, sheet_name=nama_meta)
        for nama, tabel in ((nama_data, df), (nama_meta, ringkasan)):
            ws = penulis.sheets[nama]
            ws.freeze_panes = "A2"
            for sel in ws[1]:
                sel.font = Font(bold=True)
            for i, kolom in enumerate(tabel.columns, start=1):
                panjang = max([len(str(kolom))] + [len(str(v)) for v in tabel[kolom].head(200)])
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(max(panjang + 2, 10), 60)
    return buf.getvalue()


# ======================================================================
# PILIHAN PERBANDINGAN (indikator & urutan) — tersimpan antarhalaman
# ======================================================================

URUTAN_PERBANDINGAN = {"Nilai (tertinggi dulu)": "nilai", "Nama wilayah (A–Z)": "nama"}
_KUNCI_PEMBANDING = "_ria_pembanding"


def _simpan_pembanding(kunci_widget: str, nama: str) -> None:
    tersimpan = dict(st.session_state.get(_KUNCI_PEMBANDING, {}))
    tersimpan[nama] = st.session_state[kunci_widget]
    st.session_state[_KUNCI_PEMBANDING] = tersimpan


def pilih_pembanding() -> tuple[str, str]:
    """Pilihan indikator dan urutan perbandingan; sama di halaman Analisis dan Visualisasi."""
    tersimpan = st.session_state.get(_KUNCI_PEMBANDING, {})
    indikator = tersimpan.get("indikator", INDIKATOR_PERBANDINGAN[0])
    if indikator not in INDIKATOR_PERBANDINGAN:
        indikator = INDIKATOR_PERBANDINGAN[0]
    urut = tersimpan.get("urut", list(URUTAN_PERBANDINGAN)[0])
    if urut not in URUTAN_PERBANDINGAN:
        urut = list(URUTAN_PERBANDINGAN)[0]
    st.session_state["ria_f_indikator"] = indikator
    st.session_state["ria_f_urut"] = urut
    st.session_state[_KUNCI_PEMBANDING] = {"indikator": indikator, "urut": urut}

    kolom = st.columns(2)
    indikator = kolom[0].selectbox(
        "Indikator", INDIKATOR_PERBANDINGAN, key="ria_f_indikator",
        on_change=_simpan_pembanding, args=("ria_f_indikator", "indikator"),
        help="PDRB (turunan) = PDRB per kapita × jumlah penduduk; bukan angka PDRB resmi dari sumber.",
    )
    label_urut = kolom[1].selectbox(
        "Urutan", list(URUTAN_PERBANDINGAN), key="ria_f_urut",
        on_change=_simpan_pembanding, args=("ria_f_urut", "urut"),
    )
    return indikator, URUTAN_PERBANDINGAN[label_urut]


# ======================================================================
# FORMAT TAMPILAN (dipakai halaman dan dokumen cetak agar angkanya sama)
# ======================================================================

def format_antarperiode(tabel: pd.DataFrame) -> pd.DataFrame:
    """Tabel antarperiode sebagai teks siap tampil. Nilai kosong tidak ditampilkan sebagai nol."""
    d = tabel.copy()
    d["Indeks Williamson"] = d["Indeks Williamson"].map(lambda v: "Tidak dihitung" if pd.isna(v) else f"{v:.4f}")
    d["Perubahan"] = d["Perubahan"].map(lambda v: "—" if pd.isna(v) else f"{v:+.4f}")
    d["Perubahan (%)"] = d["Perubahan (%)"].map(lambda v: "—" if pd.isna(v) else f"{v:+.2f}%")
    return d


def format_perbandingan(tabel: pd.DataFrame) -> pd.DataFrame:
    """Tabel perbandingan sebagai teks siap tampil; data kosong tertulis 'Data tidak tersedia'."""
    d = tabel.copy()
    d["Nilai"] = d["Nilai"].map(lambda v: "Data tidak tersedia" if pd.isna(v) else f"{v:,.0f}")
    d["Peringkat"] = d["Peringkat"].map(lambda v: "—" if pd.isna(v) else str(int(v)))
    d["Selisih dari tertinggi"] = d["Selisih dari tertinggi"].map(lambda v: "—" if pd.isna(v) else f"{v:,.0f}")
    return d.drop(columns=["Tahun", "Indikator"])


def format_lintas_tahun(pivot: pd.DataFrame) -> pd.DataFrame:
    """Tabel wilayah × tahun sebagai teks; sel tanpa data = 'Data tidak tersedia'."""
    d = pivot.copy()
    d.columns = [str(c) for c in d.columns]
    return d.apply(lambda kol: kol.map(lambda v: "Data tidak tersedia" if pd.isna(v) else f"{v:,.0f}"))
