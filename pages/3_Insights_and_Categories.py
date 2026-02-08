import streamlit as st
import pandas as pd
from utils import open_book, ws, read_df, normalize_transactions_df

st.set_page_config(page_title="Insights", page_icon="📈", layout="wide")
st.title("📈 Insights")

book = open_book()
tx_ws = ws(book, "Transactions")
cat_ws = ws(book, "Categories")

tx_df = normalize_transactions_df(read_df(tx_ws))
cat_df = read_df(cat_ws)

# -------------------------
# Helpers (no .dt)
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

def to_day(x):
    try:
        return x.date()
    except Exception:
        return None

def eur_bdt_text(eur: float, bdt: float) -> str:
    return f"€{eur:,.2f} (৳{bdt:,.0f})"

# -------------------------
# CATEGORY CREATION
# -------------------------
st.subheader("➕ Create Category")

existing = (
    set(cat_df["category_name"].dropna().astype(str).str.strip().tolist())
    if not cat_df.empty and "category_name" in cat_df.columns
    else set()
)

with st.form("cat_form"):
    new_cat = str(st.text_input("Category name") or "")
    cat_type_any = st.selectbox("Type", ["Expense", "Income", "Debt", "Debt Payment", "Other"])
    cat_type = str(cat_type_any)
    add = st.form_submit_button("Add Category")

if add:
    name = new_cat.strip()
    if not name:
        st.error("Category name cannot be empty.")
    elif name in existing:
        st.warning("Category already exists.")
    else:
        cat_ws.append_row([str(name), str(cat_type)])
        st.success("Category added ✅")
        st.rerun()

st.divider()

# -------------------------
# GRAPHS
# -------------------------
if tx_df.empty:
    st.warning("No transactions yet. Add entries first.")
    st.stop()

tx_df["month"] = tx_df["date"].apply(to_month_str)

currency_view_any = st.radio("Charts currency", ["EUR", "BDT"], horizontal=True)
currency_view = str(currency_view_any)
value_col = "amount_eur" if currency_view == "EUR" else "amount_bdt"

# 1) Income vs Expense by month
st.subheader(f"📊 Income vs Expense by Month ({currency_view})")

monthly = tx_df.pivot_table(
    index="month",
    columns="type",
    values=value_col,
    aggfunc="sum",
    fill_value=0.0
).sort_index()

for col in ["Income", "Expense"]:
    if col not in monthly.columns:
        monthly[col] = 0.0

st.bar_chart(monthly[["Income", "Expense"]])

# 2) Expense by category for selected month
st.subheader(f"🏷️ Expense by Category (Selected Month) ({currency_view})")

months_raw = sorted([m for m in tx_df["month"].unique().tolist() if m], reverse=True)
if not months_raw:
    st.info("No valid dates found.")
    st.stop()

# Show pretty labels (February 2026), but keep raw YYYY-MM for filtering
month_map = {month_label(m): m for m in months_raw}
month_labels = list(month_map.keys())

sel_label_any = st.selectbox("Month for category analysis", month_labels, index=0)
sel_label = str(sel_label_any)
sel_month = month_map[sel_label]

m_exp = tx_df[(tx_df["month"] == sel_month) & (tx_df["type"] == "Expense")].copy()
by_cat = m_exp.groupby("category")[value_col].sum().sort_values(ascending=False)

if by_cat.empty:
    st.info("No expense data for that month.")
else:
    st.bar_chart(by_cat)

# 3) Cumulative savings trend
st.subheader(f"📈 Cumulative Savings Trend ({currency_view})")

daily = tx_df.copy()
daily["day"] = daily["date"].apply(to_day)
daily = daily[daily["day"].notna()].copy()

# Vectorized (faster than apply(axis=1))
daily["income"] = daily[value_col].where(daily["type"] == "Income", 0.0)
daily["expense"] = daily[value_col].where(daily["type"] == "Expense", 0.0)

daily_sum = daily.groupby("day")[["income", "expense"]].sum().sort_index()
daily_sum["net"] = daily_sum["income"] - daily_sum["expense"]
daily_sum["cumulative_savings"] = daily_sum["net"].cumsum()

st.line_chart(daily_sum["cumulative_savings"])

# 4) Debt tracking – Remaining debt
st.subheader(f"📉 Debt Tracking – Remaining Debt Over Time ({currency_view})")

debt_df = tx_df[tx_df["type"].isin(["Debt", "Debt Payment"])].copy()
debt_df["day"] = debt_df["date"].apply(to_day)
debt_df = debt_df[debt_df["day"].notna()].copy()

if debt_df.empty:
    st.info("No debt entries yet.")
else:
    # Vectorized signed amount
    debt_df["signed_amount"] = debt_df[value_col].where(
        debt_df["type"] == "Debt",
        -debt_df[value_col]
    )
    remaining = debt_df.groupby("day")["signed_amount"].sum().sort_index().cumsum()
    st.line_chart(remaining)

# 5) Monthly debt added vs paid
st.subheader(f"📊 Monthly Debt Added vs Paid ({currency_view})")

md = tx_df[tx_df["type"].isin(["Debt", "Debt Payment"])].copy()
md["month"] = md["date"].apply(to_month_str)
md = md[md["month"].astype(bool)].copy()

if md.empty:
    st.info("No debt entries yet.")
else:
    md_sum = md.pivot_table(
        index="month",
        columns="type",
        values=value_col,
        aggfunc="sum",
        fill_value=0.0
    ).sort_index()

    for col in ["Debt", "Debt Payment"]:
        if col not in md_sum.columns:
            md_sum[col] = 0.0

    st.bar_chart(md_sum[["Debt", "Debt Payment"]])

from footer import footer
footer()
