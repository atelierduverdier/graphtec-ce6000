# -*- coding: utf-8 -*-
"""Découper un grand dessin en panneaux, pour le tracer en plusieurs fois.

L'axe chariot du CE6000-60 fait 60 cm ; l'axe d'avance est illimité en
rouleau. Un gabarit bois de 1,20 m ne passe donc pas d'un coup — il faut le
couper en panneaux, les tracer l'un après l'autre, et les raccorder.

LE MORCEAU DÉLICAT est le découpage lui-même : une polyligne qui traverse la
frontière doit être coupée EXACTEMENT dessus, et ce qui dépasse doit
disparaître. Un dessin recouvert de traits qui s'arrêtent au petit bonheur
ne se raccorde pas.

Le recouvrement sert au raccord : deux panneaux voisins partagent une bande,
et des repères tracés au MILIEU de cette bande apparaissent sur les deux. On
superpose les repères, on colle, et le trait est continu.
"""

import math

TOLERANCE = 1e-9


def _dedans(x, y, r):
    x0, y0, x1, y1 = r
    return x0 - TOLERANCE <= x <= x1 + TOLERANCE and \
        y0 - TOLERANCE <= y <= y1 + TOLERANCE


def couper_segment(a, b, rect):
    """Portion de [a, b] à l'intérieur de `rect`, ou None.

    Algorithme de Liang-Barsky : on exprime le segment en paramétrique et on
    resserre l'intervalle [t0, t1] à chaque bord. Plus court et plus sûr
    qu'un découpage par cas, où les coins sont une source d'erreurs.
    """
    x0, y0, x1, y1 = rect
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]),
                 (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < TOLERANCE:
            if q < -TOLERANCE:        # parallèle et hors du bord
                return None
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    if t1 - t0 < TOLERANCE:
        return None
    return ((a[0] + t0 * dx, a[1] + t0 * dy),
            (a[0] + t1 * dx, a[1] + t1 * dy))


def decouper(polylignes, rect):
    """Limite les polylignes au rectangle, en les coupant sur ses bords.

    Une polyligne entièrement dedans est rendue telle quelle, drapeau
    « fermé » compris. Dès qu'elle sort, ses morceaux deviennent OUVERTS :
    un contour fermé coupé par une frontière n'est plus un contour.
    """
    sortie = []
    for points, ferme in polylignes:
        if all(_dedans(x, y, rect) for x, y in points):
            sortie.append((list(points), ferme))
            continue
        courante = []
        for a, b in zip(points, points[1:]):
            morceau = couper_segment(a, b, rect)
            if morceau is None:
                if len(courante) >= 2:
                    sortie.append((courante, False))
                courante = []
                continue
            c, d = morceau
            if not courante:
                courante = [c, d]
            elif math.dist(courante[-1], c) < 1e-6:
                courante.append(d)
            else:
                if len(courante) >= 2:
                    sortie.append((courante, False))
                courante = [c, d]
        if len(courante) >= 2:
            sortie.append((courante, False))
    return sortie


def paves(emprise, panneau, recouvrement):
    """Rectangles des panneaux couvrant `emprise`, avec recouvrement.

    `emprise` et `panneau` sont (largeur, hauteur) en mm. Le pas vaut la
    taille du panneau MOINS le recouvrement : c'est ce qui fait que deux
    voisins partagent une bande.
    """
    lx, ly = emprise
    px, py = panneau
    if px <= recouvrement or py <= recouvrement:
        raise ValueError("le recouvrement doit rester plus petit que le panneau")
    pas_x, pas_y = px - recouvrement, py - recouvrement
    nx = max(1, math.ceil((lx - recouvrement) / pas_x))
    ny = max(1, math.ceil((ly - recouvrement) / pas_y))
    return [[(i * pas_x, j * pas_y, i * pas_x + px, j * pas_y + py)
             for i in range(nx)] for j in range(ny)]


def reperes(rect, voisins, taille=8.0):
    """Petites croix au MILIEU des bandes de recouvrement partagées.

    Placées au milieu, elles tombent au même endroit physique sur les deux
    panneaux voisins : on superpose, on colle. Une croix posée sur le bord
    d'un panneau, elle, ne serait pas sur l'autre.
    """
    x0, y0, x1, y1 = rect
    croix = []
    for (bord, autre) in voisins:
        if bord == "droite":
            cx, cy = (x1 + autre) / 2.0, (y0 + y1) / 2.0
        elif bord == "gauche":
            cx, cy = (x0 + autre) / 2.0, (y0 + y1) / 2.0
        elif bord == "haut":
            cx, cy = (x0 + x1) / 2.0, (y1 + autre) / 2.0
        else:
            cx, cy = (x0 + x1) / 2.0, (y0 + autre) / 2.0
        h = taille / 2.0
        croix.append(([(cx - h, cy), (cx + h, cy)], False))
        croix.append(([(cx, cy - h), (cx, cy + h)], False))
    return croix


def mosaique(polylignes, panneau, recouvrement, avec_reperes=True):
    """Découpe en panneaux. Rend [(i, j, rect, polylignes_recadrées), …].

    Chaque panneau est ramené à l'origine : ce qu'on envoie au traceur est
    toujours un dessin qui commence en (0, 0), quelle que soit sa place dans
    la mosaïque.
    """
    xs = [x for pts, _ in polylignes for x, _ in pts]
    ys = [y for pts, _ in polylignes for _, y in pts]
    ox, oy = min(xs), min(ys)
    emprise = (max(xs) - ox, max(ys) - oy)
    grille = paves(emprise, panneau, recouvrement)

    sortie = []
    for j, rangee in enumerate(grille):
        for i, rect in enumerate(rangee):
            absolu = (rect[0] + ox, rect[1] + oy, rect[2] + ox, rect[3] + oy)
            morceaux = decouper(polylignes, absolu)
            if avec_reperes:
                voisins = []
                if i + 1 < len(rangee):
                    voisins.append(("droite", rangee[i + 1][0] + ox))
                if i > 0:
                    voisins.append(("gauche", rangee[i - 1][2] + ox))
                if j + 1 < len(grille):
                    voisins.append(("haut", grille[j + 1][i][1] + oy))
                if j > 0:
                    voisins.append(("bas", grille[j - 1][i][3] + oy))
                morceaux = morceaux + reperes(absolu, voisins)
            recadre = [([(x - absolu[0], y - absolu[1]) for x, y in pts], f)
                       for pts, f in morceaux]
            sortie.append((i, j, absolu, recadre))
    return sortie
