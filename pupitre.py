#!/usr/bin/env python3
"""Pupitre de tracé pour le Graphtec CE6000-60.

Ce que la ligne de commande ne sait pas faire : **montrer** le dessin posé
sur le média. C'est la seule chose que le logiciel Graphtec avait vraiment
en plus (son écran « Page »), tout le reste étant soit de la découpe, soit
déjà porté par la machine elle-même.

Le média est interrogé à la machine (`OH;`), comme le fait le logiciel
d'origine — sa taille dépend de la feuille chargée et de la position des
galets, pas du modèle de traceur.

Non fait ici, et assumé : la MOSAÏQUE (découper un grand dessin en
panneaux). Elle demande de couper les polylignes à la frontière de chaque
panneau, ce qui est le seul morceau délicat de tout ça et mérite d'être
traité à part.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg2hpgl as noyau                                    # noqa: E402
from theme import SOMBRE, CLAIR, feuille_de_style           # noqa: E402
import conditions as machine                                # noqa: E402
import icones                                               # noqa: E402

from PySide6.QtCore import Qt, QPointF, QRectF, QSize        # noqa: E402
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF  # noqa: E402
from PySide6.QtWidgets import (                              # noqa: E402
    QApplication, QWidget, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QComboBox, QCheckBox, QGridLayout, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFileDialog, QMessageBox, QSizePolicy, QTabWidget, QFrame)


# ======================================================================
# A. L'APERÇU
# ======================================================================

class Apercu(QWidget):
    """Média, zone utile et dessin, à l'échelle, Y vers le haut."""

    def __init__(self, palette):
        super().__init__()
        self.setMinimumSize(420, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.pal = palette
        self.media = (380.9, 285.6)
        self.polygones = []
        self.emprise = None
        self.deborde = False

    def habiller(self, palette):
        self.pal = palette
        self.update()

    def poser(self, polylignes, media, deborde):
        self.media = media
        self.deborde = deborde
        self.polygones = [QPolygonF([QPointF(x, y) for x, y in pts])
                          for pts, _ in polylignes]
        self.emprise = noyau.cadre(polylignes) if polylignes else None
        self.update()

    def paintEvent(self, _):
        pal = self.pal
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(pal.ardoise))

        mx, my = self.media
        marge = 14
        k = min((self.width() - 2 * marge) / max(mx, 1e-6),
                (self.height() - 2 * marge) / max(my, 1e-6))
        ox = (self.width() - mx * k) / 2
        oy = (self.height() + my * k) / 2          # Y vers le haut

        def pt(x, y):
            return QPointF(ox + x * k, oy - y * k)

        # la zone utile, telle que la machine la déclare
        p.setPen(QPen(QColor(pal.texte_faible), 1, Qt.DashLine))
        p.setBrush(QColor(pal.papier))
        p.drawRect(QRectF(pt(0, my), pt(mx, 0)))

        # le dessin
        if self.polygones:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(pal.alerte if self.deborde else pal.trace), 1))
            for poly in self.polygones:
                p.drawPolyline(QPolygonF([pt(q.x(), q.y()) for q in poly]))

        # l'emprise, pour lire le placement d'un coup d'oeil
        if self.emprise:
            x0, y0, x1, y1 = self.emprise
            p.setPen(QPen(QColor(pal.alerte if self.deborde else pal.accent),
                          1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(pt(x0, y1), pt(x1, y0)))

        p.setPen(QColor(pal.texte_faible))
        p.drawText(8, self.height() - 8,
                   f"média {mx:.1f} × {my:.1f} mm")


# ======================================================================
# B. LE PUPITRE
# ======================================================================

class Pupitre(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pupitre de tracé — Graphtec CE6000-60")
        self.brut = []                    # polylignes du SVG, jamais modifiées
        self.calcule = []                 # après placement, ce qui sera tracé
        self.media = (380.9, 285.6)
        self.chemin = None
        self.pal = SOMBRE                 # comme le visualiseur G-code

        self.apercu = Apercu(self.pal)
        self.info = QLabel("Aucun dessin chargé.")
        self.info.setObjectName("faible")
        self.info.setWordWrap(True)

        racine = QVBoxLayout(self)
        racine.setContentsMargins(14, 12, 14, 12)
        racine.setSpacing(10)
        racine.addLayout(self._entete())

        trait = QFrame(); trait.setObjectName("separateur")
        trait.setFrameShape(QFrame.HLine)
        racine.addWidget(trait)

        corps = QHBoxLayout()
        corps.setSpacing(14)
        corps.addWidget(self._colonne_reglages(), 0)
        droite = QVBoxLayout()
        droite.setSpacing(8)
        droite.addWidget(self.apercu, 1)
        droite.addWidget(self.info, 0)
        corps.addLayout(droite, 1)
        racine.addLayout(corps, 1)
        self.resize(1120, 720)

        self._habiller()
        self._interroger_media(silencieux=True)
        # Charger la condition RÉELLE au démarrage. Sans ça les champs
        # affichent des valeurs par défaut, et « Appliquer maintenant » les
        # écrirait dans la machine en croyant obéir : c'est arrivé le
        # 11/08/2026, un « Stylo feutre » monté est repassé à CB09U.
        self._lire_condition(silencieux=True)

    def _entete(self):
        """Titre et état de liaison.

        Un logiciel qu'on ouvre doit dire tout de suite à quoi il est relié.
        Ici la pastille répond à la question qui revenait sans cesse pendant
        la mise au point : « la machine écoute-t-elle ? »
        """
        h = QHBoxLayout()
        titre = QLabel("Pupitre de tracé")
        titre.setObjectName("titre")
        h.addWidget(titre)
        sous = QLabel("Graphtec CE6000-60")
        sous.setObjectName("faible")
        h.addWidget(sous)
        h.addStretch(1)
        self.lbl_liaison = QLabel("liaison inconnue")
        self.lbl_liaison.setObjectName("pastille")
        h.addWidget(self.lbl_liaison)
        return h

    def _etat_liaison(self, reliee, detail=""):
        self.lbl_liaison.setText(detail or
                                 ("traceur relié" if reliee else "traceur muet"))
        self.lbl_liaison.setProperty("etat", "reliee" if reliee else "absente")
        self.lbl_liaison.style().unpolish(self.lbl_liaison)
        self.lbl_liaison.style().polish(self.lbl_liaison)

    def _habiller(self):
        self.setStyleSheet(feuille_de_style(self.pal))
        self.apercu.habiller(self.pal)
        # Les icônes sont dessinées, pas chargées : elles doivent donc être
        # refaites quand la palette change, sinon elles gardent les couleurs
        # de l'autre thème.
        if hasattr(self, "cmb_outil"):
            for i in range(self.cmb_outil.count()):
                self.cmb_outil.setItemIcon(
                    i, icones.icone(self.cmb_outil.itemText(i), self.pal))

    def _basculer_theme(self):
        self.pal = CLAIR if self.pal is SOMBRE else SOMBRE
        self.b_theme.setText("Thème clair" if self.pal is SOMBRE
                             else "Thème sombre")
        self._habiller()

    # ---------------------------------------------------------------- UI
    def _colonne_reglages(self):
        """Trois onglets, une barre d'action, rien qui déborde.

        La version d'avant empilait six cadres dans une seule colonne :
        1 500 px de haut, plus que n'importe quel écran, les derniers
        champs écrasés et le bouton « Envoyer » hors de vue. Répartir en
        onglets ramène la colonne à une hauteur tenable et rend à l'aperçu
        la place que six cadres lui volaient.
        """
        boite = QWidget()
        boite.setFixedWidth(360)
        v = QVBoxLayout(boite)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        b_ouvrir = QPushButton("Ouvrir un SVG…")
        b_ouvrir.clicked.connect(self._ouvrir)
        self.lbl_fichier = QLabel("aucun dessin")
        self.lbl_fichier.setObjectName("faible")
        self.lbl_fichier.setWordWrap(True)

        # --- média
        g = QGroupBox("Média")
        gl = QGridLayout(g)
        self.spn_mx = self._reel(50, 700, 380.9)
        self.spn_my = self._reel(50, 700, 285.6)
        b_sonde = QPushButton("Interroger la machine")
        b_sonde.clicked.connect(lambda: self._interroger_media(False))
        gl.addWidget(QLabel("largeur"), 0, 0); gl.addWidget(self.spn_mx, 0, 1)
        gl.addWidget(QLabel("hauteur"), 1, 0); gl.addWidget(self.spn_my, 1, 1)
        gl.addWidget(b_sonde, 2, 0, 1, 2)
        g_media = g

        # --- placement
        g = QGroupBox("Placement")
        gl = QGridLayout(g)
        self.spn_x = self._reel(0, 700, 5.0)
        self.spn_y = self._reel(0, 700, 5.0)
        self.cmb_rot = QComboBox(); self.cmb_rot.addItems(["0°", "90°", "180°", "270°"])
        self.cmb_rot.currentIndexChanged.connect(self._recalculer)
        self.chk_mx = QCheckBox("miroir X"); self.chk_my = QCheckBox("miroir Y")
        for c in (self.chk_mx, self.chk_my):
            c.stateChanged.connect(self._recalculer)
        self.spn_ech = self._reel(1, 400, 100.0, suffixe=" %")
        b_ajuster = QPushButton("Ajuster au média")
        b_ajuster.clicked.connect(self._ajuster)
        gl.addWidget(QLabel("origine X"), 0, 0); gl.addWidget(self.spn_x, 0, 1)
        gl.addWidget(QLabel("origine Y"), 1, 0); gl.addWidget(self.spn_y, 1, 1)
        gl.addWidget(QLabel("rotation"), 2, 0); gl.addWidget(self.cmb_rot, 2, 1)
        gl.addWidget(self.chk_mx, 3, 0); gl.addWidget(self.chk_my, 3, 1)
        gl.addWidget(QLabel("échelle"), 4, 0); gl.addWidget(self.spn_ech, 4, 1)
        gl.addWidget(b_ajuster, 5, 0, 1, 2)
        g_placement = g

        # --- copies
        g = QGroupBox("Copies matricielles")
        gl = QGridLayout(g)
        self.spn_rang = self._entier(1, 50, 1)
        self.spn_col = self._entier(1, 50, 1)
        self.spn_ex = self._reel(0, 200, 10.0)
        self.spn_ey = self._reel(0, 200, 10.0)
        gl.addWidget(QLabel("rangées"), 0, 0); gl.addWidget(self.spn_rang, 0, 1)
        gl.addWidget(QLabel("colonnes"), 1, 0); gl.addWidget(self.spn_col, 1, 1)
        gl.addWidget(QLabel("écart H"), 2, 0); gl.addWidget(self.spn_ex, 2, 1)
        gl.addWidget(QLabel("écart V"), 3, 0); gl.addWidget(self.spn_ey, 3, 1)
        g_copies = g

        # --- outil
        g = QGroupBox("Outil")
        gl = QGridLayout(g)
        self.cmb_cond = QComboBox()
        self.cmb_cond.addItems([f"condition {i}" for i in range(1, 9)])
        # Changer de numéro relit la condition : sans ça, les champs
        # montreraient encore ceux de la précédente et « Appliquer
        # maintenant » les recopierait dans la nouvelle.
        self.cmb_cond.currentIndexChanged.connect(
            lambda: self._lire_condition(silencieux=True))
        # L'outil DÉCLARÉ doit correspondre à celui qui est monté : sinon la
        # machine compense un déport que l'outil n'a pas, ou l'inverse.
        self.cmb_outil = QComboBox()
        self.cmb_outil.setIconSize(QSize(22, 22))
        for nom in machine.OUTILS:
            self.cmb_outil.addItem(icones.icone(nom, self.pal), nom)
            self.cmb_outil.setItemData(self.cmb_outil.count() - 1,
                                       icones.legende(nom), Qt.ToolTipRole)
        # Retouche d'offset, second champ de TC1002,2. Ce n'est PAS le
        # déport : celui-là (19 pour la CB09U, 29 pour la CB15U) est appliqué
        # par le firmware d'après le type de lame. On ne fait que l'ajuster,
        # et 0 est la bonne réponse tant qu'une pointe ne bave pas.
        self.spn_offset = self._entier(machine.DEPORT_MINI,
                                       machine.DEPORT_MAXI, 0)
        self.cmb_outil.currentTextChanged.connect(self._offset_utile)
        self.spn_force = self._entier(1, 38, 12)
        # Repasser sur le tracé : 2 pour les plumes d'après le carnet, et
        # c'était la réponse au trait pâle du premier essai. Gratuit en
        # déplacement, le repassage se faisant à l'envers depuis la fin.
        self.spn_passages = self._entier(1, 5, 1)
        # La vitesse passe par le protocole propriétaire TC : le `VS` du
        # HP-GL est ignoré par cette machine. Elle MODIFIE DURABLEMENT la
        # condition enregistrée, comme le fait le logiciel Graphtec.
        self.spn_vit = self._entier(1, 64, 10, suffixe=" cm/s")
        # L'accélération n'a que TROIS crans sur cette machine : demander 4
        # est écrêté à 3 sans un mot. La borne est dans conditions.BORNES.
        self.spn_accel = self._entier(1, 3, 2)
        self.chk_regler = QCheckBox("appliquer aussi au moment du tracé")
        self.chk_regler.setChecked(True)
        self.chk_regler.setToolTip(
            "Coché, les réglages ci-dessus sont posés juste avant chaque\n"
            "envoi. Décoché, le traceur garde ce qu'il a — ce qui est sans\n"
            "danger, les conditions étant PERSISTANTES dans la machine.\n"
            "Pour agir maintenant, utiliser « Appliquer maintenant ».")

        b_lire_c = QPushButton("Lire la condition")
        b_lire_c.clicked.connect(self._lire_condition)
        b_appl_c = QPushButton("Appliquer maintenant")
        b_appl_c.clicked.connect(self._appliquer_condition)
        self.lbl_condition = QLabel("condition non lue")
        self.lbl_condition.setObjectName("faible")
        self.lbl_condition.setWordWrap(True)
        gl.addWidget(QLabel("condition"), 0, 0); gl.addWidget(self.cmb_cond, 0, 1)
        gl.addWidget(QLabel("outil"), 1, 0); gl.addWidget(self.cmb_outil, 1, 1)
        self.lbl_offset = QLabel("offset")
        gl.addWidget(self.lbl_offset, 2, 0); gl.addWidget(self.spn_offset, 2, 1)
        gl.addWidget(QLabel("vitesse"), 3, 0); gl.addWidget(self.spn_vit, 3, 1)
        gl.addWidget(QLabel("force"), 4, 0); gl.addWidget(self.spn_force, 4, 1)
        gl.addWidget(QLabel("accélération"), 5, 0); gl.addWidget(self.spn_accel, 5, 1)
        gl.addWidget(QLabel("passages"), 6, 0); gl.addWidget(self.spn_passages, 6, 1)
        self.spn_passages.setToolTip(
            "repasser sur chaque tracé rend le trait franc au stylo.\n"
            "Le carnet d'établi note 2 pour le feutre comme pour le Bic.\n"
            "Ne coûte aucun déplacement : le retour se fait à l'envers.")
        gl.addWidget(b_lire_c, 7, 0); gl.addWidget(b_appl_c, 7, 1)
        gl.addWidget(self.lbl_condition, 8, 0, 1, 2)
        gl.addWidget(self.chk_regler, 9, 0, 1, 2)
        rappel = QLabel("accélération basse = trait net,\nhaute = travail plus court")
        rappel.setObjectName("faible")
        gl.addWidget(rappel, 10, 0, 1, 2)
        self._offset_utile(self.cmb_outil.currentText())
        g_outil = g

        def onglet(*cadres):
            w = QWidget()
            lay = QVBoxLayout(w)
            lay.setContentsMargins(10, 12, 10, 10)
            lay.setSpacing(10)
            for c in cadres:
                lay.addWidget(c)
            lay.addStretch(1)
            return w

        self.onglets = QTabWidget()
        self.onglets.addTab(onglet(b_ouvrir, self.lbl_fichier, g_media,
                                   g_placement), "Dessin")
        self.onglets.addTab(onglet(g_outil, g_copies), "Outil")
        self.onglets.addTab(onglet(self._groupe_machine()), "Machine")
        v.addWidget(self.onglets, 1)

        # Barre d'action, hors des onglets : ce qu'on vient faire ici doit
        # rester sous la main quel que soit l'onglet ouvert.
        self.b_envoyer = QPushButton("Envoyer au traceur")
        self.b_envoyer.setObjectName("principal")
        self.b_envoyer.setEnabled(False)
        self.b_envoyer.clicked.connect(self._envoyer)
        self.b_envoyer.setMinimumHeight(34)
        v.addWidget(self.b_envoyer)

        self.b_theme = QPushButton("Thème clair")
        self.b_theme.clicked.connect(self._basculer_theme)
        v.addWidget(self.b_theme)
        return boite

    # (paramètre, libellé, plage ou choix, échelle, suffixe, infobulle)
    # L'échelle n'est pas cosmétique : l'angle d'offset se stocke × 100 et
    # la vitesse relevée × 10. Écrire la valeur affichée réglerait la
    # machine au centième de ce qu'on croit, sans un mot.
    CHAMPS_MACHINE = None            # bâti dans _groupe_machine

    def _groupe_machine(self):
        """Les réglages MACHINE — ceux du menu, pas ceux des conditions.

        Ils ne dépendent d'aucune condition : `TC1004,<p>,<v>` pour écrire,
        `TC2004,<p>` pour lire. Le groupe reste vide tant qu'on n'a pas
        appuyé sur « Lire la machine » : afficher des valeurs par défaut
        laisserait croire qu'on montre l'état réel du traceur.
        """
        import conditions as M
        self.CHAMPS_MACHINE = [
            (M.PAS, "passe-pas", (0, 20), 1, "",
             "lissage des courbes. Le manuel recommande 1 : une valeur\n"
             "élevée déforme les découpes."),
            (M.FORCE_DEPORT, "force d'offset", (0, 60), 1, "",
             "le manuel annonce 0 à 20 ; la machine de l'atelier était\n"
             "à 30. C'est la machine qui a raison."),
            (M.ANGLE_DEPORT, "angle d'offset", (0, 60), 100, " °",
             "stocké × 100 dans la machine."),
            (M.VITESSE_RELEVE, "vitesse outil relevé", (5, 60), 10, " cm/s",
             "vitesse des trajets à vide : c'est elle, plus que la vitesse\n"
             "de tracé, qui fixe la durée d'un travail. Stockée × 10."),
        ]
        self.CHOIX_MACHINE = [
            (M.PRIORITE_CONDITION, "priorité",
             {1: "programme", 0: "panneau"},
             "Sur « panneau », le VS des fichiers est SILENCIEUSEMENT\n"
             "ignoré — un réglage qui ne fait rien sans le dire."),
            (M.LAME_INITIALE, "lame initiale",
             {0: "2 mm en-deçà", 1: "dehors"}, ""),
            (M.DEPLACEMENT_RELEVE, "déplacement relevé",
             {1: "désactivé", 0: "activé"},
             "1 vaut « désactivé » : vérifié sur la machine, pas déduit."),
        ]

        g = QGroupBox()
        gl = QGridLayout(g)
        self.widgets_machine = {}
        ligne = 0
        for p, libelle, (mini, maxi), _ech, suffixe, bulle in self.CHAMPS_MACHINE:
            w = QSpinBox(); w.setRange(mini, maxi); w.setSuffix(suffixe)
            if bulle:
                w.setToolTip(bulle)
            gl.addWidget(QLabel(libelle), ligne, 0); gl.addWidget(w, ligne, 1)
            self.widgets_machine[p] = w
            ligne += 1
        for p, libelle, choix, bulle in self.CHOIX_MACHINE:
            w = QComboBox()
            for val, texte in choix.items():
                w.addItem(texte, val)
            if bulle:
                w.setToolTip(bulle)
            gl.addWidget(QLabel(libelle), ligne, 0); gl.addWidget(w, ligne, 1)
            self.widgets_machine[p] = w
            ligne += 1

        b_lire = QPushButton("Lire la machine")
        b_lire.clicked.connect(self._lire_machine)
        b_ecrire = QPushButton("Appliquer à la machine")
        b_ecrire.clicked.connect(self._ecrire_machine)
        b_ecrire.setEnabled(False)
        self.b_machine_ecrire = b_ecrire
        gl.addWidget(b_lire, ligne, 0, 1, 2)
        gl.addWidget(b_ecrire, ligne + 1, 0, 1, 2)

        # Verrouillés tant qu'on n'a pas lu. Sans ça, les champs affichent
        # 0 et « Appliquer » écrirait ces zéros dans la machine — la même
        # faute que l'écrêtage silencieux corrigé le 11/08/2026 : une valeur
        # qui n'a pas été lue n'est pas une valeur.
        for w in self.widgets_machine.values():
            w.setEnabled(False)

        self.lbl_machine = QLabel("appuyer sur « Lire la machine » pour "
                                  "afficher l'état réel du traceur")
        self.lbl_machine.setObjectName("faible")
        self.lbl_machine.setWordWrap(True)
        gl.addWidget(self.lbl_machine, ligne + 2, 0, 1, 2)
        g.setEnabled(True)
        return g

    def _lire_condition(self, silencieux=False):
        """Charge la condition choisie depuis la machine.

        Même geste que l'onglet Machine : lire d'abord, agir ensuite. La
        case « appliquer au tracé » ne montrait rien quand on la décochait
        — normal, elle ne parle que du futur — et Christophe a cherché,
        avec raison, ce qui agissait MAINTENANT. Deux logiques dans la même
        fenêtre, c'était le défaut.
        """
        import conditions as M
        if not os.path.exists(M.PERIPH):
            if not silencieux:
                QMessageBox.information(self, "Traceur absent",
                                        f"{M.PERIPH} n'existe pas.")
            return
        try:
            etat = M.lire_condition(self.cmb_cond.currentIndex() + 1)
        except OSError as e:
            if not silencieux:
                QMessageBox.warning(self, "Traceur", str(e))
            return
        if not etat or etat.get("vitesse") is None:
            self.lbl_condition.setText("pas de réponse — panneau sur READY ?")
            return
        code_outil = etat.get("outil")
        for nom, code in M.OUTILS.items():
            if code == code_outil:
                self.cmb_outil.setCurrentText(nom)
                break
        if etat.get("offset") is not None:
            self.spn_offset.setValue(etat["offset"])
        self.spn_vit.setValue(max(1, int(round(etat["vitesse"] / 10))))
        if etat.get("force") is not None:
            self.spn_force.setValue(etat["force"])
        if etat.get("acceleration") is not None:
            self.spn_accel.setValue(etat["acceleration"])
        self.lbl_condition.setText(
            f"condition {self.cmb_cond.currentIndex() + 1} lue sur la machine")

    def _appliquer_condition(self):
        """Pose la condition MAINTENANT, et relit chaque valeur."""
        import conditions as M
        cond = self.cmb_cond.currentIndex() + 1
        try:
            fd = os.open(M.PERIPH, os.O_RDWR | os.O_NONBLOCK)
        except OSError as e:
            QMessageBox.warning(self, "Traceur", str(e))
            return
        try:
            M.regler_outil(fd, M.OUTILS[self.cmb_outil.currentText()],
                           condition=cond, offset=self.spn_offset.value())
            rendu = M.appliquer(vitesse=self.spn_vit.value(),
                                force=self.spn_force.value(),
                                acceleration=self.spn_accel.value(),
                                condition=cond, fd=fd)
        finally:
            os.close(fd)
        rates = [n for n, _d, _o, ok in rendu if not ok]
        self.lbl_condition.setText(
            f"condition {cond} appliquée et relue"
            + (f" — NON RETENU : {', '.join(rates)}" if rates
               else ", tout conforme."))

    def _lire_machine(self):
        """Charge les valeurs réelles, une seule ouverture du périphérique.

        Rouvrir /dev/usb/lp0 entre deux lectures rend la machine muette
        pour des dizaines de secondes — mesuré le 11/08/2026.
        """
        import conditions as M
        if not os.path.exists(M.PERIPH):
            QMessageBox.information(self, "Traceur absent",
                                    f"{M.PERIPH} n'existe pas.")
            return
        try:
            fd = os.open(M.PERIPH, os.O_RDWR | os.O_NONBLOCK)
        except OSError as e:
            QMessageBox.warning(self, "Périphérique occupé", str(e))
            return
        lus, muets = {}, []
        try:
            M.lire_machine(fd, M.PAS)          # coup pour rien
            for p in self.widgets_machine:
                v = M.lire_machine(fd, p)
                if v:
                    lus[p] = v[0]
                else:
                    muets.append(p)
        finally:
            os.close(fd)

        if not lus:
            self.lbl_machine.setText(
                "aucune réponse — panneau sur READY ?")
            return
        echelles = {p: e for p, _l, _pl, e, _s, _b in self.CHAMPS_MACHINE}
        elargis = []
        for p, val in lus.items():
            w = self.widgets_machine[p]
            if isinstance(w, QComboBox):
                i = w.findData(val)
                if i >= 0:
                    w.setCurrentIndex(i)
            else:
                affiche = int(round(val / echelles.get(p, 1)))
                # NE JAMAIS rabattre une valeur lue. Un QSpinBox écrête en
                # silence, et « Appliquer » réécrirait alors la valeur
                # rabattue en croyant obéir à l'utilisateur : c'est arrivé
                # le 11/08/2026, la force d'offset est passée de 30 à 20
                # parce que la plage codée ici était trop étroite. Une
                # valeur hors plage veut dire que la plage est fausse.
                if affiche < w.minimum():
                    w.setMinimum(affiche)
                    elargis.append(p)
                if affiche > w.maximum():
                    w.setMaximum(affiche)
                    elargis.append(p)
                w.setValue(affiche)
        self.machine_lue = dict(lus)
        for p, w in self.widgets_machine.items():
            w.setEnabled(p in lus)
        self.b_machine_ecrire.setEnabled(True)
        texte = f"{len(lus)} réglage(s) lus sur la machine"
        if muets:
            texte += f" — {len(muets)} muet(s)"
        if elargis:
            noms = ", ".join(M.REGLAGES_MACHINE[p][0] for p in set(elargis))
            texte += (f" — plage élargie pour {noms} : la machine "
                      f"annonçait mieux que prévu")
        self.lbl_machine.setText(texte)

    def _ecrire_machine(self):
        """N'écrit que ce qui a CHANGÉ, et relit chaque valeur écrite.

        Écrire tout à chaque fois userait la mémoire de la machine pour
        rien, et masquerait ce qu'on modifie vraiment.
        """
        import conditions as M
        echelles = {p: e for p, _l, _pl, e, _s, _b in self.CHAMPS_MACHINE}
        voulu = {}
        for p, w in self.widgets_machine.items():
            voulu[p] = (w.currentData() if isinstance(w, QComboBox)
                        else w.value() * echelles.get(p, 1))
        change = {p: v for p, v in voulu.items()
                  if getattr(self, "machine_lue", {}).get(p) != v}
        if not change:
            self.lbl_machine.setText("rien à écrire : tout est déjà à cette "
                                     "valeur.")
            return
        try:
            fd = os.open(M.PERIPH, os.O_RDWR | os.O_NONBLOCK)
        except OSError as e:
            QMessageBox.warning(self, "Périphérique occupé", str(e))
            return
        rendu = []
        try:
            for p, v in change.items():
                M.regler_machine(fd, p, v)
                relu = M.lire_machine(fd, p)
                obtenu = relu[0] if relu else None
                rendu.append((M.REGLAGES_MACHINE[p][0], v, obtenu, obtenu == v))
                if obtenu is not None:
                    self.machine_lue[p] = obtenu
        finally:
            os.close(fd)
        rates = [n for n, _d, _o, ok in rendu if not ok]
        self.lbl_machine.setText(
            f"{len(rendu)} écrit(s) et relu(s)"
            + (f" — NON RETENU : {', '.join(rates)}" if rates else
               ", tous conformes."))
        if rates:
            QMessageBox.warning(
                self, "Réglage non retenu",
                "La machine n'a pas retenu : " + ", ".join(rates)
                + "\n\nElle écrête sans le dire quand une valeur sort de "
                  "sa plage.")

    def _reel(self, mini, maxi, val, suffixe=" mm"):
        s = QDoubleSpinBox()
        s.setRange(mini, maxi); s.setDecimals(1); s.setValue(val)
        s.setSuffix(suffixe)
        s.valueChanged.connect(self._recalculer)
        return s

    def _offset_utile(self, outil):
        """Grise l'offset pour un stylo, que la machine ne compense pas.

        Le manuel est explicite : « Il n'est pas nécessaire de régler ce
        paramètre pour les outils Plume. » Un champ actif qui ne fait rien
        vaut moins qu'un champ éteint qui dit pourquoi.
        """
        plume = outil == "Stylo feutre"
        self.spn_offset.setEnabled(not plume)
        self.lbl_offset.setEnabled(not plume)
        self.spn_offset.setToolTip(
            "sans objet pour un stylo : la machine ne compense aucun déport."
            if plume else
            "retouche de −5 à +5 autour du déport que le firmware applique\n"
            "d'après la lame (19 pour une CB09U, 29 pour une CB15U).\n"
            "Laisser à 0 tant qu'une pointe ne bave pas.")

    def _entier(self, mini, maxi, val, suffixe=""):
        s = QSpinBox()
        s.setRange(mini, maxi); s.setValue(val); s.setSuffix(suffixe)
        s.valueChanged.connect(self._recalculer)
        return s

    # ------------------------------------------------------------ actions
    def _ouvrir(self):
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Choisir un SVG", os.path.expanduser("~"), "SVG (*.svg)")
        if not chemin:
            return
        try:
            self.brut, avertissements = noyau.charger(chemin)
        except Exception as e:
            QMessageBox.warning(self, "Lecture impossible", str(e))
            return
        if not self.brut:
            QMessageBox.warning(self, "Rien à tracer",
                                "Aucune géométrie exploitable dans ce SVG.\n\n"
                                + "\n".join(avertissements))
            return
        self.chemin = chemin
        self.lbl_fichier.setText(os.path.basename(chemin) +
                                 ("\n⚠ " + "\n⚠ ".join(avertissements)
                                  if avertissements else ""))
        self.b_envoyer.setEnabled(True)
        self._recalculer()

    def _interroger_media(self, silencieux):
        limites = noyau.limites_machine()
        if limites:
            self.spn_mx.setValue(limites[0])
            self.spn_my.setValue(limites[1])
            self._etat_liaison(True, f"média {limites[0]:.0f} × "
                                     f"{limites[1]:.0f} mm")
        else:
            self._etat_liaison(False)
        if not limites and not silencieux:
            QMessageBox.information(
                self, "Machine muette",
                "Pas de réponse à OH;.\n\nLe traceur est-il allumé, un média "
                "chargé, et le panneau sur READY ? Hors de cet état il "
                "n'écoute pas son tampon.")

    def _ajuster(self):
        if not self.brut:
            return
        self.spn_ech.setValue(100.0)
        self._recalculer()
        x0, y0, x1, y1 = noyau.cadre(self.calcule)
        dispo_x = self.spn_mx.value() - 2 * self.spn_x.value()
        dispo_y = self.spn_my.value() - 2 * self.spn_y.value()
        f = min(1.0,
                dispo_x / max(x1 - x0, 1e-6),
                dispo_y / max(y1 - y0, 1e-6)) * 0.995
        self.spn_ech.setValue(f * 100.0)

    def _pipeline(self):
        p = noyau.tourner(self.brut, int(self.cmb_rot.currentText().rstrip("°")))
        p = noyau.refleter(p, self.chk_mx.isChecked(), self.chk_my.isChecked())
        p = noyau.mettre_a_echelle(p, self.spn_ech.value() / 100.0)
        p = noyau.dupliquer(p, self.spn_rang.value(), self.spn_col.value(),
                            self.spn_ex.value(), self.spn_ey.value())
        return noyau.recadrer(p, self.spn_x.value(), self.spn_y.value())

    def _recalculer(self):
        self.media = (self.spn_mx.value(), self.spn_my.value())
        if not self.brut:
            self.apercu.poser([], self.media, False)
            return
        self.calcule = self._pipeline()
        x0, y0, x1, y1 = noyau.cadre(self.calcule)
        deborde = x1 > self.media[0] or y1 > self.media[1]
        self.apercu.poser(self.calcule, self.media, deborde)

        n = len(self.calcule)
        texte = (f"{n} tracé(s) — emprise {x1 - x0:.1f} × {y1 - y0:.1f} mm, "
                 f"coin à {x0:.1f}, {y0:.1f}")
        if deborde:
            texte += "  —  LE DESSIN DÉBORDE DE LA ZONE UTILE"
        self.info.setText(texte)
        # Un message d'alerte doit aussi en avoir la couleur : un texte
        # rouge sous un style neutre ne se lit pas comme un refus.
        self.info.setObjectName("alerte" if deborde else "faible")
        self.info.setStyleSheet(feuille_de_style(self.pal))
        self.b_envoyer.setEnabled(bool(self.brut) and not deborde)

    def _envoyer(self):
        # Le réordonnancement ne tourne qu'ici : il est en n², donc trop
        # lourd à rejouer à chaque mouvement d'un réglage, et il ne change
        # rien à ce que l'aperçu montre.
        avant = noyau.trajet_a_vide(self.calcule)
        candidat = noyau.ordonner(self.calcule)
        apres = noyau.trajet_a_vide(candidat)
        chemins = candidat if apres < avant else self.calcule

        condition = self.cmb_cond.currentIndex() + 1
        programme, _ = noyau.en_hpgl(chemins, condition,
                                     self.spn_force.value(),
                                     self.spn_passages.value())

        # UN SEUL descripteur pour régler PUIS envoyer. Le pupitre en
        # ouvrait trois d'affilée — outil, conditions, envoi — et fermer
        # /dev/usb/lp0 entre deux étapes rend la machine muette pour des
        # dizaines de secondes. Le correctif avait été porté à
        # envoyer_hpgl.py le 11/08/2026 et OUBLIÉ ici, où il manquait le
        # plus : c'est le pupitre qu'on utilise.
        import conditions
        regle = ""
        fd = None
        try:
            fd = os.open(conditions.PERIPH, os.O_RDWR | os.O_NONBLOCK)
            if self.chk_regler.isChecked():
                # L'offset part avec l'outil : la commande écrit les deux
                # champs d'un coup, les séparer effacerait l'un des deux.
                conditions.regler_outil(
                    fd, conditions.OUTILS[self.cmb_outil.currentText()],
                    condition=condition,
                    offset=self.spn_offset.value())
                rendu = conditions.appliquer(vitesse=self.spn_vit.value(),
                                             acceleration=self.spn_accel.value(),
                                             condition=condition, fd=fd)
                douteux = [n for n, _, _, ok in rendu if not ok]
                if douteux:
                    QMessageBox.warning(
                        self, "Réglage non retenu",
                        "La machine n'a pas retenu : " + ", ".join(douteux)
                        + "\n\nEnvoi annulé : tracer avec des réglages "
                          "qu'on croit posés et qui ne le sont pas gâche "
                          "le média.")
                    return
                regle = (f"condition {condition} réglée à "
                         f"{self.spn_vit.value()} cm/s, accél. "
                         f"{self.spn_accel.value()} — ")
            envoye = noyau.envoyer(programme, fd=fd)
        except Exception as e:
            QMessageBox.critical(self, "Envoi impossible", str(e))
            return
        finally:
            if fd is not None:
                os.close(fd)
        gain = (1 - min(apres, avant) / avant) * 100 if avant else 0
        self.info.setText(f"{regle}{envoye} octets envoyés — trajet à vide "
                          f"{min(apres, avant):.0f} mm ({gain:.0f} % gagné)")


def main():
    app = QApplication(sys.argv)
    p = Pupitre()
    p.resize(1000, 620)
    p.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
