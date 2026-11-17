"""Tema visual NEON futuristik untuk seluruh aplikasi.

Hanya mengubah tampilan (CSS). Tidak ada fitur, data, maupun teks aplikasi yang berubah.
Dipanggil sekali dari app.py lewat ``tema.terapkan()``.
"""

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Exo+2:wght@400;500;600;700&display=swap');

:root {
    --n-cyan: #00f0ff;
    --n-magenta: #ff2bd6;
    --n-violet: #9d4dff;
    --n-lime: #b6ff00;
    --n-yellow: #ffe600;
    --n-bg: #07021a;
    --n-panel: rgba(20, 6, 56, 0.72);
    --n-teks: #eae6ff;
    --n-pudar: #a79bd6;
    --n-judul: 'Orbitron', 'Segoe UI', sans-serif;
    --n-badan: 'Exo 2', 'Segoe UI', Roboto, Arial, sans-serif;
}

/* ---------- Latar: gradasi + lantai grid neon + garis pindai ---------- */
.stApp {
    background:
        radial-gradient(1200px 600px at 12% -10%, rgba(255, 43, 214, 0.28), transparent 60%),
        radial-gradient(1000px 600px at 95% 0%, rgba(0, 240, 255, 0.22), transparent 60%),
        radial-gradient(900px 700px at 50% 120%, rgba(157, 77, 255, 0.30), transparent 60%),
        var(--n-bg) !important;
    font-family: var(--n-badan);
}
.stApp::before {
    content: "";
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-image:
        linear-gradient(rgba(0, 240, 255, 0.07) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 43, 214, 0.07) 1px, transparent 1px);
    background-size: 44px 44px;
    animation: n-grid 9s linear infinite;
}
.stApp::after {
    content: "";
    position: fixed; inset: 0; z-index: 9999; pointer-events: none;
    background: repeating-linear-gradient(
        to bottom, rgba(255, 255, 255, 0.025) 0, rgba(255, 255, 255, 0.025) 1px,
        transparent 1px, transparent 3px);
    mix-blend-mode: overlay;
}
@keyframes n-grid { from { background-position: 0 0, 0 0; } to { background-position: 0 44px, 44px 0; } }
@keyframes n-warna { from { filter: hue-rotate(0deg); } to { filter: hue-rotate(360deg); } }
@keyframes n-denyut {
    0%, 100% { box-shadow: 0 0 10px rgba(0, 240, 255, .45), 0 0 24px rgba(255, 43, 214, .25); }
    50%      { box-shadow: 0 0 18px rgba(0, 240, 255, .85), 0 0 40px rgba(255, 43, 214, .55); }
}
@keyframes n-kilau { from { background-position: 0% 50%; } to { background-position: 200% 50%; } }

[data-testid="stHeader"] { background: transparent !important; }
.block-container { position: relative; z-index: 1; }

/* ---------- Judul ---------- */
h1, h2, h3, h4,
[data-testid="stHeading"] {
    font-family: var(--n-judul) !important;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
h1 {
    background: linear-gradient(90deg, var(--n-cyan), var(--n-magenta), var(--n-yellow), var(--n-cyan));
    background-size: 200% 100%;
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent !important;
    animation: n-kilau 6s linear infinite;
    filter: drop-shadow(0 0 10px rgba(0, 240, 255, .65)) drop-shadow(0 0 22px rgba(255, 43, 214, .45));
    font-weight: 900 !important;
}
h2, h3 {
    color: var(--n-cyan) !important;
    text-shadow: 0 0 6px rgba(0, 240, 255, .9), 0 0 18px rgba(0, 240, 255, .5);
}
h4 { color: var(--n-magenta) !important; text-shadow: 0 0 8px rgba(255, 43, 214, .8); }

/* garis neon di bawah subjudul */
[data-testid="stHeading"] h2, [data-testid="stHeading"] h3 {
    border-bottom: 1px solid rgba(0, 240, 255, .35);
    padding-bottom: .3rem;
    box-shadow: 0 6px 12px -10px var(--n-cyan);
}

[data-testid="stCaptionContainer"], .stCaption, small { color: var(--n-pudar) !important; }
a { color: var(--n-cyan) !important; text-shadow: 0 0 6px rgba(0, 240, 255, .55); }
a:hover { color: var(--n-magenta) !important; text-shadow: 0 0 10px rgba(255, 43, 214, .9); }
hr { border-color: rgba(255, 43, 214, .5) !important; box-shadow: 0 0 8px rgba(255, 43, 214, .6); }
strong, b { color: #ffffff; text-shadow: 0 0 6px rgba(157, 77, 255, .8); }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(255, 43, 214, .18), transparent 30%),
        linear-gradient(0deg, rgba(0, 240, 255, .16), transparent 30%),
        #0b0328 !important;
    border-right: 2px solid transparent;
    border-image: linear-gradient(180deg, var(--n-cyan), var(--n-magenta), var(--n-violet)) 1;
    box-shadow: 6px 0 28px rgba(255, 43, 214, .35);
}
[data-testid="stSidebarNav"] a, [data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] {
    border: 1px solid transparent;
    border-radius: 10px;
    font-family: var(--n-judul);
    font-size: .78rem;
    letter-spacing: .05em;
    text-transform: uppercase;
    transition: all .2s ease;
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover {
    border-color: var(--n-cyan);
    background: rgba(0, 240, 255, .12) !important;
    box-shadow: 0 0 14px rgba(0, 240, 255, .6);
    transform: translateX(4px);
}
[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] {
    border-color: var(--n-magenta);
    background: linear-gradient(90deg, rgba(255, 43, 214, .35), rgba(0, 240, 255, .18)) !important;
    box-shadow: 0 0 18px rgba(255, 43, 214, .75), inset 0 0 12px rgba(255, 43, 214, .35);
    color: #fff !important;
}
[data-testid="stSidebarNavSeparator"],
[data-testid="stSidebar"] [data-testid="stNavSectionHeader"],
[data-testid="stSidebarNav"] span[class*="Header"] {
    font-family: var(--n-judul);
    color: var(--n-yellow) !important;
    text-shadow: 0 0 8px rgba(255, 230, 0, .7);
    letter-spacing: .2em;
}

/* ---------- Tombol ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
[data-testid="stPageLink"] a {
    font-family: var(--n-judul);
    font-size: .78rem;
    letter-spacing: .08em;
    text-transform: uppercase;
    background: rgba(7, 2, 26, .8) !important;
    color: var(--n-cyan) !important;
    border: 1px solid var(--n-cyan) !important;
    border-radius: 10px;
    box-shadow: 0 0 10px rgba(0, 240, 255, .5), inset 0 0 8px rgba(0, 240, 255, .2);
    text-shadow: 0 0 6px rgba(0, 240, 255, .9);
    transition: all .18s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover,
[data-testid="stPageLink"] a:hover {
    background: rgba(0, 240, 255, .18) !important;
    color: #fff !important;
    box-shadow: 0 0 22px rgba(0, 240, 255, .95), 0 0 44px rgba(0, 240, 255, .4);
    transform: translateY(-2px) scale(1.02);
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
    background: linear-gradient(90deg, var(--n-magenta), var(--n-violet), var(--n-cyan)) !important;
    background-size: 200% 100% !important;
    color: #fff !important;
    border: 1px solid #fff !important;
    text-shadow: 0 0 8px rgba(0, 0, 0, .8);
    animation: n-denyut 2.4s ease-in-out infinite, n-kilau 5s linear infinite;
}
.stButton > button:active, .stFormSubmitButton > button:active { transform: scale(.97); }

/* ---------- Input ---------- */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
[data-testid="stNumberInput"] [data-baseweb="input"] {
    background: rgba(7, 2, 26, .85) !important;
    border: 1px solid rgba(157, 77, 255, .7) !important;
    border-radius: 10px !important;
    box-shadow: inset 0 0 10px rgba(157, 77, 255, .25);
    transition: all .2s ease;
}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {
    border-color: var(--n-cyan) !important;
    box-shadow: 0 0 14px rgba(0, 240, 255, .85), inset 0 0 10px rgba(0, 240, 255, .25);
}
input, textarea { color: var(--n-teks) !important; font-family: var(--n-badan) !important; }
label, [data-testid="stWidgetLabel"] p {
    color: var(--n-pudar) !important;
    font-weight: 600;
    letter-spacing: .03em;
}
[data-testid="stFileUploaderDropzone"] {
    background: rgba(20, 6, 56, .6) !important;
    border: 2px dashed var(--n-magenta) !important;
    border-radius: 14px;
    box-shadow: 0 0 16px rgba(255, 43, 214, .45), inset 0 0 16px rgba(255, 43, 214, .15);
}

/* ---------- Kartu / kontainer ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: rgba(0, 240, 255, .45) !important;
    border-radius: 14px !important;
}
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(255, 43, 214, .16), rgba(0, 240, 255, .12));
    border: 1px solid rgba(0, 240, 255, .6);
    border-radius: 14px;
    padding: .9rem 1rem;
    box-shadow: 0 0 16px rgba(0, 240, 255, .35), inset 0 0 18px rgba(157, 77, 255, .2);
}
[data-testid="stMetricLabel"] { color: var(--n-pudar) !important; text-transform: uppercase; letter-spacing: .08em; }
[data-testid="stMetricValue"] {
    font-family: var(--n-judul);
    color: var(--n-lime) !important;
    text-shadow: 0 0 8px rgba(182, 255, 0, .9), 0 0 22px rgba(182, 255, 0, .5);
}

[data-testid="stExpander"] {
    background: var(--n-panel);
    border: 1px solid rgba(255, 43, 214, .6) !important;
    border-radius: 14px !important;
    box-shadow: 0 0 14px rgba(255, 43, 214, .3);
}
[data-testid="stExpander"] summary { font-family: var(--n-judul); font-size: .82rem; letter-spacing: .05em; }

/* ---------- Tab ---------- */
[data-baseweb="tab-list"] { gap: .4rem; border-bottom: 1px solid rgba(157, 77, 255, .5); }
button[data-baseweb="tab"] {
    font-family: var(--n-judul);
    font-size: .78rem;
    letter-spacing: .06em;
    text-transform: uppercase;
    color: var(--n-pudar);
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--n-cyan) !important;
    text-shadow: 0 0 10px rgba(0, 240, 255, .95);
}
[data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg, var(--n-cyan), var(--n-magenta)) !important;
    height: 3px !important;
    box-shadow: 0 0 12px var(--n-cyan), 0 0 24px var(--n-magenta);
}

/* ---------- Tabel, grafik, kode ---------- */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border: 1px solid rgba(0, 240, 255, .55);
    border-radius: 12px;
    box-shadow: 0 0 16px rgba(0, 240, 255, .3);
    overflow: hidden;
}
[data-testid="stArrowVegaLiteChart"], [data-testid="stVegaLiteChart"] {
    background: rgba(12, 3, 36, .55);
    border: 1px solid rgba(157, 77, 255, .5);
    border-radius: 14px;
    padding: .6rem;
    box-shadow: 0 0 18px rgba(157, 77, 255, .35);
}
[data-testid="stCode"], pre, code {
    background: rgba(5, 1, 20, .9) !important;
    color: var(--n-lime) !important;
    border-radius: 8px;
}
[data-testid="stCode"] { border: 1px solid rgba(182, 255, 0, .5); box-shadow: 0 0 12px rgba(182, 255, 0, .25); }

/* ---------- Notifikasi ---------- */
[data-testid="stAlert"] {
    border: 1px solid rgba(0, 240, 255, .55);
    border-radius: 12px;
    box-shadow: 0 0 14px rgba(0, 240, 255, .3);
    backdrop-filter: blur(4px);
}
[data-testid="stToast"] { border: 1px solid var(--n-magenta); box-shadow: 0 0 20px rgba(255, 43, 214, .8); }

/* ---------- Pilihan (radio / checkbox) ---------- */
[data-baseweb="checkbox"] span, [data-baseweb="radio"] > div:first-child { box-shadow: 0 0 8px rgba(255, 43, 214, .7); }
[data-testid="stSpinner"] i, [data-testid="stSpinner"] svg { filter: drop-shadow(0 0 8px var(--n-cyan)); }

/* ---------- Bilah gulir ---------- */
::-webkit-scrollbar { width: 11px; height: 11px; }
::-webkit-scrollbar-track { background: #07021a; }
::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, var(--n-cyan), var(--n-magenta));
    border-radius: 8px; box-shadow: 0 0 8px var(--n-cyan);
}
::selection { background: var(--n-magenta); color: #fff; }

/* Hormati pengguna yang mematikan animasi */
@media (prefers-reduced-motion: reduce) {
    .stApp::before, h1, button[kind="primary"],
    button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
        animation: none !important;
    }
}
</style>
"""


def terapkan() -> None:
    """Pasang tema neon ke halaman yang sedang dirender."""
    st.html(CSS)
