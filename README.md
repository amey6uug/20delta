# 20DeltaStrangle

Multi-strategy options dashboard for NIFTY and SENSEX — 20Δ short strangle and
theta-shifting straddle, with backtesting, paper execution and live broker
market data.

**▶ Live app: https://amey6uug.github.io/20delta/**

The live version runs entirely in your browser via
stlite (Streamlit compiled to WebAssembly),
served as static files from GitHub Pages. First load takes 30–60s while the
Python runtime downloads, then it is cached.

> The hosted build has **no live market data** — Live Dashboard and Live Test
> are inactive there. Not a CORS limitation (Angel One does allow browser
> origins): stlite runs entirely client-side with no server, so any broker
> credential would have to ship inside a public static file. That is full
> account access published to the internet, TOTP seed included. Every page
> driven by the historical CSVs works normally. For live quotes, run locally.

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens on http://localhost:8501.

## Live market data (optional)

Copy `.env.example` to `.env` and fill in your Angel One SmartAPI credentials:

```
ANGEL_API_KEY=          # smartapi.angelbroking.com -> My Apps
ANGEL_CLIENT_CODE=      # your Angel login ID
ANGEL_PIN=              # 4-digit login PIN, not your password
ANGEL_TOTP_SECRET=      # base32 seed from the TOTP setup page
ANGEL_LIVE_TRADING=false
```

Without credentials the app reports market data as `UNAVAILABLE` rather than
substituting placeholder prices, and paper entry is refused — there is no safe
stand-in for an option price.

Check connectivity without placing anything:

```bash
python scripts/angel_check.py
```

`ANGEL_LIVE_TRADING=false` blocks every `place_order()` before any network call
is made. Setting it to `true` transmits real orders.


## Layout

| Path | Purpose |
|---|---|
| `app.py`, `nav.py`, `theme.py` | Streamlit shell and navigation |
| `engine/` | Strategy engine, risk engine, strike selection, backtest, broker adapters |
| `engine/angel_broker.py` | Angel One SmartAPI adapter (quotes + gated execution) |
| `flattrade_fetch.py` | Flattrade client — trade book sync and quotes |
| `strangle/`, `theta/`, `portfolio/` | Per-strategy loaders and dashboards |
| `data/` | Historical AlgoTest exports and executed-trade logs |
| `tests/` | `pytest tests/` |

## Strategy rules

- Entry 09:45, forced exit 15:00 IST
- NIFTY strikes ATM ±200 (±100 at DTE ≤ 1), SENSEX ATM ±300 (±100 at DTE ≤ 1)
- Protective hedges bought first, at ±300 (NIFTY) / ±500 (SENSEX) beyond the shorts
- Per-leg stop loss at 80% adverse, hard stop at 100%
- Shorting SENSEX ATM is rejected outright

Strikes are selected by fixed point distance, not by computed delta — "20Δ"
names the intent rather than the mechanism.
