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
import arms
import contour
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
          "MATERIAUX": dict(materiaux.MATERIAUX),
          "desaccords": arms.desaccords,
          "PAGE": arms.PAGE,
          "composer": arms.composer,
          "contour": contour.contour,
          "TOLERANCE": contour.TOLERANCE,
          "decouper": arms.Ecoute.decouper,
          "UNITES_PAR_MM": arms.UNITES_PAR_MM}


def contour_reduit_a_sa_boite_englobante():
    """La faute : le raccourci qui vient à l'esprit — un rectangle autour.

    L'emprise serait juste, le retrait aussi sur les côtés. Une étoile y
    perdrait ses creux, et l'autocollant ne serait plus une étoile.
    """
    def boite(polylignes, retrait=3.0, **reste):
        xs = [x for pts, _ in polylignes for x, _ in pts]
        ys = [y for pts, _ in polylignes for _, y in pts]
        x0, y0 = min(xs) - retrait, min(ys) - retrait
        x1, y1 = max(xs) + retrait, max(ys) + retrait
        return [([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], True)]
    contour.contour = boite


def tolerance_de_contour_trop_grossiere():
    """La faute : laisser la valeur par défaut de Clipper, 543 points."""
    contour.TOLERANCE = 0.25


def feuille_dont_la_marge_ne_vaut_que_d_un_cote():
    """La faute : poser les repères sans compter la marge des deux côtés.

    L'impression paraîtrait juste — les repères entourent bien le dessin.
    C'est à la DÉCOUPE que tout glisserait, d'une marge entière.
    """
    vrai = _VRAIS["composer"]

    def composer_bancal(polylignes, marge=25.0, **reste):
        svg, infos = vrai(polylignes, marge=marge, **reste)
        ax, ay = infos["ecart"]
        infos["ecart"] = (ax - marge, ay - marge)
        return svg, infos
    arms.composer = composer_bancal


def purge_muette_qui_jette_les_annonces():
    """La faute d'origine : jeter le tampon au lieu de le découper.

    C'est le code d'avant le 13/08/2026. Il ne se voit sur AUCUNE
    réponse — seulement sur l'annonce du scan, qui disparaît sans laisser
    de trace. Treize captures pour s'en apercevoir.
    """
    def decouper_sans_garder(self, depart=0.0):
        reponses = []
        while b"\x03" in self.reste or b"\r" in self.reste:
            i = min(x for x in (self.reste.find(b"\x03"),
                                self.reste.find(b"\r")) if x >= 0)
            trame, self.reste = self.reste[:i], self.reste[i + 1:]
            texte = trame.decode("ascii", "replace").strip()
            if texte:
                reponses.append(texte)
        return reponses
    arms.Ecoute.decouper = decouper_sans_garder


def unites_desaccordees():
    """La faute : changer 40 d'un côté sans l'autre. Le piège VERSION."""
    arms.UNITES_PAR_MM = 50


def arms_qui_ne_compare_pas_les_types():
    """La faute : lire les réglages sans les confronter au gabarit.

    C'est l'état de la journée du 13/08/2026 — le renseignement était
    disponible, personne ne le rapprochait de la feuille employée.
    """
    arms.desaccords = lambda lus, type_gabarit=2, branche=arms.BRANCHE: []


def gabarit_officiel_arrondi_a_l_a4():
    """La faute : « corriger » 208,8 x 296,3 en 210 x 297, ça y ressemble."""
    arms.PAGE = (210.0, 297.0)


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

    ("réglages ARMS lus mais jamais confrontés au gabarit",
     "test_arms_voit_un_type_de_repere_qui_ne_correspond_pas",
     arms_qui_ne_compare_pas_les_types,
     lambda: setattr(arms, "desaccords", _VRAIS["desaccords"])),

    ("page du gabarit officiel arrondie à l'A4",
     "test_gabarit_officiel_garde_ses_cotes_relevees",
     gabarit_officiel_arrondi_a_l_a4,
     lambda: setattr(arms, "PAGE", _VRAIS["PAGE"])),

    ("contour ramené à une boîte englobante",
     "test_contour_entoure_le_dessin_sans_le_toucher",
     contour_reduit_a_sa_boite_englobante,
     lambda: setattr(contour, "contour", _VRAIS["contour"])),

    ("tolérance de contour décrochée du pas machine",
     "test_unites_accordees",
     tolerance_de_contour_trop_grossiere,
     lambda: setattr(contour, "TOLERANCE", _VRAIS["TOLERANCE"])),

    ("marge comptée d'un seul côté de la feuille",
     "test_feuille_imprimee_et_decoupe_se_recouvrent",
     feuille_dont_la_marge_ne_vaut_que_d_un_cote,
     lambda: setattr(arms, "composer", _VRAIS["composer"])),

    ("purge muette qui jette l'annonce du scan",
     "test_annonce_poussee_nest_jamais_avalee",
     purge_muette_qui_jette_les_annonces,
     lambda: setattr(arms.Ecoute, "decouper", _VRAIS["decouper"])),

    ("unités par mm recopiées et laissées vieillir",
     "test_unites_accordees",
     unites_desaccordees,
     lambda: setattr(arms, "UNITES_PAR_MM", _VRAIS["UNITES_PAR_MM"])),

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
