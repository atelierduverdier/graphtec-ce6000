# -*- coding: utf-8 -*-
"""Petites icônes d'outil, dessinées d'après ce qui les distingue.

Le logiciel Graphtec accompagne sa liste d'outils de vignettes. L'idée est
bonne et mérite mieux qu'une décoration : ce qui sépare une CB09U d'une
CB15U, c'est le **diamètre** de la lame, et ce qui sépare une U d'une
K60/UB, c'est son **angle**. L'icône dessine donc ces deux grandeurs — un
coup d'œil renseigne, au lieu de renvoyer à une référence à mémoriser.

Et ce n'est pas cosmétique : le type déclaré dans la machine doit
correspondre à la lame réellement montée, sinon la compensation d'offset
décale le tracé d'un demi-millimètre — vérifié le 11/08/2026, où un
« Stylo feutre » oublié avait arrondi tous les angles d'une découpe.

Dessinées à la volée, sans fichier : elles suivent la palette, donc le
thème clair comme le sombre.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF

# (diamètre en mm, angle en degrés). L'angle est celui de la pointe : plus
# il est ouvert, plus la lame est robuste et adaptée aux supports épais.
LAMES = {
    "CB09U": (0.9, 45),
    "CB09U-K60": (0.9, 60),
    "CB15U": (1.5, 45),
    "CB15UB": (1.5, 60),
}

# Plages d'épaisseur, relevées dans les descriptions du logiciel Graphtec.
# C'est du constructeur, pas une déduction -- et ça ne se devine pas.
EPAISSEURS = {
    "CB09U": (0.0, 0.25, "supports adhésifs couleur, vinyle standard"),
    "CB09U-K60": (0.0, 0.25, "variante 60°"),
    "CB15U": (0.25, 0.50, "supports trop épais pour la CB09U"),
    "CB15UB": (0.0, 0.50, "petits caractères de moins de 10 mm"),
}


def lame_pour(epaisseur):
    """Lame recommandée pour une épaisseur donnée, ou None."""
    for nom, (mini, maxi, _) in EPAISSEURS.items():
        if nom.endswith("UB"):
            continue                       # cas particulier, pas un général
        if mini <= epaisseur <= maxi:
            return nom
    return None


def _dessiner_lame(p, rect, palette, diametre, angle):
    """Corps de porte-lame, puis une pointe dont la forme porte l'information."""
    largeur = rect.width()
    corps = QRectF(rect.left() + largeur * 0.34, rect.top() + rect.height() * 0.08,
                   largeur * 0.32, rect.height() * 0.44)
    p.setPen(QPen(QColor(palette.texte_faible), 1.2))
    p.setBrush(QColor(palette.ardoise_claire))
    p.drawRoundedRect(corps, 2, 2)

    # La pointe : demi-largeur proportionnelle au diamètre, hauteur déduite
    # de l'angle. Une CB15 est donc visiblement plus large qu'une CB09, et
    # une 60° visiblement plus trapue qu'une 45°.
    import math
    demi = largeur * 0.10 * (diametre / 0.9)
    hauteur = demi / math.tan(math.radians(angle / 2.0))
    hauteur = min(hauteur, rect.height() * 0.40)
    cx = rect.center().x()
    haut = corps.bottom()
    pointe = QPolygonF([QPointF(cx - demi, haut),
                        QPointF(cx + demi, haut),
                        QPointF(cx, haut + hauteur)])
    p.setBrush(QColor(palette.accent))
    p.setPen(QPen(QColor(palette.accent), 1))
    p.drawPolygon(pointe)


def _dessiner_plume(p, rect, palette):
    """Un stylo : corps allongé, pointe arrondie, aucune arête."""
    largeur = rect.width()
    corps = QRectF(rect.left() + largeur * 0.36, rect.top() + rect.height() * 0.08,
                   largeur * 0.28, rect.height() * 0.58)
    p.setPen(QPen(QColor(palette.texte_faible), 1.2))
    p.setBrush(QColor(palette.ardoise_claire))
    p.drawRoundedRect(corps, 3, 3)
    p.setBrush(QColor(palette.trace))
    p.setPen(QPen(QColor(palette.trace), 1))
    r = largeur * 0.09
    p.drawEllipse(QPointF(rect.center().x(), corps.bottom() + r * 0.8), r, r)


def _dessiner_inconnu(p, rect, palette):
    p.setPen(QPen(QColor(palette.texte_faible), 1.4, Qt.DashLine))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(rect.left() + rect.width() * 0.30,
                             rect.top() + rect.height() * 0.14,
                             rect.width() * 0.40, rect.height() * 0.62), 3, 3)


def icone(nom, palette, taille=22):
    """QIcon de l'outil `nom`, dessinée à la palette donnée."""
    pix = QPixmap(taille, taille)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0, 0, taille, taille)
    if nom in LAMES:
        _dessiner_lame(p, rect, palette, *LAMES[nom])
    elif nom == "Stylo feutre":
        _dessiner_plume(p, rect, palette)
    else:
        _dessiner_inconnu(p, rect, palette)
    p.end()
    return QIcon(pix)


def legende(nom):
    """Ce que l'icône montre, en toutes lettres — pour l'infobulle."""
    if nom in LAMES:
        d, a = LAMES[nom]
        texte = (f"lame Ø {d} mm, pointe à {a}°. "
                 f"L'icône en dessine la largeur et l'angle.")
        if nom in EPAISSEURS:
            mini, maxi, usage = EPAISSEURS[nom]
            texte += f"\nSupports de {mini:g} à {maxi:g} mm — {usage}."
        return texte
    if nom == "Stylo feutre":
        return "plume : aucun déport, la machine ne compense pas."
    return "outil non répertorié : déport inconnu."
