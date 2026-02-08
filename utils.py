import streamlit as st
import gspread
import pandas as pd
import requests
from google.oauth2.service_account import Credentials
from datetime import date
from typing import Any

# ----------------------------
# Google API scopes
# ----------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ----------------------------
# Sheet headers
# ----------------------------
TX_HEADERS = [
    "id", "date", "type", "category", "remarks",
    "amount_eur", "rate_eur_bdt", "amount_bdt", "created_at"
]
CAT_HEADERS = ["category_name", "type"]
RATE_HEADERS = ["date", "eur_bdt_rate"]


# ----------------------------
# Google Sheets client / book (CACHED)
# ----------------------------
@st.cache_resource
def get_gs_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)

@st.cache_resource
def open_book():
    """
    Cached spreadsheet handle to avoid repeated metadata reads.
    """
    client = get_gs_client()
    return client.open_by_key(st.secrets["sheet_id"])

@st.cache_resource
def ws(_book, name: str):
    """
    Cache worksheet object.
    NOTE: _book is prefixed with '_' so Streamlit doesn't try to hash it.
    """
    return _book.worksheet(name)


# ----------------------------
# Cache helpers (call after writes)
# ----------------------------
def invalidate_all_data_caches():
    """
    Call this after any append_row / update / clear so reads refresh immediately.
    """
    st.cache_data.clear()


# ----------------------------
# Helpers
# ----------------------------
def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


@st.cache_data(ttl=120)
def _read_header_row(_sheet_id: str, ws_title: str) -> list[str]:
    """
    Cache header row to reduce repeated row_values(1) calls.
    """
    book = open_book()
    w = book.worksheet(ws_title)
    return w.row_values(1)


def ensure_headers(worksheet, headers):
    """
    Ensure row1 matches headers exactly.
    If not, clear and write headers.
    """
    try:
        existing = _read_header_row(open_book().id, worksheet.title)
    except Exception:
        existing = worksheet.row_values(1)

    if existing != headers:
        worksheet.clear()
        worksheet.append_row(headers)
        invalidate_all_data_caches()


# ----------------------------
# Cached sheet reads
# ----------------------------
@st.cache_data(ttl=15)
def read_df_cached(_sheet_id: str, worksheet_title: str) -> pd.DataFrame:
    """
    Read sheet as DataFrame with TTL caching.
    Uses get_all_values (often fewer API calls than get_all_records).
    """
    book = open_book()
    w = book.worksheet(worksheet_title)

    values = w.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame()

    headers = values[0]
    rows = values[1:]
    return pd.DataFrame(rows, columns=headers)


def read_df(worksheet) -> pd.DataFrame:
    """
    Keep old signature for convenience; route to cached read.
    """
    book = open_book()
    return read_df_cached(book.id, worksheet.title)


# ----------------------------
# FX rate fetch (robust)
# ----------------------------
def _fetch_eur_to_bdt_rate_frankfurter(d: date) -> float:
    """
    Provider 1: Frankfurter (historical)
    """
    d_str = d.isoformat()
    url = f"https://api.frankfurter.app/{d_str}"
    resp = requests.get(url, params={"from": "EUR", "to": "BDT"}, timeout=25)

    if resp.status_code != 200:
        raise RuntimeError(f"Frankfurter HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    rates = data.get("rates")
    if not isinstance(rates, dict) or "BDT" not in rates:
        raise RuntimeError(f"Frankfurter missing BDT: {data}")

    rate = safe_float(rates["BDT"], 0.0)
    if rate <= 0:
        raise RuntimeError(f"Frankfurter invalid rate: {data}")

    return float(rate)


def _fetch_eur_to_bdt_rate_erapi(d: date) -> float:
    """
    Provider 2: fallback only for today's rate.
    """
    if d != date.today():
        raise RuntimeError("open.er-api.com fallback supports only today's rate")

    url = "https://open.er-api.com/v6/latest/EUR"
    resp = requests.get(url, timeout=25)

    if resp.status_code != 200:
        raise RuntimeError(f"ER-API HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    rates = data.get("rates")
    if not isinstance(rates, dict) or "BDT" not in rates:
        raise RuntimeError(f"ER-API missing BDT: {data}")

    rate = safe_float(rates["BDT"], 0.0)
    if rate <= 0:
        raise RuntimeError(f"ER-API invalid rate: {data}")

    return float(rate)


def _fetch_eur_to_bdt_rate(d: date) -> float:
    errors = []
    try:
        return _fetch_eur_to_bdt_rate_frankfurter(d)
    except Exception as e:
        errors.append(f"Frankfurter failed: {e}")

    try:
        return _fetch_eur_to_bdt_rate_erapi(d)
    except Exception as e:
        errors.append(f"ER-API failed: {e}")

    raise RuntimeError("All FX providers failed.\n" + "\n".join(errors))


# ----------------------------
# Rates: optimized lookup
# ----------------------------
@st.cache_data(ttl=300)
def _get_rate_from_sheet_cached(_sheet_id: str, d_str: str) -> float | None:
    """
    Find date in Rates!A:A and read rate from column B.
    Cached for 5 minutes.
    """
    book = open_book()
    rates_ws = book.worksheet("Rates")

    try:
        cell = rates_ws.find(d_str, in_column=1)
        if not cell:
            return None

        rate_val = rates_ws.cell(cell.row, 2).value
        rate = safe_float(rate_val, 0.0)
        return float(rate) if rate > 0 else None
    except Exception:
        return None


def get_rate_for_date(book, d: date) -> float:
    """
    Date-locked EUR->BDT rate:
    - If exists in Rates sheet for that date, use it.
    - Else fetch and store it in Rates sheet.
    """
    d_str = d.isoformat()

    existing = _get_rate_from_sheet_cached(book.id, d_str)
    if existing is not None:
        return float(existing)

    rate = _fetch_eur_to_bdt_rate(d)
    rates_ws = ws(book, "Rates")
    rates_ws.append_row([d_str, float(rate)])

    invalidate_all_data_caches()
    return float(rate)


# ----------------------------
# Categories defaults
# ----------------------------
def get_or_create_category_sheet_defaults(book):
    cat_ws = ws(book, "Categories")
    df = read_df(cat_ws)

    if df.empty:
        defaults = [
            ("Salary", "Income"),
            ("Freelance", "Income"),
            ("Rent", "Expense"),
            ("Food", "Expense"),
            ("Transport", "Expense"),
            ("Bills", "Expense"),
            ("Shopping", "Expense"),
            ("General", "Other"),
            ("Loan Taken", "Debt"),
            ("Loan Repayment", "Debt Payment"),
        ]
        for name, t in defaults:
            cat_ws.append_row([str(name), str(t)])
        invalidate_all_data_caches()


# ----------------------------
# Normalize tx dataframe
# ----------------------------
def normalize_transactions_df(tx_df: pd.DataFrame) -> pd.DataFrame:
    if tx_df.empty:
        return tx_df

    tx_df = tx_df.copy()

    required_cols = [
        "id", "date", "type", "category", "remarks",
        "amount_eur", "rate_eur_bdt", "amount_bdt", "created_at"
    ]
    for col in required_cols:
        if col not in tx_df.columns:
            tx_df[col] = ""

    tx_df["date"] = pd.to_datetime(tx_df["date"], errors="coerce")

    for col in ["amount_eur", "rate_eur_bdt", "amount_bdt"]:
        tx_df[col] = pd.to_numeric(tx_df[col], errors="coerce").fillna(0.0)

    for col in ["id", "type", "category", "remarks", "created_at"]:
        tx_df[col] = tx_df[col].astype(str)

    return tx_df


# ----------------------------
# Transaction ID helper
# ----------------------------
def make_tx_id() -> str:
    import secrets
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rand = secrets.token_hex(2).upper()
    return f"TX-{stamp}-{rand}"
