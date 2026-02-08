import streamlit as st

st.set_page_config(page_title="Personal Finance Tracker", page_icon="💶", layout="wide")

st.title("💶 Personal Finance Tracker")
st.write("Navigate using the sidebar:")
st.markdown("""
- **Entry**: Add income / expense / debt + overall status  
- **Monthly Report**: Month-wise summary + transactions table  
- **Insights + Categories**: Graphs + add categories  
""")

st.info("EUR→BDT exchange rate is locked per transaction date (saved with each entry).")

from footer import footer

footer()
