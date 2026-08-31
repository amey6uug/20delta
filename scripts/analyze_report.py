import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
from matplotlib.patches import FancyBboxPatch
import warnings
warnings.filterwarnings('ignore')

# ── Load & parse ──────────────────────────────────────────────────────────────
df = pd.read_csv(r'c:\Users\visha\Desktop\Algotest OS\bothNifty_Sensex_945.csv')
df.columns = df.columns.str.strip()

# Parent rows = whole-number index (1.0, 2.0 ...), child rows = fractional (1.1, 1.2 ...)
df['_idx'] = pd.to_numeric(df['Index'], errors='coerce')
parent = df[df['_idx'] == df['_idx'].apply(np.floor)].copy()
child  = df[df['_idx'] != df['_idx'].apply(np.floor)].copy()

parent['PL'] = pd.to_numeric(parent['P/L'], errors='coerce')
parent['Date'] = pd.to_datetime(parent['Entry Date'].str.strip(), dayfirst=True)
parent['VIX'] = pd.to_numeric(parent['Vix'].replace('NA', np.nan), errors='coerce')
parent['idx_str'] = parent['_idx'].astype(int).astype(str)

child['parent_idx'] = child['_idx'].apply(lambda x: str(int(np.floor(x))))
child['Strike'] = pd.to_numeric(child['Strike'], errors='coerce')

def guess_instrument(parent_idx, child_df):
    legs = child_df[child_df['parent_idx'] == str(parent_idx)]
    if legs.empty:
        return 'Unknown'
    avg_strike = legs['Strike'].mean()
    return 'SENSEX' if avg_strike > 40000 else 'NIFTY'

parent['Instrument'] = parent['idx_str'].apply(lambda x: guess_instrument(x, child))

# Combine both instruments per date → daily combined P&L
daily = parent.groupby('Date').agg(
    Combined_PL=('PL', 'sum'),
    VIX=('VIX', 'first')
).reset_index().sort_values('Date')

daily = daily.dropna(subset=['Combined_PL']).reset_index(drop=True)
daily['Cumulative_PL'] = daily['Combined_PL'].cumsum()
daily['Win'] = daily['Combined_PL'] > 0

# ── Stats ─────────────────────────────────────────────────────────────────────
total_days      = len(daily)
win_days        = daily['Win'].sum()
loss_days       = total_days - win_days
win_rate        = win_days / total_days * 100
avg_win         = daily[daily['Win']]['Combined_PL'].mean()
avg_loss        = daily[~daily['Win']]['Combined_PL'].mean()
best_day        = daily['Combined_PL'].max()
worst_day       = daily['Combined_PL'].min()
total_pnl       = daily['Combined_PL'].sum()
profit_factor   = (daily[daily['Win']]['Combined_PL'].sum() /
                   abs(daily[~daily['Win']]['Combined_PL'].sum()))
sharpe          = (daily['Combined_PL'].mean() / daily['Combined_PL'].std()) * np.sqrt(252)

# Max drawdown
roll_max = daily['Cumulative_PL'].cummax()
drawdown = daily['Cumulative_PL'] - roll_max
max_dd   = drawdown.min()

# Monthly P&L
daily['Month'] = daily['Date'].dt.to_period('M')
monthly = daily.groupby('Month')['Combined_PL'].sum()

# Win/loss streak
streaks = []
current, count = None, 0
for w in daily['Win']:
    if w == current:
        count += 1
    else:
        if current is not None:
            streaks.append((current, count))
        current, count = w, 1
if current is not None:
    streaks.append((current, count))
max_win_streak  = max((c for w, c in streaks if w), default=0)
max_loss_streak = max((c for w, c in streaks if not w), default=0)

# P&L buckets for histogram
bin_min = float(int(daily['Combined_PL'].min() // 500) * 500)
bin_max = float(int(daily['Combined_PL'].max() // 500 + 2) * 500)
bins = np.arange(bin_min, bin_max, 500.0)

import sys
sys.stdout.reconfigure(encoding='utf-8')

stats_text = (
    "==================================================\n"
    "  BOTH NIFTY + SENSEX  |  9:45 Strangle  |  Backtest\n"
    "==================================================\n"
    f"  Period       : {daily['Date'].min().date()} to {daily['Date'].max().date()}\n"
    f"  Trading Days : {total_days}\n"
    f"  Win Days     : {win_days}  ({win_rate:.1f}%)\n"
    f"  Loss Days    : {loss_days}  ({100-win_rate:.1f}%)\n"
    f"  Avg Win      : Rs {avg_win:,.0f}\n"
    f"  Avg Loss     : Rs {avg_loss:,.0f}\n"
    f"  Best Day     : Rs {best_day:,.0f}\n"
    f"  Worst Day    : Rs {worst_day:,.0f}\n"
    f"  Win/Loss     : {avg_win/abs(avg_loss):.2f}x\n"
    f"  Profit Factor: {profit_factor:.2f}\n"
    f"  Max Win Str  : {max_win_streak} days\n"
    f"  Max Loss Str : {max_loss_streak} days\n"
    f"  Sharpe       : {sharpe:.2f}\n"
    f"  Max Drawdown : Rs {max_dd:,.0f}\n"
    f"  Total P&L    : Rs {total_pnl:,.0f}\n"
    "==================================================\n"
)
print(stats_text)

# ── Chart ─────────────────────────────────────────────────────────────────────
DARK_BG   = '#0d1117'
CARD_BG   = '#161b22'
GREEN     = '#39d353'
RED       = '#f85149'
GOLD      = '#e3b341'
BLUE      = '#58a6ff'
PURPLE    = '#bc8cff'
MUTED     = '#8b949e'
WHITE     = '#f0f6fc'

fig = plt.figure(figsize=(20, 24), facecolor=DARK_BG)
fig.suptitle('Both NIFTY + SENSEX  |  9:45 Strangle  |  Backtest Report',
             color=WHITE, fontsize=18, fontweight='bold', y=0.98)

gs = gridspec.GridSpec(4, 3, figure=fig, hspace=0.45, wspace=0.35,
                       top=0.94, bottom=0.04, left=0.06, right=0.97)

# ── Helper: stat card ─────────────────────────────────────────────────────────
def stat_card(ax, label, value, color=WHITE, sub=None):
    ax.set_facecolor(CARD_BG)
    for spine in ax.spines.values():
        spine.set_edgecolor('#30363d')
    ax.set_xticks([]); ax.set_yticks([])
    ax.text(0.5, 0.62, value, transform=ax.transAxes,
            ha='center', va='center', fontsize=22, fontweight='bold', color=color)
    ax.text(0.5, 0.25, label, transform=ax.transAxes,
            ha='center', va='center', fontsize=10, color=MUTED)
    if sub:
        ax.text(0.5, 0.10, sub, transform=ax.transAxes,
                ha='center', va='center', fontsize=8, color=MUTED)

# Row 0 — stat cards
stat_card(fig.add_subplot(gs[0, 0]), 'Win Rate',
          f'{win_rate:.1f}%', GREEN,
          f'{win_days}W / {loss_days}L  of {total_days} days')
stat_card(fig.add_subplot(gs[0, 1]), 'Total P&L',
          f'₹{total_pnl:,.0f}', GREEN if total_pnl > 0 else RED)
stat_card(fig.add_subplot(gs[0, 2]), 'Profit Factor',
          f'{profit_factor:.2f}', GOLD)

# Row 1 — more stat cards
stat_card(fig.add_subplot(gs[1, 0]), 'Avg Win / Avg Loss',
          f'{avg_win/abs(avg_loss):.2f}×', BLUE,
          f'₹{avg_win:,.0f}  /  ₹{avg_loss:,.0f}')
stat_card(fig.add_subplot(gs[1, 1]), 'Max Drawdown',
          f'₹{max_dd:,.0f}', RED)
stat_card(fig.add_subplot(gs[1, 2]), 'Sharpe Ratio',
          f'{sharpe:.2f}', PURPLE)

# Row 2 — Equity curve (full width)
ax_eq = fig.add_subplot(gs[2, :])
ax_eq.set_facecolor(CARD_BG)
for spine in ax_eq.spines.values():
    spine.set_edgecolor('#30363d')

ax_eq.fill_between(daily['Date'], daily['Cumulative_PL'], 0,
                   where=daily['Cumulative_PL'] >= 0,
                   alpha=0.25, color=GREEN, interpolate=True)
ax_eq.fill_between(daily['Date'], daily['Cumulative_PL'], 0,
                   where=daily['Cumulative_PL'] < 0,
                   alpha=0.25, color=RED, interpolate=True)
ax_eq.plot(daily['Date'], daily['Cumulative_PL'], color=GREEN, linewidth=1.5)
ax_eq.axhline(0, color=MUTED, linewidth=0.6, linestyle='--')
ax_eq.set_title('Cumulative P&L', color=WHITE, fontsize=12, pad=8)
ax_eq.tick_params(colors=MUTED, labelsize=9)
ax_eq.set_ylabel('₹', color=MUTED, fontsize=10)
ax_eq.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'₹{x:,.0f}'))
ax_eq.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%b %Y'))
plt.setp(ax_eq.xaxis.get_majorticklabels(), rotation=30, ha='right')

# Row 3 — Daily P&L histogram | Monthly bar
ax_hist = fig.add_subplot(gs[3, 0:2])
ax_hist.set_facecolor(CARD_BG)
for spine in ax_hist.spines.values():
    spine.set_edgecolor('#30363d')

ax_hist.hist(daily[daily['Combined_PL'] >= 0]['Combined_PL'], bins=bins,
             color=GREEN, edgecolor=DARK_BG, linewidth=0.4, alpha=0.85, label='Win')
ax_hist.hist(daily[daily['Combined_PL'] < 0]['Combined_PL'], bins=bins,
             color=RED, edgecolor=DARK_BG, linewidth=0.4, alpha=0.85, label='Loss')
ax_hist.axvline(0, color=WHITE, linewidth=0.8, linestyle='--')
ax_hist.axvline(avg_win, color=GREEN, linewidth=1, linestyle=':', alpha=0.7)
ax_hist.axvline(avg_loss, color=RED, linewidth=1, linestyle=':', alpha=0.7)
ax_hist.set_title('Daily P&L Distribution', color=WHITE, fontsize=12, pad=8)
ax_hist.tick_params(colors=MUTED, labelsize=9)
ax_hist.set_xlabel('₹ P&L', color=MUTED, fontsize=9)
ax_hist.set_ylabel('Days', color=MUTED, fontsize=9)
ax_hist.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'₹{x:,.0f}'))

ax_month = fig.add_subplot(gs[3, 2])
ax_month.set_facecolor(CARD_BG)
for spine in ax_month.spines.values():
    spine.set_edgecolor('#30363d')

months_str = [str(m) for m in monthly.index]
bar_colors = [GREEN if v >= 0 else RED for v in monthly.values]
bars = ax_month.bar(range(len(monthly)), monthly.values,
                    color=bar_colors, alpha=0.85, edgecolor=DARK_BG, linewidth=0.4)
ax_month.axhline(0, color=MUTED, linewidth=0.6, linestyle='--')
ax_month.set_title('Monthly P&L', color=WHITE, fontsize=12, pad=8)
ax_month.set_xticks(range(len(monthly)))
ax_month.set_xticklabels([m[-5:] for m in months_str],
                          rotation=90, fontsize=6, color=MUTED)
ax_month.tick_params(axis='y', colors=MUTED, labelsize=8)
ax_month.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'₹{x/1000:.0f}k'))

out = r'c:\Users\visha\Desktop\Algotest OS\strangle_report.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=DARK_BG)
print(f'Saved → {out}')
