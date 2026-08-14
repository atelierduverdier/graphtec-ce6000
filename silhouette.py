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
LISSAGE = 2               # passes de vote majoritaire sur le masque

# Les niveaux offerts à l'utilisateur : (tolérance mm, passes de Chaikin).
# Mesuré le 14/08/2026 sur le logo PrintNC, à 120 mm de large — le
# changement d'angle MOYEN entre deux segments est ce qui fait facetter
# la lame, et c'est lui qu'on cherche à réduire :
#
#     fidèle    172 points, 33° de moyenne
#     moyen     191 points, 22°
#     doux      381 points, 11°
NIVEAUX = {
    "fidèle": (0.15, 0),
    "moyen": (0.30, 1),
    "doux": (0.40, 2),
    "très doux": (0.60, 3),
}
LARGEUR_TRAVAIL = 900     # l'image est réduite avant analyse : au-delà, on
                          # paie du temps pour du bruit de compression


def _lisser(encre, passes=LISSAGE):
    """Vote majoritaire : un pixel prend l'avis de ses huit voisins.

    Le JPEG laisse des pixels isolés au bord des aplats — son bruit de
    compression — et le suivi de bord les longe fidèlement. Le tracé sort
    alors couvert de petites vagues, signalées par Christophe le
    14/08/2026 sur une découpe pourtant réussie.

    Lisser le MASQUE plutôt que le tracé enlève le bruit à sa source. Une
    passe suffit d'ordinaire ; deux effacent aussi les escaliers d'un
    contour incliné, sans ronger les angles vifs — un angle a cinq voisins
    du bon côté, il survit au vote.
    """
    for _ in range(max(0, passes)):
        m = encre.astype(np.uint8)
        somme = np.zeros_like(m, dtype=np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                somme += np.roll(np.roll(m, dy, axis=0), dx, axis=1)
        encre = somme >= 5
    return encre


def masque(chemin, seuil=SEUIL, largeur=LARGEUR_TRAVAIL, lissage=LISSAGE):
    """Vrai là où il y a de l'encre, faux sur le fond.

    Rend `(masque, taille_du_masque, taille_du_fichier)`.

    Le seuil porte sur le canal le plus CLAIR : un orange vif a un canal
    rouge à 255, et le juger sur la moyenne le rangerait dans le fond.
    """
    im = Image.open(chemin).convert("RGB")
    taille_reelle = im.size
    if im.width > largeur:
        im = im.resize((largeur, round(im.height * largeur / im.width)),
                       Image.LANCZOS)
    a = np.asarray(im, dtype=np.int16)
    encre = _lisser(a.min(axis=2) < seuil, lissage)
    # UNE BORDURE DE FOND tout autour. Sans elle, un motif qui touche le
    # bord de l'image n'a pas de contour fermé : le suivi longe l'arête,
    # ne revient jamais à son départ, et rend autant de points que le
    # plafond d'itérations l'autorise. Constaté le 14/08/2026 sur un logo
    # recadré au plus juste — 1 422 001 points, et le programme figé.
    # Deux tailles rendues : celle du masque, sur laquelle on travaille,
    # et celle du FICHIER, qui seule dit combien l'image mesure. Les
    # confondre faisait dépendre la taille du dessin de notre largeur de
    # travail — 900 px — c'est-à-dire d'un réglage interne. Une image de
    # 2563 px et une de 900 px sortaient à la même taille.
    return np.pad(encre, 1, constant_values=False), im.size, taille_reelle


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

    On part du premier pixel plein rencontré de haut en bas et de gauche
    à droite, qui est forcément sur le bord extérieur. À chaque pas on
    explore les huit voisins EN REPARTANT DE CELUI D'OÙ L'ON VIENT, dans
    le sens horaire : c'est cette reprise en arrière qui fait longer le
    bord au lieu de couper à travers.

    Ma première version reprenait dans le sens du dernier pas. Elle
    marchait sur un anneau — ce qui m'a trompé — et se perdait sur une
    forme complexe : sur un logo recadré au plus juste, elle parcourait
    quatre cent mille pixels sans jamais refermer la boucle, et figeait
    tout ce qui venait ensuite. Une forme simple ne prouve rien d'un
    algorithme de suivi.
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

    # Sens horaire, en partant du nord.
    voisins = [(-1, 0), (-1, 1), (0, 1), (1, 1),
               (1, 0), (1, -1), (0, -1), (-1, -1)]

    def index_de(depuis, vers):
        d = (vers[0] - depuis[0], vers[1] - depuis[1])
        return voisins.index(d)

    contour = [depart]
    courant = depart
    arriere = (depart[0], depart[1] - 1)      # l'ouest, forcément du fond
    plafond = min(8 * h * w, 400_000)

    for _ in range(plafond):
        base = index_de(courant, arriere)
        suivant = None
        for k in range(1, 9):
            dy, dx = voisins[(base + k) % 8]
            y, x = courant[0] + dy, courant[1] + dx
            if 0 <= y < h and 0 <= x < w and plein[y, x]:
                suivant = (y, x)
                # Le pixel EXPLORÉ JUSTE AVANT devient le nouvel arrière.
                ady, adx = voisins[(base + k - 1) % 8]
                arriere = (courant[0] + ady, courant[1] + adx)
                break
        if suivant is None:
            break                              # pixel isolé
        courant = suivant
        if courant == depart:
            return contour
        contour.append(courant)

    raise ValueError(
        f"le contour ne se referme pas ({len(contour)} points parcourus). "
        f"Le seuil est-il bien choisi ?")


def _simplifier(points, tolerance):
    """Douglas–Peucker, ITÉRATIF : jeter les points qui ne disent rien.

    Un contour suivi pixel par pixel en compte des dizaines de milliers,
    tous à un pixel l'un de l'autre. Les garder ferait un fichier énorme
    et un tracé qui vibre, pour une précision que la machine ne rend pas.

    Écrit sans récursion À DESSEIN : la version récursive descendait d'un
    niveau par point sur un contour dégénéré, et faisait tomber le
    programme avant même de rendre la main. Une pile explicite ne connaît
    pas cette limite.
    """
    n = len(points)
    if n < 3:
        return list(points)
    garder = np.zeros(n, dtype=bool)
    garder[0] = garder[-1] = True
    pile = [(0, n - 1)]
    while pile:
        i0, i1 = pile.pop()
        if i1 <= i0 + 1:
            continue
        x0, y0 = points[i0]
        x1, y1 = points[i1]
        dx, dy = x1 - x0, y1 - y0
        long2 = dx * dx + dy * dy
        pire, imax = -1.0, i0
        for i in range(i0 + 1, i1):
            px, py = points[i]
            if long2 == 0:
                d = ((px - x0) ** 2 + (py - y0) ** 2) ** 0.5
            else:
                t = max(0.0, min(1.0,
                                 ((px - x0) * dx + (py - y0) * dy) / long2))
                d = ((px - x0 - t * dx) ** 2 + (py - y0 - t * dy) ** 2) ** 0.5
            if d > pire:
                pire, imax = d, i
        if pire > tolerance:
            garder[imax] = True
            pile.append((i0, imax))
            pile.append((imax, i1))
    return [points[i] for i in range(n) if garder[i]]


def adoucir(points, passes=1):
    """Chaikin : couper les angles, deux fois par passe.

    Chaque segment est remplacé par ses points au quart et aux trois
    quarts. Les angles s'arrondissent, la courbe se rapproche d'une
    spline, et la lame cesse de facetter — c'est ce que Christophe voyait
    en « petites vagues » sur une découpe pourtant juste : à un point
    tous les neuf dixièmes de millimètre, la machine réagit à chaque
    changement d'angle.

    Sur un tour d'autocollant c'est ce qu'on veut. Sur un gabarit à angles
    vifs, non — d'où le réglage plutôt qu'un lissage d'office.
    """
    boucle = points[0] == points[-1]
    for _ in range(max(0, passes)):
        base = points[:-1] if boucle else points
        n = len(base)
        if n < 3:
            break
        sortie = []
        for i in range(n if boucle else n - 1):
            (x0, y0), (x1, y1) = base[i], base[(i + 1) % n]
            sortie.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            sortie.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        if boucle:
            sortie.append(sortie[0])
        else:
            sortie = [points[0]] + sortie + [points[-1]]
        points = sortie
    return points


def detourer(chemin, largeur_mm=None, hauteur_mm=None, seuil=SEUIL,
             tolerance_mm=0.15, lissage=LISSAGE, adoucissement=0):
    """Image -> [(points_mm, True)], le tour du motif.

    Donner `largeur_mm` OU `hauteur_mm` fixe l'échelle ; l'autre suit les
    proportions. Sans rien, l'image est prise pour du 96 points par pouce.

    Les points sont en convention machine — Y vers le haut — comme tout le
    reste du logiciel.
    """
    encre, (w_px, h_px), (w_reel, h_reel) = masque(chemin, seuil,
                                                  lissage=lissage)
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
        # 96 points par pouce, la convention du SVG — mais sur la taille
        # RÉELLE du fichier, pas sur celle du masque réduit.
        echelle = (w_reel / w_px) * 25.4 / 96.0

    # (y, x) en pixels, Y vers le BAS -> (x, y) en mm, Y vers le HAUT.
    # Le masque porte une bordure d'un pixel : la retirer ici, sinon tout
    # le contour serait décalé d'un pixel vers le bas et la droite.
    points = [((x - 1) * echelle, (h_px - (y - 1)) * echelle)
              for y, x in pixels]
    points = _simplifier(points, tolerance_mm)
    if points[0] != points[-1]:
        points.append(points[0])
    if adoucissement:
        points = adoucir(points, adoucissement)
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
