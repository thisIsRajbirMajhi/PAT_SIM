"""
Professional light theme — neutral slate with blue accent.
Designed to look engineered, not "vibe coded": 6px radius, 1px hairline borders,
system font stack, tabular numbers, muted state colors.
"""

COLORS = {
    "bg": "#F1F5F9",          # app background
    "surface": "#FFFFFF",    # cards / panels
    "panel": "#FFFFFF",
    "card": "#FFFFFF",
    "border": "#E2E8F0",     # hairline
    "border_strong": "#CBD5E1",
    "text": "#0F172A",       # slate-900
    "text2": "#334155",      # slate-700
    "muted": "#64748B",      # slate-500
    "subtle": "#94A3B8",     # slate-400
    "faint": "#F8FAFC",      # slate-50
    "primary": "#1E293B",    # slate-800 — header / primary button
    "primary_hover": "#0F172A",
    "accent": "#2563EB",     # blue-600
    "accent_hover": "#1D4ED8",
    "success": "#15803D",
    "warning": "#A16207",
    "danger": "#B91C1C",
    # overlay / marker colors (opaque, work on both light and dark image)
    "reticle": "#2563EB",
    "det": "#B45309",        # amber-700 for detection (visible on gray)
    "est": "#15803D",        # green-700
    "est_warn": "#B45309",
    "est_lost": "#B91C1C",
    "trail": "#D97706",
    "footprint": "#2563EB",
    "grid": "#E2E8F0",
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

# Slight elevation via border only — no blur shadows (Qt doesn't render them reliably)
STYLESHEET = f"""
* {{ font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif; }}

QMainWindow {{ background: {COLORS['bg']}; color: {COLORS['text']}; }}

QLabel {{ color: {COLORS['text']}; }}
QLabel#Muted {{ color: {COLORS['muted']}; }}
QLabel#Caption {{ color: {COLORS['muted']}; font-size: 10px; font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase; }}
QLabel#Mono {{ font-family: "JetBrains Mono", "Consolas", monospace; }}

QFrame#TopBar {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}
QFrame#Card {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}
QFrame#ViewShell {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}
QFrame#InfoStrip {{
    background: {COLORS['faint']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
}}

/* Buttons — primary is slate, secondary is white */
QPushButton {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 12px;
    color: {COLORS['text']};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {COLORS['faint']}; border-color: {COLORS['border_strong']}; }}
QPushButton:pressed {{ background: #EEF2F7; }}
QPushButton:disabled {{ color: {COLORS['subtle']}; border-color: {COLORS['border']}; background: {COLORS['faint']}; }}

QPushButton#Primary {{
    background: {COLORS['primary']};
    color: #FFFFFF;
    border-color: {COLORS['primary']};
    padding: 7px 16px;
}}
QPushButton#Primary:hover {{ background: {COLORS['primary_hover']}; }}
QPushButton#Accent {{
    background: {COLORS['accent']};
    color: #FFFFFF;
    border-color: {COLORS['accent']};
}}
QPushButton#Accent:hover {{ background: {COLORS['accent_hover']}; }}
QPushButton#Ghost {{
    background: transparent;
    border-color: transparent;
    color: {COLORS['muted']};
}}
QPushButton#Ghost:hover {{ background: {COLORS['faint']}; color: {COLORS['text']}; }}

QCheckBox {{ color: {COLORS['text2']}; font-size: 12px; spacing: 6px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {COLORS['border_strong']}; border-radius: 4px; background: white; }}
QCheckBox::indicator:checked {{ background: {COLORS['accent']}; border-color: {COLORS['accent']}; }}

/* Tabs */
QTabWidget::pane {{ border: 1px solid {COLORS['border']}; background: {COLORS['surface']}; border-radius: 8px; margin-top: -1px; }}
QTabBar::tab {{
    background: transparent;
    padding: 7px 12px;
    margin-right: 2px;
    color: {COLORS['muted']};
    font-size: 12px;
    font-weight: 600;
    border: 1px solid transparent;
    border-radius: 6px;
}}
QTabBar::tab:selected {{ background: {COLORS['faint']}; color: {COLORS['text']}; border-color: {COLORS['border']}; }}
QTabBar::tab:hover {{ color: {COLORS['text']}; }}

/* Inputs */
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 5px 8px;
    color: {COLORS['text']};
    font-size: 12px;
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}

QSlider::groove:horizontal {{ background: {COLORS['border']}; height: 4px; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {COLORS['accent']}; width: 14px; height: 14px; border-radius: 7px; margin: -5px 0; }}
QSlider::handle:horizontal:hover {{ background: {COLORS['accent_hover']}; }}

QStatusBar {{ background: {COLORS['surface']}; border-top: 1px solid {COLORS['border']}; color: {COLORS['muted']}; font-size: 11px; }}
QStatusBar::item {{ border: none; }}

QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {COLORS['border_strong']}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
