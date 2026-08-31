"""Shared Backtest / Live / Compare tabs (strangle & theta)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from theme import GREEN, RED, GOLD, BLUE, MUTED, TEXT as TEXT_COL, GRID as GRID_COL


def render_strategy_tabs(
    bt: pd.DataFrame,
    live: pd.DataFrame,
    live_daily: pd.DataFrame,
    *,
    capital: float = 550_000,
    plot_layout: dict,
    legend: dict,
    render_table,
    dow_caption: str = "Tuesday = NIFTY expiry  |  Thursday = SENSEX expiry",
    day_cat_caption: str | None = None,
    day_cat_order: list[str] | None = None,
    live_log_columns: list[str] | None = None,
    live_empty_hint: str | None = None,
    expiry_days: dict[str, str] | None = None,
    dte_map: dict[str, dict[str, int]] | None = None,
):
    """Render 📊 Backtest · 🟢 Live · 🔍 Compare — same layout as strangle tab.

    expiry_days: {weekday: label} for expiry-day highlighting in the DOW charts
        and the Expiry column (e.g. {"Tuesday": "🟡 NIFTY", "Thursday": "🟡 SENSEX"}).
        Defaults to Thursday=SENSEX only.
    dte_map: {weekday: {"NIFTY DTE": int, "SENSEX DTE": int}} for the DOW table.
    day_cat_order: category labels for the Day Category breakdown (strangle uses
        50% SL wording; theta uses ₹50 SL wording).
    """
    if expiry_days is None:
        expiry_days = {"Thursday": "🟡 SENSEX"}
    if dte_map is None:
        dte_map = {
            "Monday": {"NIFTY DTE": 1, "SENSEX DTE": 3},
            "Tuesday": {"NIFTY DTE": 0, "SENSEX DTE": 2},
            "Wednesday": {"NIFTY DTE": 6, "SENSEX DTE": 1},
            "Thursday": {"NIFTY DTE": 5, "SENSEX DTE": 0},
            "Friday": {"NIFTY DTE": 4, "SENSEX DTE": 6},
        }
    if day_cat_order is None:
        day_cat_order = [
            "Both Clean", "1 Instr: 50% SL only", "Both: 50% SL only",
            "1 Instr: 50%+BE hit", "Mixed: 50%+BE + 50%SL", "Both: 50%+BE hit",
        ]
    tab_bt, tab_live, tab_compare = st.tabs(
        ["📊 Backtest", "🟢 Live Trading", "🔍 Backtest vs Live"]
    )

    live_days = len(live_daily)
    live_wins = live_daily["Win"].sum() if live_days else 0
    live_total = live_daily["Day_PL"].sum() if live_days else 0
    live_wr = live_wins / live_days * 100 if live_days else 0
    live_charges = (
        float(pd.to_numeric(live["Charges"], errors="coerce").fillna(0).sum())
        if live_days and not live.empty and "Charges" in live.columns
        else 0.0
    )
    live_gross = live_total + live_charges if live_charges else live_total
    bt_avg_day = bt["PL"].mean()
    expected = bt_avg_day * live_days if live_days else 0

    # ── BACKTEST ──────────────────────────────────────────────────────────────
    with tab_bt:
        total_days = len(bt)
        win_days = bt["Win"].sum()
        loss_days = total_days - win_days
        win_rate = win_days / total_days * 100
        avg_win = bt[bt["Win"]]["PL"].mean()
        avg_loss = bt[~bt["Win"]]["PL"].mean()
        total_pl = bt["PL"].sum()
        pf = bt[bt["Win"]]["PL"].sum() / abs(bt[~bt["Win"]]["PL"].sum())
        sharpe = (bt["PL"].mean() / bt["PL"].std()) * (252 ** 0.5)
        roll_max = bt["Cumulative"].cummax()
        max_dd = (bt["Cumulative"] - roll_max).min()
        best_day = bt["PL"].max()
        worst_day = bt["PL"].min()

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Win Rate", f"{win_rate:.1f}%", f"{win_days}W / {loss_days}L")
        c2.metric(
            "Total P&L", f"₹{total_pl:,.0f}",
            f"{bt['Date'].min().strftime('%b %Y')} – {bt['Date'].max().strftime('%b %Y')}",
        )
        c3.metric("Sharpe Ratio", f"{sharpe:.2f}", "annualised")
        c4.metric("Profit Factor", f"{pf:.2f}", f"Best ₹{best_day:,.0f} / Worst ₹{worst_day:,.0f}")
        c5.metric("Max Drawdown", f"₹{max_dd:,.0f}", f"{(max_dd / capital) * 100:.1f}% of ₹{capital/100_000:.1f}L capital")
        c6.metric("Avg Win / Loss", f"{avg_win / abs(avg_loss):.2f}×", f"₹{avg_win:,.0f} / ₹{avg_loss:,.0f}")

        st.markdown("<br>", unsafe_allow_html=True)

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=bt["Date"], y=bt["Cumulative"],
            mode="lines", line=dict(color=GREEN, width=2),
            fill="tozeroy", fillcolor="rgba(57,211,83,0.1)",
            name="Cumulative P&L",
            hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>",
        ))
        fig_eq.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
        fig_eq.update_layout(**plot_layout, height=300,
                             title=dict(text="Cumulative P&L — Backtest", font=dict(size=14)))
        fig_eq.update_xaxes(tickformat="%b %Y")
        fig_eq.update_yaxes(tickprefix="₹", tickformat=",.0f")
        st.plotly_chart(fig_eq, width="stretch")

        col_left, col_right = st.columns([2, 1])
        with col_left:
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(
                x=bt[bt["Win"]]["PL"], xbins=dict(size=500),
                marker_color=GREEN, opacity=0.85, name="Win days",
            ))
            fig_hist.add_trace(go.Histogram(
                x=bt[~bt["Win"]]["PL"], xbins=dict(size=500),
                marker_color=RED, opacity=0.85, name="Loss days",
            ))
            fig_hist.add_vline(x=avg_win, line_color=GREEN, line_dash="dot", line_width=1.5)
            fig_hist.add_vline(x=avg_loss, line_color=RED, line_dash="dot", line_width=1.5)
            fig_hist.add_vline(x=0, line_color="white", line_dash="dash", line_width=0.8)
            fig_hist.update_layout(**plot_layout, height=280, barmode="overlay",
                                   title=dict(text="Daily P&L Distribution", font=dict(size=14)),
                                   legend=legend)
            fig_hist.update_xaxes(tickprefix="₹", tickformat=",.0f")
            fig_hist.update_yaxes(title_text="Days")
            st.plotly_chart(fig_hist, width="stretch")

        with col_right:
            bt_m = bt.copy()
            bt_m["Month"] = bt_m["Date"].dt.to_period("M")
            monthly = bt_m.groupby("Month")["PL"].sum().reset_index()
            monthly["Month_str"] = monthly["Month"].astype(str)
            monthly["Color"] = monthly["PL"].apply(lambda x: GREEN if x >= 0 else RED)
            fig_m = go.Figure(go.Bar(
                x=monthly["Month_str"], y=monthly["PL"],
                marker_color=monthly["Color"], opacity=0.85,
                hovertemplate="%{x}<br>₹%{y:,.0f}<extra></extra>",
            ))
            fig_m.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
            fig_m.update_layout(**plot_layout, height=280, title=dict(text="Monthly P&L", font=dict(size=14)))
            fig_m.update_xaxes(tickangle=90, tickfont=dict(size=8))
            fig_m.update_yaxes(tickprefix="₹", tickformat=",.0f")
            st.plotly_chart(fig_m, width="stretch")

        st.markdown("#### Day Category Breakdown")
        if day_cat_caption:
            st.caption(day_cat_caption)
        cat_colors = [GREEN, "#2ea043", GOLD, BLUE, "#ff7b54", RED]
        rows = []
        for cat in day_cat_order:
            d = bt[bt["Day_Cat"] == cat]
            if d.empty:
                continue
            wins_c = d["Win"].sum()
            losses_c = len(d) - wins_c
            rows.append({
                "Category": cat,
                "Days": len(d),
                "Days (%)": round(len(d) / total_days * 100, 1),
                "Win Rate (%)": round(wins_c / len(d) * 100, 1),
                "W/L": f"{wins_c}/{losses_c}",
                "Avg Day (₹)": int(round(d["PL"].mean(), 0)),
                "Total P&L (₹)": int(round(d["PL"].sum(), 0)),
                "Contribution (%)": round(d["PL"].sum() / total_pl * 100, 1) if total_pl else 0,
            })
        cat_df = pd.DataFrame(rows)
        col_tbl, col_pie = st.columns([3, 2])
        with col_tbl:
            render_table(cat_df)
        with col_pie:
            if rows:
                fig_pie = go.Figure(go.Pie(
                    labels=[r["Category"] for r in rows],
                    values=[int(r["Days"]) for r in rows],
                    marker_colors=cat_colors[:len(rows)],
                    hole=0.55, textinfo="label+percent", textfont=dict(size=10),
                    hovertemplate="%{label}<br>%{value} days (%{percent})<extra></extra>",
                ))
                fig_pie.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False, height=280,
                    margin=dict(l=10, r=10, t=30, b=10),
                    title=dict(text="Day Mix", font=dict(size=14)),
                )
                st.plotly_chart(fig_pie, width="stretch")

        st.markdown("#### VIX Analysis")
        vix_grp = bt.groupby("VIX_Bucket", observed=True).agg(
            Days=("PL", "count"), Win_Rate=("Win", "mean"),
            Avg_PL=("PL", "mean"), Total_PL=("PL", "sum"),
        ).reset_index()
        vix_grp["Win_Rate_pct"] = vix_grp["Win_Rate"] * 100
        col_vb, col_vs = st.columns(2)
        with col_vb:
            fig_vb = go.Figure()
            bar_colors = [GREEN if v >= 0 else RED for v in vix_grp["Avg_PL"]]
            fig_vb.add_trace(go.Bar(
                x=vix_grp["VIX_Bucket"].astype(str), y=vix_grp["Avg_PL"],
                marker_color=bar_colors, opacity=0.85,
                text=[f"₹{v:,.0f}" for v in vix_grp["Avg_PL"]],
                textposition="outside", textfont=dict(color=TEXT_COL),
            ))
            fig_vb.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
            fig_vb.update_layout(**plot_layout, height=280,
                                 title=dict(text="Avg Day P&L by VIX Zone", font=dict(size=14)))
            fig_vb.update_yaxes(tickprefix="₹", tickformat=",.0f")
            st.plotly_chart(fig_vb, width="stretch")
        with col_vs:
            fig_vw = go.Figure()
            fig_vw.add_trace(go.Bar(
                x=vix_grp["VIX_Bucket"].astype(str), y=vix_grp["Win_Rate_pct"],
                marker_color=BLUE, opacity=0.85,
                text=[f"{v:.1f}%" for v in vix_grp["Win_Rate_pct"]],
                textposition="outside", textfont=dict(color=TEXT_COL),
            ))
            fig_vw.add_hline(y=50, line_color=MUTED, line_dash="dot", line_width=0.8)
            fig_vw.update_layout(**plot_layout, height=280,
                                 title=dict(text="Win Rate by VIX Zone", font=dict(size=14)))
            fig_vw.update_yaxes(title_text="Win Rate %", range=[0, 100])
            st.plotly_chart(fig_vw, width="stretch")

        vix_table = vix_grp.copy()
        vix_table["Win Rate (%)"] = vix_table["Win_Rate_pct"].round(1)
        vix_table["Avg P&L (₹)"] = vix_table["Avg_PL"].round(0).astype(int)
        vix_table["Total P&L (₹)"] = vix_table["Total_PL"].round(0).astype(int)
        vix_table["Days (%)"] = (vix_table["Days"] / total_days * 100).round(1)
        render_table(vix_table[["VIX_Bucket", "Days", "Days (%)", "Win Rate (%)", "Avg P&L (₹)", "Total P&L (₹)"]].rename(
            columns={"VIX_Bucket": "VIX Zone"}))

        st.markdown("#### Day of Week Performance")
        st.caption(dow_caption)
        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        dow_grp = bt.groupby("DOW").agg(
            Days=("PL", "count"), Win_Rate=("Win", "mean"),
            Avg_PL=("PL", "mean"), Total_PL=("PL", "sum"),
            Best=("PL", "max"), Worst=("PL", "min"),
        ).reindex(dow_order).reset_index()
        dow_grp["Win_Rate_pct"] = dow_grp["Win_Rate"] * 100
        expiry_colors = [GOLD if d in expiry_days else BLUE for d in dow_grp["DOW"]]

        col_da, col_dw = st.columns(2)
        with col_da:
            fig_da = go.Figure()
            fig_da.add_trace(go.Bar(
                x=dow_grp["DOW"], y=dow_grp["Avg_PL"],
                marker_color=expiry_colors, opacity=0.85,
                text=[f"₹{v:,.0f}" for v in dow_grp["Avg_PL"]],
                textposition="outside", textfont=dict(color=TEXT_COL),
            ))
            fig_da.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
            fig_da.update_layout(**plot_layout, height=280,
                                 title=dict(text="Avg Day P&L by Weekday  (🟡 = expiry day)", font=dict(size=14)))
            fig_da.update_yaxes(tickprefix="₹", tickformat=",.0f")
            st.plotly_chart(fig_da, width="stretch")
        with col_dw:
            fig_dw = go.Figure()
            fig_dw.add_trace(go.Bar(
                x=dow_grp["DOW"], y=dow_grp["Win_Rate_pct"],
                marker_color=expiry_colors, opacity=0.85,
                text=[f"{v:.1f}%" for v in dow_grp["Win_Rate_pct"]],
                textposition="outside", textfont=dict(color=TEXT_COL),
            ))
            fig_dw.add_hline(y=50, line_color=MUTED, line_dash="dot", line_width=0.8)
            fig_dw.update_layout(**plot_layout, height=280,
                                 title=dict(text="Win Rate by Weekday  (🟡 = expiry day)", font=dict(size=14)))
            fig_dw.update_yaxes(title_text="Win Rate %", range=[0, 100])
            st.plotly_chart(fig_dw, width="stretch")

        dte = dte_map
        dow_table = dow_grp.copy()
        dow_table["Expiry"] = dow_table["DOW"].apply(lambda d: expiry_days.get(d, "—"))
        dow_table["NIFTY DTE"] = dow_table["DOW"].map(lambda d: dte.get(d, {}).get("NIFTY DTE", "—"))
        dow_table["SENSEX DTE"] = dow_table["DOW"].map(lambda d: dte.get(d, {}).get("SENSEX DTE", "—"))
        dow_table["Win Rate (%)"] = dow_table["Win_Rate_pct"].round(1)
        dow_table["Avg P&L (₹)"] = dow_table["Avg_PL"].round(0).astype(int)
        dow_table["Total P&L (₹)"] = dow_table["Total_PL"].round(0).astype(int)
        dow_table["Best Day (₹)"] = dow_table["Best"].round(0).astype(int)
        dow_table["Worst Day (₹)"] = dow_table["Worst"].round(0).astype(int)
        render_table(dow_table[[
            "DOW", "Expiry", "NIFTY DTE", "SENSEX DTE", "Days", "Win Rate (%)",
            "Avg P&L (₹)", "Total P&L (₹)", "Best Day (₹)", "Worst Day (₹)",
        ]].rename(columns={"DOW": "Day"}))

    # ── LIVE ──────────────────────────────────────────────────────────────────
    with tab_live:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric(
            "Live Days", str(live_days),
            f"since {live_daily['Date'].min().strftime('%d %b %Y')}" if live_days > 0 else "—",
        )
        c2.metric(
            "Live P&L (net)", f"₹{live_total:,.0f}",
            f"{'↑' if live_total >= 0 else '↓'} vs expected ₹{expected:,.0f}" if live_days else "—",
        )
        c3.metric(
            "Charges",
            f"₹{live_charges:,.0f}" if live_days else "—",
            f"gross ₹{live_gross:,.0f}" if live_days and live_charges else "Flattrade statutory",
        )
        c4.metric("Win Rate", f"{live_wr:.1f}%", f"{live_wins}W / {live_days - live_wins}L" if live_days else "—")
        live_avg_day = live_total / live_days if live_days else 0
        gap = live_avg_day - bt_avg_day if live_days else 0
        c5.metric(
            "Avg/Day",
            f"₹{live_avg_day:,.0f}" if live_days else "—",
            (
                f"live · BT ₹{bt_avg_day:,.0f} ({'↑' if gap >= 0 else '↓'}₹{abs(gap):,.0f})"
                if live_days
                else "—"
            ),
        )

        st.markdown("<br>", unsafe_allow_html=True)

        if live_days == 0 and live_empty_hint:
            st.info(live_empty_hint)

        col_eq, col_vix = st.columns([3, 2])
        with col_eq:
            fig_live = go.Figure()
            if live_days > 0:
                expected_line = [bt_avg_day * (i + 1) for i in range(live_days)]
                fig_live.add_trace(go.Scatter(
                    x=live_daily["Date"], y=expected_line,
                    mode="lines", line=dict(color=MUTED, width=1.5, dash="dot"),
                    name="Backtest Expected",
                ))
                color_actual = GREEN if live_total >= 0 else RED
                fig_live.add_trace(go.Scatter(
                    x=live_daily["Date"], y=live_daily["Cumulative"],
                    mode="lines+markers", line=dict(color=color_actual, width=2.5),
                    marker=dict(size=8, color=color_actual), name="Actual",
                ))
            fig_live.add_hline(y=0, line_color=MUTED, line_dash="dash", line_width=0.8)
            fig_live.update_layout(**plot_layout, height=280,
                                   title=dict(text="Live Cumulative P&L vs Expected", font=dict(size=14)),
                                   legend=legend)
            fig_live.update_yaxes(tickprefix="₹", tickformat=",.0f")
            st.plotly_chart(fig_live, width="stretch")

        with col_vix:
            fig_vix = go.Figure()
            if live_days > 0 and "VIX_Close" in live_daily.columns:
                bar_colors = [GREEN if p >= 0 else RED for p in live_daily["Day_PL"]]
                fig_vix.add_trace(go.Bar(
                    x=live_daily["Date"], y=live_daily["Day_PL"],
                    marker_color=bar_colors, opacity=0.85, name="Day P&L",
                ))
                fig_vix.add_trace(go.Scatter(
                    x=live_daily["Date"], y=live_daily["VIX_Close"],
                    mode="lines+markers", yaxis="y2",
                    line=dict(color=GOLD, width=2), marker=dict(size=6), name="VIX Close",
                ))
            fig_vix.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=TEXT_COL, size=12),
                margin=dict(l=50, r=50, t=40, b=40), height=280,
                title=dict(text="Day P&L vs VIX", font=dict(size=14, color=TEXT_COL)),
                xaxis=dict(gridcolor=GRID_COL, zeroline=False, tickfont=dict(color=TEXT_COL)),
                yaxis=dict(title="P&L (₹)", gridcolor=GRID_COL, tickprefix="₹", zeroline=False,
                           tickfont=dict(color=TEXT_COL), title_font=dict(color=TEXT_COL)),
                yaxis2=dict(title="VIX", overlaying="y", side="right",
                            gridcolor="rgba(0,0,0,0)", zeroline=False,
                            tickfont=dict(color=GOLD), title_font=dict(color=GOLD)),
                legend=legend,
            )
            st.plotly_chart(fig_vix, width="stretch")

        st.markdown("#### Trade Log")
        if live_days > 0 and not live.empty:
            log_display = live.copy()
            log_display["Date"] = log_display["Date"].dt.strftime("%d-%b-%Y")
            cols = live_log_columns or [
                "Date", "Index", "Type", "Strike", "Entry_Price", "Entry_Time",
                "Exit_Price", "Exit_Time", "Exit_Reason", "PL", "Instr_Category", "Day_Category",
            ]
            cols = [c for c in cols if c in log_display.columns]
            render_table(log_display[cols].rename(columns={
                "Entry_Price": "Entry", "Entry_Time": "E.Time",
                "Exit_Price": "Exit", "Exit_Time": "X.Time",
                "Exit_Reason": "Reason", "Instr_Category": "Instr Cat",
                "Day_Category": "Day Cat",
            }))
        else:
            st.caption("No live trades logged yet.")

        st.markdown("#### Day Summary")
        if live_days > 0:
            day_summary = live_daily.copy()
            day_summary["Date_fmt"] = day_summary["Date"].dt.strftime("%d-%b-%Y (%a)")
            day_summary["Result"] = day_summary["Day_PL"].apply(lambda x: "✅ Win" if x > 0 else "❌ Loss")
            sum_cols = ["Date_fmt", "Result", "Day_PL", "Cumulative", "Day_Category"]
            if "VIX_Open" in day_summary.columns:
                sum_cols += ["VIX_Open", "VIX_Close", "VIX_Change_Pct"]
            render_table(day_summary[sum_cols].rename(columns={
                "Date_fmt": "Date", "Day_PL": "Day P&L (₹)",
                "Cumulative": "Running Total (₹)", "Day_Category": "Category",
                "VIX_Change_Pct": "VIX Chg (%)",
            }))
        else:
            st.caption("No live days yet.")

    # ── COMPARE ───────────────────────────────────────────────────────────────
    with tab_compare:
        st.markdown("#### Live vs Backtest — Category Distribution")
        bt_cats = bt.groupby("Day_Cat").agg(
            Days=("PL", "count"), Total_PL=("PL", "sum"), Avg_PL=("PL", "mean"),
        ).reset_index()
        bt_cats["Win_Rate"] = bt.groupby("Day_Cat")["Win"].mean().values * 100
        if day_cat_order:
            bt_cats["_ord"] = bt_cats["Day_Cat"].apply(
                lambda c: day_cat_order.index(c) if c in day_cat_order else 99
            )
            bt_cats = bt_cats.sort_values("_ord").drop(columns="_ord")

        if live_days > 0:
            live_cat_grp = live_daily.groupby("Day_Category").agg(
                Days=("Day_PL", "count"), Total_PL=("Day_PL", "sum"), Avg_PL=("Day_PL", "mean"),
            ).reset_index().rename(columns={"Day_Category": "Day_Cat"})
            live_cat_grp["Win_Rate"] = live_daily.groupby("Day_Category")["Win"].mean().values * 100
            if day_cat_order:
                live_cat_grp["_ord"] = live_cat_grp["Day_Cat"].apply(
                    lambda c: day_cat_order.index(c) if c in day_cat_order else 99
                )
                live_cat_grp = live_cat_grp.sort_values("_ord").drop(columns="_ord")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Backtest**")
                bt_show = bt_cats[["Day_Cat", "Days", "Win_Rate", "Avg_PL"]].copy()
                bt_show["Win_Rate"] = bt_show["Win_Rate"].round(1)
                bt_show["Avg_PL"] = bt_show["Avg_PL"].round(0).astype(int)
                render_table(bt_show.rename(columns={
                    "Day_Cat": "Category", "Win_Rate": "Win Rate (%)", "Avg_PL": "Avg P&L (₹)",
                }))
            with col2:
                st.markdown("**Live**")
                live_show = live_cat_grp[["Day_Cat", "Days", "Win_Rate", "Avg_PL"]].copy()
                live_show["Win_Rate"] = live_show["Win_Rate"].round(1)
                live_show["Avg_PL"] = live_show["Avg_PL"].round(0).astype(int)
                render_table(live_show.rename(columns={
                    "Day_Cat": "Category", "Win_Rate": "Win Rate (%)", "Avg_PL": "Avg P&L (₹)",
                }))
        else:
            st.info("Live category comparison will appear once trades are logged.")

        st.markdown("#### Slippage Tracker")
        st.caption("Difference between live fill prices and backtest assumed prices — to be populated as data grows")
        if live_days >= 5:
            live_avg = live_daily["Day_PL"].mean()
            slippage = live_avg - bt_avg_day
            c1, c2, c3 = st.columns(3)
            c1.metric("Live Avg/Day", f"₹{live_avg:,.0f}")
            c2.metric("Backtest Avg/Day", f"₹{bt_avg_day:,.0f}")
            c3.metric("Gap (Slippage est)", f"₹{slippage:,.0f}",
                      f"{'Better' if slippage >= 0 else 'Worse'} than backtest")
        else:
            st.info(f"Need at least 5 live days for meaningful slippage estimate. Currently: {live_days} days.")

        st.markdown("#### Running P&L Tracker")
        track_data = {
            "Metric": ["Days traded", "Wins", "Losses", "Win Rate", "Total P&L", "Avg/Day", "Backtest Expected", "vs Expected"],
            "Live": [
                str(live_days), str(int(live_wins)), str(int(live_days - live_wins)),
                f"{live_wr:.1f}%", f"₹{live_total:,.0f}",
                f"₹{live_daily['Day_PL'].mean():,.0f}" if live_days else "—",
                f"₹{expected:,.0f}" if live_days else "—",
                f"₹{live_total - expected:,.0f}" if live_days else "—",
            ],
            "Backtest": [
                str(len(bt)), str(int(bt["Win"].sum())), str(int(len(bt) - bt["Win"].sum())),
                f"{bt['Win'].mean() * 100:.1f}%", f"₹{bt['PL'].sum():,.0f}",
                f"₹{bt_avg_day:,.0f}", "—", "—",
            ],
        }
        render_table(pd.DataFrame(track_data))
