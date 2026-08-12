#!/usr/bin/env python3
"""Fabrique un gabarit de planche TechDraw taillé pour le traceur.

Le format A3 standard (420 × 297) ne tient PAS sur du A3 chargé dans le
CE6000-60 : les galets presseurs et les marges mangent 39 mm dans le sens
d'avance et 11 mm en largeur, la zone utile mesurée valant 380,9 × 285,6 mm.
D'où une page de 375 × 280, qui laisse ~5 mm de garde sur chaque dimension
pour les variations d'un chargement à l'autre.

Différence de fond avec un gabarit ordinaire : **tous les textes fixes sont
en monotrait**, dessinés glyphe par glyphe depuis les polices de
LaserAtelier. Un gabarit classique écrit ses libellés en texte, qu'il faut
convertir en chemins avant de tracer — ce qui donne des lettres CREUSES,
parcourues deux fois par la plume. Ici les libellés sont déjà des traits.

Restent en <text> les seuls champs que TechDraw remplit à l'exécution
(titre, auteur, date…). Eux devront encore passer par « Objet en chemin »
dans Inkscape : voir le README, section « Tracer une planche TechDraw ».
"""

import argparse
import os
import sys
from xml.sax.saxutils import escape

CHEMIN_ATELIER = os.path.expanduser(
    "~/.local/share/FreeCAD/v1-1/Mod/LaserAtelier")
sys.path.insert(0, CHEMIN_ATELIER)
try:
    from polices_monotrait import hershey_font as POLICE
except ImportError:                                     # pragma: no cover
    sys.exit(f"polices monotrait introuvables dans {CHEMIN_ATELIER}")

NS_FREECAD = "http://www.freecad.org/wiki/index.php?title=Svg_Namespace"

# --- géométrie de la page, en millimètres -------------------------------
# 375 x 280 est la taille d'UNE feuille A3 dans le traceur. Une page plus
# grande reste légitime : la pièce à tracer commande, et `svg2hpgl
# --mosaique` découpe ensuite en tuiles qui, elles, tiennent dans la
# machine. C'est ce qu'a demandé le porte-manteau, long de 600 mm.
LARGEUR, HAUTEUR = 375.0, 280.0
BORD = 5.0             # cadre extérieur, en retrait du bord de page
BANDE = 10.0           # bande des repères, entre cadre extérieur et cadre utile
CARTOUCHE_L, CARTOUCHE_H = 190.0, 52.0

TRAIT_FIN, TRAIT_FORT = 0.25, 0.5
H_LIBELLE = 2.0        # hauteur de capitale des libellés fixes
H_REPERE = 3.5         # hauteur des lettres/chiffres de repérage


# ======================================================================
# A. TEXTE MONOTRAIT
# ======================================================================

def polylignes_texte(txt, x, y, hauteur):
    """Rend (polylignes, largeur) pour `txt`, ligne de base en (x, y).

    Les polices comptent Y vers le HAUT et le SVG vers le bas : d'où le
    `y - py*k`. `hauteur` est une hauteur de CAPITALE, la seule cote qu'on
    puisse mesurer au pied à coulisse sur un tracé.
    """
    k = hauteur / POLICE.CAP_HEIGHT
    curseur = x
    lignes = []
    for c in txt:
        entree = POLICE.GLYPHES.get(c)
        if entree is None:
            curseur += POLICE.ADV_DEFAULT * k
            continue
        avance, traits = entree
        for trait in traits:
            lignes.append([(curseur + px * k, y - py * k) for px, py in trait])
        curseur += avance * k
    return lignes, curseur - x


def largeur_texte(txt, hauteur):
    return polylignes_texte(txt, 0.0, 0.0, hauteur)[1]


# ======================================================================
# B. PRIMITIVES SVG
# ======================================================================

def chemin(polylignes, epaisseur):
    if not polylignes:
        return ""
    morceaux = []
    for pts in polylignes:
        if len(pts) < 2:
            continue
        d = "M {:.3f},{:.3f}".format(*pts[0])
        d += "".join(" L {:.3f},{:.3f}".format(x, y) for x, y in pts[1:])
        morceaux.append(d)
    if not morceaux:
        return ""
    return ('<path d="{}" fill="none" stroke="#000000" '
            'stroke-width="{}" stroke-linecap="round"/>'.format(
                " ".join(morceaux), epaisseur))


def rectangle(x, y, l, h):
    return [[(x, y), (x + l, y), (x + l, y + h), (x, y + h), (x, y)]]


def texte(txt, x, y, hauteur, epaisseur=TRAIT_FIN):
    return chemin(polylignes_texte(txt, x, y, hauteur)[0], epaisseur)


def texte_centre(txt, cx, y, hauteur, epaisseur=TRAIT_FIN):
    return texte(txt, cx - largeur_texte(txt, hauteur) / 2.0, y, hauteur, epaisseur)


def champ(nom, autofill, x, y, hauteur_px, contenu):
    """Champ éditable, rempli par TechDraw à l'exécution."""
    remplissage = (' freecad:autofill="{}"'.format(autofill) if autofill else "")
    return ('<text freecad:editable="{nom}"{rmp} x="{x:.3f}" y="{y:.3f}" '
            'font-size="{fs}px" font-family="osifont, sans-serif" '
            'fill="#000000" stroke="none">'
            '<tspan>{c}</tspan></text>'.format(
                nom=nom, rmp=remplissage, x=x, y=y, fs=hauteur_px,
                c=escape(contenu)))


# ======================================================================
# C. LE GABARIT
# ======================================================================

def cadres():
    """Cadre extérieur + cadre utile."""
    ext = rectangle(BORD, BORD, LARGEUR - 2 * BORD, HAUTEUR - 2 * BORD)
    u = BORD + BANDE
    utile = rectangle(u, u, LARGEUR - 2 * u, HAUTEUR - 2 * u)
    return chemin(ext, TRAIT_FIN) + "\n  " + chemin(utile, TRAIT_FORT)


def reperes(colonnes=8, rangees=4):
    """Lettres en haut/bas, chiffres à gauche/droite, plus les traits.

    Les lettres descendent de droite à gauche (A à droite), les chiffres
    montent de bas en haut : c'est la convention ISO, et c'est celle du
    gabarit A3 de l'atelier.
    """
    u = BORD + BANDE
    l_utile = LARGEUR - 2 * u
    h_utile = HAUTEUR - 2 * u
    sortie, traits = [], []

    pas_x = l_utile / colonnes
    for i in range(colonnes):
        cx = u + (i + 0.5) * pas_x
        lettre = chr(ord("A") + colonnes - 1 - i)
        sortie.append(texte_centre(lettre, cx, BORD + BANDE / 2 + H_REPERE / 2, H_REPERE))
        sortie.append(texte_centre(lettre, cx, HAUTEUR - BORD - BANDE / 2 + H_REPERE / 2, H_REPERE))
        if i:                                   # séparateurs entre cases
            x = u + i * pas_x
            traits.append([(x, BORD), (x, u)])
            traits.append([(x, HAUTEUR - u), (x, HAUTEUR - BORD)])

    pas_y = h_utile / rangees
    for j in range(rangees):
        cy = u + (j + 0.5) * pas_y + H_REPERE / 2
        chiffre = str(rangees - j)
        sortie.append(texte_centre(chiffre, BORD + BANDE / 2, cy, H_REPERE))
        sortie.append(texte_centre(chiffre, LARGEUR - BORD - BANDE / 2, cy, H_REPERE))
        if j:
            y = u + j * pas_y
            traits.append([(BORD, y), (u, y)])
            traits.append([(LARGEUR - u, y), (LARGEUR - BORD, y)])

    return chemin(traits, TRAIT_FIN) + "\n  " + "\n  ".join(sortie)


def cartouche():
    """Cartouche ancré au coin bas-droit du cadre utile.

    Mêmes noms de champs que le gabarit A3 de l'atelier : TechDraw les
    remplit par les mêmes `autofill`, donc une planche bascule d'un gabarit
    à l'autre sans rien perdre.
    """
    u = BORD + BANDE
    x0 = LARGEUR - u - CARTOUCHE_L
    y0 = HAUTEUR - u - CARTOUCHE_H

    traits = rectangle(x0, y0, CARTOUCHE_L, CARTOUCHE_H)
    # colonne de gauche (auteur, dates, format) puis la ligne du bas
    traits.append([(x0 + 50, y0), (x0 + 50, y0 + 45)])
    for dy in (7.5, 15.0, 22.5, 30.0):
        traits.append([(x0, y0 + dy), (x0 + 50, y0 + dy)])
    traits.append([(x0, y0 + 45), (x0 + CARTOUCHE_L, y0 + 45)])
    for dx in (20.0, 46.0, 146.0):              # échelle | masse | n° | feuille
        traits.append([(x0 + dx, y0 + 45), (x0 + dx, y0 + CARTOUCHE_H)])

    sortie = [chemin(traits, TRAIT_FIN)]

    libelles = [
        ("DESSINE PAR",  1.5,  3.3), ("DATE",        1.5, 10.8),
        ("VERIFIE PAR",  1.5, 18.3), ("DATE",        1.5, 25.8),
        ("FORMAT",       1.5, 33.3),
        ("ECHELLE",      1.5, 48.0), ("MASSE (kg)", 21.5, 48.0),
        ("N° DE PLAN",  47.5, 48.0), ("FEUILLE",   147.5, 48.0),
    ]
    for txt, dx, dy in libelles:
        sortie.append(texte(txt, x0 + dx, y0 + dy, H_LIBELLE))

    # Le format n'est plus un A3, et une planche qui le prétendrait serait
    # imprimée de travers ailleurs : il s'écrit en clair, dans sa propre case.
    sortie.append(texte("{:.0f} × {:.0f} mm".format(LARGEUR, HAUTEUR),
                        x0 + 1.5, y0 + 38.5, 3.0))
    sortie.append(texte("TRACEUR CE6000", x0 + 1.5, y0 + 43.0, H_LIBELLE))

    champs = [
        ("AuthorName",     "author", 1.5,  7.0, 3.0, "AUTEUR"),
        ("CreationDate",   "date",   1.5, 14.5, 3.0, "DATE"),
        ("SupervisorName", None,     1.5, 22.0, 3.0, "VERIFICATEUR"),
        ("CheckDate",      None,     1.5, 29.5, 3.0, "DATE"),
        ("scale",          "scale",  1.5, 51.0, 3.0, "ECHELLE"),
        ("Weight",         None,    21.5, 51.0, 3.0, ""),
        ("drawing_number", None,    47.5, 51.0, 3.0, "N-PLAN"),
        ("SheetNumber",    "sheet", 147.5, 51.0, 3.0, "1"),
        ("FC-Title",       "title",  52.0, 14.0, 6.0, "TITRE"),
        ("Subtitle",       None,     52.0, 21.0, 3.5, "sous-titre"),
    ]
    for nom, autofill, dx, dy, fs, defaut in champs:
        sortie.append(champ(nom, autofill, x0 + dx, y0 + dy, fs, defaut))

    return "\n  ".join(sortie)


def gabarit():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:freecad="{ns}"\n'
        '     width="{L}mm" height="{H}mm" viewBox="0 0 {L:g} {H:g}"\n'
        '     version="1.1">\n'
        '  <!-- Gabarit taille pour le Graphtec CE6000-60 : zone utile mesuree\n'
        '       380,9 x 285,6 mm sur du A3, page ramenee a {L:g} x {H:g}.\n'
        '       Textes fixes en MONOTRAIT (police Hershey Sans 1 trait). -->\n'
        '  {cadres}\n'
        '  {reperes}\n'
        '  {cartouche}\n'
        '</svg>\n'
    ).format(ns=NS_FREECAD, L=LARGEUR, H=HAUTEUR,
             cadres=cadres(), reperes=reperes(), cartouche=cartouche())


def main():
    global LARGEUR, HAUTEUR
    ap = argparse.ArgumentParser(
        description="Fabrique un gabarit de planche TechDraw pour le traceur.")
    ap.add_argument("--largeur", type=float, default=LARGEUR,
                    help="largeur de page en mm (défaut : une feuille A3 "
                         "dans le traceur)")
    ap.add_argument("--hauteur", type=float, default=HAUTEUR,
                    help="hauteur de page en mm")
    ap.add_argument("-o", "--sortie",
                    default=os.path.expanduser(
                        "~/Projets/logiciels/graphtec-ce6000/gabarits/A3_Traceur_TD.svg"),
                    help="fichier SVG à écrire")
    args = ap.parse_args()

    LARGEUR, HAUTEUR = args.largeur, args.hauteur
    if LARGEUR - 2 * (BORD + BANDE) <= 0 or HAUTEUR - 2 * (BORD + BANDE) <= 0:
        sys.exit("page trop petite : il ne reste rien après les bandes de "
                 "repères.")

    contenu = gabarit()
    os.makedirs(os.path.dirname(args.sortie), exist_ok=True)
    with open(args.sortie, "w", encoding="utf-8") as f:
        f.write(contenu)
    print(f"écrit  {args.sortie}  ({len(contenu)} octets)")
    print(f"page   {LARGEUR:.0f} x {HAUTEUR:.0f} mm, "
          f"cadre utile {LARGEUR - 2*(BORD+BANDE):.0f} x {HAUTEUR - 2*(BORD+BANDE):.0f} mm")


if __name__ == "__main__":
    main()
