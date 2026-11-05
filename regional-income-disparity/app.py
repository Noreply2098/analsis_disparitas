"""Regional Income Analysis (RIA) — entry point aplikasi Streamlit.

Jalankan dengan:  streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Regional Income Analysis",
    page_icon="📊",
    layout="wide",
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
