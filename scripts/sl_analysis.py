import pandas as pd
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv(r'c:\Users\visha\Desktop\Algotest OS\bothNifty_Sensex_945.csv')
df.columns = df.columns.str.strip()
df['_idx'] = pd.to_numeric(df['Index'], errors='coerce')

parent = df[df['_idx'] == df['_idx'].apply(np.floor)].copy()
child  = df[df['_idx'] != df['_idx'].apply(np.floor)].copy()

parent['PL']       = pd.to_numeric(parent['P/L'], errors='coerce')
parent['Date']     = pd.to_datetime(parent['Entry Date'].str.strip(), dayfirst=True)
parent['idx_str']  = parent['_idx'].astype(int).astype(str)

child['parent_idx'] = child['_idx'].apply(lambda x: str(int(np.floor(x))))
child['Exit Time']  = child['Exit Time'].str.strip()

# SL hit = leg exited before 3:15 PM (EOD)
# AlgoTest marks early exits as any time != 3:15:00 PM
EOD = '3:15:00 PM'
child['sl_hit'] = child['Exit Time'] != EOD

# Count SL hits per parent trade
sl_per_parent = child.groupby('parent_idx')['sl_hit'].sum().reset_index()
sl_per_parent.columns = ['idx_str', 'sl_count']

parent = parent.merge(sl_per_parent, on='idx_str', how='left')
parent['sl_count'] = parent['sl_count'].fillna(0).astype(int)

# Sum SL hits per day (both instruments combined)
daily = parent.groupby('Date').agg(
    Combined_PL=('PL', 'sum'),
    Total_SL_Hits=('sl_count', 'sum')
).reset_index().sort_values('Date')

daily = daily.dropna(subset=['Combined_PL']).reset_index(drop=True)
daily['Win'] = daily['Combined_PL'] > 0

# Classify: 0 SL hits = clean day, 1 SL hit = one leg stopped, 2+ = both legs stopped
daily['Category'] = daily['Total_SL_Hits'].apply(
    lambda x: 'No SL' if x == 0 else ('1 SL Hit' if x == 1 else '2 SL Hits')
)

print("\n--- SL Category Breakdown ---\n")
for cat in ['No SL', '1 SL Hit', '2 SL Hits']:
    d = daily[daily['Category'] == cat]
    if len(d) == 0:
        continue
    wins      = d['Win'].sum()
    losses    = len(d) - wins
    win_rate  = wins / len(d) * 100
    avg_win   = d[d['Win']]['Combined_PL'].mean() if wins > 0 else 0
    avg_loss  = d[~d['Win']]['Combined_PL'].mean() if losses > 0 else 0
    total_pl  = d['Combined_PL'].sum()
    avg_day   = d['Combined_PL'].mean()
    best      = d['Combined_PL'].max()
    worst     = d['Combined_PL'].min()
    print(f"  [{cat}]")
    print(f"    Days      : {len(d)}  ({len(d)/len(daily)*100:.1f}% of all days)")
    print(f"    Win Rate  : {win_rate:.1f}%  ({wins}W / {losses}L)")
    print(f"    Avg Win   : Rs {avg_win:,.0f}")
    print(f"    Avg Loss  : Rs {avg_loss:,.0f}")
    print(f"    Avg Day   : Rs {avg_day:,.0f}")
    print(f"    Best Day  : Rs {best:,.0f}")
    print(f"    Worst Day : Rs {worst:,.0f}")
    print(f"    Total P&L : Rs {total_pl:,.0f}  ({total_pl/daily['Combined_PL'].sum()*100:.1f}% of all P&L)")
    print()

print(f"  [ALL DAYS]")
print(f"    Days      : {len(daily)}")
print(f"    Win Rate  : {daily['Win'].mean()*100:.1f}%")
print(f"    Total P&L : Rs {daily['Combined_PL'].sum():,.0f}")
