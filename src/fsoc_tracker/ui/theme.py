"""
New GUI theme — matches New GUI Design PDFs exactly.
Top/bottom bars: dark gray #595959
Page background: white
Pill buttons: light gray #D9D9D9 with colored text
Metric pills: light gray #E8E8E8
Config inputs: dark gray #5E5E5E, black action buttons #000000
"""

COLORS = {
    "bg": "#FFFFFF",
    "surface": "#FFFFFF",
    "panel": "#595959",
    "card": "#FFFFFF",
    "border": "#E2E8F0",
    "border_strong": "#CBD5E1",
    "text": "#0F172A",
    "text2": "#334155",
    "muted": "#64748B",
    "subtle": "#94A3B8",
    "faint": "#F8FAFC",
    "primary": "#1E293B",
    "primary_hover": "#0F172A",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "success": "#15803D",
    "warning": "#A16207",
    "danger": "#B91C1C",
    # overlay / marker colors
    "reticle": "#FFFFFF",
    "det": "#B45309",
    "est": "#15803D",
    "est_warn": "#B45309",
    "est_lost": "#B91C1C",
    "trail": "#D97706",
    "footprint": "#FFFFFF",
    "grid": "#3A3A3A",
    # new GUI specific
    "bar_dark": "#595959",
    "pill_gray": "#D9D9D9",
    "value_pill": "#E8E8E8",
    "input_dark": "#5E5E5E",
    "label_gray": "#777777",
}

STATE_COLORS = {
    "LOCKED": "#15803D",
    "ACQUIRING": "#2563EB",
    "SEARCHING": "#475569",
    "CANDIDATE": "#475569",
    "TEMP_LOST": "#A16207",
    "REACQUIRING": "#A16207",
    "FAILED": "#B91C1C",
    "IDLE": "#64748B",
}

STYLESHEET = """
* { font-family: "Segoe UI", system-ui, sans-serif; }
QMainWindow { background: white; }
QDialog { background: white; }
"""
