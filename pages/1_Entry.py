import streamlit as st
from datetime import date, datetime
from typing import Any

from utils import (
    open_book, ws, read_df, ensure_headers,
    TX_HEADERS, CAT_HEADERS, RATE_HEADERS,
    get_rate_for_date, get_or_create_category_sheet_defaults,
    normalize_transactions_df, make_tx_id,
    invalidate_all_data_caches,
)

st.set_page_config(page_title="Entry", page_icon="📝", layout="wide")

st.title("📝 Transactions Entry")


# -------------------------
# Open + ensure base sheets
# -------------------------
book = open_book()

ensure_headers(ws(book, "Transactions"), TX_HEADERS)
ensure_headers(ws(book, "Categories"), CAT_HEADERS)
ensure_headers(ws(book, "Rates"), RATE_HEADERS)

get_or_create_category_sheet_defaults(book)

# -------------------------
# Helpers
# -------------------------
def _coerce_single_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, tuple) and value and isinstance(value[0], date):
        return value[0]
    return date.today()

# -------------------------
# Load data (cached reads via utils.read_df)
# -------------------------
tx_df = normalize_transactions_df(read_df(ws(book, "Transactions")))
cat_df = read_df(ws(book, "Categories"))

# -------------------------
# Currency display selector
# -------------------------
currency_view_any = st.radio(
    "Display currency",
    ["EUR only", "EUR (BDT)", "BDT only"],
    horizontal=True
)
currency_view: str = str(currency_view_any)

def fmt_money(eur: float, bdt: float) -> str:
    if currency_view == "EUR (BDT)":
        return f"€{eur:,.2f} (৳{bdt:,.0f})"
    if currency_view == "EUR only":
        return f"€{eur:,.2f}"
    return f"৳{bdt:,.0f}"

# -------------------------
# TOP STATUS
# -------------------------
if tx_df.empty:
    income_eur = expense_eur = debt_eur = 0.0
    income_bdt = expense_bdt = debt_bdt = 0.0
else:
    income_eur = float(tx_df.loc[tx_df["type"] == "Income", "amount_eur"].sum())
    expense_eur = float(tx_df.loc[tx_df["type"] == "Expense", "amount_eur"].sum())
    debt_add_eur = float(tx_df.loc[tx_df["type"] == "Debt", "amount_eur"].sum())
    debt_pay_eur = float(tx_df.loc[tx_df["type"] == "Debt Payment", "amount_eur"].sum())
    debt_eur = debt_add_eur - debt_pay_eur

    income_bdt = float(tx_df.loc[tx_df["type"] == "Income", "amount_bdt"].sum())
    expense_bdt = float(tx_df.loc[tx_df["type"] == "Expense", "amount_bdt"].sum())
    debt_add_bdt = float(tx_df.loc[tx_df["type"] == "Debt", "amount_bdt"].sum())
    debt_pay_bdt = float(tx_df.loc[tx_df["type"] == "Debt Payment", "amount_bdt"].sum())
    debt_bdt = debt_add_bdt - debt_pay_bdt

savings_eur = income_eur - expense_eur
savings_bdt = income_bdt - expense_bdt

c1, c2, c3 = st.columns(3)
c1.metric("Total Income", fmt_money(income_eur, income_bdt))
c2.metric("Savings", fmt_money(savings_eur, savings_bdt))
c3.metric("Debt Status", fmt_money(debt_eur, debt_bdt))

st.divider()

# -------------------------
# Options
# -------------------------
types = ["Income", "Expense", "Debt", "Debt Payment", "Other"]
categories = (
    sorted(cat_df["category_name"].dropna().astype(str).unique().tolist())
    if not cat_df.empty and "category_name" in cat_df.columns
    else ["General"]
)

default_type = types[0]
default_category = categories[0] if categories else "General"

# -------------------------
# Session defaults
# -------------------------
st.session_state.setdefault("entry_type", default_type)
st.session_state.setdefault("entry_category", default_category)
st.session_state.setdefault("entry_date", date.today())
st.session_state.setdefault("entry_remarks", "")
st.session_state.setdefault("entry_amount_eur", 0.0)
st.session_state.setdefault("_reset_entry_form", False)

# -------------------------
# Reset block (MUST be before widgets)
# -------------------------
if st.session_state.get("_reset_entry_form", False):
    st.session_state["_reset_entry_form"] = False
    st.session_state["entry_type"] = default_type
    st.session_state["entry_category"] = default_category
    st.session_state["entry_date"] = date.today()
    st.session_state["entry_remarks"] = ""
    st.session_state["entry_amount_eur"] = 0.0

# -------------------------
# Entry UI (match picture: Type | Category | Date in one row)
# -------------------------
col_type, col_cat, col_date = st.columns(3)

with col_type:
    entry_type = st.selectbox("Type", types, key="entry_type")

with col_cat:
    category = st.selectbox("Category", categories, key="entry_category")

with col_date:
    entry_date_val = st.date_input("Date", key="entry_date")
    entry_date = _coerce_single_date(entry_date_val)

# Remarks full width (below)
remarks = st.text_input("Remarks", key="entry_remarks")

# Amounts in 2 columns (below)
col_eur, col_bdt = st.columns(2)

with col_eur:
    amount_eur = float(
        st.number_input("Amount (EUR)", min_value=0.0, step=10.0, key="entry_amount_eur")
    )

# -------------------------
# Instant rate lookup + conversion
# -------------------------
rate: float | None = None
amount_bdt: float = 0.0

try:
    rate = float(get_rate_for_date(book, entry_date))
    amount_bdt = float(amount_eur * rate)
    st.info(f"Today's Euro to BDT exchange rate : {rate:.4f}")
except Exception as e:
    rate = None
    amount_bdt = 0.0
    st.error("Failed to fetch exchange rate")
    st.code(str(e))

with col_bdt:
    st.text_input("Amount (BDT)", value=f"{amount_bdt:,.2f}", disabled=True)

# -------------------------
# Save Button
# -------------------------
save_disabled = (rate is None) or (amount_eur <= 0)

if st.button("✅ Save Entry", disabled=save_disabled):
    if rate is None:
        st.error("Cannot save entry without exchange rate.")
        st.stop()

    tx_ws = ws(book, "Transactions")
    now = datetime.now().isoformat(timespec="seconds")

    tx_ws.append_row([
        str(make_tx_id()),
        str(entry_date.isoformat()),
        str(entry_type),
        str(category),
        str(remarks or ""),
        float(amount_eur),
        float(rate),
        float(amount_bdt),
        str(now),
    ])

    invalidate_all_data_caches()

    st.success("Entry saved successfully ✅")

    st.session_state["_reset_entry_form"] = True
    st.rerun()


from footer import footer

footer()
