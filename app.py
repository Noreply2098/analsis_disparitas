"""Regional Income Analysis (RIA) — entry point aplikasi Streamlit.

Jalankan dengan:  streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Regional Income Analysis",
    page_icon="📊",
    layout="wide",
)

st.html(
    """
    <style>
    /* Teks metrik tidak boleh terpotong (...) - biarkan turun ke baris berikutnya */
    [data-testid="stMetricLabel"] *,
    [data-testid="stMetricValue"] * {
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        overflow-wrap: anywhere;
    }
    [data-testid="stMetricValue"] { line-height: 1.25; }

    /* Tampilan layar kecil (HP) */
    @media (max-width: 640px) {
        .block-container {
            padding: 3.5rem 0.9rem 4rem 0.9rem !important;
        }
        h1 { font-size: 1.7rem !important; line-height: 1.25 !important; }
        h2, h3 { font-size: 1.3rem !important; line-height: 1.3 !important; }
        [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
        [data-testid="stVerticalBlockBorderWrapper"] { padding: 0.25rem; }
        .stButton > button, .stDownloadButton > button {
            width: 100%;
            min-height: 2.75rem;
        }
    }
    </style>
    """
)

halaman = st.navigation(
    {
        "MENU UTAMA": [
            st.Page("views/dashboard.py", title="Dashboard",
                    icon=":material/dashboard:", default=True),
            st.Page("views/import_data.py", title="Import Data BPS",
                    icon=":material/upload_file:", url_path="import-data"),
            st.Page("views/data_pendapatan.py", title="Data Pendapatan",
                    icon=":material/table_chart:", url_path="data-pendapatan"),
            st.Page("views/analisis.py", title="Analisis Disparitas",
                    icon=":material/calculate:", url_path="analisis"),
            st.Page("views/visualisasi.py", title="Visualisasi",
                    icon=":material/bar_chart:", url_path="visualisasi"),
            st.Page("views/tentang.py", title="Tentang Aplikasi",
                    icon=":material/info:", url_path="tentang"),
        ]
    }
)

with st.sidebar:
    st.caption("Academic Research Project · Version 1.0")

halaman.run()
