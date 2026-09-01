"""
Flattrade API client — fetches today's executed trades and updates live_trades.csv.
Based on the Flattrade/Shoonya NorenAPI framework.

Required .env variables (see .env.example):
    FLATTRADE_USER_ID, FLATTRADE_PASSWORD, FLATTRADE_TOTP_SECRET,
    FLATTRADE_API_SECRET, FLATTRADE_VENDOR_CODE
"""

import os
import re
import json
import hashlib
import logging
import requests
import pandas as pd
from datetime import date, timedelta
from collections import defaultdict

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

log = logging.getLogger(__name__)

BASE_URL = os.getenv("FLATTRADE_BASE_URL", "https://piconnect.flattrade.in/NorenWClientTP")


# ── Authentication ─────────────────────────────────────────────────────────────

def login():
    """Authenticate with Flattrade. Returns susertoken (session token)."""
    uid         = os.getenv("FLATTRADE_USER_ID", "").strip()
    pwd         = os.getenv("FLATTRADE_PASSWORD", "").strip()
    totp_secret = os.getenv("FLATTRADE_TOTP_SECRET", "").strip()
    api_key     = os.getenv("FLATTRADE_API_KEY", "").strip()
    api_secret  = os.getenv("FLATTRADE_API_SECRET", "").strip()

    if not all([uid, pwd, api_key, api_secret]):
        raise ValueError(
            "Missing .env vars: FLATTRADE_USER_ID, FLATTRADE_PASSWORD, "
            "FLATTRADE_API_KEY, FLATTRADE_API_SECRET"
        )
    if not totp_secret:
        raise ValueError(
            "FLATTRADE_TOTP_SECRET not set. "
            "Get the base32 seed from your authenticator app's 'show key' option."
        )
    if pyotp is None:
        raise RuntimeError("Run: pip install pyotp")

    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
    factor2  = pyotp.TOTP(totp_secret).now()
    # Standard NorenAPI appkey = SHA256(uid + "|" + api_secret)
    app_key  = hashlib.sha256(f"{uid}|{api_secret}".encode()).hexdigest()
    imei     = "mac_" + hashlib.md5(uid.encode()).hexdigest()[:12]

    jdata = json.dumps({
        "uid":        uid,
        "pwd":        pwd_hash,
        "factor2":    factor2,
        "vc":         api_key,
        "appkey":     app_key,
        "imei":       imei,
        "source":     "API",
        "apkversion": "1.0.0",
    })
    # NorenAPI requires the raw JSON string — not form-encoded
    payload = "jKey=&jData=" + jdata

    log.debug("Login payload (masked): uid=%s vc=%s appkey=%s...", uid, api_key, app_key[:8])
    print(f"[Flattrade] Logging in: uid={uid}, vc={api_key[:4]}****, appkey={app_key[:8]}...")

    resp = requests.post(f"{BASE_URL}/QuickAuth", data=payload, timeout=15)

    if resp.status_code != 200:
        raise ValueError(f"Login HTTP {resp.status_code}: {resp.text[:600]}")

    data = resp.json()

    if data.get("stat") != "Ok":
        raise ValueError(f"Login failed: {data.get('emsg', data)}")

    log.info("Flattrade login OK for %s", uid)
    return data["susertoken"]


# ── Trade Book ─────────────────────────────────────────────────────────────────

def get_trade_book(session_token):
    """Fetch today's executed trades. Returns list of trade dicts (may be empty)."""
    uid = os.getenv("FLATTRADE_USER_ID", "").strip()

    payload = f'jKey={session_token}&jData={json.dumps({"uid": uid, "actid": uid})}'

    resp = requests.post(f"{BASE_URL}/TradeBook", data=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, dict):
        if data.get("stat") == "Not_Ok":
            emsg = data.get("emsg", "")
            if any(x in emsg.lower() for x in ("no data", "not found", "no trades")):
                return []
            raise ValueError(f"TradeBook error: {emsg}")
        return []

    return data  # list of trade dicts


# ── Live Quotes ────────────────────────────────────────────────────────────────

# Index scrip names as they appear in Noren's SearchScrip results.
_INDEX_SCRIP = {
    "NIFTY":     ("NSE", "Nifty 50"),
    "BANKNIFTY": ("NSE", "Nifty Bank"),
    "SENSEX":    ("BSE", "SENSEX"),
}

# Session tokens are valid for the trading day. Re-logging in on every Streamlit
# rerun would burn TOTP codes and hit rate limits, so the token is cached here.
_SESSION = {"token": None, "date": None}


def get_session(force=False):
    """Return a cached session token, logging in only once per calendar day."""
    from datetime import date as _date
    today = _date.today()
    if force or _SESSION["token"] is None or _SESSION["date"] != today:
        _SESSION["token"] = login()
        _SESSION["date"] = today
    return _SESSION["token"]


def _post(endpoint, session_token, jdata, timeout=10):
    """POST to a NorenAPI endpoint using the jKey/jData form. Returns parsed JSON."""
    payload = f"jKey={session_token}&jData={json.dumps(jdata)}"
    resp = requests.post(f"{BASE_URL}/{endpoint}", data=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("stat") == "Not_Ok":
        raise ValueError(f"{endpoint}: {data.get('emsg', data)}")
    return data


def search_scrip(session_token, text, exch="NFO"):
    """Resolve a symbol to its exchange token. Returns list of match dicts."""
    uid = os.getenv("FLATTRADE_USER_ID", "").strip()
    data = _post("SearchScrip", session_token, {"uid": uid, "stext": text, "exch": exch})
    return data.get("values", []) if isinstance(data, dict) else []


def get_quotes(session_token, exch, token):
    """Raw quote payload for one instrument token (lp, c, o, h, l, v ...)."""
    uid = os.getenv("FLATTRADE_USER_ID", "").strip()
    return _post("GetQuotes", session_token, {"uid": uid, "exch": exch, "token": str(token)})


def get_index_spot(underlying, session_token=None):
    """
    Live index spot from Flattrade.
    Returns (ltp, change, change_pct). Raises on failure - callers decide the fallback.
    """
    underlying = underlying.upper().strip()
    if underlying not in _INDEX_SCRIP:
        raise ValueError(f"Unknown index: {underlying}")
    exch, name = _INDEX_SCRIP[underlying]
    tok = session_token or get_session()

    hits = search_scrip(tok, name, exch)
    if not hits:
        raise ValueError(f"No scrip found for {name} on {exch}")
    # Prefer an exact name match; SearchScrip returns fuzzy hits ordered loosely.
    match = next((h for h in hits if h.get("tsym", "").upper() == name.upper()), hits[0])

    q = get_quotes(tok, exch, match["token"])
    ltp = float(q.get("lp") or 0.0)
    prev = float(q.get("c") or 0.0)          # 'c' is previous close on Noren
    chg = ltp - prev
    pct = (chg / prev * 100.0) if prev else 0.0
    return round(ltp, 2), round(chg, 2), round(pct, 2)


def get_option_quote(tsym, exch="NFO", session_token=None):
    """
    Live quote for one option contract by trading symbol.
    Returns dict with ltp/bid/ask/volume, or raises.
    """
    tok = session_token or get_session()
    hits = search_scrip(tok, tsym, exch)
    if not hits:
        raise ValueError(f"No contract found for {tsym} on {exch}")
    match = next((h for h in hits if h.get("tsym", "").upper() == tsym.upper()), hits[0])

    q = get_quotes(tok, exch, match["token"])
    return {
        "tsym":   q.get("tsym", tsym),
        "token":  match["token"],
        "ltp":    float(q.get("lp") or 0.0),
        "bid":    float(q.get("bp1") or 0.0),
        "ask":    float(q.get("sp1") or 0.0),
        "volume": float(q.get("v") or 0.0),
    }


def get_option_chain(tsym, strike, exch="NFO", count=5, session_token=None):
    """
    Option chain around `strike` for the given contract symbol.
    Returns the raw Noren 'values' list (each entry has tsym, token, optt, strprc).
    """
    uid = os.getenv("FLATTRADE_USER_ID", "").strip()
    tok = session_token or get_session()
    data = _post("GetOptionChain", tok, {
        "uid": uid, "exch": exch, "tsym": tsym,
        "strprc": str(strike), "cnt": str(count),
    })
    return data.get("values", []) if isinstance(data, dict) else []


def credentials_present():
    """True when enough .env vars exist to attempt a Flattrade login."""
    return all(os.getenv(k, "").strip() for k in (
        "FLATTRADE_USER_ID", "FLATTRADE_PASSWORD",
        "FLATTRADE_API_KEY", "FLATTRADE_API_SECRET", "FLATTRADE_TOTP_SECRET",
    ))


# ── Symbol Parsing ─────────────────────────────────────────────────────────────

_MONTH_ABB = {
    'JAN': 'Jan', 'FEB': 'Feb', 'MAR': 'Mar', 'APR': 'Apr',
    'MAY': 'May', 'JUN': 'Jun', 'JUL': 'Jul', 'AUG': 'Aug',
    'SEP': 'Sep', 'OCT': 'Oct', 'NOV': 'Nov', 'DEC': 'Dec',
}
_MONTH_NUM = {
    '1': 'Jan', '2': 'Feb',  '3': 'Mar', '4': 'Apr',
    '5': 'May', '6': 'Jun',  '7': 'Jul', '8': 'Aug',
    '9': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}

# NFO (NSE): NIFTY23JUN26C24400  → underlying + DD + MMM + YY + C/P + strike
_NFO_RE = re.compile(r'^(NIFTY|BANKNIFTY)(\d{2})([A-Z]{3})(\d{2})(C|P)(\d+)$')

# BFO (BSE): SENSEX2661877700CE  → underlying + YY + M[M] + DD + strike + CE/PE
_BFO_NUMERIC_RE = re.compile(r'^(SENSEX|BANKEX)(\d{2})(\d+)(CE|PE)$')
# BFO alt: SENSEX26JUN77000PE  → underlying + DD + MMM + strike + CE/PE
_BFO_ALPHA_RE = re.compile(r'^(SENSEX|BANKEX)(\d{2})([A-Z]{3})(\d+)(CE|PE)$')


def _parse_symbol(tsym):
    """
    Parse an NFO or BFO option symbol. Returns (index, expiry_str, strike, opt_type) or None.

    NFO example: NIFTY23JUN26C24400  → ('NIFTY', '23-Jun-2026', 24400, 'CE')
    BFO example: SENSEX2661877700CE  → ('SENSEX', '18-Jun-2026', 77700, 'CE')
    """
    t = tsym.upper()

    # Try NFO format first
    m = _NFO_RE.match(t)
    if m:
        underlying, dd, mon, yy, cp, strike_str = m.groups()
        opt_type = 'CE' if cp == 'C' else 'PE'
        expiry   = f"{dd}-{_MONTH_ABB[mon]}-20{yy}"
        return underlying, expiry, int(strike_str), opt_type

    # Try BFO numeric date format (e.g. SENSEX2670276200PE → 02-Jul-2026 PE 76200)
    m = _BFO_NUMERIC_RE.match(t)
    if m:
        underlying, yy, mid, opt_type = m.groups()
        for mlen in (1, 2):
            month_num = mid[:mlen]
            mon_name = _MONTH_NUM.get(month_num)
            if not mon_name:
                continue
            dd = mid[mlen:mlen + 2]
            strike_str = mid[mlen + 2:]
            if len(dd) == 2 and dd.isdigit() and strike_str.isdigit():
                expiry = f"{int(dd):02d}-{mon_name}-20{yy}"
                return underlying, expiry, int(strike_str), opt_type

    # Try BFO month-abbreviation format (e.g. SENSEX26JUN77000PE)
    m = _BFO_ALPHA_RE.match(t)
    if m:
        underlying, dd, mon, strike_str, opt_type = m.groups()
        if mon not in _MONTH_ABB:
            return None
        expiry = f"{dd}-{_MONTH_ABB[mon]}-2026"
        return underlying, expiry, int(strike_str), opt_type

    return None


# ── Trade Processing ───────────────────────────────────────────────────────────

def _first_val(trade, *keys):
    """Return the first non-empty value for any of the given keys."""
    for k in keys:
        v = trade.get(k)
        if v is not None and str(v).strip() not in ('', '0', '0.0'):
            return v
    return None


def _wavg_price(fills):
    """Quantity-weighted average fill price."""
    total_qty = sum(f['qty'] for f in fills)
    if total_qty == 0:
        return 0.0
    return sum(f['qty'] * f['price'] for f in fills) / total_qty


def _exit_reason(entry_price, exit_price, exit_time_str):
    """Infer exit reason from price ratio and exit time (HH:MM or HH:MM:SS)."""
    parts = exit_time_str.strip().split(':')
    h, m = int(parts[0]), int(parts[1])

    if h == 15 and m >= 13:          # 3:13 PM onwards → end-of-day exit
        return "EOD"
    if entry_price > 0 and exit_price / entry_price >= 1.45:
        return "50% SL"              # premium ~50% above entry → SL hit
    return "BE Trail"                # exited near entry after hitting profit


def _instr_category(exit_reasons):
    """Compute instrument-level category from a list of exit reason strings."""
    n_early = sum(1 for r in exit_reasons if r != 'EOD')
    if n_early == 0:
        return "Both: EOD"
    if n_early == 1:
        return "50% SL only"
    return "50%SL + BE hit"


_CAT_N = {"Both: EOD": 0, "50% SL only": 1, "50%SL + BE hit": 2, "Both: 50% SL": 2}


def _day_category(nifty_cat, sensex_cat):
    n, s = _CAT_N.get(nifty_cat, 0), _CAT_N.get(sensex_cat, 0)
    if n == 0 and s == 0:                         return 'Both Clean'
    if (n == 1 and s == 0) or (n == 0 and s == 1): return '1 Instr: 50% SL only'
    if n == 1 and s == 1:                          return 'Both: 50% SL only'
    if (n == 2 and s == 0) or (n == 0 and s == 2): return '1 Instr: 50%+BE hit'
    if (n == 2 and s == 1) or (n == 1 and s == 2): return 'Mixed: 50%+BE + 50%SL'
    if n == 2 and s == 2:                          return 'Both: 50%+BE hit'
    return 'Other'


def process_trades(raw_trades, trade_date=None):
    """
    Convert raw Flattrade trade book entries into live_trades.csv-format row dicts.
    VIX columns are left as None; call get_vix_data() and update them after.
    Returns an empty list if no complete strangle legs are found.
    """
    if trade_date is None:
        trade_date = date.today()

    date_str = trade_date.strftime("%d-%m-%Y")

    # Aggregate fills by (tsym, side)
    fills = defaultdict(list)   # (tsym, side) → [{qty, price, time}]
    sym_meta = {}               # tsym → parsed tuple

    for t in raw_trades:
        exch = t.get('exch', '')
        if exch not in ('NFO', 'BFO'):
            continue

        tsym   = t.get('tsym', '')
        parsed = _parse_symbol(tsym)
        if parsed is None:
            continue

        side  = t.get('trantype', t.get('side', ''))   # 'S' or 'B'
        qty   = float(_first_val(t, 'fillshares', 'flqty', 'qty') or 0)
        price = float(_first_val(t, 'fillprice', 'avgprc', 'prc') or 0)
        fltm  = str(_first_val(t, 'fltm', 'exchtime', 'ordertime') or '')

        if qty == 0 or price == 0 or side not in ('S', 'B'):
            continue

        fills[(tsym, side)].append({'qty': qty, 'price': price, 'time': fltm[:5]})
        sym_meta[tsym] = parsed

    # Build one leg record per symbol (need both S and B to be complete)
    leg_records = []
    for tsym in sym_meta:
        sells = fills.get((tsym, 'S'), [])
        buys  = fills.get((tsym, 'B'), [])
        if not sells or not buys:
            continue    # still open or incomplete

        index, expiry, strike, opt_type = sym_meta[tsym]

        entry_price = _wavg_price(sells)
        exit_price  = _wavg_price(buys)
        total_qty   = int(sum(f['qty'] for f in sells))
        entry_time  = min(f['time'] for f in sells)
        exit_time   = max(f['time'] for f in buys)

        pl     = round((entry_price - exit_price) * total_qty, 2)
        reason = _exit_reason(entry_price, exit_price, exit_time)

        leg_records.append({
            'Date':        date_str,
            'Index':       index,
            'Expiry':      expiry,
            'Type':        opt_type,
            'Strike':      strike,
            'Qty':         total_qty,
            'Entry_Price': round(entry_price, 2),
            'Entry_Time':  entry_time,
            'Exit_Price':  round(exit_price, 2),
            'Exit_Time':   exit_time,
            'PL':          pl,
            'Exit_Reason': reason,
        })

    if not leg_records:
        return []

    # Compute Instr_PL / Instr_Category per instrument
    instr_legs = defaultdict(list)
    for rec in leg_records:
        instr_legs[rec['Index']].append(rec)

    instr_info = {}
    for idx, legs in instr_legs.items():
        instr_pl  = round(sum(l['PL'] for l in legs), 2)
        instr_cat = _instr_category([l['Exit_Reason'] for l in legs])
        instr_info[idx] = {'Instr_PL': instr_pl, 'Instr_Category': instr_cat}

    # Day-level aggregation
    day_pl     = round(sum(r['PL'] for r in leg_records), 2)
    nifty_cat  = instr_info.get('NIFTY',  {}).get('Instr_Category', 'Both: EOD')
    sensex_cat = instr_info.get('SENSEX', {}).get('Instr_Category', 'Both: EOD')
    day_cat    = _day_category(nifty_cat, sensex_cat)

    rows = []
    for rec in leg_records:
        idx = rec['Index']
        rows.append({
            **rec,
            'Instr_PL':       instr_info[idx]['Instr_PL'],
            'Instr_Category': instr_info[idx]['Instr_Category'],
            'Day_PL':         day_pl,
            'Day_Category':   day_cat,
            'VIX_Open':  None, 'VIX_High':       None,
            'VIX_Low':   None, 'VIX_Close':       None,
            'VIX_Change_Pct': None,
        })

    return rows


# ── VIX Data ───────────────────────────────────────────────────────────────────

def get_vix_data(trade_date):
    """Fetch India VIX OHLC for trade_date via yfinance. Returns dict or None."""
    if yf is None:
        log.warning("yfinance not installed — VIX data skipped")
        return None

    try:
        df = yf.download(
            "^INDIAVIX",
            start=trade_date.strftime("%Y-%m-%d"),
            end=(trade_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return None

        open_ = float(df['Open'].to_numpy().ravel()[0])
        close = float(df['Close'].to_numpy().ravel()[0])
        chg   = round((close - open_) / open_ * 100, 2) if open_ else 0

        return {
            'VIX_Open':       round(open_, 4),
            'VIX_High':       round(float(df['High'].to_numpy().ravel()[0]), 4),
            'VIX_Low':        round(float(df['Low'].to_numpy().ravel()[0]),  4),
            'VIX_Close':      round(close, 4),
            'VIX_Change_Pct': chg,
        }
    except Exception as e:
        log.warning("VIX fetch failed: %s", e)
        return None


# ── CSV Update ─────────────────────────────────────────────────────────────────

_COLS = [
    'Date', 'Index', 'Expiry', 'Type', 'Strike', 'Qty',
    'Entry_Price', 'Entry_Time', 'Exit_Price', 'Exit_Time',
    'PL', 'Exit_Reason', 'Instr_PL', 'Instr_Category',
    'Day_PL', 'Day_Category',
    'VIX_Open', 'VIX_High', 'VIX_Low', 'VIX_Close', 'VIX_Change_Pct',
]


def update_live_trades(new_rows, csv_path="data/live_trades.csv"):
    """
    Append new_rows to CSV, skipping any dates already present.
    Returns number of rows added (0 if all already exist).
    """
    try:
        existing = pd.read_csv(csv_path)
        existing['Date'] = pd.to_datetime(existing['Date'], dayfirst=True)
        seen = set(existing['Date'].dt.strftime('%d-%m-%Y'))
        existing['Date'] = existing['Date'].dt.strftime('%d-%m-%Y')
    except FileNotFoundError:
        existing = pd.DataFrame(columns=_COLS)
        seen     = set()

    fresh = [r for r in new_rows if r['Date'] not in seen]
    if not fresh:
        return 0

    combined = pd.concat(
        [existing, pd.DataFrame(fresh, columns=_COLS)],
        ignore_index=True,
    )
    combined.to_csv(csv_path, index=False)
    return len(fresh)


# ── Main Entry Point ───────────────────────────────────────────────────────────

def fetch_and_update(session_token=None, trade_date=None):
    """
    Full pipeline: login → fetch trade book → process → fetch VIX → update CSV.

    Returns:
        session_token  – reuse in subsequent calls to avoid re-logging in
        success        – bool
        message        – human-readable status string
        rows           – processed row dicts (empty on failure)
    """
    if trade_date is None:
        trade_date = date.today()

    try:
        if session_token is None:
            session_token = login()

        raw  = get_trade_book(session_token)
        rows = process_trades(raw, trade_date)

        if not rows:
            return session_token, False, "No complete strangle trades found for today.", []

        vix = get_vix_data(trade_date)
        if vix:
            for r in rows:
                r.update(vix)

        added = update_live_trades(rows)

        if added == 0:
            msg = f"{trade_date.strftime('%d %b %Y')} trades already in CSV."
        else:
            vix_note = "" if vix else " (VIX unavailable — fill manually)"
            msg = (
                f"Added {trade_date.strftime('%d %b %Y')}: "
                f"{len(rows)} legs · Day P&L = ₹{rows[0]['Day_PL']:,.2f}{vix_note}"
            )

        return session_token, True, msg, rows

    except Exception as e:
        return session_token, False, str(e), []


def credentials_configured():
    """Return True if the minimum required .env vars are set."""
    return bool(
        os.getenv("FLATTRADE_USER_ID") and
        os.getenv("FLATTRADE_API_KEY") and
        os.getenv("FLATTRADE_API_SECRET") and
        os.getenv("FLATTRADE_TOTP_SECRET")
    )
