"""Theme engine for qBt Reclaim.

Token-driven QSS. Two dark industrial variants:

  * obsidian  — deep navy chassis, teal primaries, amber warnings (default)
  * phosphor  — near-black chassis, phosphor-green primaries

Every colour in the UI is derived from the token dict so the whole app
re-skins from a single source of truth.
"""

from __future__ import annotations

MONO_STACK = '"JetBrains Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'

THEMES: dict[str, dict[str, str]] = {
    "obsidian": {
        # chassis
        "bg":            "#0d1420",   # window
        "bg_raised":     "#131c2b",   # panels / frames
        "bg_sunken":     "#0a0f18",   # inputs, table body
        "bg_hover":      "#1a2740",
        "bg_active":     "#22344f",
        "border":        "#233450",
        "border_bright": "#31496e",
        # ink
        "fg":            "#c9d6e8",
        "fg_dim":        "#7b8ca6",
        "fg_faint":      "#4a5a72",
        # signals
        "accent":        "#2dd4bf",   # teal — primary action / selection
        "accent_dim":    "#14665c",
        "accent_fg":     "#04211d",   # text on accent
        "warn":          "#f5b641",   # amber — orphans, caution
        "danger":        "#f26d6d",   # red — destructive / admin
        "ok":            "#4ade80",
        # table
        "row_alt":       "#101a29",
        "sel_bg":        "#173a3f",
        "sel_fg":        "#d9fef8",
        "grid":          "#1b2942",
    },
    "phosphor": {
        "bg":            "#0a0e0b",
        "bg_raised":     "#101711",
        "bg_sunken":     "#070b08",
        "bg_hover":      "#16211a",
        "bg_active":     "#1d2c22",
        "border":        "#1f3327",
        "border_bright": "#2e4c39",
        "fg":            "#c4e8cf",
        "fg_dim":        "#6f9a7f",
        "fg_faint":      "#41604d",
        "accent":        "#39c784",
        "accent_dim":    "#1c6644",
        "accent_fg":     "#04160c",
        "warn":          "#e8c34a",
        "danger":        "#f07d6a",
        "ok":            "#5aef9e",
        "row_alt":       "#0d130e",
        "sel_bg":        "#153826",
        "sel_fg":        "#dcffe9",
        "grid":          "#182a1e",
    },
}


def tokens(theme: str) -> dict[str, str]:
    return THEMES.get(theme, THEMES["obsidian"])


def build_qss(theme: str) -> str:
    t = tokens(theme)
    return f"""
/* ============ chassis ============ */
QMainWindow, QDialog {{
    background-color: {t['bg']};
    color: {t['fg']};
}}
QWidget {{
    background-color: transparent;
    color: {t['fg']};
    font-family: {MONO_STACK};
    font-size: 13px;
}}
QFrame#panel {{
    background-color: {t['bg_raised']};
    border: 1px solid {t['border']};
    border-radius: 6px;
}}
QFrame#headerBar {{
    background-color: {t['bg_raised']};
    border: 1px solid {t['border']};
    border-left: 3px solid {t['accent']};
    border-radius: 6px;
}}
QLabel#appTitle {{
    color: {t['fg']};
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#appSubtitle {{
    color: {t['fg_dim']};
    font-size: 11px;
    letter-spacing: 3px;
}}
QLabel.dim   {{ color: {t['fg_dim']}; }}
QLabel.faint {{ color: {t['fg_faint']}; font-size: 11px; }}
QLabel.statValue {{
    color: {t['accent']};
    font-size: 16px;
    font-weight: 700;
}}
QLabel.statValueWarn {{
    color: {t['warn']};
    font-size: 16px;
    font-weight: 700;
}}
QLabel.statLabel {{
    color: {t['fg_faint']};
    font-size: 10px;
    letter-spacing: 2px;
}}

/* ============ buttons ============ */
QPushButton {{
    background-color: {t['bg_hover']};
    color: {t['fg']};
    border: 1px solid {t['border_bright']};
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: 600;
}}
QPushButton:hover  {{ background-color: {t['bg_active']}; border-color: {t['accent_dim']}; }}
QPushButton:pressed {{ background-color: {t['bg_sunken']}; }}
QPushButton:disabled {{
    color: {t['fg_faint']};
    background-color: {t['bg_raised']};
    border-color: {t['border']};
}}
QPushButton#primary {{
    background-color: {t['accent_dim']};
    color: {t['fg']};
    border: 1px solid {t['accent']};
}}
QPushButton#primary:hover {{ background-color: {t['accent']}; color: {t['accent_fg']}; }}
QPushButton#danger {{
    border: 1px solid {t['danger']};
    color: {t['danger']};
    background-color: transparent;
}}
QPushButton#danger:hover {{ background-color: {t['danger']}; color: {t['bg']}; }}
QPushButton#danger:disabled {{
    border-color: {t['border']};
    color: {t['fg_faint']};
    background-color: transparent;
}}

/* ============ inputs ============ */
QLineEdit, QSpinBox, QComboBox {{
    background-color: {t['bg_sunken']};
    color: {t['fg']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {t['sel_bg']};
    selection-color: {t['sel_fg']};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
QLineEdit:disabled, QSpinBox:disabled {{ color: {t['fg_faint']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background-color: {t['bg_raised']};
    border: 1px solid {t['border_bright']};
    selection-background-color: {t['sel_bg']};
    selection-color: {t['sel_fg']};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {t['bg_hover']};
    border: none;
    width: 16px;
}}

/* ============ checkboxes ============ */
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {t['border_bright']};
    border-radius: 3px;
    background-color: {t['bg_sunken']};
}}
QCheckBox::indicator:hover   {{ border-color: {t['accent']}; }}
QCheckBox::indicator:checked {{
    background-color: {t['accent']};
    border-color: {t['accent']};
}}

/* ============ tabs ============ */
QTabWidget::pane {{
    border: 1px solid {t['border']};
    border-radius: 6px;
    background-color: {t['bg_raised']};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {t['fg_dim']};
    padding: 8px 20px;
    border: 1px solid transparent;
    border-bottom: none;
    letter-spacing: 1px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {t['accent']};
    background-color: {t['bg_raised']};
    border-color: {t['border']};
    border-top: 2px solid {t['accent']};
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}}
QTabBar::tab:hover:!selected {{ color: {t['fg']}; }}

/* ============ table ============ */
QTableView {{
    background-color: {t['bg_sunken']};
    alternate-background-color: {t['row_alt']};
    gridline-color: {t['grid']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    selection-background-color: {t['sel_bg']};
    selection-color: {t['sel_fg']};
}}
QTableView::item {{ padding: 3px 6px; }}
QHeaderView::section {{
    background-color: {t['bg_raised']};
    color: {t['fg_dim']};
    padding: 6px 8px;
    border: none;
    border-bottom: 2px solid {t['accent_dim']};
    border-right: 1px solid {t['border']};
    font-weight: 700;
    letter-spacing: 1px;
    font-size: 11px;
}}
QHeaderView::section:hover {{ color: {t['accent']}; }}
QTableCornerButton::section {{
    background-color: {t['bg_raised']};
    border: none;
    border-bottom: 2px solid {t['accent_dim']};
}}

/* ============ scrollbars ============ */
QScrollBar:vertical {{
    background: {t['bg_sunken']};
    width: 11px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['border_bright']};
    border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {t['accent_dim']}; }}
QScrollBar:horizontal {{
    background: {t['bg_sunken']};
    height: 11px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {t['border_bright']};
    border-radius: 5px; min-width: 28px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ============ status bar / progress ============ */
QStatusBar {{
    background-color: {t['bg_raised']};
    color: {t['fg_dim']};
    border-top: 1px solid {t['border']};
}}
QStatusBar::item {{ border: none; }}
QProgressBar {{
    background-color: {t['bg_sunken']};
    border: 1px solid {t['border']};
    border-radius: 3px;
    height: 12px;
    text-align: center;
    color: {t['fg']};
    font-size: 10px;
}}
QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 2px;
}}

/* ============ misc ============ */
QToolTip {{
    background-color: {t['bg_raised']};
    color: {t['fg']};
    border: 1px solid {t['accent_dim']};
    padding: 4px 8px;
}}
QPlainTextEdit#logView {{
    background-color: {t['bg_sunken']};
    color: {t['fg_dim']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    font-size: 12px;
}}
QMenu {{
    background-color: {t['bg_raised']};
    border: 1px solid {t['border_bright']};
    padding: 4px;
}}
QMenu::item {{ padding: 5px 22px; border-radius: 3px; }}
QMenu::item:selected {{ background-color: {t['sel_bg']}; color: {t['sel_fg']}; }}
QMessageBox {{ background-color: {t['bg_raised']}; }}
QGroupBox {{
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 700;
    letter-spacing: 1px;
    color: {t['fg_dim']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {t['accent']};
    font-size: 11px;
}}
"""
