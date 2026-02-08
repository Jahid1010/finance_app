import streamlit as st

def footer():
    st.markdown(
        """
        <style>
        .pf-footer-fixed {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            padding: 8px 0;
            text-align: center;
            font-size: 12px;
            color: rgba(255,255,255,0.65);
            background: rgba(18,18,18,0.55);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-top: 1px solid rgba(255,255,255,0.08);
            z-index: 9999;
        }

        /* prevent overlap */
        .block-container { padding-bottom: 3rem; }
        </style>

        <div class="pf-footer-fixed">
            © 2026 • Personal Finance Tracker • Made by <b>Md Jahid Hassan</b>
        </div>
        """,
        unsafe_allow_html=True
    )
