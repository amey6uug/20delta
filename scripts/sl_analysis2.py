import pandas as pd
import numpy as np
import sys
sys.stdout.reconfigure(encoding='utf-8')

df = pd.read_csv(r'c:\Users\visha\Desktop\Algotest OS\bothNifty_Sensex_945.csv')
df.columns = df.columns.str.strip()
df['_idx'] = pd.to_numeric(df['Index'], errors='coerce')

parent = df[df['_idx'] == df['_idx'].apply(np.floor)].copy()
child  = df[df['_idx'] != df['_idx'].apply(np.floor)].copy()

parent['PL']      = pd.to_numeric(parent['P/L'], errors='coerce')
parent['Date']    = pd.to_datetime(parent['Entry Date'].str.strip(), dayfirst=True)
parent['idx_str'] = parent['_idx'].astype(int).astype(str)

child['parent_idx'] = child['_idx'].apply(lambda x: str(int(np.floor(x))))
child['Exit Time']  = child['Exit Time'].str.strip()
child['Strike']     = pd.to_numeric(child['Strike'], errors='coerce')

EOD = '3:15:00 PM'
child['sl_hit'] = child['Exit Time'] != EOD

# Per instrument: how many legs stopped
sl_per_parent = child.groupby('parent_idx')['sl_hit'].sum().reset_index()
sl_per_parent.columns = ['idx_str', 'legs_stopped']

parent = parent.merge(sl_per_parent, on='idx_str', how='left')
parent['legs_stopped'] = parent['legs_stopped'].fillna(0).astype(int)

# Label per-instrument scenario
# 0 = clean (no SL), 1 = only 50% SL hit (survivor ran to EOD), 2 = 50% SL + BE trail hit
parent['instr_cat'] = parent['legs_stopped'].map({
    0: 'Clean (0 SL)',
    1: '50% SL only',
    2: '50% SL + BE hit'
})

# Per-instrument stats
print("=== PER INSTRUMENT (each NIFTY/SENSEX trade separately) ===\n")
for cat in ['Clean (0 SL)', '50% SL only', '50% SL + BE hit']:
    d = parent[parent['instr_cat'] == cat]
    if len(d) == 0:
        continue
    wins     = (d['PL'] > 0).sum()
    losses   = len(d) - wins
    win_rate = wins / len(d) * 100
    avg_win  = d[d['PL'] > 0]['PL'].mean() if wins > 0 else 0
    avg_loss = d[d['PL'] <= 0]['PL'].mean() if losses > 0 else 0
    avg_day  = d['PL'].mean()
    total_pl = d['PL'].sum()
    print(f"  [{cat}]")
    print(f"    Occurrences : {len(d)}  ({len(d)/len(parent)*100:.1f}% of all instrument-days)")
    print(f"    Win Rate    : {win_rate:.1f}%  ({wins}W / {losses}L)")
    print(f"    Avg Win     : Rs {avg_win:,.0f}")
    print(f"    Avg Loss    : Rs {avg_loss:,.0f}")
    print(f"    Avg P&L     : Rs {avg_day:,.0f}")
    print(f"    Total P&L   : Rs {total_pl:,.0f}")
    print()

# Now per day: classify by what combination fired across both instruments
# Build per-day summary with each instrument's category
def guess_instrument(parent_idx, child_df):
    legs = child_df[child_df['parent_idx'] == str(parent_idx)]
    if legs.empty:
        return 'Unknown'
    return 'SENSEX' if legs['Strike'].mean() > 40000 else 'NIFTY'

parent['Instrument'] = parent['idx_str'].apply(lambda x: guess_instrument(x, child))

daily_wide = parent.pivot_table(
    index='Date', columns='Instrument',
    values=['PL', 'legs_stopped'], aggfunc='first'
).reset_index()

daily_wide.columns = ['_'.join(c).strip('_') if c[1] else c[0]
                      for c in daily_wide.columns]

# Rename for clarity
daily_wide = daily_wide.rename(columns={
    'PL_NIFTY': 'NIFTY_PL', 'PL_SENSEX': 'SENSEX_PL',
    'legs_stopped_NIFTY': 'NIFTY_SL', 'legs_stopped_SENSEX': 'SENSEX_SL'
})

daily_wide['Combined_PL'] = daily_wide['NIFTY_PL'].fillna(0) + daily_wide['SENSEX_PL'].fillna(0)
daily_wide['NIFTY_SL']    = daily_wide['NIFTY_SL'].fillna(0).astype(int)
daily_wide['SENSEX_SL']   = daily_wide['SENSEX_SL'].fillna(0).astype(int)

def day_cat(row):
    n, s = row['NIFTY_SL'], row['SENSEX_SL']
    # Both clean
    if n == 0 and s == 0: return 'Both Clean'
    # One instrument had only 50% SL (survivor ran), other was clean
    if (n == 1 and s == 0) or (n == 0 and s == 1): return '1 instr: 50% SL only'
    # Both instruments had only 50% SL each
    if n == 1 and s == 1: return 'Both: 50% SL only'
    # One had 50%+BE, other was clean
    if (n == 2 and s == 0) or (n == 0 and s == 2): return '1 instr: 50%+BE hit'
    # One had 50%+BE, other had only 50% SL
    if (n == 2 and s == 1) or (n == 1 and s == 2): return 'Mixed: 50%+BE + 50%SL'
    # Both had 50%+BE
    if n == 2 and s == 2: return 'Both: 50%+BE hit'
    return f'Other ({n},{s})'

daily_wide['Day_Cat'] = daily_wide.apply(day_cat, axis=1)

print("\n=== PER DAY COMBINED (NIFTY + SENSEX together) ===\n")
order = ['Both Clean', '1 instr: 50% SL only', 'Both: 50% SL only',
         '1 instr: 50%+BE hit', 'Mixed: 50%+BE + 50%SL', 'Both: 50%+BE hit']

total_days = len(daily_wide)
for cat in order:
    d = daily_wide[daily_wide['Day_Cat'] == cat]
    if len(d) == 0:
        continue
    wins     = (d['Combined_PL'] > 0).sum()
    losses   = len(d) - wins
    win_rate = wins / len(d) * 100
    avg_day  = d['Combined_PL'].mean()
    total_pl = d['Combined_PL'].sum()
    print(f"  [{cat}]")
    print(f"    Days     : {len(d)}  ({len(d)/total_days*100:.1f}%)")
    print(f"    Win Rate : {win_rate:.1f}%  ({wins}W / {losses}L)")
    print(f"    Avg Day  : Rs {avg_day:,.0f}")
    print(f"    Total PL : Rs {total_pl:,.0f}")
    print()
