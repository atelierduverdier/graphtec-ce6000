#!/usr/bin/env python3
"""Casse exprès ce que les tests surveillent, et vérifie qu'ils le voient.

Une suite qui passe ne prouve rien : elle peut très bien ne rien
surveiller. Le 11/08/2026 a produit CINQ détecteurs successifs qui
annonçaient « aucune erreur » sur des séquences qui en produisaient —
l'un comptait un journal vide comme zéro, l'autre comptait les entrées
d'un tampon circulaire dont le total ne peut pas bouger, un troisième
polluait ce qu'il mesurait. Aucun n'avait été éprouvé avant de servir.

Ce programme éprouve. Pour chaque propriété : on introduit la faute EN
MÉMOIRE, on lance le test qui la surveille, et on exige qu'il échoue. Un
test qui passe malgré la faute est un test qui ne sert à rien, et c'est
signalé comme tel.

    python3 tests/verifier_les_tests.py
"""

import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import materiaux                                             # noqa: E402
import mosaique                                              # noqa: E402
import svg2hpgl as noyau                                     # noqa: E402
import test_traceur as T                                     # noqa: E402


def sans_arrondi(points):
    """La faute : des coordonnées décimales au lieu d'unités entières."""
    return [(x * noyau.UNITES_PAR_MM, y * noyau.UNITES_PAR_MM)
            for x, y in points]


def une_seule_croix(rect, voisins, dessin=None, taille=8.0):
    """La faute d'origine : une croix par raccord, donc l'angle libre."""
    x0, y0, x1, y1 = rect
    croix = []
    for bord, autre in voisins:
        if bord in ("droite", "gauche"):
            cx = (x1 + autre) / 2.0 if bord == "droite" else (x0 + autre) / 2.0
            cy = (y0 + y1) / 2.0
        else:
            cy = (y1 + autre) / 2.0 if bord == "haut" else (y0 + autre) / 2.0
            cx = (x0 + x1) / 2.0
        h = taille / 2.0
        croix.append(([(cx - h, cy), (cx + h, cy)], False))
        croix.append(([(cx, cy - h), (cx, cy + h)], False))
    return croix


def passages_a_l_endroit(polylignes, outil=1, force=None, passages=1):
    """La faute : repasser depuis le DÉPART, donc lever et revenir."""
    lignes = ["IN;"]
    if force:
        lignes.append(f"FS{force};")
    lignes.append(f"SP{outil};")
    for points, _ in polylignes:
        couples = noyau.en_unites(points)
        if len(couples) < 2:
            continue
        for _ in range(max(1, passages)):
            lignes += noyau._grouper("PU", couples[:1])
            lignes += noyau._grouper("PD", couples[1:])
    lignes += ["PU0,0;", "SP0;"]
    return "\n".join(lignes) + "\n", 0


def croix_sur_la_tuile(rect, voisins, dessin=None, taille=8.0):
    """La faute : se caler sur la tuile en ignorant l'emprise du dessin."""
    return _VRAIS["reperes"](rect, voisins, None, taille)


_VRAIS = {"en_unites": noyau.en_unites,
          "reperes": mosaique.reperes,
          "en_hpgl": noyau.en_hpgl,
          "MATERIAUX": dict(materiaux.MATERIAUX)}


def reperage_qui_reinitialise_quand_meme():
    """La faute : ignorer l'option et émettre IN; dans tous les cas.

    C'est exactement l'état du code avant le 13/08/2026, et le défaut ne
    se voit sur AUCUN travail ordinaire — seulement sur une feuille déjà
    repérée, où il fait rater la découpe sans rien dire.
    """
    def toujours_initialiser(polylignes, outil=1, force=None, passages=1,
                             reperage=False):
        return _VRAIS["en_hpgl"](polylignes, outil, force, passages, False)
    noyau.en_hpgl = toujours_initialiser


def rainage_devenu_coupe():
    """La faute : « corriger » la force 2 du canson en la croyant fautive."""
    for nom, m in materiaux.MATERIAUX.items():
        if m.get("usage") == "rainer":
            m["force"] = 20


CAS = [
    ("coordonnées décimales",
     "test_coordonnees_entieres",
     lambda: setattr(noyau, "en_unites", sans_arrondi),
     lambda: setattr(noyau, "en_unites", _VRAIS["en_unites"])),

    ("une seule croix de raccord",
     "test_reperes_coincident",
     lambda: setattr(mosaique, "reperes", une_seule_croix),
     lambda: setattr(mosaique, "reperes", _VRAIS["reperes"])),

    ("croix calées sur la tuile, pas sur le dessin",
     "test_reperes_dans_le_dessin",
     lambda: setattr(mosaique, "reperes", croix_sur_la_tuile),
     lambda: setattr(mosaique, "reperes", _VRAIS["reperes"])),

    ("repassage à l'endroit, avec retour au départ",
     "test_passages_sans_deplacement",
     lambda: setattr(noyau, "en_hpgl", passages_a_l_endroit),
     lambda: setattr(noyau, "en_hpgl", _VRAIS["en_hpgl"])),

    ("IN; émis malgré le mode repérage",
     "test_reperage_sans_reinitialisation",
     reperage_qui_reinitialise_quand_meme,
     lambda: setattr(noyau, "en_hpgl", _VRAIS["en_hpgl"])),

    ("rainage « corrigé » en découpe",
     "test_rainage_reste_du_rainage",
     rainage_devenu_coupe,
     lambda: materiaux.MATERIAUX.update(_VRAIS["MATERIAUX"])),

    ("profil dont la force sort des bornes machine",
     "test_profils_coherents",
     lambda: materiaux.MATERIAUX.__setitem__(
         "papier fictif", dict(vitesse=20, force=99, passages=1)),
     lambda: materiaux.MATERIAUX.pop("papier fictif", None)),
]


def main():
    print("Chaque ligne : on casse la propriété, le test doit s'en "
          "apercevoir.\n")
    aveugles = []
    for intitule, nom_test, casser, reparer in CAS:
        casser()
        try:
            getattr(T, nom_test)()
            vu = False
        except AssertionError:
            vu = True
        except Exception:
            vu = True
        finally:
            reparer()
        print(f"  {'vu   ' if vu else 'AVEUGLE'}  {intitule}")
        if not vu:
            aveugles.append((intitule, nom_test))

    print()
    if aveugles:
        for intitule, nom_test in aveugles:
            print(f"{nom_test} ne voit pas « {intitule} » : il ne surveille "
                  f"pas ce qu'il prétend.")
        return 1
    print(f"Les {len(CAS)} propriétés sont réellement surveillées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
