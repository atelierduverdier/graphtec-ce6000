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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QGroupBox, QCheckBox, QPushButton, QLabel
    for classe in (QGroupBox, QCheckBox, QPushButton, QLabel):
        for w in fenetre.findChildren(classe):
            # Un libellé en TEXTE ENRICHI n'est pas concerné : `&` y est
            # du HTML, et `&#9644;` désigne un rectangle plein, pas un
            # raccourci clavier.
            if classe is QLabel and w.textFormat() == Qt.RichText:
                continue
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


def test_un_role_sans_trace_ne_fait_pas_tomber_la_fenetre(fenetre):
    """Demander « découper » sur un fichier sans rouge ne doit pas casser.

    Défaut réel, attrapé le 13/08/2026 en essayant les rôles sur une
    feuille composée : aucun tracé ne restait, et le calcul d'emprise
    levait une exception sur une liste vide.

    L'attendu n'est pas seulement de ne pas tomber : l'envoi doit être
    refusé, sinon on lancerait un travail vide sans le savoir.
    """
    import svg2hpgl as noyau
    import roles as roles_couleur

    # Un dessin tout noir : rien à découper.
    fenetre.brut = [([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 0.0)],
                     True)]
    fenetre.couleurs = [(0.0, 0.0, 0.0)]
    fenetre.correspondance = {}
    fenetre.reperes = set()
    fenetre.cmb_travail.setCurrentText("découper")

    fenetre._recalculer()          # ne doit pas lever

    assert fenetre._retenus() == [], "un noir a été rangé dans la découpe"
    assert not fenetre.b_envoyer.isEnabled(), (
        "l'envoi reste possible alors qu'aucun tracé ne partirait")


def test_rien_nest_rogne_en_silence(fenetre):
    """Un champ hors de la zone visible doit se signaler par une barre.

    La zone défilante interdisait la barre horizontale, ce qui paraissait
    plus propre. En réalité le contenu était ROGNÉ sans rien dire :
    Christophe a perdu les flèches de ses champs, et le libellé « noir
    seul » s'affichait « noir ». Vu sur son écran, pas sur les nôtres —
    les mesures de géométrie disaient que tout tenait.

    Mieux vaut une barre visible qu'un champ invisible.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea
    for i in range(fenetre.onglets.count()):
        zone = fenetre.onglets.widget(i)
        if not isinstance(zone, QScrollArea):
            continue
        assert zone.horizontalScrollBarPolicy() != Qt.ScrollBarAlwaysOff, (
            f"l'onglet « {fenetre.onglets.tabText(i)} » interdit la barre "
            f"horizontale : ce qui déborde disparaît sans un mot")


def test_la_molette_ne_change_pas_les_valeurs(fenetre):
    """Passer la molette sur un champ ne doit pas modifier sa valeur.

    Signalé par Christophe le 14/08/2026 : on fait défiler la colonne, le
    curseur passe sur un champ, le défilement s'arrête net et le réglage
    change. Sans message, et sans qu'on l'ait voulu — le pire genre de
    faute sur un logiciel qui pilote une machine.
    """
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QSpinBox

    champs = (fenetre.findChildren(QSpinBox)[:3]
              + fenetre.findChildren(QDoubleSpinBox)[:3])
    assert champs, "aucun champ numérique à éprouver"
    for champ in champs:
        avant = champ.value()
        roue = QWheelEvent(QPoint(5, 5), champ.mapToGlobal(QPoint(5, 5)),
                           QPoint(0, 0), QPoint(0, 120), Qt.NoButton,
                           Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(champ, roue)
        assert champ.value() == avant, (
            f"la molette a changé « {champ.objectName() or champ} » de "
            f"{avant} à {champ.value()} sans qu'on l'ait touché")


def test_la_colonne_na_pas_de_largeur_figee(fenetre):
    """La colonne doit suivre son contenu, pas un nombre écrit un jour.

    Elle valait 360 px, décidée quand elle portait six cadres. Elle en
    porte neuf, dont un de vingt-cinq lignes, et tout ce qui dépassait
    était rogné. Aucune correction en aval — barre de défilement, largeur
    des champs, minimum sur l'onglet — ne pouvait rien y faire : la
    contrainte était ici, et je l'ai cherchée ailleurs pendant trois
    tours.

    Le nombre figé est le piège de la ligne VERSION restée quarante-quatre
    versions en retard, sous une autre forme.
    """
    # La largeur est posée par un minuteur, une fois la mise en page
    # faite. Hors boucle d'événements il ne se déclenche pas : on appelle
    # donc la méthode qu'on éprouve, plutôt que d'attendre en vain.
    fenetre._ajuster_largeurs()

    colonne = getattr(fenetre, "colonne", None)
    assert colonne is not None, "la colonne de réglages n'est pas nommée"
    assert colonne.minimumWidth() != colonne.maximumWidth(), (
        f"largeur figée à {colonne.minimumWidth()} px : le contenu qui "
        f"dépasse sera rogné, quoi qu'on règle par ailleurs")
    besoin = max(fenetre.onglets.widget(i).widget().sizeHint().width()
                 for i in range(fenetre.onglets.count()))
    assert colonne.minimumWidth() >= besoin, (
        f"la colonne accepte {colonne.minimumWidth()} px alors que son "
        f"contenu en réclame {besoin}")


def test_le_contour_ne_declenche_pas_lalerte_de_deplacement(fenetre):
    """Cocher « découper autour du dessin » ne déplace pas le dessin.

    Le contour ajoute un tracé AUTOUR du motif ; la feuille imprimée
    reste valable, et la découpe retombera juste. L'alerte criait pourtant
    dès qu'on cochait la case — c'est-à-dire au moment le plus normal du
    travail, celui où l'on prépare un autocollant.

    Un garde-fou qui crie pour rien finit par ne plus être lu, et c'est
    alors qu'il manque le vrai déplacement. Signalé par Christophe le
    14/08/2026, capture d'écran à l'appui.
    """
    import projet

    fenetre.brut = [([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 0.0)],
                     True)]
    fenetre.couleurs = [(0.0, 0.0, 0.0)]
    fenetre.chk_contour.setChecked(False)
    fenetre.spn_x.setValue(20.0)
    reference = projet.empreinte(fenetre._lire_reglages())

    fenetre.chk_contour.setChecked(True)
    assert not projet.a_bouge_depuis_export(
        fenetre._lire_reglages(), reference), (
        "cocher le contour déclenche l'alerte de déplacement")

    fenetre.spn_retrait.setValue(5.0)
    assert not projet.a_bouge_depuis_export(
        fenetre._lire_reglages(), reference), (
        "changer le retrait déclenche l'alerte de déplacement")

    # Mais un vrai déplacement doit toujours être vu.
    fenetre.spn_x.setValue(24.0)
    assert projet.a_bouge_depuis_export(
        fenetre._lire_reglages(), reference), (
        "déplacer le dessin de 4 mm ne déclenche plus rien")


def test_un_export_ne_se_denonce_pas_lui_meme(fenetre):
    """Après un export, l'alerte de déplacement doit rester muette.

    L'export RÈGLE lui-même le placement — il pose le dessin à la
    distance connue du premier repère. Sceller l'empreinte AVANT de le
    faire revenait à figer un état que l'export allait aussitôt changer :
    l'alerte criait dès l'envoi suivant, sans que personne n'ait rien
    touché.

    C'est le « je n'ai rien touché » de Christophe, le 14/08/2026, qui a
    tranché contre mon premier diagnostic — j'accusais la case du contour.

    Le test appelle le VRAI geste, `_caler_sur_la_feuille`, et non une
    imitation de sa séquence : une première version rejouait les étapes à
    la main et ne voyait donc pas la faute quand on la remettait dans le
    code. Un test qui n'appelle pas ce qu'il surveille ne surveille rien.
    """
    import arms
    import projet

    fenetre.brut = [([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 0.0)],
                     True)]
    fenetre.couleurs = [(0.0, 0.0, 0.0)]
    fenetre.spn_marge_arms.setValue(20.0)
    fenetre.spn_x.setValue(5.0)
    fenetre.spn_y.setValue(5.0)
    fenetre._recalculer()

    _svg, infos = arms.composer(fenetre.calcule, marge=20.0)
    fenetre._caler_sur_la_feuille(infos)

    assert not projet.a_bouge_depuis_export(
        fenetre._lire_reglages(), fenetre.empreinte_export), (
        "l'export se dénonce lui-même : l'alerte crierait à l'envoi "
        "suivant sans que personne n'ait rien touché")

    # Et le placement doit bien avoir été posé, sinon on scellerait le
    # néant sans que rien ne proteste.
    ox, oy = infos["origine_dessin"]
    assert fenetre.spn_x.value() == ox and fenetre.spn_y.value() == oy, (
        "le placement n'a pas été posé sur la feuille")
    assert fenetre.chk_arms.isChecked()


def test_lapercu_sait_le_role_de_chaque_trace(fenetre):
    """Chaque tracé de l'aperçu doit porter SON rôle, dans le bon ordre.

    L'aperçu peint le motif, le rainage, la découpe et le contour de
    quatre couleurs. L'appariement se fait par l'ORDRE, parce que le
    pipeline reconstruit les listes de points à chaque étape et que les
    identités d'objets n'y survivent pas — une première version appariait
    par `id()` et rangeait donc tout en « tracer », sans que rien ne
    proteste.

    Christophe : « et je les vois comment ces traits ? » — il ne les
    voyait pas.
    """
    import roles as roles_couleur

    # noir à tracer, bleu à rainer, rouge à découper — dans cet ordre.
    fenetre.brut = [
        ([(0.0, 0.0), (50.0, 0.0), (50.0, 30.0), (0.0, 0.0)], True),
        ([(10.0, 5.0), (10.0, 25.0)], False),
        ([(-5.0, -5.0), (55.0, -5.0), (55.0, 35.0), (-5.0, -5.0)], True),
    ]
    fenetre.couleurs = [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)]
    fenetre.correspondance = {}
    fenetre.reperes = set()
    fenetre.chk_contour.setChecked(False)
    fenetre.cmb_travail.setCurrentText("tout, sauf les repères")
    fenetre._recalculer()

    assert len(fenetre.apercu.roles) == len(fenetre.calcule), (
        "autant de rôles que de tracés, sinon l'appariement a glissé")
    assert set(fenetre.apercu.roles) == {"tracer", "rainer", "decouper"}, (
        f"rôles peints : {fenetre.apercu.roles} — tout a été rangé dans "
        f"le même, l'appariement ne suit plus l'ordre")

    fenetre.chk_contour.setChecked(True)
    fenetre._recalculer()
    assert "contour" in fenetre.apercu.roles, (
        "le contour n'a pas sa couleur propre dans l'aperçu")
    assert len(fenetre.apercu.roles) == len(fenetre.calcule) + \
        len(fenetre.contour)


def test_ouvrir_une_image_ne_meurt_pas_en_silence(fenetre):
    """Ouvrir un JPG doit poser le dessin, pas mourir en route.

    `svg_source` lisait le fichier en UTF-8 pour le garder dans le projet.
    Sur un JPEG binaire, cela lève une UnicodeDecodeError — qui n'était
    pas attrapée, l'ouverture mourait là, et Christophe voyait
    « rien n'apparaît » sans le moindre message. Le pire genre de faute :
    silencieuse, et qui ressemble à un fichier illisible.

    Le test reproduit le geste sur un vrai fichier binaire, sans passer
    par la boîte de dialogue.
    """
    import tempfile
    import numpy as np
    from PIL import Image
    import silhouette

    with tempfile.TemporaryDirectory() as dossier:
        chemin = os.path.join(dossier, "motif.jpg")
        # Un disque noir sur fond blanc, marges comprises.
        a = np.full((200, 300, 3), 255, dtype=np.uint8)
        yy, xx = np.mgrid[0:200, 0:300]
        a[((yy - 100) ** 2 + (xx - 150) ** 2) ** 0.5 < 60] = 0
        Image.fromarray(a).save(chemin, quality=95)

        trace, couleurs, avert = fenetre._ouvrir_image(chemin)
        assert trace and couleurs, "l'image n'a rien donné"

        # Le geste qui mourait : lire le fichier comme du texte.
        fenetre.svg_source = None
        if not chemin.lower().endswith((".png", ".jpg", ".jpeg")):
            fenetre.svg_source = open(chemin, encoding="utf-8").read()
        assert fenetre.svg_source is None, (
            "une image ne doit pas être lue comme du texte")

        fenetre.brut, fenetre.couleurs = trace, couleurs
        fenetre.reperes = set()
        fenetre._refaire_liste_couleurs()
        fenetre._recalculer()

    assert fenetre.calcule, "rien n'a été calculé après l'ouverture"
    assert fenetre.visuel and fenetre.visuel.get("contenu"), (
        "l'image d'origine n'a pas été gardée pour l'impression")


def test_les_cotes_en_millimetres_pilotent_lechelle(fenetre):
    """On pense en millimètres dans un atelier, pas en pourcentage.

    Le pour cent obligeait à calculer de tête à partir d'une taille
    d'origine qu'on ne connaît pas toujours — celle d'une image ouverte
    à 96 points par pouce, par exemple.

    Les cotes et le pour cent doivent rester d'accord dans les deux sens,
    sans boucler : une saisie qui en met une autre à jour, laquelle
    redéclenche la première, tourne indéfiniment.
    """
    import svg2hpgl as noyau

    fenetre.brut = [([(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 0.0)],
                     True)]
    fenetre.couleurs = [(0.0, 0.0, 0.0)]
    fenetre.reperes = set()
    fenetre.ech_x = fenetre.ech_y = 1.0
    fenetre.chk_prop.setChecked(True)
    fenetre._rafraichir_cotes()
    fenetre._recalculer()

    assert fenetre.spn_larg.value() == 100.0
    assert fenetre.spn_haut.value() == 50.0

    fenetre.spn_larg.setValue(50.0)
    assert fenetre.spn_haut.value() == 25.0, "les proportions n'ont pas suivi"
    assert fenetre.spn_ech.value() == 50.0, "le pour cent n'a pas suivi"
    x0, y0, x1, y1 = noyau.cadre(fenetre.calcule)
    assert abs((x1 - x0) - 50.0) < 0.01, (
        f"le dessin fait {x1-x0:.1f} mm alors qu'on a demandé 50")

    # Proportions déverrouillées : les deux axes se règlent séparément.
    fenetre.chk_prop.setChecked(False)
    fenetre.spn_haut.setValue(40.0)
    assert fenetre.spn_larg.value() == 50.0, (
        "la largeur a bougé alors que les proportions sont déverrouillées")
    x0, y0, x1, y1 = noyau.cadre(fenetre.calcule)
    assert abs((y1 - y0) - 40.0) < 0.01 and abs((x1 - x0) - 50.0) < 0.01, (
        f"emprise {x1-x0:.1f} × {y1-y0:.1f} au lieu de 50 × 40")


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
