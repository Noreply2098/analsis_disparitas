"""Dokumen cetak (laporan) dan tombol cetak untuk halaman Analisis dan Visualisasi.

Dokumen cetak dibuat sebagai HTML mandiri (grafik berupa SVG) lalu dibuka di
jendela baru dan dicetak oleh browser. Dengan begitu hasil cetak tidak
bergantung pada tampilan layar Streamlit (sidebar, area gulir, dsb.)."""

import html
import json
import re
import streamlit as st
import vl_convert as vlc

from utils import (
    COL_PDRB,
    COL_PENDUDUK,
    COL_TAHUN,
    COL_WILAYAH,
    DATASET_PATH,
    FilterData,
    baca_metadata,
    beri_label_unik,
    format_antarperiode,
    format_perbandingan,
    hitung_antarperiode,
    keterangan_batas_kategori,
    load_dataset,
    narasi_antarperiode,
    narasi_perbandingan,
    narasi_ringkasan,
    opsi_filter,
    ringkasan_filter,
    satuan_indikator,
    susun_analisis,
    tabel_perbandingan,
    terapkan_filter,
    terapkan_filter_rinci,
    to_numeric_frame,
)
from charts import (
    grafik_perbandingan,
    BIRU,
    BIRU_TUA,
    grafik_batang,
    grafik_indikator,
    grafik_selisih,
    grafik_tren,
)

NAMA_APLIKASI = "Regional Income Analysis (RIA)"
PENGEMBANG = "Kelompok 2"

# ==============================
# UTILITAS HTML
# ==============================

def _e(teks) -> str:
    return html.escape(str(teks))


def _angka_besar(nilai: float) -> str:
    """Angka biasa bila di bawah 1 miliar, selain itu notasi ilmiah agar muat di tabel cetak."""
    return f"{nilai:,.0f}" if abs(nilai) < 1e9 else f"{nilai:.3e}"


def _tebal(teks: str) -> str:
    """Escape HTML lalu ubah **teks** menjadi <strong>teks</strong>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _e(teks))


def _svg(chart, lebar: int) -> str:
    spec = chart.properties(width=lebar).to_json()
    svg = vlc.vegalite_to_svg(spec)
    return svg[svg.index("<svg"):]


def _gambar(chart, lebar: int, judul: str | None = None, ket: str | None = None) -> str:
    kepala = f"<h3>{_e(judul)}</h3>" if judul else ""
    catatan = f'<figcaption>{_e(ket)}</figcaption>' if ket else ""
    return f'<figure class="gambar">{kepala}{_svg(chart, lebar)}{catatan}</figure>'


CSS = """
@page { size: A4; margin: 12mm 12mm 16mm 12mm; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html { background: #e9eef5; }
body { margin: 0; font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
       color: #26364a; font-size: 10.5pt; line-height: 1.45; }
.toolbar { position: sticky; top: 0; z-index: 10; display: flex; gap: 8px; flex-wrap: wrap;
           align-items: center; justify-content: space-between; background: #173b65;
           color: #fff; padding: 10px 16px; }
.toolbar button { border: 0; border-radius: 6px; padding: 8px 16px; font-size: 14px;
                  cursor: pointer; background: #2874B8; color: #fff; font-weight: 600; }
.toolbar button.sekunder { background: rgba(255,255,255,.15); }
.toolbar span { font-size: 13px; opacity: .9; }
.halaman { max-width: 210mm; margin: 16px auto; background: #fff; padding: 12mm;
           box-shadow: 0 2px 12px rgba(0,0,0,.15); }
.kop { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px;
       border-bottom: 3px solid #2874B8; padding-bottom: 8px; margin-bottom: 14px; }
.kop .judul { font-size: 17pt; font-weight: 700; color: #173b65; line-height: 1.2; }
.kop .sub { font-size: 10pt; color: #5b6b7f; margin-top: 2px; }
.kop .tgl { font-size: 9pt; color: #5b6b7f; text-align: right; white-space: nowrap; }
h1.bagian { font-size: 13pt; color: #fff; background: #173b65; padding: 6px 12px;
            border-radius: 4px; margin: 18px 0 10px; break-after: avoid; }
h2 { font-size: 12.5pt; color: #173b65; margin: 16px 0 8px; padding-left: 8px;
     border-left: 4px solid #2874B8; break-after: avoid; }
h3 { font-size: 10.5pt; margin: 0 0 4px; color: #26364a; break-after: avoid; }
p { margin: 6px 0; }
.ket, figcaption { font-size: 8.5pt; color: #5b6b7f; margin-top: 4px; }
.hasil { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 6px; }
.hasil .angka { font-size: 30pt; font-weight: 700; color: #173b65; line-height: 1; }
.hasil .delta { font-size: 9.5pt; color: #5b6b7f; }
.status { padding: 6px 12px; border-radius: 6px; font-weight: 600; font-size: 10.5pt; }
.status-rendah { background: #dff0e6; color: #1e6b3f; }
.status-sedang { background: #fbf0cf; color: #8a6200; }
.status-tinggi { background: #f8dcdc; color: #a12b2b; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.sel { border: 1px solid #d5deea; border-radius: 6px; padding: 6px 10px; break-inside: avoid; }
.sel .l { font-size: 8.5pt; color: #5b6b7f; }
.sel .v { font-size: 12.5pt; font-weight: 700; color: #173b65; overflow-wrap: anywhere; }
.sel .s { font-size: 8.5pt; color: #5b6b7f; }
figure.gambar { margin: 8px 0 12px; break-inside: avoid; text-align: center; }
figure.gambar h3 { text-align: left; }
figure.gambar svg { max-width: 100%; height: auto; }
figure.gambar figcaption { text-align: left; }
table { width: 100%; border-collapse: collapse; font-size: 7.4pt; }
th, td { border: 1px solid #cfd8e4; padding: 3px 4px; text-align: right; white-space: nowrap; }
td.t, th.t { white-space: normal; min-width: 70px; }
th { white-space: normal; }
th { background: #eaf1f9; color: #173b65; font-weight: 700; text-align: center; }
td.t, th.t { text-align: left; }
thead { display: table-header-group; }
tfoot { display: table-row-group; }
tfoot td { font-weight: 700; background: #f4f7fb; }
tr { break-inside: avoid; }
ol.langkah { padding-left: 18px; margin: 6px 0; }
ol.langkah li { margin-bottom: 7px; break-inside: avoid; }
ol.langkah .hasilnya { color: #173b65; font-weight: 700; }
.rumus { background: #f4f7fb; border: 1px solid #d5deea; border-radius: 6px;
         padding: 8px 12px; margin: 6px 0; font-size: 10pt; }
.catatan { background: #fbf0cf; border: 1px solid #ecd48a; border-radius: 6px; padding: 8px 12px; }
.footer { margin-top: 18px; padding-top: 6px; border-top: 1px solid #d5deea;
          font-size: 8pt; color: #7b8896; text-align: center; }
@media print {
  html { background: #fff; }
  .toolbar { display: none; }
  .halaman { margin: 0; padding: 0; box-shadow: none; max-width: none; }
}
"""


def _dokumen(judul: str, subjudul: str, isi: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8"><title>{_e(judul)}</title>
<style>{CSS}</style></head><body>
<div class="toolbar"><span>Pratinjau cetak — pilih "Simpan sebagai PDF" di dialog cetak bila ingin berkas PDF.</span>
<div><button id="btn-cetak">Cetak</button> <button id="btn-tutup" class="sekunder">Tutup</button></div></div>
<main class="halaman">
<header class="kop"><div><div class="judul">{_e(judul)}</div><div class="sub">{_e(subjudul)}</div></div>
<div class="tgl">Dicetak: {{{{TANGGAL}}}}</div></header>
{isi}
<footer class="footer">{_e(NAMA_APLIKASI)} · Dikembangkan oleh {_e(PENGEMBANG)}</footer>
</main></body></html>"""


# ==============================
# BAGIAN: ANALISIS
# ==============================

def bagian_analisis(df, tahun: int) -> str:
    a, pesan = susun_analisis(df, tahun)
    if a is None:
        return (
            f'<h2>Analisis Indeks Williamson Tahun {tahun}</h2>'
            f'<p class="catatan">Analisis tidak tersedia: {_e(pesan)}</p>'
        )

    h, d = a.hasil, a.detail
    kelas = {"Ketimpangan rendah": "rendah", "Ketimpangan sedang": "sedang"}.get(
        a.kategori, "tinggi"
    )

    delta = ""
    if a.sebelumnya:
        selisih = h.indeks - a.sebelumnya[1]
        panah = "▲ naik" if selisih > 0 else "▼ turun" if selisih < 0 else "● tetap"
        delta = (
            f'<span class="delta">{panah} {abs(selisih):.4f} '
            f'dibanding tahun {a.sebelumnya[0]}</span>'
        )

    # ---- hasil utama ----
    out = [
        f"<h2>Hasil Analisis Indeks Williamson — Tahun {tahun}</h2>",
        '<div class="hasil">',
        f'<div class="angka">{h.indeks:.4f}</div>',
        f'<div class="status status-{kelas}">{_e(a.kategori)} pada tahun {tahun}</div>',
        delta,
        "</div>",
        f'<p class="ket">{_e(keterangan_batas_kategori())} Semakin besar nilai indeks, '
        "semakin timpang PDRB per kapita antarwilayah.</p>",
        f"<p>{_tebal(narasi_ringkasan(a))}</p>",
    ]

    # ---- ringkasan perhitungan ----
    def sel(label, nilai, sub=""):
        sub_html = f'<div class="s">{_e(sub)}</div>' if sub else ""
        return f'<div class="sel"><div class="l">{_e(label)}</div><div class="v">{_e(nilai)}</div>{sub_html}</div>'

    out += [
        "<h2>Ringkasan Perhitungan</h2>",
        '<div class="grid">',
        sel("Tahun Pengamatan", tahun),
        sel("Jumlah Wilayah", a.jumlah_wilayah),
        sel("Total Penduduk", f"{h.total_penduduk:,.0f}"),
        sel("Rata-rata PDRB Per Kapita", f"{h.rata_rata:,.2f}", "dibobot jumlah penduduk"),
        sel("PDRB Tertinggi", f"{a.tertinggi[COL_PDRB]:,.0f}", a.tertinggi[COL_WILAYAH]),
        sel("PDRB Terendah", f"{a.terendah[COL_PDRB]:,.0f}", a.terendah[COL_WILAYAH]),
        sel("Selisih Tertinggi–Terendah", f"{a.tertinggi[COL_PDRB] - a.terendah[COL_PDRB]:,.0f}"),
        sel("Rasio Tertinggi/Terendah", f"{a.rasio:.2f}×" if a.rasio else "—"),
        "</div>",
    ]

    # ---- perkembangan indeks antarperiode ----
    ap = hitung_antarperiode(df)
    if len(ap.tabel) > 1:
        out.append("<h2>Perkembangan Indeks Williamson Antarperiode</h2>")
        out.append(f"<p>{_tebal(narasi_antarperiode(ap.tabel))}</p>")
        for w in ap.peringatan:
            out.append(f'<p class="catatan">{_e(w)}</p>')
        tampil = format_antarperiode(ap.tabel)
        kolom_ap = ["Tahun", "Indeks Williamson", "Jumlah wilayah", "Kategori", "Perubahan", "Perubahan (%)", "Arah", "Catatan"]
        out.append("<table><thead><tr>" + "".join(f"<th>{_e(k)}</th>" for k in kolom_ap) + "</tr></thead><tbody>")
        for _, r in tampil.iterrows():
            out.append("<tr>" + "".join(
                f'<td class="t">{_e(r[k])}</td>' if k in ("Kategori", "Arah", "Catatan") else f"<td>{_e(r[k])}</td>"
                for k in kolom_ap) + "</tr>")
        out.append("</tbody></table>")
        out.append(
            f'<p class="ket">{_e(keterangan_batas_kategori())} Perubahan dihitung terhadap tahun terdekat '
            f"sebelumnya yang memiliki indeks; perubahan di bawah ambang 0,005 disebut relatif stabil "
            f"(ketetapan aplikasi).</p>"
        )

    # ---- tabel rincian ----
    baris = []
    for i, (_, r) in enumerate(d.iterrows(), start=1):
        baris.append(
            "<tr>"
            f"<td>{i}</td>"
            f'<td class="t">{_e(r[COL_WILAYAH])}</td>'
            f"<td>{r[COL_PDRB]:,.2f}</td>"
            f"<td>{r[COL_PENDUDUK]:,.0f}</td>"
            f"<td>{r['Proporsi Penduduk']:.2%}</td>"
            f"<td>{r['Selisih']:+,.2f}</td>"
            f"<td>{_angka_besar(r['Selisih Kuadrat'])}</td>"
            f"<td>{_angka_besar(r['Kontribusi'])}</td>"
            f"<td>{r['Porsi Kontribusi']:.2%}</td>"
            "</tr>"
        )
    out += [
        "<h2>Rincian Perhitungan</h2>",
        "<table><thead><tr><th>No.</th><th class='t'>Nama Wilayah</th><th>PDRB Per Kapita</th>"
        "<th>Jumlah Penduduk</th><th>Proporsi Penduduk</th><th>Selisih</th>"
        "<th>Selisih Kuadrat</th><th>Kontribusi</th><th>Porsi Kontribusi</th>"
        "</tr></thead><tbody>",
        "".join(baris),
        "</tbody><tfoot><tr><td></td><td class='t'>Total</td><td></td>"
        f"<td>{d[COL_PENDUDUK].sum():,.0f}</td><td>{d['Proporsi Penduduk'].sum():.2%}</td>"
        f"<td></td><td></td><td>{_angka_besar(a.total_kontribusi)}</td>"
        f"<td>{d['Porsi Kontribusi'].sum():.2%}</td></tr></tfoot></table>",
        '<p class="ket">Tanda selisih (+/−) menunjukkan posisi di atas/di bawah rata-rata PDRB per '
        "kapita. Selisih kuadrat dan kontribusi ditampilkan tanpa desimal; nilai di atas 1 miliar "
        "ditulis dalam notasi ilmiah (mis. 3.107e+15).</p>",
    ]

    # ---- langkah perhitungan ----
    akar = a.total_kontribusi ** 0.5
    out += [
        "<h2>Langkah Perhitungan</h2>",
        '<div class="rumus">IW = √[ Σ (Yᵢ − Ȳ)² × (fᵢ / N) ] / Ȳ</div>',
        '<ol class="langkah">',
        f'<li>Total penduduk (N) = Σ fᵢ = <span class="hasilnya">{h.total_penduduk:,.0f}</span></li>',
        "<li>Rata-rata PDRB per kapita dibobot penduduk (Ȳ) = Σ (Yᵢ × fᵢ) / N = "
        f'<span class="hasilnya">{h.rata_rata:,.2f}</span></li>',
        "<li>Jumlah kontribusi seluruh wilayah = Σ (Yᵢ − Ȳ)² × (fᵢ / N) = "
        f'<span class="hasilnya">{a.total_kontribusi:,.2f}</span></li>',
        f'<li>Akar dari jumlah kontribusi = √ {a.total_kontribusi:,.2f} = '
        f'<span class="hasilnya">{akar:,.2f}</span></li>',
        f'<li>Indeks Williamson = {akar:,.2f} / {h.rata_rata:,.2f} = '
        f'<span class="hasilnya">{h.indeks:.4f}</span></li>',
        "</ol>",
    ]
    return "\n".join(out)


# ==============================
# BAGIAN: GRAFIK
# ==============================

def bagian_grafik(
    df, tahun: int, indikator: str = "PDRB per kapita", urut: str = "nilai",
    metadata: dict | None = None, wilayah_dipilih: list[str] | None = None,
) -> str:
    a, _ = susun_analisis(df, tahun)
    out = []

    # ---- perbandingan antarwilayah (indikator terpilih) ----
    satuan = satuan_indikator(indikator, metadata)
    tabel_p, catatan = tabel_perbandingan(df, tahun, indikator, urut, satuan, wilayah_dipilih)
    if tabel_p["Nilai"].notna().any():
        rata = a.hasil.rata_rata if (a and indikator == "PDRB per kapita") else None
        ket = f"Satuan: {satuan}. Label disingkat: rb = ribu, jt = juta, M = miliar."
        if rata is not None:
            ket += f" Garis putus-putus oranye: rata-rata PDRB per kapita dibobot penduduk ({rata:,.2f})."
        kosong = tabel_p.loc[tabel_p["Nilai"].isna(), "Wilayah"].tolist()
        if kosong:
            ket += " Data tidak tersedia (tidak digambar): " + ", ".join(kosong) + "."
        ket += " " + " ".join(catatan)
        out.append(_gambar(
            grafik_perbandingan(tabel_p, indikator, urut, rata_rata=rata, langkah=38),
            500, f"Perbandingan {indikator} Antarwilayah Tahun {tahun}", ket.strip(),
        ))

    if a:
        out.append(_gambar(
            grafik_selisih(a.detail, langkah=38), 480,
            f"Posisi Terhadap Rata-rata Tahun {tahun}",
            f"Selisih PDRB per kapita setiap wilayah terhadap rata-rata ({a.hasil.rata_rata:,.2f}).",
        ))
        out.append(_gambar(
            grafik_batang(a.detail, "Porsi Kontribusi", "Porsi Kontribusi", BIRU_TUA,
                          label_fn=lambda v: f"{v:.1%}", format_tooltip=".2%", langkah=38),
            500, f"Kontribusi Terhadap Ketimpangan Tahun {tahun}",
            "Porsi tiap wilayah terhadap total ketimpangan "
            "(proporsi penduduk × selisih kuadrat terhadap rata-rata).",
        ))
        out.append(_gambar(
            grafik_indikator(a.hasil.indeks), 650,
            f"Posisi Indeks Williamson Tahun {tahun}", f"{a.kategori}. {keterangan_batas_kategori()}",
        ))

    ap = hitung_antarperiode(df)
    tren = ap.untuk_grafik()
    if not tren.empty:
        ket_tren = keterangan_batas_kategori() + " Pita warna menunjukkan kategori ketimpangan."
        ket_tren += " " + " ".join(ap.peringatan)
        out.append(_gambar(grafik_tren(tren), 600, "Perkembangan Indeks Williamson Antarperiode", ket_tren.strip()))

    if not out:
        return '<p class="catatan">Tidak ada data valid untuk ditampilkan.</p>'
    return f"<h2>Visualisasi Data Tahun {tahun}</h2>" + "\n".join(out)


# ==============================
# DOKUMEN SIAP CETAK (di-cache)
# ==============================

def _versi_data() -> int:
    return DATASET_PATH.stat().st_mtime_ns if DATASET_PATH.exists() else 0


@st.cache_data(show_spinner="Menyiapkan dokumen cetak...", max_entries=20)
def _bagian(
    tahun: int, versi_data: int, kunci_filter: tuple, indikator: str, urut: str
) -> tuple[str, str, str]:
    """Bagian analisis dan grafik dari data yang SUDAH difilter, plus ringkasan filternya."""
    df, _ = load_dataset()
    awal, akhir, wilayah, provinsi, konsisten = kunci_filter
    f = FilterData(awal, akhir, wilayah, provinsi, konsisten)
    opsi = opsi_filter(df)
    df_f, dikecualikan = terapkan_filter_rinci(df, f, opsi)
    ringkasan = ringkasan_filter(f, opsi, len(df_f), len(df), len(dikecualikan))
    meta = baca_metadata()
    return (
        bagian_analisis(df_f, tahun),
        bagian_grafik(df_f, tahun, indikator, urut, meta, list(wilayah)),
        ringkasan,
    )


def dokumen_cetak(
    tahun: int, f: FilterData, indikator: str = "PDRB per kapita", urut: str = "nilai"
) -> dict[str, str]:
    """Tiga jenis dokumen cetak untuk satu tahun dan satu filter: analisis, grafik, lengkap."""
    analisis, grafik, ringkasan = _bagian(tahun, _versi_data(), f.kunci(), indikator, urut)
    sub = f"{NAMA_APLIKASI} · Indeks Williamson · Tahun {tahun}"
    cakupan = f'<p class="ket"><strong>Cakupan data (filter):</strong> {_e(ringkasan)}</p>'
    return {
        "analisis": _dokumen("Laporan Analisis Disparitas Pendapatan Regional", sub, cakupan + analisis),
        "grafik": _dokumen("Laporan Visualisasi Data Pendapatan Regional", sub, cakupan + grafik),
        "lengkap": _dokumen(
            "Laporan Analisis dan Visualisasi Pendapatan Regional", sub,
            cakupan + '<h1 class="bagian">Bagian 1 — Analisis</h1>' + analisis
            + '<h1 class="bagian">Bagian 2 — Grafik</h1>' + grafik,
        ),
    }


# ==============================
# TOMBOL CETAK
# ==============================

_TEMPLATE_TOMBOL = """
<style>
  html, body { margin: 0; background: transparent; }
  button { width: 100%; height: 42px; border-radius: 8px; cursor: pointer;
           font: 600 15px "Source Sans Pro", "Segoe UI", Roboto, Arial, sans-serif;
           border: 1px solid __BORDER__; background: __BG__; color: __FG__; }
  button:hover { filter: brightness(0.96); }
</style>
<button id="b" type="button">__LABEL__</button>
<script>
  const DOK = __DATA__;
  document.getElementById('b').addEventListener('click', function () {
    const w = window.open('', '_blank');
    if (!w) { alert('Pop-up diblokir browser. Izinkan pop-up untuk situs ini, lalu coba lagi.'); return; }
    const tgl = new Date().toLocaleDateString('id-ID', {day: 'numeric', month: 'long', year: 'numeric'});
    w.document.open();
    w.document.write(DOK.split('{{TANGGAL}}').join(tgl));
    w.document.close();
    const cetak = w.document.getElementById('btn-cetak');
    const tutup = w.document.getElementById('btn-tutup');
    if (cetak) cetak.addEventListener('click', function () { w.print(); });
    if (tutup) tutup.addEventListener('click', function () { w.close(); });
    setTimeout(function () { w.focus(); w.print(); }, 700);
  });
</script>
"""


def tombol_cetak(label: str, dokumen_html: str, utama: bool = False) -> None:
    """Tombol yang membuka dokumen cetak di jendela baru dan memanggil dialog cetak."""
    data = json.dumps(dokumen_html).replace("</", "<\\/")
    gaya = (
        ("#2874B8", "#2874B8", "#ffffff") if utama else ("rgba(49,51,63,0.25)", "#ffffff", "#26364a")
    )
    isi = (
        _TEMPLATE_TOMBOL
        .replace("__BORDER__", gaya[0]).replace("__BG__", gaya[1]).replace("__FG__", gaya[2])
        .replace("__LABEL__", html.escape(label)).replace("__DATA__", data)
    )
    isi = isi.strip()
    if hasattr(st, "iframe"):
        st.iframe(isi, height=46)  # Streamlit terbaru
    else:  # Streamlit versi lama (st.iframe belum tersedia)
        import streamlit.components.v1 as components
        components.html(isi, height=46)


def blok_cetak(
    tahun: int, bagian: str, f: FilterData, indikator: str = "PDRB per kapita", urut: str = "nilai"
) -> None:
    """Tampilkan dua tombol cetak: satu bagian (analisis/grafik) dan gabungan.

    bagian: "analisis" atau "grafik".
    """
    dok = dokumen_cetak(tahun, f, indikator, urut)
    nama = "Analisis" if bagian == "analisis" else "Grafik"

    kol = st.columns(2)
    with kol[0]:
        tombol_cetak(f"🖨️ Cetak {nama}", dok[bagian])
    with kol[1]:
        tombol_cetak("🖨️ Cetak Analisis + Grafik", dok["lengkap"], utama=True)
    st.caption(
        f"Dokumen cetak mengikuti filter data yang sedang aktif dan dibuat untuk tahun {tahun}. "
        f"Di dialog cetak, pilih \"Simpan sebagai PDF\" jika ingin berkas PDF."
    )
