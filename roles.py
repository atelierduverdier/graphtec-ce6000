#!/usr/bin/env python3
"""Classer la géométrie d'un fichier par RÔLE, d'après la couleur du trait.

Un même dessin porte plusieurs travaux : le motif qu'on imprime, le
contour qu'on découpe, les plis qu'on raine, les traits qu'on perfore
pour qu'une pièce tienne dans sa feuille. Les distinguer par la
couleur est la convention de tous les logiciels de découpe, et elle a
l'avantage de survivre à l'export depuis n'importe quel dessin — Inkscape,
Illustrator, ou notre propre composeur.

Le rôle `repere` existe parce qu'un fichier ISSU du composeur porte ses
quatre équerres. Les réimprimer serait sans conséquence, mais les
DÉCOUPER trancherait la feuille en travers des repères qui viennent de
servir. Ils sont donc reconnus à leur forme et écartés.
"""

import math

# Les rôles, et ce qu'on en fait. L'ordre est celui de l'atelier : ce
# qu'on trace, ce qu'on marque, ce qu'on coupe.
ROLES = ["tracer", "rainer", "decouper", "perforer", "repere", "ignorer"]

LIBELLES = {
    "tracer": "tracer (stylo)",
    "rainer": "rainer (marquer le pli)",
    "decouper": "découper",
    "perforer": "perforer (pointillé)",
    "repere": "repère ARMS — ni tracé ni découpé",
    "ignorer": "ignorer",
}

# Correspondance par défaut. Le noir se trace parce que c'est la couleur
# d'un dessin qui n'a rien déclaré ; le rouge se découpe parce que c'est
# la convention la plus répandue.
DEFAUTS = [
    ((0.0, 0.0, 0.0), "tracer"),
    ((1.0, 0.0, 0.0), "decouper"),
    ((0.0, 0.0, 1.0), "rainer"),
    ((1.0, 0.0, 1.0), "perforer"),
]

TOLERANCE_COULEUR = 0.25          # distance RGB en deçà de laquelle on assimile


def nom_couleur(rgb):
    """Un nom lisible pour une couleur, pour l'afficher dans l'interface."""
    r, v, b = rgb
    connues = [((0, 0, 0), "noir"), ((1, 1, 1), "blanc"), ((1, 0, 0), "rouge"),
               ((0, 1, 0), "vert"), ((0, 0, 1), "bleu"), ((1, 1, 0), "jaune"),
               ((0, 1, 1), "cyan"), ((1, 0, 1), "magenta"),
               ((0.5, 0.5, 0.5), "gris")]
    proche = min(connues, key=lambda c: sum((a - b) ** 2
                                            for a, b in zip(c[0], rgb)))
    ecart = math.sqrt(sum((a - b) ** 2 for a, b in zip(proche[0], rgb)))
    if ecart < TOLERANCE_COULEUR:
        return proche[1]
    return f"#{round(r*255):02x}{round(v*255):02x}{round(b*255):02x}"


def _cle(rgb):
    """Arrondi qui rend deux nuances voisines égales — un rouge exporté
    par Inkscape n'est pas toujours exactement (1, 0, 0)."""
    return tuple(round(c * 20) / 20 for c in rgb)


def couleurs_presentes(couleurs):
    """Les couleurs du fichier, dans l'ordre où elles apparaissent, avec
    le nombre de tracés de chacune."""
    vues, compte = [], {}
    for rgb in couleurs:
        c = _cle(rgb)
        if c not in compte:
            vues.append(c)
            compte[c] = 0
        compte[c] += 1
    return [(c, compte[c]) for c in vues]


def role_par_defaut(rgb):
    """Le rôle qu'on propose pour une couleur, avant tout choix humain."""
    for reference, role in DEFAUTS:
        ecart = math.sqrt(sum((a - b) ** 2 for a, b in zip(reference, rgb)))
        if ecart < TOLERANCE_COULEUR:
            return role
    return "tracer"


def classer(polylignes, couleurs, correspondance=None, reperes=()):
    """{rôle: [polylignes]}, d'après la couleur de chaque tracé.

    `correspondance` associe une couleur arrondie à un rôle ; ce qu'elle
    ne nomme pas prend son rôle par défaut. `reperes` est l'ensemble des
    INDICES reconnus comme repères ARMS — ils l'emportent sur la couleur,
    parce qu'un repère est noir comme le dessin et qu'aucune couleur ne
    l'en distinguerait.
    """
    correspondance = correspondance or {}
    par_role = {role: [] for role in ROLES}
    for i, (trace, rgb) in enumerate(zip(polylignes, couleurs)):
        if i in reperes:
            par_role["repere"].append(trace)
            continue
        c = _cle(rgb)
        par_role[correspondance.get(c) or role_par_defaut(rgb)].append(trace)
    return par_role


# ======================================================================
# RECONNAÎTRE LES REPÈRES ARMS
# ======================================================================

def _boite(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def reperes_arms(polylignes, branche=20.0, epaisseur=1.0, tolerance=0.5):
    """Les INDICES des tracés qui sont des repères ARMS.

    Un repère est un L plein : six sommets, une boîte de `branche` de côté,
    et une aire d'environ `2 x branche x epaisseur` — bien plus petite que
    celle de sa boîte. C'est ce dernier point qui le distingue d'un carré
    de même encombrement, et il se calcule sans ambiguïté.

    On n'exige PAS qu'il y en ait quatre, ni qu'ils soient aux coins : un
    fichier peut n'en porter que deux, ou avoir été recadré. Reconnaître
    la forme suffit.
    """
    attendue = (2 * branche - epaisseur) * epaisseur
    trouves = set()
    for i, (points, ferme) in enumerate(polylignes):
        sommets = points[:-1] if (len(points) > 1 and
                                  points[0] == points[-1]) else points
        if not ferme or len(sommets) != 6:
            continue
        x0, y0, x1, y1 = _boite(sommets)
        if (abs((x1 - x0) - branche) > tolerance or
                abs((y1 - y0) - branche) > tolerance):
            continue
        aire = abs(sum(sommets[j][0] * sommets[(j + 1) % 6][1]
                       - sommets[(j + 1) % 6][0] * sommets[j][1]
                       for j in range(6))) / 2
        if abs(aire - attendue) > attendue * 0.25:
            continue
        trouves.add(i)
    return trouves
