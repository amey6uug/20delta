"""Central theme — colors, Plotly layout, CSS, and shared UI helpers.

Single source of truth imported by app.py and every dashboard module so the
whole app shares one palette, one chart style, and one set of widgets.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from engine.calendar import format_date_day, format_timestamp_day

# ── Palette (GitHub dark) ──────────────────────────────────────────────────────
BG = "#0d1117"
CARD = "#161b22"
TEXT = "#f0f6fc"
GRID = "#30363d"
MUTED = "#8b949e"

GREEN = "#39d353"
RED = "#f85149"
GOLD = "#e3b341"
BLUE = "#58a6ff"
PURPLE = "#bc8cff"

# Back-compat aliases
BG_COL = BG
CARD_COL = CARD
TEXT_COL = TEXT
GRID_COL = GRID

# ── Plotly layout ───────────────────────────────────────────────────────────────
AXIS = dict(
    gridcolor=GRID, zeroline=False, showline=False,
    tickfont=dict(color=TEXT), title_font=dict(color=TEXT),
)
LEGEND = dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT))
PLOT_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=TEXT, size=12),
    title_font=dict(color=TEXT),
    margin=dict(l=50, r=20, t=40, b=40),
    xaxis=AXIS,
    yaxis=AXIS,
)


# ── Formatting ──────────────────────────────────────────────────────────────────
def fmt_inr(v) -> str:
    if v is None:
        return "—"
    try:
        val = float(v)
        return f"₹{val:,.0f}"
    except Exception:
        return str(v)


def render_table(df: pd.DataFrame):
    """Standard full-width, index-less table used across every page."""
    st.dataframe(df, width="stretch", hide_index=True)


# ── Global CSS ──────────────────────────────────────────────────────────────────
def inject_theme():
    """Inject the app-wide stylesheet. Call once, right after set_page_config."""
    st.markdown(
        """
    <style>
        .stApp { background-color: #0d1117; color: #f0f6fc; }
        .block-container { padding-top: 2.5rem; padding-bottom: 1rem; }

        /* Metric cards */
        div[data-testid="stMetric"] {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px 20px;
            min-height: 110px;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        div[data-testid="stMetric"] label { font-size: 13px; color: #8b949e !important; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-size: 24px; font-weight: 700; color: #ffffff !important; }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] * { color: #ffffff !important; }
        div[data-testid="stMetricDelta"] { font-size: 12px; min-height: 20px; color: #ffffff !important; }
        div[data-testid="stMetricDelta"] * { color: #ffffff !important; }

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] { background-color: #161b22; border-radius: 8px; padding: 4px; }
        .stTabs [data-baseweb="tab"] { border-radius: 6px; color: #8b949e; }
        .stTabs [aria-selected="true"] { color: #f0f6fc !important; }

        h1, h2, h3, h4 { color: #f0f6fc !important; }
        p { color: #8b949e; }

        /* Sidebar / navigation */
        [data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
        [data-testid="stSidebarNav"] { padding-top: 0.5rem; }
        [data-testid="stSidebarNav"] ul { padding-top: 0.25rem; }
        [data-testid="stSidebarNav"] a { border-radius: 6px; }
        [data-testid="stSidebarNav"] a:hover { background-color: rgba(88,166,255,0.10); }

        /* Page header block */
        .page-header { text-align: center; margin: 0 0 0.25rem 0; }
        .page-header h1 { font-size: 28px; margin-bottom: 4px; }
        .page-header .subtitle { color: #8b949e; margin-top: 0; font-size: 14px; }

        /* Status badge pills */
        .status-badge {
            display: inline-block; padding: 2px 10px; border-radius: 999px;
            font-size: 11px; font-weight: 700; letter-spacing: 0.03em;
            vertical-align: middle; margin-left: 6px;
        }
        .status-badge.live     { background: rgba(57,211,83,0.15);  color: #39d353; border: 1px solid rgba(57,211,83,0.4); }
        .status-badge.backtest { background: rgba(88,166,255,0.15); color: #58a6ff; border: 1px solid rgba(88,166,255,0.4); }
        .status-badge.paper    { background: rgba(227,179,65,0.15); color: #e3b341; border: 1px solid rgba(227,179,65,0.4); }
        .status-badge.danger   { background: rgba(248,81,73,0.15);  color: #f85149; border: 1px solid rgba(248,81,73,0.4); }

        /* Risk Status Box */
        .risk-box {
            border-radius: 8px; padding: 14px 18px; margin: 10px 0;
            display: flex; align-items: center; justify-content: space-between;
        }
        .risk-box.green  { background: rgba(57,211,83,0.10); border: 1px solid rgba(57,211,83,0.35); color: #39d353; }
        .risk-box.yellow { background: rgba(227,179,65,0.10); border: 1px solid rgba(227,179,65,0.35); color: #e3b341; }
        .risk-box.red    { background: rgba(248,81,73,0.10); border: 1px solid rgba(248,81,73,0.35); color: #f85149; }

        .last-updated { text-align: center; color: #8b949e; font-size: 12px; margin-bottom: 0.5rem; }

        /* Strategy summary cards (Home) */
        .strategy-card {
            background: #161b22; border: 1px solid #30363d; border-radius: 10px;
            padding: 18px 20px; height: 100%;
        }
        .strategy-card .sc-title { font-size: 16px; font-weight: 700; color: #f0f6fc; margin-bottom: 2px; }
        .strategy-card .sc-desc { font-size: 12px; color: #8b949e; margin-bottom: 12px; min-height: 32px; }
        .strategy-card .sc-kpis { display: flex; gap: 18px; flex-wrap: wrap; }
        .strategy-card .sc-kpi .k { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.03em; }
        .strategy-card .sc-kpi .v { font-size: 20px; font-weight: 700; }

        /* Callout box */
        .callout {
            background: #161b22; border: 1px solid #30363d; border-left: 3px solid #58a6ff;
            border-radius: 8px; padding: 14px 18px; margin: 8px 0;
        }
        .callout .c-title { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.03em; }
        .callout .c-body { font-size: 14px; color: #f0f6fc; margin-top: 4px; }
    </style>
    """,
        unsafe_allow_html=True,
    )


# ── HTML helpers ─────────────────────────────────────────────────────────────────
def page_header(title: str, subtitle: str | None = None, badge: str | None = None):
    """Centered page title with optional subtitle line and status badge."""
    badge_html = f'<span class="status-badge {badge.lower()}">{badge.upper()}</span>' if badge else ""
    sub_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="page-header"><h1>{title}{badge_html}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def status_badge(kind: str) -> str:
    """Return HTML for a LIVE / BACKTEST / PAPER pill (inline use)."""
    return f'<span class="status-badge {kind.lower()}">{kind.upper()}</span>'


def render_risk_banner(status_color: str, title: str, description: str):
    """
    Render risk status indicator:
    - green: Normal Operation
    - yellow: Profit Lock Active (+1% protected)
    - red: Stop Loss / Hard Stop / Risk Event
    """
    color_class = status_color.lower()
    icon = "🟢" if color_class == "green" else ("🟡" if color_class == "yellow" else "🔴")
    st.markdown(
        f'<div class="risk-box {color_class}">'
        f'<div><b>{icon} {title}</b><div style="font-size:13px; margin-top:2px; color:#f0f6fc;">{description}</div></div>'
        f'<div style="font-weight:700; font-size:14px; text-transform:uppercase;">{status_color.upper()} RISK</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def last_updated(ts: datetime | pd.Timestamp | None = None):
    """Render a centered 'last updated' caption using strict DD-MM-YYYY, Day format."""
    if ts is None:
        return
    formatted = format_timestamp_day(ts)
    st.markdown(
        f'<div class="last-updated">Data updated: <b>{formatted}</b></div>',
        unsafe_allow_html=True,
    )


def color_for(v: float) -> str:
    return GREEN if v >= 0 else RED
