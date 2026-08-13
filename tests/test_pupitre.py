#!/usr/bin/env python3
"""Ce qu'une capture d'écran a vu et que la syntaxe ne voit pas.

Le 11/08/2026, la liste « outil » a DISPARU de l'interface : une
renumérotation des lignes s'était appliquée en cascade — 1 devient 3, puis
3 devient 5, puis 5 devient 7 — et le champ a fini par occuper la case d'un
autre. Rien n'a protesté : le fichier compilait, le champ existait, il
répondait aux réglages. Il n'était simplement plus visible.

Qt empile silencieusement deux widgets rangés dans la même case. C'est
exactement le genre de faute qu'un test attrape mieux qu'un relecteur.

    QT_QPA_PLATFORM=offscreen python3 tests/test_pupitre.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from PySide6.QtWidgets import QApplication, QGridLayout, QWidget  # noqa: E402

import pupitre                                                    # noqa: E402


def _grilles(racine):
    """Toutes les QGridLayout de l'arbre, avec le titre qui les porte."""
    trouvees = []
    for w in racine.findChildren(QWidget):
        lay = w.layout()
        if isinstance(lay, QGridLayout):
            titre = w.title() if hasattr(w, "title") else w.objectName()
            trouvees.append((titre or w.__class__.__name__, lay))
    return trouvees


def test_aucune_case_occupee_deux_fois(fenetre):
    """Deux widgets dans la même case : Qt les empile, l'un disparaît."""
    for titre, grille in _grilles(fenetre):
        cases = {}
        for i in range(grille.count()):
            item = grille.itemAt(i)
            if item.widget() is None:
                continue
            r, c, hr, hc = grille.getItemPosition(i)
            for dr in range(hr):
                for dc in range(hc):
                    cle = (r + dr, c + dc)
                    autre = cases.get(cle)
                    assert autre is None, (
                        f"grille « {titre} » : la case {cle} porte à la fois "
                        f"{autre} et {_nom(item.widget())}")
                    cases[cle] = _nom(item.widget())


def _nom(w):
    txt = ""
    for methode in ("text", "currentText"):
        if hasattr(w, methode):
            try:
                txt = getattr(w, methode)()
                break
            except Exception:
                pass
    return f"{w.__class__.__name__}({txt[:24]!r})" if txt else w.__class__.__name__


def test_tous_les_champs_sont_places(fenetre):
    """Un champ créé mais jamais rangé dans une mise en page est invisible."""
    prefixes = ("spn_", "cmb_", "chk_", "lbl_", "b_")
    orphelins = []
    for nom in dir(fenetre):
        if not nom.startswith(prefixes):
            continue
        w = getattr(fenetre, nom)
        if isinstance(w, QWidget) and w.parentWidget() is None:
            orphelins.append(nom)
    assert not orphelins, f"champs jamais placés : {orphelins}"


def test_aucun_titre_ne_perd_son_esperluette(fenetre):
    """Qt lit `&` comme un raccourci clavier et l'EFFACE de l'affichage.

    « Print & cut » s'affichait « Print _cut », le `c` souligné. Aucun
    test ne pouvait le voir : le texte est bien celui qu'on a écrit, c'est
    le rendu qui diffère. Repéré sur une capture d'écran, comme la liste
    « outil » qui avait disparu sous un autre widget.

    La règle : dans un libellé Qt, une esperluette littérale se double.
    """
    from PySide6.QtWidgets import QGroupBox, QCheckBox, QPushButton, QLabel
    for classe in (QGroupBox, QCheckBox, QPushButton, QLabel):
        for w in fenetre.findChildren(classe):
            titre = w.title() if classe is QGroupBox else w.text()
            sans_doubles = titre.replace("&&", "")
            assert "&" not in sans_doubles, (
                f"« {titre} » : esperluette non doublée, Qt l'effacera "
                f"et soulignera la lettre suivante")


def test_tous_les_reglages_sont_enregistres(fenetre):
    """Un réglage absent de la table de `projet` ne serait jamais gardé.

    Et ça ne se verrait pas : à la réouverture il reprendrait simplement
    sa valeur par défaut, en silence. C'est le pire genre de défaut —
    celui qui ressemble à une erreur de l'utilisateur.

    D'où la table déclarative plutôt que deux fonctions symétriques, et
    d'où ce test, qui exige que TOUT widget de réglage y figure.
    """
    import re
    import projet

    source = open(os.path.join(os.path.dirname(__file__), "..",
                               "pupitre.py"), encoding="utf-8").read()
    dans_l_interface = {n for n in re.findall(
        r"self\.((?:spn|chk|cmb)_[a-z0-9_]+)\s*=", source)}
    dans_la_table = {nom for nom, _ in projet.REGLAGES}

    oublies = sorted(dans_l_interface - dans_la_table)
    assert not oublies, (
        f"réglage(s) absent(s) de projet.REGLAGES : {oublies} — ils ne "
        f"seraient pas enregistrés, et reprendraient leur valeur par "
        f"défaut sans rien dire")

    fantomes = sorted(dans_la_table - dans_l_interface)
    assert not fantomes, (
        f"projet.REGLAGES nomme des widgets qui n'existent plus : "
        f"{fantomes}")


def test_un_projet_revient_comme_il_est_parti(fenetre):
    """Enregistrer puis rouvrir doit rendre EXACTEMENT les mêmes réglages.

    La propriété qui compte : un placement patiemment ajusté ne doit pas
    se perdre. Le 13/08/2026, un print & cut a été gâché parce qu'il ne
    vivait que dans la fenêtre ouverte.
    """
    import tempfile
    import projet

    fenetre.spn_x.setValue(37.5)
    fenetre.spn_ech.setValue(62.0)
    fenetre.cmb_rot.setCurrentText("90°")
    fenetre.chk_contour.setChecked(True)
    fenetre.spn_retrait.setValue(4.5)
    avant = fenetre._lire_reglages()

    with tempfile.TemporaryDirectory() as dossier:
        chemin = projet.enregistrer(os.path.join(dossier, "essai"), avant,
                                    svg="<svg/>", source="/tmp/x.svg")
        relu = projet.charger(chemin)

    # On dérange tout, puis on repose.
    fenetre.spn_x.setValue(1.0)
    fenetre.spn_ech.setValue(100.0)
    fenetre.cmb_rot.setCurrentText("0°")
    fenetre.chk_contour.setChecked(False)
    fenetre._poser_reglages(relu["reglages"])

    apres = fenetre._lire_reglages()
    differences = {k: (avant[k], apres[k]) for k in avant
                   if avant[k] != apres.get(k)}
    assert not differences, f"réglages perdus au retour : {differences}"


def test_un_deplacement_apres_export_est_signale(fenetre):
    """Déplacer le dessin après l'export invalide la feuille imprimée.

    Rien ne le signalait, et c'est ce qui a rendu la mesure du
    13/08/2026 inexploitable : l'écart mêlait le décalage de la machine
    et le recadrage fait entre-temps.
    """
    import projet

    fenetre.spn_x.setValue(25.0)
    reference = projet.empreinte(fenetre._lire_reglages())

    assert not projet.a_bouge_depuis_export(
        fenetre._lire_reglages(), reference), "faux positif sans rien bouger"

    fenetre.spn_x.setValue(26.0)
    assert projet.a_bouge_depuis_export(
        fenetre._lire_reglages(), reference), (
        "un déplacement de 1 mm après l'export n'est pas signalé")

    # Sans export, il n'y a pas de référence : ne rien signaler.
    assert not projet.a_bouge_depuis_export(fenetre._lire_reglages(), None)


def test_un_recalcul_nefface_pas_ce_qui_a_ete_scelle(fenetre):
    """Bouger un réglage ne doit effacer NI le SVG gardé NI l'empreinte.

    Défaut réel, introduit et attrapé le 13/08/2026 : une insertion avait
    touché deux endroits à la fois, parce que la même ligne existait dans
    le constructeur et dans le recalcul. Chaque mouvement d'un curseur
    remettait tout à zéro.

    Rien ne l'aurait signalé : le projet enregistré aurait simplement été
    vide, et l'alerte de déplacement n'aurait jamais pu se déclencher.
    """
    fenetre.brut = [([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 0.0)],
                     True)]
    fenetre.svg_source = "<svg/>"
    fenetre.empreinte_export = "scelle"

    fenetre.spn_x.setValue(12.0)
    fenetre._recalculer()

    assert fenetre.svg_source == "<svg/>", (
        "le recalcul a effacé le dessin gardé pour l'enregistrement")
    assert fenetre.empreinte_export == "scelle", (
        "le recalcul a effacé l'empreinte de l'export")


def test_les_onglets_defilent(fenetre):
    """Chaque onglet doit pouvoir défiler, sinon la fenêtre déborde l'écran.

    Le 13/08/2026, l'ajout du cadre Print & cut a allongé la colonne de
    l'onglet Dessin au point de pousser la fenêtre hors du bureau de
    Christophe — barre de titre comprise, donc impossible à déplacer.

    Un panneau qui grandit est normal. Une fenêtre qu'on ne peut plus
    attraper ne l'est pas, et ça ne se voit sur aucun écran assez grand.
    """
    from PySide6.QtWidgets import QScrollArea
    for i in range(fenetre.onglets.count()):
        page = fenetre.onglets.widget(i)
        nom = fenetre.onglets.tabText(i)
        assert isinstance(page, QScrollArea), (
            f"l'onglet « {nom} » ne défile pas : tout ajout futur "
            f"repoussera la fenêtre hors de l'écran")
        assert page.widgetResizable(), (
            f"l'onglet « {nom} » défile mais ne s'ajuste pas en largeur")


def test_les_onglets_sont_nommes(fenetre):
    attendus = ["Dessin", "Outil", "Machine"]
    obtenus = [fenetre.onglets.tabText(i)
               for i in range(fenetre.onglets.count())]
    assert obtenus == attendus, f"onglets : {obtenus}, attendu {attendus}"


def lancer():
    app = QApplication.instance() or QApplication([])
    fenetre = pupitre.Pupitre()
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    echecs = []
    for nom, f in tests:
        try:
            f(fenetre)
            print(f"  ok    {nom}")
        except AssertionError as e:
            echecs.append((nom, str(e)))
            print(f"  RATÉ  {nom}")
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
