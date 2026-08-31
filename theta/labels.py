"""Theta Shifting exit / day-category labels (₹50 fixed leg SL)."""

from __future__ import annotations

# Exit reason for a single leg
EXIT_SL = "₹50 SL"
EXIT_BE = "BE Trail"
EXIT_EOD = "EOD"

# Per-slot (straddle) categories
INSTR_EOD = "Both: EOD"
INSTR_SL_ONLY = "₹50 SL only"
INSTR_SL_BE = "₹50 SL + BE hit"

# Day categories (9:45 slot = first, 11:45 slot = second)
DAY_CAT_ORDER = [
    "Both Clean",
    "1 Instr: ₹50 SL only",
    "Both: ₹50 SL only",
    "1 Instr: ₹50+BE hit",
    "Mixed: ₹50+BE + ₹50 SL",
    "Both: ₹50+BE hit",
]

# Migrate leftover strangle-style labels (e.g. stale Streamlit cache)
_LEGACY_RENAME = {
    "50% SL": EXIT_SL,
    "50% SL only": INSTR_SL_ONLY,
    "50%SL + BE hit": INSTR_SL_BE,
    "1 Instr: 50% SL only": "1 Instr: ₹50 SL only",
    "Both: 50% SL only": "Both: ₹50 SL only",
    "1 Instr: 50%+BE hit": "1 Instr: ₹50+BE hit",
    "Mixed: 50%+BE + 50%SL": "Mixed: ₹50+BE + ₹50 SL",
    "Both: 50%+BE hit": "Both: ₹50+BE hit",
}


def remap_legacy_labels(series):
    """Replace any 50% SL wording with ₹50 SL equivalents."""
    return series.replace(_LEGACY_RENAME)

_CAT_N = {
    INSTR_EOD: 0,
    INSTR_SL_ONLY: 1,
    INSTR_SL_BE: 2,
}


def exit_reason(entry_price: float, exit_price: float, exit_time_str: str) -> str:
    """₹50 fixed leg SL (allow fill slippage down to ~45 pts)."""
    parts = exit_time_str.strip().split(":")
    h, m = int(parts[0]), int(parts[1])
    if h == 15 and m >= 13:
        return EXIT_EOD
    if exit_price - entry_price >= 45:
        return EXIT_SL
    return EXIT_BE


def instr_category(exit_reasons: list[str]) -> str:
    n_early = sum(1 for r in exit_reasons if r != EXIT_EOD)
    if n_early == 0:
        return INSTR_EOD
    if n_early == 1:
        return INSTR_SL_ONLY
    return INSTR_SL_BE


def day_category(slot_945_cat: str, slot_1145_cat: str) -> str:
    n, s = _CAT_N.get(slot_945_cat, 0), _CAT_N.get(slot_1145_cat, 0)
    if n == 0 and s == 0:
        return "Both Clean"
    if (n == 1 and s == 0) or (n == 0 and s == 1):
        return "1 Instr: ₹50 SL only"
    if n == 1 and s == 1:
        return "Both: ₹50 SL only"
    if (n == 2 and s == 0) or (n == 0 and s == 2):
        return "1 Instr: ₹50+BE hit"
    if (n == 2 and s == 1) or (n == 1 and s == 2):
        return "Mixed: ₹50+BE + ₹50 SL"
    if n == 2 and s == 2:
        return "Both: ₹50+BE hit"
    return "Other"
