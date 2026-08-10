# -*- coding: utf-8 -*-
"""Couleurs et feuille de style, communes aux logiciels de l'atelier.

Les valeurs sont **celles du visualiseur G-code** (`interface/theme.py` du
dépôt `visualiseur-gcode`), recopiées plutôt qu'importées : une dépendance
entre deux dépôts pour une question de couleurs casserait le jour où l'un
des deux bouge, et seule la moitié « interface » de sa palette a un sens
ici — le reste décrit un rendu 3D.

Sombre par défaut, clair pour les captures et l'impression. L'accent
`#ff8a00` est l'orange de l'Atelier du Verdier, celui des icônes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    nom: str
    ardoise: str
    ardoise_claire: str
    texte: str
    texte_faible: str
    accent: str
    alerte: str
    attention: str
    trace: str            # le dessin, dans l'aperçu
    papier: str           # le média


SOMBRE = Palette(
    nom="sombre",
    ardoise="#12151b",
    ardoise_claire="#1a1f27",
    texte="#dfe4ec",
    texte_faible="#8e97a6",
    accent="#ff8a00",
    alerte="#ff5f56",
    attention="#ffbd2e",
    trace="#5cc7fa",
    papier="#232935",
)

CLAIR = Palette(
    nom="clair",
    ardoise="#eef0f4",
    ardoise_claire="#ffffff",
    texte="#1b1f27",
    texte_faible="#5c6473",
    accent="#d96b00",
    alerte="#c0392b",
    attention="#b8860b",
    trace="#0d6bb8",
    papier="#ffffff",
)


def feuille_de_style(p):
    """Style Qt de la fenêtre, dérivé de la palette."""
    return f"""
    QWidget {{
        background: {p.ardoise};
        color: {p.texte};
        font-size: 13px;
    }}
    QGroupBox {{
        background: {p.ardoise_claire};
        border: 1px solid rgba(127,127,127,0.22);
        border-radius: 6px;
        margin-top: 14px;
        padding: 8px 8px 6px 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {p.texte_faible};
        font-weight: 600;
    }}
    QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {p.ardoise};
        border: 1px solid rgba(127,127,127,0.30);
        border-radius: 5px;
        padding: 3px 8px;
        min-height: 20px;
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {p.ardoise_claire};
        selection-background-color: {p.accent};
        selection-color: #16181d;
        border: 1px solid rgba(127,127,127,0.30);
    }}
    QPushButton {{
        background: {p.ardoise};
        border: 1px solid rgba(127,127,127,0.30);
        border-radius: 5px;
        padding: 6px 10px;
    }}
    QPushButton:hover {{ background: rgba(127,127,127,0.18); }}
    QPushButton:disabled {{ color: {p.texte_faible}; }}
    QPushButton#principal {{
        background: {p.accent};
        color: #16181d;
        font-weight: 600;
        border: none;
        padding: 8px 10px;
    }}
    QPushButton#principal:disabled {{
        background: rgba(127,127,127,0.22);
        color: {p.texte_faible};
    }}
    QLabel {{ background: transparent; }}
    QCheckBox {{ spacing: 7px; background: transparent; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border: 1px solid rgba(127,127,127,0.55);
        border-radius: 3px;
        background: {p.ardoise};
    }}
    QCheckBox::indicator:checked {{
        background: {p.accent};
        border: 1px solid {p.accent};
    }}
    QLabel#faible {{ color: {p.texte_faible}; }}
    QLabel#alerte {{ color: {p.alerte}; font-weight: 600; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: rgba(127,127,127,0.38); border-radius: 5px; min-height: 28px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
    """
