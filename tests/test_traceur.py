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
import arms
import contour
import mosaique
import roles
import silhouette                                              # noqa: E402
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


def test_arms_voit_un_type_de_repere_qui_ne_correspond_pas():
    """Le désaccord qui a coûté le plus cher le 13/08/2026.

    La machine était réglée sur `MARK TYPE=2` ; tant qu'on l'ignorait,
    elle balayait en cherchant une forme absente du papier et s'arrêtait
    sur le bord de la feuille — qui offre exactement le même contraste
    qu'un repère pour un capteur de réflexion.

    Le renseignement dormait dans un vidage de configuration, lisible
    depuis le début. Ce test exige qu'un logiciel le dise.
    """
    machine = {"ARMS": {"MARK TYPE": "2", "MARK SIZE": "20.0",
                        "MARK AUTO SCAN": "ON"}}
    lus = arms.reglages(machine)

    assert not arms.desaccords(lus, type_gabarit=2), (
        "un gabarit type 2 sur une machine réglée type 2 : rien à signaler")

    ennuis = arms.desaccords(lus, type_gabarit=1)
    assert ennuis, "type 1 sur une machine réglée type 2 : non signalé"
    assert any("TYPE" in e for e in ennuis), (
        "le désaccord est signalé mais ne nomme pas le type de repère")


def test_arms_voit_une_taille_de_repere_qui_ne_correspond_pas():
    """MARK SIZE doit valoir la longueur de branche du gabarit."""
    machine = {"ARMS": {"MARK TYPE": "2", "MARK SIZE": "10.0",
                        "MARK AUTO SCAN": "ON"}}
    ennuis = arms.desaccords(arms.reglages(machine), type_gabarit=2,
                             branche=20.0)
    assert any("MARK SIZE" in e for e in ennuis), (
        "10 mm annoncés contre 20 mm tracés : non signalé")


def test_des_reperes_rallonges_restent_des_reperes():
    """Rallonger les branches ne doit pas les faire passer pour du dessin.

    Christophe, le 14/08/2026 : « pour la détection automatique, une chose
    que l'on n'a pas testée, c'est des repères plus longs ». Le manuel
    donne 4 à 20 mm et le gabarit était figé à 20 — donc déjà au maximum,
    et l'essai était impossible à monter.

    En le rendant réglable, un piège s'ouvre : la RECONNAISSANCE des
    repères était figée à 20 mm elle aussi. Mesuré — un gabarit à 30 mm
    rouvert n'en faisait reconnaître aucun, et les quatre équerres
    seraient parties à la découpe, en travers des repères qui venaient de
    servir. Exactement ce que le rôle « repère » existe pour empêcher.
    """
    import tempfile

    dessin = [([(0., 0.), (80., 0.), (80., 50.), (0., 50.), (0., 0.)], True)]
    for branche in (10.0, 20.0, 30.0, 40.0):
        # Marge au moins égale à la branche : en type 2 les branches
        # rentrent vers le dessin, et `composer` le signale par ailleurs.
        svg, _infos = arms.composer(dessin, marge=branche + 5.0,
                                    branche=branche, epaisseur=1.0,
                                    type_repere=2)
        with tempfile.NamedTemporaryFile("w", suffix=".svg",
                                         delete=False) as f:
            f.write(svg)
            chemin = f.name
        couleurs = []
        trace, _ = noyau.charger(chemin, couleurs=couleurs)
        os.unlink(chemin)
        vus = roles.reperes_arms(trace, branche=branche, epaisseur=1.0)
        assert len(vus) == 4, (
            f"branches de {branche:g} mm : {len(vus)} repère(s) reconnu(s) "
            f"sur 4 — les autres partiraient à la découpe")


def test_une_branche_plus_longue_que_MARK_SIZE_nest_pas_une_faute():
    """Les deux sens du désaccord ne veulent pas dire la même chose.

    Branches plus COURTES que MARK SIZE : la machine cherche plus de
    matière qu'il n'y en a et s'arrête sur le premier contraste venu — le
    bord de la feuille. C'est le symptôme observé depuis le début.

    Branches plus LONGUES : elle en trouve plus que prévu là où elle
    regarde. C'est l'essai demandé, pas une faute. Les confondre ferait
    crier une alerte sur une manipulation délibérée — et une alerte qui
    crie pour rien finit par ne plus être lue, c'est alors qu'elle manque
    le vrai désaccord.
    """
    machine = {"ARMS": {"MARK TYPE": "2", "MARK SIZE": "20.0",
                        "MARK AUTO SCAN": "ON"}}
    lus = arms.reglages(machine)

    court = " ".join(arms.desaccords(lus, type_gabarit=2, branche=10.0))
    assert "bord de la feuille" in court, (
        f"branches trop courtes : la conséquence n'est pas dite — {court}")

    long = " ".join(arms.desaccords(lus, type_gabarit=2, branche=30.0))
    assert "bord de la feuille" not in long, (
        f"branches rallongées prises pour une faute — {long}")
    assert long.strip(), "branches rallongées : rien n'est dit du tout"


def test_contour_entoure_le_dessin_sans_le_toucher():
    """Le tour d'un autocollant passe AUTOUR du motif, à la bonne distance.

    Une boîte englobante serait plus simple et mentirait : une étoile
    perdrait ses creux, et l'autocollant ne serait plus une étoile. Ce
    test emploie donc une forme à creux, celle qui distingue un vrai
    décalage d'une approximation.
    """
    import math
    etoile = []
    for k in range(11):
        a = math.pi / 2 + k * math.pi / 5
        r = 30.0 if k % 2 == 0 else 13.0
        etoile.append((60 + r * math.cos(a), 45 + r * math.sin(a)))
    dessin = [(etoile, True)]
    retrait = 4.0

    tour = contour.contour(dessin, retrait=retrait)
    assert len(tour) == 1, f"{len(tour)} contours pour une seule forme"

    # L'emprise doit grandir d'exactement deux retraits sur chaque axe.
    dx0, dy0, dx1, dy1 = noyau.cadre(dessin)
    cx0, cy0, cx1, cy1 = noyau.cadre(tour)
    assert abs((cx1 - cx0) - (dx1 - dx0) - 2 * retrait) < 0.05, (
        "le contour ne s'écarte pas du retrait demandé en largeur")
    assert abs((cy1 - cy0) - (dy1 - dy0) - 2 * retrait) < 0.05

    # Et il doit ENTOURER le dessin : aucun point du motif au-delà.
    for x, y in etoile:
        assert cx0 <= x <= cx1 and cy0 <= y <= cy1, (
            "le dessin déborde de son propre contour")

    # LA propriété d'un décalage, et non une approximation de longueur :
    # chaque sommet du motif est à `retrait` de son contour. Un creux
    # d'étoile est le cas qui tranche — une boîte englobante l'en
    # éloignerait de plusieurs centimètres.
    points_contour = tour[0][0]

    def _distance_au_contour(px, py):
        proche = float("inf")
        for (x0, y0), (x1, y1) in zip(points_contour, points_contour[1:]):
            dx, dy = x1 - x0, y1 - y0
            long2 = dx * dx + dy * dy
            u = 0.0 if long2 == 0 else max(0.0, min(
                1.0, ((px - x0) * dx + (py - y0) * dy) / long2))
            proche = min(proche, math.hypot(px - x0 - u * dx,
                                            py - y0 - u * dy))
        return proche

    # Les sommets SAILLANTS (les pointes) reçoivent un raccord arrondi de
    # rayon `retrait` : ils sont à exactement cette distance.
    for x, y in etoile[0:10:2]:
        d = _distance_au_contour(x, y)
        assert abs(d - retrait) < 0.1, (
            f"pointe ({x:.1f}, {y:.1f}) à {d:.2f} mm au lieu de {retrait}")

    # Les sommets RENTRANTS — les creux — sont forcément plus loin : le
    # décalage y forme un coin, à l'intersection des deux bords décalés.
    # C'est correct. Ce qui ne le serait pas, c'est qu'ils soient loin au
    # point de trahir une boîte englobante : ici 4,75 mm mesurés, contre
    # une vingtaine si le contour ne suivait pas les creux.
    for x, y in etoile[1:10:2]:
        d = _distance_au_contour(x, y)
        assert d >= retrait - 0.05, (
            f"creux ({x:.1f}, {y:.1f}) à {d:.2f} mm : le contour mord "
            f"dans le motif")
        assert d < 2 * retrait, (
            f"creux ({x:.1f}, {y:.1f}) à {d:.2f} mm du contour — il ne "
            f"suit pas les creux, c'est une enveloppe déguisée et "
            f"l'autocollant n'aura plus sa forme")


def test_feuille_imprimee_et_decoupe_se_recouvrent():
    """Ce qu'on imprime et ce qu'on découpe doivent tomber au même endroit.

    C'est toute la valeur du print & cut, et c'est une propriété
    GÉOMÉTRIQUE qu'on peut éprouver sans machine : la feuille pose les
    repères autour du dessin, la découpe repart de l'origine que la
    détection place sur le premier repère. Les deux ne se recouvrent que
    si le dessin est envoyé exactement à la distance annoncée.

    Le manuel (p. 5-5) dit de MESURER cet offset. Ici on n'a pas à le
    mesurer : c'est nous qui posons les repères ET le dessin, donc on le
    connaît. Encore faut-il que les deux calculs s'accordent.
    """
    dessin = [([(12.0, 7.0), (72.0, 7.0), (72.0, 47.0), (12.0, 47.0),
                (12.0, 7.0)], True)]
    marge = 25.0
    _svg, infos = arms.composer(dessin, marge=marge)

    ox, oy = infos["origine_dessin"]
    assert (ox, oy) == (marge, marge), (
        "le dessin doit se trouver à `marge` de l'angle du premier repère")

    # La découpe part recadrée à cette origine — c'est ce que fait le
    # pupitre après l'export.
    decoupe = noyau.recadrer(dessin, ox, oy)
    x0, y0, x1, y1 = noyau.cadre(decoupe)
    assert abs(x0 - ox) < 1e-9 and abs(y0 - oy) < 1e-9, (
        "la découpe ne part pas de l'origine annoncée")

    # Et l'écart annoncé à la machine doit encadrer ce dessin, marge
    # comprise des deux côtés. Sinon on cherche des repères là où il n'y
    # en a pas.
    ax, ay = infos["ecart"]
    assert abs(ax - ((x1 - x0) + 2 * marge)) < 1e-9, (
        f"écart d'avance {ax} incompatible avec un dessin de "
        f"{x1 - x0} mm et une marge de {marge}")
    assert abs(ay - ((y1 - y0) + 2 * marge)) < 1e-9, (
        "écart de chariot incompatible avec l'emprise du dessin")


def test_reperes_composes_sont_de_type_2():
    """Les repères posés autour du dessin ont leurs angles vers l'EXTÉRIEUR.

    Type 2 : les branches rentrent vers le centre, donc l'angle est le
    point le plus extérieur de la feuille. En type 1 elles sortiraient, et
    la page serait plus grande que l'écart entre repères.

    La machine de l'atelier est réglée sur `MARK TYPE=2` — un gabarit de
    l'autre type la ferait balayer en cherchant une forme absente du
    papier, puis s'arrêter sur le bord de la feuille.
    """
    dessin = [([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 0.0)], True)]
    bord = 10.0
    # `page=None` : la page taillée sur mesure, celle où l'encombrement du
    # bloc se lit directement. Sur une page fixe la propriété existe
    # toujours mais se noie dans les marges de centrage.
    _svg, infos = arms.composer(dessin, marge=25.0, bord=bord, page=None)
    ax, ay = infos["ecart"]
    pl, ph = infos["page"]
    assert abs(pl - (ax + 2 * bord)) < 1e-9, (
        f"page de {pl} mm pour un écart de {ax} : les branches débordent, "
        f"ce ne sont pas des repères de type 2")
    assert abs(ph - (ay + 2 * bord)) < 1e-9


def test_type_1_laisse_la_place_a_ses_branches():
    """En type 1 les branches SORTENT : la page doit s'agrandir d'autant.

    Sans quoi les repères seraient rognés à l'impression — et un repère
    tronqué n'est plus détectable. Le type 2, dont les branches rentrent,
    n'a pas ce besoin : ses angles sont déjà les points extrêmes.
    """
    dessin = [([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 0.0)], True)]
    bord, branche = 10.0, 20.0

    _s2, i2 = arms.composer(dessin, marge=25.0, bord=bord, page=None,
                            branche=branche, type_repere=2)
    _s1, i1 = arms.composer(dessin, marge=25.0, bord=bord, page=None,
                            branche=branche, type_repere=1)

    assert i1["ecart"] == i2["ecart"], (
        "le type ne change que le SENS des angles, pas leur position")

    l2, h2 = i2["page"]
    l1, h1 = i1["page"]
    assert abs((l1 - l2) - 2 * branche) < 1e-9, (
        f"page type 1 large de {l1} contre {l2} en type 2 : il manque la "
        f"place des branches sortantes")
    assert abs((h1 - h2) - 2 * branche) < 1e-9


def test_un_repere_ne_se_confond_pas_avec_un_carre():
    """La forme du repère se reconnaît à son AIRE, pas à son encombrement.

    Un L de 20 mm de côté et un carré de 20 mm ont exactement la même
    boîte. Ce qui les sépare est l'aire : 39 mm² pour le L, 400 pour le
    carré. S'en tenir à la boîte ferait passer tout carré de 20 mm pour
    un repère — et il serait alors écarté de la découpe, en silence.
    """
    b, e = 20.0, 1.0
    repere = [(list(arms._coin(0.0, 0.0, +1, +1, b, e))
               + [(0.0, 0.0)], True)]
    carre = [([(0.0, 0.0), (b, 0.0), (b, b), (0.0, b), (0.0, 0.0)], True)]

    assert roles.reperes_arms(repere) == {0}, "un vrai repère n'est pas vu"
    assert roles.reperes_arms(carre) == set(), (
        "un carré de 20 mm est pris pour un repère — il serait écarté de "
        "la découpe sans rien dire")


def test_les_reperes_dune_feuille_composee_sont_reconnus():
    """Rouvrir une feuille du composeur ne doit pas redécouper ses repères.

    Les découper trancherait la feuille en travers des repères qui
    viennent de servir à la détection.
    """
    dessin = [([(20.0, 20.0), (80.0, 20.0), (80.0, 60.0), (20.0, 60.0),
                (20.0, 20.0)], True)]
    svg, _infos = arms.composer(dessin, marge=25.0)

    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False,
                                     encoding="utf-8") as f:
        f.write(svg)
        chemin = f.name
    try:
        couleurs = []
        relu, _ = noyau.charger(chemin, couleurs=couleurs)
    finally:
        os.unlink(chemin)

    reperes = roles.reperes_arms(relu)
    assert len(reperes) == 4, (
        f"{len(reperes)} repère(s) reconnu(s) sur 4 dans une feuille "
        f"sortie du composeur")

    par_role = roles.classer(relu, couleurs, reperes=reperes)
    assert len(par_role["repere"]) == 4
    assert len(par_role["tracer"]) == len(relu) - 4, (
        "le dessin a été rangé avec les repères")


def test_la_couleur_decide_du_role():
    """Rouge se découpe, bleu se raine, noir se trace.

    C'est la convention des logiciels de découpe, et elle permet à un
    seul fichier de porter le motif et son contour.
    """
    assert roles.role_par_defaut((1.0, 0.0, 0.0)) == "decouper"
    assert roles.role_par_defaut((0.0, 0.0, 1.0)) == "rainer"
    assert roles.role_par_defaut((0.0, 0.0, 0.0)) == "tracer"

    # Une nuance voisine doit tomber du même côté : Inkscape n'exporte pas
    # toujours un rouge exactement pur.
    assert roles.role_par_defaut((0.94, 0.06, 0.04)) == "decouper", (
        "un rouge légèrement dénaturé n'est plus reconnu")

    # Et une couleur inconnue ne doit pas être découpée par surprise.
    assert roles.role_par_defaut((0.0, 0.65, 0.0)) != "decouper"


def test_la_feuille_a_imprimer_a_toujours_le_meme_format():
    """Deux dessins différents doivent donner la MÊME page.

    Une page taillée sur mesure autour du dessin paraissait économe.
    Elle ne l'était qu'en apparence : l'imprimante centre ce qu'elle
    reçoit, donc deux dessins de tailles différentes posaient leurs
    repères à deux endroits différents du papier — décidés par le pilote
    et connus de personne.

    Or c'est l'endroit des repères sur la feuille qui décide si la tête
    les trouve. Toute la journée du 13/08/2026 a tourné autour de ça.
    """
    petit = [([(0.0, 0.0), (40.0, 0.0), (40.0, 25.0), (0.0, 0.0)], True)]
    grand = [([(0.0, 0.0), (110.0, 0.0), (110.0, 90.0), (0.0, 0.0)], True)]

    _s1, i1 = arms.composer(petit, marge=25.0)
    _s2, i2 = arms.composer(grand, marge=25.0)

    assert i1["page"] == i2["page"] == arms.A4, (
        f"pages différentes : {i1['page']} et {i2['page']} — l'impression "
        f"les centrera chacune à sa façon")

    # Et le bloc doit rester DANS la page, sinon les repères sont rognés.
    for infos in (i1, i2):
        mx, my = infos["bords"]
        assert mx > 0 and my > 0, (
            f"le premier repère tombe à {mx:.1f} ; {my:.1f} du bord — "
            f"hors de la feuille")


def test_l_a4_est_dans_les_axes_de_la_machine():
    """L'avance court sur les 297 mm, pas sur les 210.

    La feuille entre par le petit côté. Écrire A4 = (210, 297) — l'ordre
    d'un format de papier — plaçait l'écart d'avance dans la largeur : le
    premier repère d'un dessin de 175,9 mm avec 25 mm de marge tombait à
    MOINS 8 mm du bord, c'est-à-dire hors de la feuille.

    Trouvé le 14/08/2026 parce que Christophe s'est demandé s'il ne
    fallait pas plus de marge en bas — la question était juste, la réponse
    était que le calcul était faux.
    """
    assert arms.A4 == (297.0, 210.0), (
        "A4 doit être écrit dans les axes de la machine : avance d'abord")

    # Un dessin long dans l'avance doit tenir sur la feuille.
    dessin = [([(0.0, 0.0), (175.9, 0.0), (175.9, 98.8), (0.0, 0.0)], True)]
    _svg, infos = arms.composer(dessin, marge=20.0)
    bx, by = infos["bords"]
    assert bx > 0 and by > 0, (
        f"repère à {bx:.1f} ; {by:.1f} du bord — hors de la feuille")
    ax, ay = infos["ecart"]
    assert bx + ax <= arms.A4[0] and by + ay <= arms.A4[1], (
        "le repère opposé sort de la feuille")


def test_quatre_marges_independantes():
    """Comme le panneau de Graphtec Studio : gauche, droite, bas, haut.

    Les axes sont ceux de la MACHINE et non d'une feuille posée sur une
    table : gauche et droite bornent la course du chariot, bas et haut
    l'avance du média. Les confondre a déjà coûté deux essais le
    13/08/2026.
    """
    dessin = [([(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 0.0)], True)]

    egales = arms.composer(dessin, marge=25.0)[1]
    quatre = arms.composer(dessin, marges=(30.0, 20.0, 40.0, 10.0))[1]

    assert egales["origine_dessin"] == (25.0, 25.0)
    assert quatre["origine_dessin"] == (40.0, 30.0), (
        "le dessin doit être à (bas ; gauche) de l'angle du repère 1")

    # bas + emprise + haut sur l'avance, gauche + emprise + droite sur le
    # chariot : c'est ça, quatre marges indépendantes.
    ax, ay = quatre["ecart"]
    assert ax == 40.0 + 60.0 + 10.0
    assert ay == 30.0 + 40.0 + 20.0

    # Une marge plus courte que les branches doit être signalée, en la
    # NOMMANT — sinon on cherche laquelle.
    assert any("haut" in a for a in quatre["avertissements"]), (
        "la marge fautive n'est pas nommée dans l'avertissement")


def test_le_scan_peut_amener_la_tete_avant_de_chercher():
    """Le panneau fait poser la pointe sur le premier repère ; pas nous.

    « Positionnez le chariot dans la zone de détection du 1er repère »,
    dit le manuel pour la détection AUTOMATIQUE comme pour la manuelle
    (p. 5-37 et 5-39). Toutes les détections abouties du 13/08/2026 ont eu
    ce geste ; aucun de nos scans pilotés depuis le PC ne l'a fait.

    Le test ne peut pas vérifier que la tête bouge — il vérifie que le
    paramètre existe et qu'il est converti en unités machine.
    """
    import inspect
    src = inspect.getsource(arms.scanner)
    assert "depart" in inspect.signature(arms.scanner).parameters, (
        "le scan ne sait pas amener la tête avant de chercher")
    assert "UNITES_PAR_MM" in src, (
        "le déplacement n'est pas converti en unités machine")
    assert "PU" in src, "aucun ordre de déplacement dans le scan"


def test_un_repere_hors_datteinte_est_signale_avant_impression():
    """Un « HORS SURFACE » se calcule : il ne doit pas se découvrir sur
    la machine, feuille déjà imprimée.

    Cas réel du 14/08/2026, chiffres relevés à l'établi : premier repère
    à 34 ; 39 mm de l'origine, écart de 225,9 × 148,8, zone atteignable
    de 255,9 × 174,4. Le repère opposé tombait à 259,9 et 187,8 — hors
    d'atteinte des deux côtés, dont 13,4 mm sur le chariot parce que
    rapprocher les galets avait rétréci la course.

    La machine l'a découvert en s'y cassant le nez ; le logiciel avait
    tout ce qu'il fallait pour le dire avant.
    """
    ennuis = arms.tient_dans_la_zone((225.9, 148.8), (255.9, 174.4),
                                     premier=(34.0, 39.0))
    assert len(ennuis) >= 2, "les deux axes débordent, un seul est signalé"
    assert any("259.9" in e for e in ennuis), (
        "l'avertissement ne dit pas OÙ tombe le repère — sans le chiffre "
        "on ne sait pas de combien réduire")
    assert any("187.8" in e for e in ennuis)

    # Et il ne doit pas crier pour rien.
    assert not arms.tient_dans_la_zone((150.0, 100.0), (255.9, 174.4),
                                       premier=(20.0, 20.0)), (
        "faux positif sur un jeu de repères qui tient largement")

    # Sans la position du premier repère, le calcul est OPTIMISTE, et il
    # doit le dire plutôt que de laisser croire à une vérification.
    aveugle = arms.tient_dans_la_zone((250.0, 170.0), (255.9, 174.4))
    assert any("ORIGINE" in e for e in aveugle), (
        "l'hypothèse du calcul n'est pas annoncée")


def test_le_pointille_est_un_role_comme_un_autre():
    """Une couleur peut demander la perforation, sans toucher au reste.

    Christophe : « comment distinguer les traits perforés du dessin ? ».
    Par la couleur, comme tout le reste — le magenta perfore. Sans ce
    rôle, la perforation était globale : tout l'envoi en pointillé ou
    rien, ce qui interdit une planche où quelques traits seulement
    doivent tenir dans la feuille.
    """
    assert "perforer" in roles.ROLES
    assert roles.role_par_defaut((1.0, 0.0, 1.0)) == "perforer"
    # Et une nuance voisine tombe du même côté : Inkscape n'exporte pas
    # toujours un magenta exactement pur.
    assert roles.role_par_defaut((0.95, 0.05, 0.92)) == "perforer"
    # Sans empiéter sur le rouge, qui découpe franchement.
    assert roles.role_par_defaut((1.0, 0.0, 0.0)) == "decouper"

    dessin = [([(0.0, 0.0), (10.0, 0.0)], False),
              ([(0.0, 5.0), (10.0, 5.0)], False)]
    couleurs = [(0.0, 0.0, 0.0), (1.0, 0.0, 1.0)]
    par_role = roles.classer(dessin, couleurs)
    assert len(par_role["tracer"]) == 1
    assert len(par_role["perforer"]) == 1, (
        "le magenta n'a pas été rangé dans la perforation")


def test_une_image_se_detoure_trous_bouches():
    """Le tour de l'encre, y compris ce qui est enfermé par le motif.

    Une image n'a pas de géométrie, seulement des pixels. Un seuil suivi
    d'un suivi de bord naïf se perdrait dans les trous — l'intérieur d'un
    « o », le blanc entre deux lettres — ou les prendrait pour des
    contours à part.

    On inonde donc le fond depuis le BORD de l'image : ce que l'inondation
    n'atteint pas est intérieur au motif, quelle que soit sa couleur. Le
    liseré blanc d'un autocollant est exactement ce cas, et c'est ce qui
    le range du bon côté sans qu'on ait à le reconnaître.
    """
    import numpy as np
    # Un anneau : de l'encre en couronne, du blanc au milieu ET autour.
    encre = np.zeros((60, 60), dtype=bool)
    yy, xx = np.mgrid[0:60, 0:60]
    r = ((yy - 30) ** 2 + (xx - 30) ** 2) ** 0.5
    encre[(r > 15) & (r < 22)] = True

    plein = silhouette._boucher_les_trous(encre)
    assert plein[30, 30], (
        "le centre de l'anneau n'a pas été bouché — un suivi de bord y "
        "verrait un second contour")
    assert not plein[2, 2], "le fond extérieur a été bouché aussi"

    bord = silhouette._suivre_le_bord(plein)
    assert len(bord) > 40, f"contour de {len(bord)} points sur un anneau"
    # Il doit longer le RAYON EXTÉRIEUR, pas l'intérieur.
    rayons = [(((y - 30) ** 2 + (x - 30) ** 2) ** 0.5) for y, x in bord]
    # L'anneau va de 15 à 22 px ; une fois bouché c'est un disque de 22.
    # Le contour doit longer ce bord-là, pas celui de 15 — relevé à 19,1
    # au plus près, la marche en diagonale coupant les angles.
    assert min(rayons) > 18, (
        f"le contour passe à {min(rayons):.0f} px du centre : il a suivi "
        f"le bord intérieur")


def test_le_suivi_de_bord_se_referme_sur_une_forme_tordue():
    """Une forme SIMPLE ne prouve rien d'un algorithme de suivi.

    Ma première version reprenait l'exploration dans le sens du dernier
    pas. Elle marchait parfaitement sur un anneau — ce qui m'a trompé —
    et se perdait sur un contour dentelé : quatre cent mille pixels
    parcourus sans jamais refermer la boucle, et le programme figé
    ensuite dans la simplification.

    D'où cette forme volontairement tordue : un peigne, avec des dents
    étroites et des vallées profondes, qui met la reprise en défaut si
    elle est mauvaise.
    """
    import numpy as np
    plein = np.zeros((40, 60), dtype=bool)
    plein[25:35, 5:55] = True                 # le dos du peigne
    for x in range(6, 54, 6):                 # les dents
        plein[8:25, x:x + 3] = True

    bord = silhouette._suivre_le_bord(plein)   # ne doit pas lever
    assert 100 < len(bord) < 4000, (
        f"{len(bord)} points : la boucle ne s'est pas refermée proprement")
    # Le contour doit toucher le sommet des dents ET le bas du dos.
    ys = [y for y, _ in bord]
    assert min(ys) <= 9, "le sommet des dents n'est pas atteint"
    assert max(ys) >= 33, "le bas du peigne n'est pas atteint"


def test_le_lissage_adoucit_sans_deplacer():
    """Chaikin doit réduire les angles SANS déformer la pièce.

    Christophe a vu « plein de petites vagues » sur une découpe pourtant
    juste. Ce n'était ni le bruit JPEG ni le contour : à un point tous les
    neuf dixièmes de millimètre, la lame réagit à chaque changement
    d'angle. Le remède est de réduire ces changements — mesuré, le
    changement moyen passe de 33° à 11° sur le logo PrintNC.

    Mais adoucir ne doit pas rétrécir la pièce au point que ça se voie :
    Chaikin coupe les angles, donc rogne un peu. On borne cette perte.
    """
    import math
    carre = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0), (0.0, 0.0)]

    def angle_moyen(points):
        total, n = 0.0, 0
        for i in range(1, len(points) - 1):
            a = (points[i][0] - points[i-1][0], points[i][1] - points[i-1][1])
            b = (points[i+1][0] - points[i][0], points[i+1][1] - points[i][1])
            na, nb = math.hypot(*a), math.hypot(*b)
            if na > 1e-9 and nb > 1e-9:
                c = max(-1.0, min(1.0, (a[0]*b[0] + a[1]*b[1]) / (na * nb)))
                total += abs(math.degrees(math.acos(c)))
                n += 1
        return total / max(1, n)

    doux = silhouette.adoucir(carre, 2)
    assert angle_moyen(doux) < angle_moyen(carre) / 2, (
        f"{angle_moyen(doux):.0f}° contre {angle_moyen(carre):.0f}° : "
        f"le lissage n'adoucit pas")
    assert doux[0] == doux[-1], "la boucle ne se referme plus"

    xs = [p[0] for p in doux]
    ys = [p[1] for p in doux]
    perte = 20.0 - max(max(xs) - min(xs), max(ys) - min(ys))
    assert 0 <= perte < 2.0, (
        f"la pièce a rétréci de {perte:.1f} mm — Chaikin coupe trop")

    # Zéro passe ne doit RIEN changer : le réglage « fidèle » existe pour
    # les gabarits à angles vifs.
    assert silhouette.adoucir(carre, 0) == carre


def test_le_detourage_simplifie_sans_deformer():
    """Un contour suivi pixel par pixel en compte des dizaines de milliers.

    Les garder ferait un fichier énorme et un tracé qui vibre, pour une
    précision que la machine ne rend pas. Mais simplifier ne doit pas
    déformer : l'emprise doit survivre.
    """
    carre = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    dense = []
    for a, b in zip(carre, carre[1:]):
        for i in range(50):
            t = i / 50
            dense.append((a[0] + (b[0] - a[0]) * t,
                          a[1] + (b[1] - a[1]) * t))
    dense.append(carre[0])

    simple = silhouette._simplifier(dense, 0.15)
    assert len(simple) < 12, f"{len(simple)} points pour un carré"
    xs = [p[0] for p in simple]
    ys = [p[1] for p in simple]
    assert abs(max(xs) - min(xs) - 10.0) < 0.2, "l'emprise a bougé"
    assert abs(max(ys) - min(ys) - 10.0) < 0.2


def test_unites_accordees():
    """`arms.UNITES_PAR_MM` recopie une valeur qui vit ailleurs.

    Quarante unités par millimètre, mesuré par `OF;`. La constante est
    dupliquée pour ne pas entraîner tout LaserAtelier dans un module qui
    n'en a pas besoin — donc elle est surveillée, comme la ligne VERSION
    restée quarante-quatre versions en retard.
    """
    assert arms.UNITES_PAR_MM == noyau.UNITES_PAR_MM, (
        f"arms dit {arms.UNITES_PAR_MM} unités/mm, svg2hpgl dit "
        f"{noyau.UNITES_PAR_MM} — l'une des deux a vieilli")

    # La tolérance du contour vaut la MOITIÉ du pas machine : plus fin ne
    # se voit pas, plus grossier se voit dans les virages.
    attendu = 1.0 / noyau.UNITES_PAR_MM / 2
    assert abs(contour.TOLERANCE - attendu) < 1e-12, (
        f"tolérance de contour {contour.TOLERANCE} pour un pas machine de "
        f"{1.0 / noyau.UNITES_PAR_MM} mm — elle devrait valoir {attendu}")


def test_sequence_de_scan_est_calculee():
    """Les commandes `TB` se déduisent des millimètres, pas de la capture.

    `TB51,800` vaut 800 parce que 20 mm font 800 unités. Recopier les
    valeurs de la capture du 13/08/2026 aurait figé un gabarit particulier
    dans le code.
    """
    seq = arms.sequence_scan(190.0, 140.0, branche=20.0, epaisseur=1.0)
    assert "TB51,800" in seq, "la longueur de branche n'est pas calculée"
    assert "TB53,40" in seq, "l'épaisseur de trait n'est pas calculée"
    assert "TB124,7600,5600" in seq, (
        "TB124 doit porter l'AVANCE puis le chariot, en unités machine")

    # Changer une cote doit changer la commande, sinon elle est en dur.
    autre = arms.sequence_scan(190.0, 140.0, branche=10.0)
    assert "TB51,400" in autre, "TB51 ne suit pas la longueur de branche"

    # TB57 porte un MODE — Cutting Master 3 nomme AccumPCode_TB57_MODE et
    # ne le garde pas en constante. C'est le seul paramètre de la séquence
    # qu'on n'ait jamais fait varier, donc il doit être réglable.
    assert "TB57,1,1" in seq, "valeur par défaut de TB57 perdue"
    assert "TB57,2,0" in arms.sequence_scan(190.0, 140.0, tb57=(2, 0)), (
        "TB57 est figé dans la séquence — impossible d'éprouver son mode")


def test_annonce_poussee_nest_jamais_avalee():
    """Une trame terminée par CR est une ANNONCE, et doit être gardée.

    C'est la découverte du 13/08/2026 : le résultat d'un scan n'est pas
    une réponse à lire, c'est une annonce que la machine pousse. La
    première version de l'écouteur purgeait le tampon avant chaque
    question et la jetait à tous les coups.
    """
    ecoute = arms.Ecoute.__new__(arms.Ecoute)
    ecoute.fd, ecoute.reste = None, b"1,254\r"
    ecoute.annonces, ecoute.journal = [], []

    ecoute.recolter()

    assert [texte for _, texte in ecoute.annonces] == ["1,254"], (
        "l'annonce du scan a été avalée — c'est la faute qui a coûté "
        "treize captures")


def test_vidage_de_configuration_nest_pas_pris_pour_des_annonces():
    """Le piège INVERSE, payé le même jour.

    Le vidage `TC2009,5` est un bloc de deux cents lignes séparées par des
    CR et terminé par un SEUL ETX. Une version qui coupait sur les CR sans
    regarder plus loin a rapporté deux cents annonces là où il n'y en
    avait aucune. Un instrument qui ment dans l'autre sens ment quand
    même.

    La règle : un bloc qui contient un ETX est UNE réponse, quels que
    soient les CR qu'il porte.
    """
    ecoute = arms.Ecoute.__new__(arms.Ecoute)
    ecoute.fd = None
    ecoute.reste = b"[ARMS]\r\nMARK TYPE=2\r\nMARK SIZE=20.0\r\n\x03"
    ecoute.annonces, ecoute.journal = [], []

    ecoute.recolter()

    assert ecoute.annonces == [], (
        f"{len(ecoute.annonces)} annonce(s) tirées d'un vidage de "
        f"configuration — ce sont les lignes d'UNE réponse")
    assert ecoute.reste == b"", "le vidage n'a pas été consommé"


def test_gabarit_officiel_garde_ses_cotes_relevees():
    """Les cotes du gabarit Graphtec sont RELEVÉES sur le fichier.

    Page 208,8 × 296,3 mm — et surtout PAS de l'A4. C'est ce qui rend
    toute « mise à l'échelle » à l'impression fatale, et c'est le genre de
    nombre qu'on arrondit en croyant bien faire.
    """
    assert arms.PAGE == (208.8, 296.3), (
        "la page du gabarit officiel n'est pas de l'A4 — ne pas l'arrondir")
    assert arms.BRANCHE == 20.0
    assert arms.GABARITS[2]["chute"] == (75.0, 75.0), (
        "le point de chute a été MESURÉ en trois croix, pas calculé")
    assert arms.GABARITS[1]["chute"] is None, (
        "le type 1 n'a jamais été mesuré : ne pas lui inventer une valeur")

    echelle = " ".join(arms.marche_a_suivre(2)).lower()
    assert "échelle 1" in echelle and "ajuster" in echelle, (
        "la marche à suivre ne rappelle plus le piège de la mise à l'échelle")


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
