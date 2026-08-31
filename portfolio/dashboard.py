"""Portfolio diversification UI — embedded in app.py or run via portfolio_app.py."""

import importlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from portfolio.returns import build_returns_analysis
from theme import (
    BG as BG_COL, TEXT as TEXT_COL, GRID as GRID_COL, MUTED,
    GREEN, RED, GOLD, BLUE, PURPLE, PLOT_LAYOUT, fmt_inr,
)


def metrics_row(m, capital):
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Win Rate", f"{m['win_rate']:.1f}%", f"{m['wins']}W / {m['losses']}L")
    c2.metric(
        "Net P&L",
        fmt_inr(m["total_pl"]),
        f"Gross {fmt_inr(m.get('gross_pl', m['total_pl']))} · Charges {fmt_inr(m.get('total_charges', 0))}",
    )
    c3.metric("Return", f"{m.get('return_pct', 0):.1f}%", f"CAGR {m.get('cagr', 0):.1f}% on {fmt_inr(capital)}")
    c4.metric("Sharpe", f"{m['sharpe']:.2f}")
    c5.metric("Max Drawdown", fmt_inr(m["max_drawdown"]), f"{m['max_dd_pct']:.1f}% of capital")
    win_loss = abs(m["avg_win"] / m["avg_loss"]) if m["avg_loss"] else 0
    c6.metric("Profit Factor", f"{m['profit_factor']:.2f}",
              f"Avg W/L {win_loss:.2f}×" if m["avg_loss"] else "—")


def strategy_metrics_block(title, metrics, capital):
    st.markdown(f"##### {title}")
    metrics_row(metrics, capital)
    st.markdown("<br>", unsafe_allow_html=True)


def inject_portfolio_styles():
    """Standalone-entry styling. Delegates to the shared app theme."""
    from theme import inject_theme
    inject_theme()


def get_portfolio_data():
    import portfolio.charges as _charges
    import portfolio.algotest_loader as _loader
    import portfolio.yearly as _yearly
    import portfolio.returns as _returns
    import portfolio.analysis as _pan

    # Reload in dependency order so yearly_compare is never stale in Streamlit.
    for mod in (_charges, _loader, _yearly, _returns, _pan):
        importlib.reload(mod)

    data = _pan.load_portfolio_data()
    cap_each, cap_combined = _resolve_capitals_from_cfg(data)
    data.setdefault("capital_per_strategy", cap_each)
    data.setdefault("capital_combined", cap_combined)
    data.setdefault("capital", cap_each)
    # Always recompute — avoids cached aligned-window logic from old yearly module.
    data["yearly"] = _yearly.yearly_compare(
        data["merged"], data["name_a"], data["name_b"], cap_combined,
    )
    return data


def _resolve_capitals_from_cfg(data: dict) -> tuple[float, float]:
    cfg = data.get("config", {})
    cap_each = data.get(
        "capital_per_strategy",
        cfg.get("capital_per_strategy", cfg.get("capital", 550_000)),
    )
    cap_combined = data.get("capital_combined", cfg.get("capital_combined", cap_each * 2))
    return float(cap_each), float(cap_combined)


def render_portfolio_dashboard(*, embedded: bool = False):
    """Render strangle vs theta portfolio comparison (sub-tabs)."""
    data = get_portfolio_data()
    rets = build_returns_analysis(data)
    la, lb = data["label_a"], data["label_b"]
    na, nb = data["name_a"], data["name_b"]
    merged = data["merged"]
    cap_each = data.get("capital_per_strategy", data.get("capital", 550_000))
    cap_combined = data.get("capital_combined", cap_each * 2)
    overlap_start = data.get("overlap_start", merged["Date"].min())
    overlap_end = data.get("overlap_end", merged["Date"].max())

    st.markdown(f"""
    <h1 style='text-align:center; font-size:28px; margin-bottom:4px;'>
        Portfolio Comparison — Strangle + Theta
    </h1>
    <p style='text-align:center;'>
        <b>{la}</b> vs <b>{lb}</b> &nbsp;|&nbsp;
        {len(merged)} aligned days ({overlap_start.strftime('%d-%b-%Y')} → {overlap_end.strftime('%d-%b-%Y')}) &nbsp;|&nbsp;
        {fmt_inr(cap_each)} per strategy &nbsp;|&nbsp; {fmt_inr(cap_combined)} combined
    </p>
    """, unsafe_allow_html=True)

    st.caption(f"**A — {la}:** {data['desc_a']}")
    st.caption(f"**B — {lb}:** {data['desc_b']}")
    st.caption(
        "Net P&L after Flattrade statutory charges (STT, exchange, stamp, SEBI, IPFT, GST). "
        "Rates are date-accurate per trade. **Brokerage = ₹0.** "
        "Wife's account: strangle live · Your account: theta live from Jul 2026."
    )

    tab_overview, tab_returns, tab_year, tab_corr, tab_weights, tab_regime = st.tabs(
        ["Overview", "Returns", "Year-wise", "Correlation & Overlap", "Weight Optimisation", "Regime Analysis"]
    )

    # ── Overview ──────────────────────────────────────────────────────────────────
    with tab_overview:
        st.markdown("#### Standalone Strategy Profiles")
        strategy_metrics_block(la, data["metrics_a"], cap_each)
        strategy_metrics_block(lb, data["metrics_b"], cap_each)
        strategy_metrics_block("Combined (full size both)", data["metrics_combined"], cap_combined)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=data["daily_a"]["Date"], y=data["daily_a"]["Cumulative"],
            name=la, line=dict(color=BLUE, width=2),
        ))
        fig.add_trace(go.Scatter(
            x=data["daily_b"]["Date"], y=data["daily_b"]["Cumulative"],
            name=lb, line=dict(color=PURPLE, width=2),
        ))
        fig.add_trace(go.Scatter(
            x=merged["Date"], y=merged["Cumulative_combined"],
            name="Combined", line=dict(color=GREEN, width=2.5),
        ))
        fig.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
        fig.update_layout(**PLOT_LAYOUT, height=360, title="Cumulative P&L — Individual vs Combined",
                          legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_COL)))
        fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
        st.plotly_chart(fig, width="stretch")

        # Side-by-side daily histogram
        fig_h = make_subplots(rows=1, cols=2, subplot_titles=[la, lb])
        for i, (daily, color, name) in enumerate(
            [(data["daily_a"], BLUE, la), (data["daily_b"], PURPLE, lb)], 1
        ):
            fig_h.add_trace(go.Histogram(
                x=daily["PL"], xbins=dict(size=500), marker_color=color, opacity=0.85, name=name,
            ), row=1, col=i)
        fig_h.update_layout(**PLOT_LAYOUT, height=280, barmode="overlay", showlegend=False)
        fig_h.update_xaxes(tickprefix="₹")
        st.plotly_chart(fig_h, width="stretch")

        compare = pd.DataFrame([
            {"Metric": "Days", la: data["metrics_a"]["days"], lb: data["metrics_b"]["days"],
             "Combined": data["metrics_combined"]["days"]},
            {"Metric": "Win Rate (%)", la: round(data["metrics_a"]["win_rate"], 1),
             lb: round(data["metrics_b"]["win_rate"], 1),
             "Combined": round(data["metrics_combined"]["win_rate"], 1)},
            {"Metric": "Net P&L (₹)", la: int(data["metrics_a"]["total_pl"]),
             lb: int(data["metrics_b"]["total_pl"]),
             "Combined": int(data["metrics_combined"]["total_pl"])},
            {"Metric": "Gross P&L (₹)", la: int(data["metrics_a"].get("gross_pl", 0)),
             lb: int(data["metrics_b"].get("gross_pl", 0)),
             "Combined": None},
            {"Metric": "Charges (₹)", la: int(data["metrics_a"].get("total_charges", 0)),
             lb: int(data["metrics_b"].get("total_charges", 0)),
             "Combined": int(data["metrics_a"].get("total_charges", 0) + data["metrics_b"].get("total_charges", 0))},
            {"Metric": "Return (%)", la: round(data["metrics_a"].get("return_pct", 0), 1),
             lb: round(data["metrics_b"].get("return_pct", 0), 1),
             "Combined": round(data["metrics_combined"].get("return_pct", 0), 1)},
            {"Metric": "CAGR (%)", la: round(data["metrics_a"].get("cagr", 0), 1),
             lb: round(data["metrics_b"].get("cagr", 0), 1),
             "Combined": round(data["metrics_combined"].get("cagr", 0), 1)},
            {"Metric": "Avg/Day (₹)", la: int(data["metrics_a"]["avg_day"]),
             lb: int(data["metrics_b"]["avg_day"]),
             "Combined": int(data["metrics_combined"]["avg_day"])},
            {"Metric": "Sharpe", la: round(data["metrics_a"]["sharpe"], 2),
             lb: round(data["metrics_b"]["sharpe"], 2),
             "Combined": round(data["metrics_combined"]["sharpe"], 2)},
            {"Metric": "Max DD (₹)", la: int(data["metrics_a"]["max_drawdown"]),
             lb: int(data["metrics_b"]["max_drawdown"]),
             "Combined": int(data["metrics_combined"]["max_drawdown"])},
            {"Metric": "Best Day (₹)", la: int(data["metrics_a"]["best_day"]),
             lb: int(data["metrics_b"]["best_day"]),
             "Combined": int(data["metrics_combined"]["best_day"])},
            {"Metric": "Worst Day (₹)", la: int(data["metrics_a"]["worst_day"]),
             lb: int(data["metrics_b"]["worst_day"]),
             "Combined": int(data["metrics_combined"]["worst_day"])},
        ])
        st.markdown("#### Comparison Table")
        st.dataframe(compare, hide_index=True, width="stretch")

    # ── Returns Analysis ────────────────────────────────────────────────────────────
    with tab_returns:
        st.markdown("#### Returns Comparison (Net of Charges · Flattrade · Brokerage ₹0)")
        st.caption(
            f"Capital: **{fmt_inr(cap_each)}** per strategy · **{fmt_inr(cap_combined)}** combined · "
            f"Period: {overlap_start.strftime('%d-%b-%Y')} → {overlap_end.strftime('%d-%b-%Y')}"
        )

        # Headline metrics
        ma, mb, mc = data["metrics_a"], data["metrics_b"], data["metrics_combined"]
        h1, h2, h3, h4 = st.columns(4)
        h1.metric(la, f"{ma['return_pct']:.1f}%", f"CAGR {ma['cagr']:.1f}% · Net {fmt_inr(ma['total_pl'])}")
        h2.metric(lb, f"{mb['return_pct']:.1f}%", f"CAGR {mb['cagr']:.1f}% · Net {fmt_inr(mb['total_pl'])}")
        h3.metric("Combined", f"{mc['return_pct']:.1f}%", f"CAGR {mc['cagr']:.1f}% · Net {fmt_inr(mc['total_pl'])}")
        h4.metric("Total Charges", fmt_inr(ma["total_charges"] + mb["total_charges"]),
                  f"{la} {fmt_inr(ma['total_charges'])} · {lb} {fmt_inr(mb['total_charges'])}")

        st.markdown("##### Master Comparison")
        st.dataframe(rets["summary"], hide_index=True, width="stretch")

        c_risk, c_ch = st.columns(2)
        with c_risk:
            st.markdown("##### Risk-Adjusted Returns")
            st.dataframe(rets["risk_adjusted"], hide_index=True, width="stretch")
        with c_ch:
            st.markdown("##### Charges Impact")
            st.dataframe(rets["charges"], hide_index=True, width="stretch")

        st.markdown("##### Cumulative Return (% of capital)")
        fig_cr = go.Figure()
        for eq, label, color in [
            (rets["equity_a"], la, BLUE),
            (rets["equity_b"], lb, PURPLE),
            (rets["equity_c"], "Combined", GREEN),
        ]:
            fig_cr.add_trace(go.Scatter(
                x=eq["Date"], y=eq["CumReturn_pct"],
                name=label, line=dict(color=color, width=2),
                hovertemplate="%{x|%d-%b-%Y}<br>%{y:.2f}%<extra></extra>",
            ))
        fig_cr.add_hline(y=0, line_color=MUTED, line_dash="dash")
        fig_cr.update_layout(**PLOT_LAYOUT, height=320, legend=dict(font=dict(color=TEXT_COL)))
        fig_cr.update_yaxes(title_text="Cumulative Return %")
        st.plotly_chart(fig_cr, width="stretch")

        col_dd, col_roll = st.columns(2)
        with col_dd:
            fig_dd = go.Figure()
            for eq, label, color in [
                (rets["equity_a"], la, BLUE),
                (rets["equity_b"], lb, PURPLE),
                (rets["equity_c"], "Combined", GREEN),
            ]:
                fig_dd.add_trace(go.Scatter(
                    x=eq["Date"], y=eq["Drawdown_pct"],
                    name=label, line=dict(color=color, width=1.5),
                    fill="tozeroy", opacity=0.6,
                ))
            fig_dd.update_layout(**PLOT_LAYOUT, height=280, title="Drawdown (% of capital)",
                                  legend=dict(font=dict(color=TEXT_COL)))
            fig_dd.update_yaxes(title_text="Drawdown %")
            st.plotly_chart(fig_dd, width="stretch")

        with col_roll:
            fig_roll = go.Figure()
            for roll, label, color in [
                (rets["rolling_a"], la, BLUE),
                (rets["rolling_b"], lb, PURPLE),
                (rets["rolling_c"], "Combined", GREEN),
            ]:
                fig_roll.add_trace(go.Scatter(
                    x=roll["Date"], y=roll["RollReturn_pct"],
                    name=label, line=dict(color=color, width=1.5),
                ))
            fig_roll.add_hline(y=0, line_color=MUTED, line_dash="dash")
            fig_roll.update_layout(**PLOT_LAYOUT, height=280, title="60-Day Rolling Return (%)",
                                    legend=dict(font=dict(color=TEXT_COL)))
            st.plotly_chart(fig_roll, width="stretch")

        st.markdown("##### Monthly Returns")
        mcol1, mcol2 = st.columns(2)
        with mcol1:
            fig_m = go.Figure()
            mc_month = rets["monthly_compare"]
            colors_m = [GREEN if v >= 0 else RED for v in mc_month["Combined P&L"]]
            fig_m.add_trace(go.Bar(
                x=mc_month["Month_str"], y=mc_month["Combined Ret %"],
                marker_color=colors_m, opacity=0.9, name="Combined",
            ))
            fig_m.add_hline(y=0, line_color=MUTED, line_dash="dash")
            fig_m.update_layout(**PLOT_LAYOUT, height=280, title="Combined Monthly Return (%)", showlegend=False)
            st.plotly_chart(fig_m, width="stretch")

        with mcol2:
            fig_m3 = go.Figure()
            fig_m3.add_trace(go.Bar(name=la, x=mc_month["Month_str"], y=mc_month[f"{la} Ret %"], marker_color=BLUE))
            fig_m3.add_trace(go.Bar(name=lb, x=mc_month["Month_str"], y=mc_month[f"{lb} Ret %"], marker_color=PURPLE))
            fig_m3.add_trace(go.Bar(name="Combined", x=mc_month["Month_str"], y=mc_month["Combined Ret %"], marker_color=GREEN))
            fig_m3.add_hline(y=0, line_color=MUTED, line_dash="dash")
            fig_m3.update_layout(**PLOT_LAYOUT, height=280, barmode="group",
                                  title="Monthly Return % — All Strategies",
                                  legend=dict(font=dict(color=TEXT_COL)))
            st.plotly_chart(fig_m3, width="stretch")

        st.dataframe(rets["monthly_compare"], hide_index=True, width="stretch")

        st.markdown("##### Yearly Returns")
        ycol1, ycol2 = st.columns(2)
        with ycol1:
            fig_y = go.Figure()
            for ydf, label, color in [
                (rets["yearly_a"], la, BLUE),
                (rets["yearly_b"], lb, PURPLE),
                (rets["yearly_c"], "Combined", GREEN),
            ]:
                fig_y.add_trace(go.Bar(
                    name=label, x=ydf["Year"].astype(str), y=ydf["Return (%)"],
                    marker_color=color, opacity=0.85,
                ))
            fig_y.add_hline(y=0, line_color=MUTED, line_dash="dash")
            fig_y.update_layout(**PLOT_LAYOUT, height=280, barmode="group",
                                title="Annual Return (% of capital)", legend=dict(font=dict(color=TEXT_COL)))
            st.plotly_chart(fig_y, width="stretch")

        with ycol2:
            yearly_tbl = rets["yearly_a"][["Year", "Net P&L (₹)", "Return (%)"]].rename(
                columns={"Net P&L (₹)": f"{la} P&L", "Return (%)": f"{la} Ret %"}
            ).merge(
                rets["yearly_b"][["Year", "Net P&L (₹)", "Return (%)"]].rename(
                    columns={"Net P&L (₹)": f"{lb} P&L", "Return (%)": f"{lb} Ret %"}
                ), on="Year"
            ).merge(
                rets["yearly_c"][["Year", "Net P&L (₹)", "Return (%)"]].rename(
                    columns={"Net P&L (₹)": "Combined P&L", "Return (%)": "Combined Ret %"}
                ), on="Year"
            )
            st.dataframe(yearly_tbl, hide_index=True, width="stretch")

        st.markdown("##### Gross vs Net P&L (Charges Drag)")
        fig_gn = go.Figure()
        for daily, label, color, cap in [
            (data["daily_a"], la, BLUE, cap_each),
            (data["daily_b"], lb, PURPLE, cap_each),
        ]:
            if "PL_gross" in daily.columns:
                fig_gn.add_trace(go.Bar(
                    name=f"{label} Gross", x=[label], y=[daily["PL_gross"].sum()],
                    marker_color=color, opacity=0.45,
                ))
                fig_gn.add_trace(go.Bar(
                    name=f"{label} Net", x=[label], y=[daily["PL"].sum()],
                    marker_color=color, opacity=0.95,
                ))
        fig_gn.update_layout(**PLOT_LAYOUT, height=260, barmode="group",
                              title="Gross vs Net Total P&L", legend=dict(font=dict(color=TEXT_COL)))
        fig_gn.update_yaxes(tickprefix="₹", tickformat=",.0f")
        st.plotly_chart(fig_gn, width="stretch")

    # ── Year-wise Comparison ──────────────────────────────────────────────────────
    with tab_year:
        o_full_start = overlap_start.strftime("%d-%b-%Y")
        o_full_end = overlap_end.strftime("%d-%b-%Y")
        span_years = (overlap_end - overlap_start).days / 365.25

        st.markdown("#### Year-wise Comparison")
        st.caption(
            f"Full **{span_years:.1f}-year** comparison window: **{o_full_start}** → **{o_full_end}** "
            f"({len(merged)} aligned trading days). "
            f"Each year shows all available trading days in that calendar year "
            f"(2024 & 2025 full year; 2026 Jan–Jun only)."
        )

        ydf = data["yearly"]

        if ydf.empty:
            st.warning("No year-wise data available.")
        else:
            # Charts
            col_pl, col_days = st.columns(2)
            years = ydf["Year"].astype(str)

            with col_pl:
                fig_ypl = go.Figure()
                fig_ypl.add_trace(go.Bar(name=la, x=years, y=ydf[f"PL_{na}"], marker_color=BLUE))
                fig_ypl.add_trace(go.Bar(name=lb, x=years, y=ydf[f"PL_{nb}"], marker_color=PURPLE))
                fig_ypl.add_trace(go.Bar(name="Combined", x=years, y=ydf["PL_Combined"], marker_color=GREEN))
                fig_ypl.add_hline(y=0, line_color=MUTED, line_dash="dash")
                fig_ypl.update_layout(**PLOT_LAYOUT, height=320, barmode="group",
                                      title="Total P&L by Year", legend=dict(font=dict(color=TEXT_COL)))
                fig_ypl.update_yaxes(tickprefix="₹", tickformat=",.0f")
                st.plotly_chart(fig_ypl, width="stretch")

            with col_days:
                fig_yd = go.Figure()
                fig_yd.add_trace(go.Bar(
                    x=years, y=ydf["Days"], marker_color=GOLD, opacity=0.9, name="Trading days",
                    text=ydf["Days"], textposition="outside", textfont=dict(color=TEXT_COL),
                ))
                fig_yd.update_layout(**PLOT_LAYOUT, height=320, title="Trading Days by Year", showlegend=False)
                st.plotly_chart(fig_yd, width="stretch")

            # Win rate by year
            fig_wr = go.Figure()
            fig_wr.add_trace(go.Scatter(
                x=years, y=ydf[f"WR_{na}"], mode="lines+markers+text",
                name=la, line=dict(color=BLUE, width=2), marker=dict(size=8),
                text=[f"{v:.1f}%" for v in ydf[f"WR_{na}"]], textposition="top center",
                textfont=dict(color=TEXT_COL, size=10),
            ))
            fig_wr.add_trace(go.Scatter(
                x=years, y=ydf[f"WR_{nb}"], mode="lines+markers+text",
                name=lb, line=dict(color=PURPLE, width=2), marker=dict(size=8),
                text=[f"{v:.1f}%" for v in ydf[f"WR_{nb}"]], textposition="bottom center",
                textfont=dict(color=TEXT_COL, size=10),
            ))
            fig_wr.add_trace(go.Scatter(
                x=years, y=ydf["WR_Combined"], mode="lines+markers",
                name="Combined", line=dict(color=GREEN, width=2.5), marker=dict(size=8),
            ))
            fig_wr.add_hline(y=50, line_color=MUTED, line_dash="dot")
            fig_wr.update_layout(**PLOT_LAYOUT, height=300, title="Win Rate by Year (%)",
                                  legend=dict(font=dict(color=TEXT_COL)))
            fig_wr.update_yaxes(range=[0, 100], title_text="Win Rate %")
            st.plotly_chart(fig_wr, width="stretch")

            # Table
            show = ydf.copy()
            show["W/L A"] = show.apply(
                lambda r: f"{int(r[f'Days_{na}_W'])}/{int(r['Days'] - r[f'Days_{na}_W'])}", axis=1
            )
            show["W/L B"] = show.apply(
                lambda r: f"{int(r[f'Days_{nb}_W'])}/{int(r['Days'] - r[f'Days_{nb}_W'])}", axis=1
            )
            show["W/L Combined"] = show.apply(
                lambda r: f"{int(r['Days_Combined_W'])}/{int(r['Days'] - r['Days_Combined_W'])}", axis=1
            )

            table = pd.DataFrame({
                "Year": show["Year"].astype(int),
                "Period": show["Period"],
                "Dates": show.apply(
                    lambda r: f"{r['Window Start']} – {r['Window End']}", axis=1,
                ),
                "Days": show["Days"].astype(int),
                f"{la} P&L": show[f"PL_{na}"].astype(int),
                f"{lb} P&L": show[f"PL_{nb}"].astype(int),
                "Combined P&L": show["PL_Combined"].astype(int),
                f"{la} WR %": show[f"WR_{na}"].round(1),
                f"{lb} WR %": show[f"WR_{nb}"].round(1),
                "Combined WR %": show["WR_Combined"].round(1),
                f"{la} Avg/Day": show[f"Avg_{na}"].round(0).astype(int),
                f"{lb} Avg/Day": show[f"Avg_{nb}"].round(0).astype(int),
                "W/L A": show["W/L A"],
                "W/L B": show["W/L B"],
                "W/L Combined": show["W/L Combined"],
                "Combined Sharpe": show["Sharpe_Combined"].round(2),
                "Combined Max DD": show["MaxDD_Combined"].astype(int),
            })

            st.markdown("#### Year-wise Table")
            st.dataframe(table, hide_index=True, width="stretch")

    # ── Correlation & Overlap ─────────────────────────────────────────────────────
    with tab_corr:
        corr = data["correlation"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Pearson Correlation", f"{corr['pearson']:.3f}")
        c2.metric("Both Win Days", f"{corr['both_win_pct']:.1f}%", f"{corr['both_win']} days")
        c3.metric("Both Loss Days", f"{corr['both_loss_pct']:.1f}%", f"{corr['both_loss']} days")
        c4.metric("Loss Overlap (given A loss)", f"{corr['loss_overlap_given_a_loss']:.1f}%")
        c5.metric("Tail Overlap (worst 5%)", f"{corr['tail_overlap_days']} days")

        col_sc, col_roll = st.columns(2)
        with col_sc:
            fig_sc = go.Figure()
            colors = [GREEN if r["PL_combined"] > 0 else RED for _, r in merged.iterrows()]
            fig_sc.add_trace(go.Scatter(
                x=merged[f"PL_{na}"], y=merged[f"PL_{nb}"],
                mode="markers", marker=dict(color=colors, size=6, opacity=0.7),
                text=merged["Date"].dt.strftime("%d-%b-%Y"),
                hovertemplate=f"{la}: ₹%{{x:,.0f}}<br>{lb}: ₹%{{y:,.0f}}<extra></extra>",
            ))
            fig_sc.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
            fig_sc.add_vline(x=0, line_color=MUTED, line_dash="dash", line_width=0.8)
            fig_sc.update_layout(**PLOT_LAYOUT, height=320,
                                 title="Daily P&L Scatter", xaxis_title=la, yaxis_title=lb)
            fig_sc.update_xaxes(tickprefix="₹")
            fig_sc.update_yaxes(tickprefix="₹")
            st.plotly_chart(fig_sc, width="stretch")

        with col_roll:
            rc = corr["rolling_corr"]
            fig_rc = go.Figure()
            fig_rc.add_trace(go.Scatter(
                x=rc["Date"], y=rc["rolling_corr"],
                line=dict(color=GOLD, width=2), fill="tozeroy", fillcolor="rgba(227,179,65,0.1)",
            ))
            fig_rc.add_hline(y=0, line_color=MUTED, line_dash="dash")
            fig_rc.add_hline(y=corr["pearson"], line_color=BLUE, line_dash="dot",
                             annotation_text=f"Full-period: {corr['pearson']:.2f}")
            fig_rc.update_layout(**PLOT_LAYOUT, height=320, title="60-Day Rolling Correlation")
            st.plotly_chart(fig_rc, width="stretch")

        # Overlap matrix
        overlap = pd.DataFrame([
            {"Scenario": "Both win", "Days": corr["both_win"],
             "% of total": round(corr["both_win"] / corr["days"] * 100, 1)},
            {"Scenario": f"{la} win, {lb} loss",
             "Days": int(((merged[f"PL_{na}"] > 0) & (merged[f"PL_{nb}"] <= 0)).sum()),
             "% of total": round(((merged[f"PL_{na}"] > 0) & (merged[f"PL_{nb}"] <= 0)).sum() / len(merged) * 100, 1)},
            {"Scenario": f"{la} loss, {lb} win",
             "Days": int(((merged[f"PL_{na}"] <= 0) & (merged[f"PL_{nb}"] > 0)).sum()),
             "% of total": round(((merged[f"PL_{na}"] <= 0) & (merged[f"PL_{nb}"] > 0)).sum() / len(merged) * 100, 1)},
            {"Scenario": "Both loss", "Days": corr["both_loss"],
             "% of total": round(corr["both_loss_pct"], 1)},
        ])
        st.markdown("#### Win/Loss Overlap Matrix")
        st.dataframe(overlap, hide_index=True, width="stretch")

        # Worst combined days
        worst = merged.nsmallest(10, "PL_combined")[
            ["Date", f"PL_{na}", f"PL_{nb}", "PL_combined"]
        ].copy()
        worst["Date"] = worst["Date"].dt.strftime("%d-%b-%Y")
        worst.columns = ["Date", la, lb, "Combined"]
        st.markdown("#### Worst 10 Combined Days (tail overlap)")
        st.dataframe(worst, hide_index=True, width="stretch")

    # ── Weight Optimisation ───────────────────────────────────────────────────────
    with tab_weights:
        weights = data["weights"]
        best_sharpe = weights.loc[weights["sharpe"].idxmax()]
        best_calmar = weights.loc[weights["calmar"].idxmax()]
        full_both = weights[weights["label"] == "100/100 (full both)"].iloc[0]

        c1, c2, c3 = st.columns(3)
        c1.metric("Best Sharpe Split", best_sharpe["label"], f"Sharpe {best_sharpe['sharpe']:.2f}")
        c2.metric("Best Calmar Split", best_calmar["label"], f"Calmar {best_calmar['calmar']:.2f}")
        c3.metric("Full Both Sharpe", f"{full_both['sharpe']:.2f}",
                  f"DD {fmt_inr(full_both['max_dd'])}")

        fig_w = make_subplots(rows=1, cols=2, subplot_titles=["Sharpe by Weight Split", "Max DD by Weight Split"])
        split_only = weights[weights["label"] != "100/100 (full both)"]
        fig_w.add_trace(go.Scatter(
            x=split_only["w_a"], y=split_only["sharpe"],
            mode="lines+markers", line=dict(color=GREEN, width=2), name="Sharpe",
        ), row=1, col=1)
        fig_w.add_trace(go.Scatter(
            x=split_only["w_a"], y=split_only["max_dd"],
            mode="lines+markers", line=dict(color=RED, width=2), name="Max DD",
        ), row=1, col=2)
        fig_w.update_xaxes(title_text=f"Weight on {la}", tickformat=".0%")
        fig_w.update_yaxes(title_text="Sharpe", row=1, col=1)
        fig_w.update_yaxes(title_text="Max DD (₹)", tickprefix="₹", row=1, col=2)
        fig_w.update_layout(**PLOT_LAYOUT, height=320, showlegend=False)
        st.plotly_chart(fig_w, width="stretch")

        show = weights.copy()
        show["total_pl"] = show["total_pl"].astype(int)
        show["avg_day"] = show["avg_day"].astype(int)
        show["max_dd"] = show["max_dd"].astype(int)
        show["sharpe"] = show["sharpe"].round(2)
        show["calmar"] = show["calmar"].round(2)
        show["div_ratio"] = show["div_ratio"].round(3)
        show["max_dd_pct"] = show["max_dd_pct"].round(1)
        st.markdown("#### Weight Scan (A/B capital split + full-size both)")
        st.dataframe(
            show[["label", "total_pl", "avg_day", "sharpe", "max_dd", "max_dd_pct", "calmar", "div_ratio"]].rename(
                columns={"label": "Split (A/B)", "total_pl": "Total P&L", "avg_day": "Avg/Day",
                         "max_dd": "Max DD", "max_dd_pct": "DD %", "div_ratio": "Div Ratio"}
            ),
            hide_index=True, width="stretch",
        )
        st.caption("Div Ratio = combined vol / weighted sum of individual vols. Lower = better diversification benefit.")

        # Interactive weight slider
        st.markdown("#### Custom Weight Preview")
        w_a = st.slider(f"Weight on {la}", 0.0, 1.0, float(best_sharpe["w_a"]), 0.05)
        w_b = 1.0 - w_a
        pl_custom = w_a * merged[f"PL_{na}"] + w_b * merged[f"PL_{nb}"]
        cum_custom = pl_custom.cumsum()
        std_c = pl_custom.std()
        sharpe_c = pl_custom.mean() / std_c * np.sqrt(252) if std_c > 0 else 0
        max_dd_c = (cum_custom - cum_custom.cummax()).min()
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Split", f"{int(w_a*100)}/{int(w_b*100)}")
        cc2.metric("Total P&L", fmt_inr(pl_custom.sum()))
        cc3.metric("Sharpe", f"{sharpe_c:.2f}")
        cc4.metric("Max DD", fmt_inr(max_dd_c))

    # ── Regime Analysis ───────────────────────────────────────────────────────────
    with tab_regime:
        regime = data["regime"]
        vix_reg = regime[regime["Type"] == "VIX"].copy()
        dow_reg = regime[regime["Type"] == "DOW"].copy()

        st.markdown("#### By VIX Zone")
        if not vix_reg.empty:
            fig_v = go.Figure()
            fig_v.add_trace(go.Bar(name=la, x=vix_reg["Regime"], y=vix_reg[f"Avg_{na}"], marker_color=BLUE))
            fig_v.add_trace(go.Bar(name=lb, x=vix_reg["Regime"], y=vix_reg[f"Avg_{nb}"], marker_color=PURPLE))
            fig_v.add_trace(go.Bar(name="Combined", x=vix_reg["Regime"], y=vix_reg["Avg_Combined"], marker_color=GREEN))
            fig_v.add_hline(y=0, line_color=MUTED, line_dash="dash")
            fig_v.update_layout(**PLOT_LAYOUT, height=300, barmode="group",
                                  title="Avg Daily P&L by VIX Zone", legend=dict(font=dict(color=TEXT_COL)))
            fig_v.update_yaxes(tickprefix="₹")
            st.plotly_chart(fig_v, width="stretch")

        st.markdown("#### By Day of Week")
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        dow_reg["order"] = dow_reg["Regime"].map({d: i for i, d in enumerate(dow_order)})
        dow_reg = dow_reg.sort_values("order")
        if not dow_reg.empty:
            fig_d = go.Figure()
            fig_d.add_trace(go.Bar(name=la, x=dow_reg["Regime"], y=dow_reg[f"Avg_{na}"], marker_color=BLUE))
            fig_d.add_trace(go.Bar(name=lb, x=dow_reg["Regime"], y=dow_reg[f"Avg_{nb}"], marker_color=PURPLE))
            fig_d.add_trace(go.Bar(name="Combined", x=dow_reg["Regime"], y=dow_reg["Avg_Combined"], marker_color=GREEN))
            fig_d.add_hline(y=0, line_color=MUTED, line_dash="dash")
            fig_d.update_layout(**PLOT_LAYOUT, height=300, barmode="group",
                                  title="Avg Daily P&L by Weekday", legend=dict(font=dict(color=TEXT_COL)))
            fig_d.update_yaxes(tickprefix="₹")
            st.plotly_chart(fig_d, width="stretch")

        vix_show = vix_reg[["Regime", "Days", f"Avg_{na}", f"Avg_{nb}", "Avg_Combined", "WinRate_Combined"]].copy()
        for c in [f"Avg_{na}", f"Avg_{nb}", "Avg_Combined"]:
            vix_show[c] = vix_show[c].round(0).astype(int)
        vix_show["WinRate_Combined"] = vix_show["WinRate_Combined"].round(1)
        vix_show.columns = ["VIX Zone", "Days", la, lb, "Combined", "Combined WR %"]
        st.dataframe(vix_show, hide_index=True, width="stretch")
