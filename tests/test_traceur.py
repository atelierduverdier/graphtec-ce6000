#!/usr/bin/env python3
"""Ce que la machine ne dira pas, et qu'on a payé pour apprendre.

Chaque test rejoue une faute RÉELLE de la mise au point du 11/08/2026, pas
une faute imaginable. C'est la seule sorte qui vaille : on ne sait pas
douter de ce à quoi on n'a pas encore pensé, et cette journée a produit
assez d'exemples pour s'en passer.

Aucun n'a besoin du traceur : tout se vérifie sur la géométrie et sur le
texte HP-GL produit. `python3 tests/test_traceur.py`
"""

import math
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import conditions                                            # noqa: E402
import materiaux                                             # noqa: E402
import mosaique                                              # noqa: E402
import svg2hpgl as noyau                                     # noqa: E402


CARRE = [([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)],
          True)]


def bande(largeur=600.0, hauteur=130.0):
    """Un rectangle long, comme le gabarit du porte-manteau."""
    return [([(0.0, 0.0), (largeur, 0.0), (largeur, hauteur),
              (0.0, hauteur), (0.0, 0.0)], True)]


# ======================================================================
# A. LE PROGRAMME HP-GL
# ======================================================================

def test_coordonnees_entieres():
    """Un point décimal dans une commande et la machine ne la comprend plus.

    La piste avait été suivie le 11/08/2026 quand le traceur s'est mis à
    ÉCRIRE le fichier au lieu de le tracer : on lisait `U572.2620;` sur la
    feuille. La cause était ailleurs — `COMMANDE = AUTO` — mais vérifier
    que rien ne peut produire de décimale coûte trois lignes.
    """
    poly = noyau.mettre_a_echelle(bande(879.53, 493.87), 0.42)
    programme, _ = noyau.en_hpgl(poly)
    assert "." not in programme, "une coordonnée décimale s'est glissée"


def test_grammaire_hpgl():
    """Le programme n'emploie QUE les commandes qu'on a vérifiées."""
    poly = noyau.perforer(bande(), 8.0, 0.25)
    programme, _ = noyau.en_hpgl(poly, outil=3, force=12, passages=2)
    permis = re.compile(r"(IN;|SP\d+;|FS\d+;|P[UD][-\d,]*;)")
    for ligne in programme.splitlines():
        assert permis.fullmatch(ligne), f"commande inattendue : {ligne!r}"


def test_bornes_de_condition():
    """La machine ÉCRÊTE en silence : on refuse avant elle.

    Une accélération 4 demandée est appliquée à 3 sans un mot, ce qui a
    d'abord ressemblé à un décalage d'une unité.
    """
    for parametre, (mini, maxi) in conditions.BORNES.items():
        for hors in (mini - 1, maxi + 1):
            try:
                conditions.regler(None, parametre, hors)
            except ValueError:
                continue
            except Exception:
                raise AssertionError(
                    f"paramètre {parametre} : {hors} devrait être refusé "
                    f"AVANT toute écriture")
            raise AssertionError(f"paramètre {parametre} : {hors} accepté")


# ======================================================================
# B. LES PASSAGES
# ======================================================================

def test_passages_sans_deplacement():
    """Repasser ne doit RIEN coûter en trajet à vide.

    Le repassage se fait à l'envers, depuis où la plume s'est arrêtée.
    Repasser à l'endroit demanderait un retour au départ de chaque tracé :
    sur une planche de plusieurs centaines de segments, c'est la durée du
    travail qui double au lieu de la seule écriture.
    """
    leves = []
    for n in (1, 2, 3):
        programme, _ = noyau.en_hpgl(CARRE, passages=n)
        leves.append(programme.count("PU"))
    assert len(set(leves)) == 1, (
        f"le nombre de levés de plume varie avec les passages : {leves}")


def test_passages_repassent_le_meme_chemin():
    """Deux passages tracent deux fois la même longueur."""
    un, _ = noyau.en_hpgl(CARRE, passages=1)
    deux, _ = noyau.en_hpgl(CARRE, passages=2)

    def longueur(programme):
        total, place = 0.0, None
        for ligne in programme.splitlines():
            if ligne[:2] not in ("PU", "PD"):
                continue
            v = [int(x) for x in ligne[2:].rstrip(";").split(",") if x.strip()]
            points = list(zip(v[0::2], v[1::2]))
            if ligne.startswith("PD") and place:
                for p in points:
                    total += math.dist(place, p)
                    place = p
            elif points:
                place = points[-1]
        return total

    assert abs(longueur(deux) - 2 * longueur(un)) < 1e-6, (
        "un second passage ne retrace pas exactement le premier")


# ======================================================================
# C. LA MOSAÏQUE
# ======================================================================

def test_reperes_coincident():
    """Les croix de deux panneaux voisins doivent tomber au MÊME endroit.

    C'est toute la fonction du recouvrement : on superpose les croix, on
    colle. Décalées d'un millimètre, elles font mentir le raccord.
    """
    panneaux = mosaique.mosaique(bande(), (330, 250), 5)
    assert len(panneaux) == 2, f"attendu 2 panneaux, obtenu {len(panneaux)}"

    def croix(rect, morceaux):
        return sorted({(round((p[0][0] + p[1][0]) / 2 + rect[0], 4),
                        round((p[0][1] + p[1][1]) / 2 + rect[1], 4))
                       for p, _ in morceaux if len(p) == 2 and
                       abs((p[1][0] - p[0][0]) + (p[1][1] - p[0][1])) == 8.0})

    a = croix(panneaux[0][2], panneaux[0][3])
    b = croix(panneaux[1][2], panneaux[1][3])
    assert a == b, f"croix décalées entre les panneaux :\n  {a}\n  {b}"
    assert len(a) == 2, (
        f"il faut DEUX croix par raccord, pas {len(a)} : une seule ne fixe "
        f"que la translation et laisse les feuilles pivoter")


def test_reperes_dans_le_dessin():
    """Les croix se bornent au dessin, pas à la tuile.

    Sur une pièce plus basse que le panneau, des repères calés sur la
    tuile flotteraient loin du tracé, et on alignerait deux marques
    perdues dans le vide.
    """
    dessin = bande(600.0, 40.0)
    panneaux = mosaique.mosaique(dessin, (330, 250), 5)
    for _i, _j, rect, morceaux in panneaux:
        for p, _ in morceaux:
            if len(p) == 2 and abs((p[1][0] - p[0][0])
                                   + (p[1][1] - p[0][1])) == 8.0:
                y = (p[0][1] + p[1][1]) / 2 + rect[1]
                assert -4 <= y <= 44, (
                    f"croix à y={y:.1f}, hors du dessin (0 à 40 mm)")


def test_mosaique_ne_perd_rien():
    """Chaque panneau, remis à sa place, doit rendre le dessin entier."""
    dessin = bande(600.0, 130.0)
    panneaux = mosaique.mosaique(dessin, (330, 250), 5)
    xs = [x + rect[0] for _i, _j, rect, m in panneaux
          for pts, _ in m for x, _ in pts]
    assert min(xs) <= 0.01, f"bord gauche perdu : {min(xs):.2f}"
    assert max(xs) >= 599.99, f"bord droit perdu : {max(xs):.2f}"


# ======================================================================
# D. LE CARNET D'ÉTABLI
# ======================================================================

def test_profils_coherents():
    """Chaque profil porte ce qu'il faut pour être appliqué sans surprise."""
    for nom, m in materiaux.MATERIAUX.items():
        for cle in ("vitesse", "force", "passages"):
            assert cle in m, f"{nom} : « {cle} » manquant"
        mini, maxi = conditions.BORNES[conditions.FORCE]
        assert mini <= m["force"] <= maxi, (
            f"{nom} : force {m['force']} hors des bornes machine")
        assert 1 <= m["vitesse"] <= 64, (
            f"{nom} : vitesse {m['vitesse']} hors des bornes machine")
        if m.get("acceleration") is not None:
            assert 1 <= m["acceleration"] <= 3, (
                f"{nom} : accélération {m['acceleration']}, la machine n'a "
                f"que trois crans")
        outil = m.get("outil") or m.get("lame")
        assert outil is None or outil in conditions.OUTILS, (
            f"{nom} : outil « {outil} » inconnu de la machine")


def test_rainage_reste_du_rainage():
    """Le canson 224 g marque le pli, il ne coupe pas.

    Sa force 2 a été prise pour une faute de frappe et « corrigée » le
    11/08/2026 avant que Christophe ne rétablisse : « c'est juste pour
    marquer le papier afin de mieux le plier ». Ce test empêche la
    correction de revenir.
    """
    rainages = [m for m in materiaux.MATERIAUX.values()
                if m.get("usage") == "rainer"]
    assert rainages, "le profil de rainage a disparu du carnet"
    for m in rainages:
        assert m["force"] <= 5, (
            f"force {m['force']} : ce n'est plus un rainage mais une coupe")


def test_reperage_sans_reinitialisation():
    """Un travail lancé après une détection ARMS ne doit PAS émettre IN;.

    `IN;` réinitialise le traceur, donc efface l'origine que la détection
    des repères vient de poser sur le premier repère. La découpe repartirait
    du coin de la feuille au lieu du dessin imprimé, sans le moindre
    message — on croirait la détection ratée alors que c'est le fichier
    qui l'a défaite.

    Vérifié sur le papier le 13/08/2026 : la croix témoin du gabarit
    officiel de Graphtec ne retombe sur celle imprimée que sans `IN;`.
    """
    carre = [([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], True)]

    ordinaire, _ = noyau.en_hpgl(carre)
    assert "IN;" in ordinaire, (
        "un travail ordinaire doit initialiser la machine")

    reperage, _ = noyau.en_hpgl(carre, reperage=True)
    assert "IN;" not in reperage, (
        "IN; émis après une détection de repères : il efface l'origine")

    # Et le reste du programme doit être intact — c'est la seule
    # différence attendue, pas une sortie appauvrie.
    assert reperage.count("PD") == ordinaire.count("PD"), (
        "le mode repérage a perdu des tracés en route")


# ======================================================================

def lancer():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    echecs = []
    for nom, f in tests:
        try:
            f()
            print(f"  ok    {nom}")
        except AssertionError as e:
            echecs.append((nom, str(e)))
            print(f"  RATÉ  {nom}")
        except Exception as e:
            echecs.append((nom, f"{type(e).__name__}: {e}"))
            print(f"  ERREUR {nom}")
    print()
    if echecs:
        for nom, message in echecs:
            print(f"{nom} :\n    {message}")
        print(f"\n{len(echecs)} test(s) sur {len(tests)} ont échoué.")
        return 1
    print(f"{len(tests)} tests passent.")
    return 0


if __name__ == "__main__":
    sys.exit(lancer())
