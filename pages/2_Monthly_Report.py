import streamlit as st
import pandas as pd
from utils import open_book, ws, read_df, normalize_transactions_df

st.set_page_config(page_title="Monthly Report", page_icon="📅", layout="wide")
st.title("📅 Monthly Report")

book = open_book()
tx_df = normalize_transactions_df(read_df(ws(book, "Transactions")))

if tx_df.empty:
    st.warning("No transactions yet.")
    st.stop()

# -------------------------
# Helpers
# -------------------------
def to_month_str(x) -> str:
    try:
        return x.strftime("%Y-%m")
    except Exception:
        return ""

def month_label(ym: str) -> str:
    """Convert YYYY-MM -> February 2026"""
    try:
        return pd.to_datetime(ym, format="%Y-%m").strftime("%B %Y")
    except Exception:
        return ym

def to_date_str(x) -> str:
    try:
        return x.strftime("%d %b %Y")  # 07 Feb 2026
    except Exception:
        return ""

def eur_bdt_text(eur: float, bdt: float) -> str:
    return f"€ {eur:,.2f} (৳ {bdt:,.0f})"

def fmt(eur: float, bdt: float, currency_view: str) -> str:
    if currency_view == "EUR (BDT)":
        return eur_bdt_text(eur, bdt)
    if currency_view == "EUR only":
        return f"€ {eur:,.2f}"
    return f"৳ {bdt:,.0f}"

# -------------------------
# Month selection
# -------------------------
tx_df["month"] = tx_df["date"].apply(to_month_str)
months_raw = sorted([m for m in tx_df["month"].unique().tolist() if m], reverse=True)

if not months_raw:
    st.warning("No valid month found (check your dates).")
    st.stop()

month_map = {month_label(m): m for m in months_raw}
month_labels = list(month_map.keys())

# ✅ Cast to str to satisfy Pylance (radio returns str|None in typing)
currency_view_any = st.radio(
    "Display currency",
    ["EUR only","EUR (BDT)","BDT only"],
    horizontal=True
)
currency_view: str = str(currency_view_any)

selected_label_any = st.selectbox("Select Month", month_labels, index=0)
selected_label: str = str(selected_label_any)

sel_month: str = month_map[selected_label]
m = tx_df[tx_df["month"] == sel_month].copy().sort_values("date", ascending=False)

# -------------------------
# Summary
# -------------------------
income_eur = float(m.loc[m["type"] == "Income", "amount_eur"].sum())
expense_eur = float(m.loc[m["type"] == "Expense", "amount_eur"].sum())
debt_add_eur = float(m.loc[m["type"] == "Debt", "amount_eur"].sum())
debt_pay_eur = float(m.loc[m["type"] == "Debt Payment", "amount_eur"].sum())

income_bdt = float(m.loc[m["type"] == "Income", "amount_bdt"].sum())
expense_bdt = float(m.loc[m["type"] == "Expense", "amount_bdt"].sum())
debt_add_bdt = float(m.loc[m["type"] == "Debt", "amount_bdt"].sum())
debt_pay_bdt = float(m.loc[m["type"] == "Debt Payment", "amount_bdt"].sum())

net_eur = income_eur - expense_eur
net_bdt = income_bdt - expense_bdt
debt_net_eur = debt_add_eur - debt_pay_eur
debt_net_bdt = debt_add_bdt - debt_pay_bdt

st.subheader("Summary")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Income", fmt(income_eur, income_bdt, currency_view))
c2.metric("Expense", fmt(expense_eur, expense_bdt, currency_view))
c3.metric("Net Savings", fmt(net_eur, net_bdt, currency_view))
c4.metric("Debt Net (Taken − Paid)", fmt(debt_net_eur, debt_net_bdt, currency_view))

# -------------------------
# Transactions Table (Professional)
# -------------------------
st.subheader("Transactions")

table = pd.DataFrame({
    "Date": m["date"].apply(to_date_str),
    "Type": m["type"],
    "Category": m["category"],
    "Remarks": m["remarks"],
    "Amount (EUR)": m["amount_eur"].map(lambda x: f"€{x:,.2f}"),
    "Rate (EUR → BDT)": m["rate_eur_bdt"].map(lambda x: f"{x:,.4f}"),
    "Amount (BDT)": m["amount_bdt"].map(lambda x: f"৳{x:,.2f}")
})

if currency_view == "EUR only":
    table = table.drop(columns=["Amount (BDT)"])
elif currency_view == "BDT only":
    table = table.drop(columns=["Amount (EUR)", "Rate (EUR → BDT)"])

st.dataframe(
    table,
    width="stretch",
    hide_index=True
)

# -------------------------
# Export
# -------------------------
safe_label = selected_label.replace(" ", "_")

st.download_button(
    "⬇️ Download this month as CSV",
    data=table.to_csv(index=False).encode("utf-8"),
    file_name=f"transactions_{safe_label}.csv",
    mime="text/csv"
)


from footer import footer


footer()
