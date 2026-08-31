"""Home / Overview — diversification at a glance.

Reuses the portfolio analysis pipeline (portfolio.analysis.load_portfolio_data)
so the combined KPIs, equity curves, and correlation callout on this landing
page are computed exactly the same way as the Portfolio Comparison page.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from portfolio.analysis import load_portfolio_data
from portfolio.dashboard import metrics_row
from theme import (
    BLUE, GREEN, MUTED, PURPLE, PLOT_LAYOUT, LEGEND,
    color_for, fmt_inr, last_updated, page_header,
)

DATA_DIR = Path("data")
_WATCH_FILES = [
    "live_trades.csv", "live_trades_theta.csv",
    "Nifty+Sensex_945_new.csv", "Thetashift.csv",
]


@st.cache_data
def _portfolio():
    return load_portfolio_data()


def _newest_data_mtime():
    stamps = []
    for name in _WATCH_FILES:
        p = DATA_DIR / name
        if p.exists():
            stamps.append(os.path.getmtime(p))
    return datetime.fromtimestamp(max(stamps)) if stamps else None


def _strategy_kpis(m: dict):
    return [
        ("Return", f"{m.get('return_pct', 0):.1f}%", color_for(m.get("return_pct", 0))),
        ("Net P&L", fmt_inr(m.get("total_pl", 0)), color_for(m.get("total_pl", 0))),
        ("Sharpe", f"{m.get('sharpe', 0):.2f}", "#f0f6fc"),
        ("Max DD", f"{m.get('max_dd_pct', 0):.1f}%", "#f85149"),
    ]


def render_home():
    data = _portfolio()
    cap_each = data["capital_per_strategy"]
    cap_combined = data["capital_combined"]
    merged = data["merged"]
    corr = data["correlation"]

    page_header(
        "Diversified Options Portfolio",
        subtitle=(
            f"{data['label_a']} &nbsp;+&nbsp; {data['label_b']} &nbsp;|&nbsp; "
            f"{len(merged)} aligned days "
            f"({data['overlap_start'].strftime('%b %Y')} – {data['overlap_end'].strftime('%b %Y')}) "
            f"&nbsp;|&nbsp; {fmt_inr(cap_combined)} combined capital"
        ),
    )
    last_updated(_newest_data_mtime())

    # ── Combined KPI row ─────────────────────────────────────────────────────────
    st.markdown("##### Combined Portfolio (both strategies, full size)")
    metrics_row(data["metrics_combined"], cap_combined)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Equity curves ────────────────────────────────────────────────────────────
    st.markdown("##### Equity Curves")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data["daily_a"]["Date"], y=data["daily_a"]["Cumulative"],
        name=data["label_a"], line=dict(color=BLUE, width=2),
        hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=data["daily_b"]["Date"], y=data["daily_b"]["Cumulative"],
        name=data["label_b"], line=dict(color=PURPLE, width=2),
        hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=merged["Date"], y=merged["Cumulative_combined"],
        name="Combined", line=dict(color=GREEN, width=2.5),
        fill="tozeroy", fillcolor="rgba(57,211,83,0.08)",
        hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
    fig.update_layout(**PLOT_LAYOUT, height=340, legend=LEGEND,
                      title=dict(text="Cumulative Net P&L", font=dict(size=14)))
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")

    # ── Diversification callout ──────────────────────────────────────────────────
    pearson = corr.get("pearson", 0)
    both_loss_pct = corr.get("both_loss_pct", 0)
    tail = corr.get("tail_overlap_days", 0)
    if pearson < 0.3:
        benefit = "Low correlation — the two strategies rarely lose together, so combining them smooths the equity curve."
    elif pearson < 0.6:
        benefit = "Moderate correlation — some shared risk, but the blend still reduces drawdowns versus either strategy alone."
    else:
        benefit = "High correlation — the strategies move together; diversification benefit is limited."
    st.markdown(
        f'<div class="callout">'
        f'<div class="c-title">Diversification</div>'
        f'<div class="c-body">Daily P&L correlation <b style="color:{color_for(-pearson)}">{pearson:+.2f}</b> · '
        f'both strategies lose on <b>{both_loss_pct:.0f}%</b> of days · '
        f'<b>{tail}</b> shared tail (worst-5%) days. {benefit}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Strategy cards ───────────────────────────────────────────────────────────
    st.markdown("##### Strategies")
    import nav  # lazy — avoids import cycle; populated by build_pages() this run
    strategy_pages = nav.CURRENT_STRATEGY_PAGES

    cfg_strats = data["config"]["strategies"]
    per_strat = [
        (data["name_a"], data["label_a"], data["desc_a"], data["metrics_a"]),
        (data["name_b"], data["label_b"], data["desc_b"], data["metrics_b"]),
    ]
    cols = st.columns(len(per_strat))
    for col, (key, label, desc, m) in zip(cols, per_strat):
        with col:
            kpi_html = "".join(
                f'<div class="sc-kpi"><div class="k">{k}</div>'
                f'<div class="v" style="color:{c}">{v}</div></div>'
                for k, v, c in _strategy_kpis(m)
            )
            st.markdown(
                f'<div class="strategy-card">'
                f'<div class="sc-title">{label}</div>'
                f'<div class="sc-desc">{cfg_strats.get(key, {}).get("description", desc)}</div>'
                f'<div class="sc-kpis">{kpi_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            page = strategy_pages.get(key)
            if page is not None:
                st.page_link(page, label="Open dashboard →", icon="📂")

    # ── Portfolio deep-dive link ─────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Net of Flattrade statutory charges (STT, exchange, stamp, SEBI, IPFT, GST) · "
        "brokerage ₹0. See **Portfolio** for correlation, weight optimisation, and regime analysis."
    )

