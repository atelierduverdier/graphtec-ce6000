#!/usr/bin/env python3
"""Le contour de découpe : le trait qui fait d'un dessin un autocollant.

On imprime le motif, on découpe **autour**, à quelques millimètres — pas
sur le trait. Ce module fabrique ce tour, par un vrai décalage de
polygone et non par une boîte englobante : un dessin qui a des creux doit
garder ses creux, sinon l'autocollant n'a plus sa forme.

POURQUOI PYCLIPPER ET PAS UN CALCUL MAISON. Décaler un contour fermé est
un problème qui mord : les segments voisins se croisent dès que le retrait
dépasse le rayon d'un virage, et il faut supprimer les boucles ainsi
créées. Clipper fait exactement ça, il est éprouvé, et il est déjà
installé. Une tentative maison sur LaserAtelier s'est arrêtée sur sept
trous qui se percutaient — le même piège.
"""

import pyclipper

ECHELLE = 1000.0          # Clipper travaille en entiers : le micron

# Finesse des coins arrondis. Calée sur la MOITIÉ du pas de la machine
# (1/40 mm), donc sous ce qu'elle sait exprimer. Mesuré le 13/08/2026 sur
# une étoile décalée de 4 mm : la valeur par défaut de Clipper produisait
# 543 points, celle-ci en donne 85 pour un écart que la machine ne peut
# même pas restituer. Six fois moins de données pour la même précision
# réelle — et un tracé qui ne saccade pas dans les virages.
TOLERANCE = 0.0125


def _vers_clipper(points):
    return [(int(round(x * ECHELLE)), int(round(y * ECHELLE)))
            for x, y in points]


def _depuis_clipper(chemin):
    return [(x / ECHELLE, y / ECHELLE) for x, y in chemin]


def contour(polylignes, retrait=3.0, arrondi=True, trous=False,
            tolerance=TOLERANCE):
    """Le tour du dessin, écarté de `retrait` millimètres.

    `polylignes` est la liste `[(points, ferme), ...]` du reste du
    logiciel, en millimètres. Rend la même forme, prête à être découpée.

    Les tracés FERMÉS sont réunis puis dilatés — deux formes qui se
    touchent donnent un seul contour, ce qu'on veut pour un autocollant.
    Les tracés OUVERTS sont gonflés en gélule autour de leur trait : un
    dessin fait de traits libres reste ainsi découpable.

    `trous=False` ne garde que les contours EXTÉRIEURS. C'est le défaut
    parce qu'un autocollant se découpe d'un seul tour ; garder les trous
    percerait la matière au milieu du motif.
    """
    if retrait <= 0:
        raise ValueError("le retrait doit être positif")
    fermes = [_vers_clipper(p) for p, f in polylignes if f and len(p) >= 3]
    ouverts = [_vers_clipper(p) for p, f in polylignes if not f and len(p) >= 2]
    if not fermes and not ouverts:
        return []

    joint = pyclipper.JT_ROUND if arrondi else pyclipper.JT_MITER

    # Réunir d'abord les formes fermées : sans quoi deux motifs qui se
    # chevauchent donneraient deux contours emboîtés au lieu d'un seul.
    if fermes:
        reunion = pyclipper.Pyclipper()
        reunion.AddPaths(fermes, pyclipper.PT_SUBJECT, True)
        fermes = reunion.Execute(pyclipper.CT_UNION,
                                 pyclipper.PFT_NONZERO,
                                 pyclipper.PFT_NONZERO)

    decaleur = pyclipper.PyclipperOffset()
    decaleur.ArcTolerance = tolerance * ECHELLE
    if fermes:
        decaleur.AddPaths(fermes, joint, pyclipper.ET_CLOSEDPOLYGON)
    if ouverts:
        decaleur.AddPaths(ouverts, joint, pyclipper.ET_OPENROUND)
    resultat = decaleur.Execute(retrait * ECHELLE)

    sortie = []
    for chemin in resultat:
        if not trous and not pyclipper.Orientation(chemin):
            continue          # orientation négative = un trou intérieur
        points = _depuis_clipper(chemin)
        points.append(points[0])          # refermer : la lame doit revenir
        sortie.append((points, True))
    return sortie


def longueur(polylignes):
    """Longueur totale de trait, en mm — de quoi annoncer une durée."""
    total = 0.0
    for points, _ in polylignes:
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return total
