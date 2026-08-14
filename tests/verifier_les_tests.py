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
import mosaique
import roles                                              # noqa: E402
import svg2hpgl as noyau                                     # noqa: E402
import test_traceur as T                                     # noqa: E402

# Les tests d'interface s'éprouvent aussi. Ils prennent une fenêtre en
# argument et demandent Qt ; elle n'est construite que si un cas en
# réclame une, pour que ce programme reste lançable sans écran.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import test_pupitre as P                                     # noqa: E402

_FENETRE = [None]


def fenetre():
    if _FENETRE[0] is None:
        from PySide6.QtWidgets import QApplication
        import pupitre
        QApplication.instance() or QApplication([])
        _FENETRE[0] = pupitre.Pupitre()
    return _FENETRE[0]


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
          "A4": arms.A4,
          "composer": arms.composer,
          "contour": contour.contour,
          "sequence_scan": arms.sequence_scan,
          "tient_dans_la_zone": arms.tient_dans_la_zone,
          "reperes_arms": roles.reperes_arms,
          "TOLERANCE_COULEUR": roles.TOLERANCE_COULEUR,
          "TOLERANCE": contour.TOLERANCE,
          "recolter": arms.Ecoute.recolter,
          "UNITES_PAR_MM": arms.UNITES_PAR_MM}


def zone_verifiee_sans_le_premier_repere():
    """La faute : ne comparer l'écart qu'à la taille de la zone.

    225,9 tient dans 255,9, et 148,8 tient dans 174,4 — donc rien à
    signaler, en apparence. C'est faux : les repères ne partent pas de
    l'origine, et le cas réel du 14/08/2026 débordait des DEUX côtés.
    """
    def sans_origine(ecart, zone, premier=None, branche=arms.BRANCHE):
        return [f"écart {ecart} plus grand que la zone {zone}"] \
            if ecart[0] > zone[0] or ecart[1] > zone[1] else []
    arms.tient_dans_la_zone = sans_origine


def tb57_fige_dans_la_sequence():
    """La faute : recopier TB57,1,1 de la capture au lieu de le paramétrer.

    C'est l'état d'avant le 14/08/2026, et le défaut ne se voit sur aucun
    scan : la séquence part, la machine cherche. Il se voit seulement à ce
    qu'on ne peut RIEN essayer.
    """
    vraie = _VRAIS["sequence_scan"]

    def figee(ecart_x, ecart_y, branche=arms.BRANCHE, epaisseur=1.0,
              type_repere=1, tb57=(1, 1)):
        return vraie(ecart_x, ecart_y, branche, epaisseur, type_repere, (1, 1))
    arms.sequence_scan = figee


def repere_reconnu_a_sa_seule_boite():
    """La faute tentante : reconnaître un repère à son encombrement.

    Un carré de 20 mm passerait alors pour un repère et serait écarté de
    la découpe, sans le moindre message.
    """
    def sur_la_boite(polylignes, branche=20.0, epaisseur=1.0, tolerance=0.5):
        trouves = set()
        for i, (points, ferme) in enumerate(polylignes):
            xs = [x for x, _ in points]
            ys = [y for _, y in points]
            if (ferme and abs((max(xs) - min(xs)) - branche) < tolerance
                    and abs((max(ys) - min(ys)) - branche) < tolerance):
                trouves.add(i)
        return trouves
    roles.reperes_arms = sur_la_boite


def rouge_qui_cesse_d_etre_du_rouge():
    """La faute : exiger un rouge EXACT, que peu de logiciels exportent."""
    roles.TOLERANCE_COULEUR = 0.001


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
    """La faute d'origine : jeter le tampon au lieu de le regarder.

    C'est le code d'avant le 13/08/2026. Il ne se voit sur AUCUNE
    réponse — seulement sur l'annonce du scan, qui disparaît sans laisser
    de trace. Treize captures pour s'en apercevoir.
    """
    def recolter_en_jetant(self, depart=0.0):
        self.reste = b""
    arms.Ecoute.recolter = recolter_en_jetant


def annonces_decoupees_sur_les_CR_sans_voir_l_ETX():
    """La faute INVERSE, payée le même jour : deux cents fausses annonces
    tirées des lignes d'un unique vidage de configuration."""
    def recolter_naif(self, depart=0.0):
        while b"\r" in self.reste:
            i = self.reste.find(b"\r")
            trame, self.reste = self.reste[:i], self.reste[i + 1:]
            self._noter(trame.decode("ascii", "replace"), depart)
        self.reste = b""
    arms.Ecoute.recolter = recolter_naif


def unites_desaccordees():
    """La faute : changer 40 d'un côté sans l'autre. Le piège VERSION."""
    arms.UNITES_PAR_MM = 50


def arms_qui_ne_compare_pas_les_types():
    """La faute : lire les réglages sans les confronter au gabarit.

    C'est l'état de la journée du 13/08/2026 — le renseignement était
    disponible, personne ne le rapprochait de la feuille employée.
    """
    arms.desaccords = lambda lus, type_gabarit=2, branche=arms.BRANCHE: []


def a4_dans_l_ordre_du_papier():
    """La faute : écrire A4 = (210, 297) parce qu'un A4 « fait 210×297 ».

    L'avance court sur les 297. Avec l'ordre du papier, un dessin un peu
    long met ses repères hors de la feuille — et l'impression paraît
    normale, c'est la détection qui échoue ensuite.
    """
    arms.A4 = (210.0, 297.0)


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


_vraies = {}


def echelles_non_accordees():
    """La faute vue le 14/08/2026 : les champs rétablis, pas les facteurs.

    `_poser_reglages` travaille en silence pour que les champs ne se
    répondent pas ; le silence coupait du même coup le calcul de
    `ech_x`/`ech_y`. Un projet rouvert affichait 150 x 40 mm et découpait
    100 x 50 — le défaut ne se voyait pas dans l'interface.
    """
    import pupitre
    _vraies["accorder"] = pupitre.Pupitre._accorder_echelles
    pupitre.Pupitre._accorder_echelles = lambda self, echelles=None: None


def molette_non_protegee():
    """La faute : ne protéger que les widgets NÉS AVANT le balayage."""
    import pupitre
    _vraies["molette"] = pupitre.Pupitre._proteger_de_la_molette
    pupitre.Pupitre._proteger_de_la_molette = lambda self, *a: None


def visuel_transforme_dans_l_ordre_du_pipeline():
    """La faute : écrire rotation puis miroir comme le fait le pipeline.

    Les transformations d'un pinceau Qt agissent sur le REPÈRE : la
    dernière écrite s'applique la première au contenu. Écrites dans
    l'ordre du pipeline, quatre combinaisons sur seize posaient l'image
    de travers — et une image de travers fait valider un placement faux.
    """
    import pupitre
    _vraies["visuel"] = pupitre.Apercu._peindre_visuel
    vrai = _vraies["visuel"]

    def a_l_envers(self, p, pt):
        rot, (mx, my) = self.rotation % 360, self.miroirs
        if not (rot and (mx or my)):
            return vrai(self, p, pt)
        self.rotation, self.miroirs = 0, (False, False)
        try:
            from PySide6.QtCore import QRectF
            rendu = self._rendu_visuel()
            if rendu is None or not self.place:
                return
            x0, y0, x1, y1 = self.place
            rect = QRectF(pt(x0, y1), pt(x1, y0))
            centre = rect.center()
            p.save()
            p.setOpacity(0.75)
            p.translate(centre)
            p.rotate(rot)                      # ordre du pipeline : faux
            p.scale(-1.0 if mx else 1.0, -1.0 if my else 1.0)
            p.translate(-centre.x(), -centre.y())
            if rot in (90, 270):
                rect = QRectF(centre.x() - rect.height() / 2,
                              centre.y() - rect.width() / 2,
                              rect.height(), rect.width())
            rendu.render(p, rect)
            p.restore()
        finally:
            self.rotation, self.miroirs = rot, (mx, my)

    pupitre.Apercu._peindre_visuel = a_l_envers


def rainage_devenu_coupe():
    """La faute : « corriger » la force 2 du canson en la croyant fautive."""
    for nom, m in materiaux.MATERIAUX.items():
        if m.get("usage") == "rainer":
            m["force"] = 20


# La vraie méthode, gardée avant toute casse : la remettre après coup
# suppose de l'avoir prise intacte.
def _vraie_methode():
    import pupitre
    return pupitre.Pupitre._accorder_echelles


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

    ("A4 écrit dans l'ordre du papier, pas des axes machine",
     "test_l_a4_est_dans_les_axes_de_la_machine",
     a4_dans_l_ordre_du_papier,
     lambda: setattr(arms, "A4", _VRAIS["A4"])),

    ("page du gabarit officiel arrondie à l'A4",
     "test_gabarit_officiel_garde_ses_cotes_relevees",
     gabarit_officiel_arrondi_a_l_a4,
     lambda: setattr(arms, "PAGE", _VRAIS["PAGE"])),

    ("zone vérifiée sans la position du premier repère",
     "test_un_repere_hors_datteinte_est_signale_avant_impression",
     zone_verifiee_sans_le_premier_repere,
     lambda: setattr(arms, "tient_dans_la_zone", _VRAIS["tient_dans_la_zone"])),

    ("TB57 figé, donc impossible à éprouver",
     "test_sequence_de_scan_est_calculee",
     tb57_fige_dans_la_sequence,
     lambda: setattr(arms, "sequence_scan", _VRAIS["sequence_scan"])),

    ("repère reconnu à sa seule boîte englobante",
     "test_un_repere_ne_se_confond_pas_avec_un_carre",
     repere_reconnu_a_sa_seule_boite,
     lambda: setattr(roles, "reperes_arms", _VRAIS["reperes_arms"])),

    ("tolérance de couleur ramenée à l'exactitude",
     "test_la_couleur_decide_du_role",
     rouge_qui_cesse_d_etre_du_rouge,
     lambda: setattr(roles, "TOLERANCE_COULEUR", _VRAIS["TOLERANCE_COULEUR"])),

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
     lambda: setattr(arms.Ecoute, "recolter", _VRAIS["recolter"])),

    ("lignes d'un vidage prises pour des annonces",
     "test_vidage_de_configuration_nest_pas_pris_pour_des_annonces",
     annonces_decoupees_sur_les_CR_sans_voir_l_ETX,
     lambda: setattr(arms.Ecoute, "recolter", _VRAIS["recolter"])),

    ("unités par mm recopiées et laissées vieillir",
     "test_unites_accordees",
     unites_desaccordees,
     lambda: setattr(arms, "UNITES_PAR_MM", _VRAIS["UNITES_PAR_MM"])),

    ("rainage « corrigé » en découpe",
     "test_rainage_reste_du_rainage",
     rainage_devenu_coupe,
     lambda: materiaux.MATERIAUX.update(_VRAIS["MATERIAUX"])),

    ("taille d'un projet rétablie à l'affichage mais pas au dessin",
     "test_un_projet_rouvert_garde_la_TAILLE_du_dessin",
     echelles_non_accordees,
     lambda: setattr(__import__("pupitre").Pupitre,
                     "_accorder_echelles", _vraies["accorder"])),

    ("molette protégée seulement sur les widgets du constructeur",
     "test_la_molette_epargne_aussi_les_listes_nees_plus_tard",
     molette_non_protegee,
     lambda: setattr(__import__("pupitre").Pupitre,
                     "_proteger_de_la_molette", _vraies["molette"])),

    ("image de l'aperçu tournée dans l'ordre du pipeline",
     "test_limage_se_pose_sous_les_traces_au_bon_endroit",
     visuel_transforme_dans_l_ordre_du_pipeline,
     lambda: setattr(__import__("pupitre").Apercu,
                     "_peindre_visuel", _vraies["visuel"])),

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
            if hasattr(T, nom_test):
                getattr(T, nom_test)()
            else:
                getattr(P, nom_test)(fenetre())
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
