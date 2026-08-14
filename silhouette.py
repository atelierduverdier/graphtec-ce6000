#!/usr/bin/env python3
"""Détourer une image : trouver le tour de ce qui est imprimé.

Pour découper un motif pris sur internet, il faut une géométrie que le
traceur puisse suivre. Une image n'en a pas : elle n'a que des pixels.
Ce module en tire le contour extérieur de l'encre — la silhouette — et le
rend en polylignes millimétrées, prêtes à passer dans `contour.py` qui
les écartera de quelques millimètres.

POURQUOI PAS UN SIMPLE SEUIL PUIS UN SUIVI DE BORD. Parce qu'un motif a
des trous — l'intérieur d'un « o », le blanc entre deux lettres — et
qu'un suivi naïf s'y perdrait ou les prendrait pour des contours à part.
On bouche donc d'abord les trous, en inondant le fond depuis le bord de
l'image : ce que l'inondation n'atteint pas est intérieur au motif, quel
que soit sa couleur.

Le liseré blanc d'un autocollant est justement dans ce cas — il fait
partie du motif alors qu'il est de la couleur du fond. Le boucher le
range du bon côté sans qu'on ait à le reconnaître.
"""

import numpy as np
from PIL import Image

SEUIL = 240               # au-dessus, c'est du fond ; mesuré sur du blanc JPEG
LARGEUR_TRAVAIL = 900     # l'image est réduite avant analyse : au-delà, on
                          # paie du temps pour du bruit de compression


def masque(chemin, seuil=SEUIL, largeur=LARGEUR_TRAVAIL):
    """Vrai là où il y a de l'encre, faux sur le fond.

    Le seuil porte sur le canal le plus CLAIR : un orange vif a un canal
    rouge à 255, et le juger sur la moyenne le rangerait dans le fond.
    """
    im = Image.open(chemin).convert("RGB")
    if im.width > largeur:
        im = im.resize((largeur, round(im.height * largeur / im.width)),
                       Image.LANCZOS)
    a = np.asarray(im, dtype=np.int16)
    return a.min(axis=2) < seuil, im.size


def _boucher_les_trous(encre):
    """Bouche ce qui est enfermé par le motif, en inondant depuis le bord.

    Un trou est une zone de fond que l'on n'atteint pas en partant du
    bord de l'image. Le liseré blanc d'un autocollant en est un.
    """
    h, w = encre.shape
    fond = ~encre
    atteint = np.zeros_like(fond)
    pile = []
    for x in range(w):
        for y in (0, h - 1):
            if fond[y, x]:
                pile.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if fond[y, x]:
                pile.append((y, x))
    while pile:
        y, x = pile.pop()
        if atteint[y, x] or not fond[y, x]:
            continue
        atteint[y, x] = True
        if y > 0:
            pile.append((y - 1, x))
        if y < h - 1:
            pile.append((y + 1, x))
        if x > 0:
            pile.append((y, x - 1))
        if x < w - 1:
            pile.append((y, x + 1))
    return encre | (fond & ~atteint)


def _suivre_le_bord(plein):
    """Le contour extérieur, par suivi de Moore, en pixels.

    On part du premier pixel plein rencontré de haut en bas, qui est
    forcément sur le bord extérieur, et on longe en gardant le fond à sa
    gauche. Rend une boucle fermée.
    """
    h, w = plein.shape
    depart = None
    for y in range(h):
        ligne = np.flatnonzero(plein[y])
        if ligne.size:
            depart = (y, int(ligne[0]))
            break
    if depart is None:
        return []

    voisins = [(-1, 0), (-1, 1), (0, 1), (1, 1),
               (1, 0), (1, -1), (0, -1), (-1, -1)]
    contour = [depart]
    courant, direction = depart, 6          # on vient de la gauche
    for _ in range(4 * h * w):
        trouve = False
        for k in range(8):
            # La reprise se fait DANS LE SENS DU DERNIER PAS. Les sept
            # autres conventions ont été essayées sur un anneau : elles
            # rendent trois à huit points au lieu de cent huit, en
            # repartant aussitôt vers le point de départ. Mesuré, pas
            # deviné — la convention de Moore se décrit de plusieurs
            # façons et je m'étais trompé de description.
            d = (direction + k) % 8
            dy, dx = voisins[d]
            y, x = courant[0] + dy, courant[1] + dx
            if 0 <= y < h and 0 <= x < w and plein[y, x]:
                courant, direction, trouve = (y, x), d, True
                break
        if not trouve:
            break
        if courant == depart and len(contour) > 2:
            break
        contour.append(courant)
    return contour


def _simplifier(points, tolerance):
    """Douglas–Peucker : jeter les points qui ne disent rien.

    Un contour suivi pixel par pixel en compte des dizaines de milliers,
    tous à un pixel l'un de l'autre. Les garder ferait un fichier énorme
    et un tracé qui vibre, pour une précision que la machine ne rend pas.
    """
    if len(points) < 3:
        return list(points)
    debut, fin = points[0], points[-1]
    dx, dy = fin[0] - debut[0], fin[1] - debut[1]
    long2 = dx * dx + dy * dy
    pire, imax = -1.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if long2 == 0:
            d = ((px - debut[0]) ** 2 + (py - debut[1]) ** 2) ** 0.5
        else:
            t = max(0.0, min(1.0, ((px - debut[0]) * dx
                                   + (py - debut[1]) * dy) / long2))
            d = ((px - debut[0] - t * dx) ** 2
                 + (py - debut[1] - t * dy) ** 2) ** 0.5
        if d > pire:
            pire, imax = d, i
    if pire <= tolerance:
        return [debut, fin]
    gauche = _simplifier(points[:imax + 1], tolerance)
    droite = _simplifier(points[imax:], tolerance)
    return gauche[:-1] + droite


def detourer(chemin, largeur_mm=None, hauteur_mm=None, seuil=SEUIL,
             tolerance_mm=0.15):
    """Image -> [(points_mm, True)], le tour du motif.

    Donner `largeur_mm` OU `hauteur_mm` fixe l'échelle ; l'autre suit les
    proportions. Sans rien, l'image est prise pour du 96 points par pouce.

    Les points sont en convention machine — Y vers le haut — comme tout le
    reste du logiciel.
    """
    encre, (w_px, h_px) = masque(chemin, seuil)
    if not encre.any():
        raise ValueError("aucune encre trouvée : le seuil est-il trop bas ?")
    plein = _boucher_les_trous(encre)
    pixels = _suivre_le_bord(plein)
    if len(pixels) < 3:
        raise ValueError("contour introuvable")

    if largeur_mm:
        echelle = largeur_mm / w_px
    elif hauteur_mm:
        echelle = hauteur_mm / h_px
    else:
        echelle = 25.4 / 96.0

    # (y, x) en pixels, Y vers le BAS -> (x, y) en mm, Y vers le HAUT.
    points = [(x * echelle, (h_px - y) * echelle) for y, x in pixels]
    points = _simplifier(points, tolerance_mm)
    if points[0] != points[-1]:
        points.append(points[0])
    return [(points, True)]


if __name__ == "__main__":
    import sys
    chemin = sys.argv[1]
    largeur = float(sys.argv[2]) if len(sys.argv) > 2 else None
    trace = detourer(chemin, largeur_mm=largeur)
    pts = trace[0][0]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    print(f"{len(pts)} points, emprise {max(xs)-min(xs):.1f} × "
          f"{max(ys)-min(ys):.1f} mm")
