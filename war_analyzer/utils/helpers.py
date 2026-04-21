"""
Shared utility functions for War Impact Commodity Analyzer.
"""

def format_inr(amount: float) -> str:
    """Format a number in Indian numbering system (lakhs, crores)."""
    if amount >= 1_00_00_000:
        return f"₹{amount/1_00_00_000:.2f} Cr"
    if amount >= 1_00_000:
        return f"₹{amount/1_00_000:.2f} L"
    return f"₹{amount:,.2f}"


def get_trend_label(change_pct: float) -> str:
    if change_pct > 5:
        return "🔴 Sharp Rise"
    if change_pct > 0:
        return "🟡 Slight Rise"
    if change_pct < -5:
        return "🟢 Sharp Fall"
    return "🟡 Slight Fall"


def conflict_color(conflict: str) -> str:
    colors = {
        "Russia-Ukraine": "#3b82f6",
        "Iran-Israel-USA": "#ef4444",
    }
    return colors.get(conflict, "#f59e0b")
