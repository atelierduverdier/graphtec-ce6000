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

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg2hpgl as noyau
import mosaique                                    # noqa: E402
import materiaux                                   # noqa: E402
from theme import SOMBRE, CLAIR, feuille_de_style           # noqa: E402
import conditions as machine                                # noqa: E402
import icones                                               # noqa: E402

from PySide6.QtCore import Qt, QPointF, QRectF, QSize        # noqa: E402
from PySide6.QtGui import (QPainter, QPen, QColor, QPolygonF,  # noqa: E402
                           QIcon, QPixmap)
from PySide6.QtSvg import QSvgRenderer                        # noqa: E402
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
        self.tuiles = []
        self.zoom = 1.0
        self.decalage = QPointF(0, 0)
        self._saisie = None
        self.setCursor(Qt.OpenHandCursor)

    def habiller(self, palette):
        self.pal = palette
        self.update()

    def reinitialiser_vue(self):
        """Recadre sur l'ensemble. Appelé à l'ouverture d'un dessin, pas à
        chaque réglage : garder le zoom en ajustant l'échelle ou l'origine
        est tout l'intérêt de pouvoir zoomer."""
        self.zoom = 1.0
        self.decalage = QPointF(0, 0)
        self.update()

    def _cadrage(self):
        """(k, ox, oy) : échelle et origine de l'aperçu, zoom compris."""
        mx, my = self.media
        vx, vy = mx, my
        if self.emprise:
            vx = max(vx, self.emprise[2])
            vy = max(vy, self.emprise[3])
        marge = 14
        k = min((self.width() - 2 * marge) / max(vx, 1e-6),
                (self.height() - 2 * marge) / max(vy, 1e-6)) * self.zoom
        ox = (self.width() - vx * k) / 2 + self.decalage.x()
        oy = (self.height() + vy * k) / 2 + self.decalage.y()
        return k, ox, oy

    def wheelEvent(self, e):
        """Zoom autour du curseur : le point visé ne bouge pas.

        Zoomer autour du CENTRE obligerait à recentrer après chaque cran,
        ce qui rend l'examen d'un raccord pénible — et c'est précisément
        pour examiner les raccords qu'on zoome.
        """
        k, ox, oy = self._cadrage()
        px, py = (e.position().x() - ox) / k, (oy - e.position().y()) / k
        crans = e.angleDelta().y() / 120.0
        self.zoom = max(0.25, min(60.0, self.zoom * (1.18 ** crans)))
        k2, ox2, oy2 = self._cadrage()
        self.decalage += QPointF(e.position().x() - (ox2 + px * k2),
                                 e.position().y() - (oy2 - py * k2))
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._saisie = e.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._saisie is not None:
            self.decalage += e.position() - self._saisie
            self._saisie = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        self._saisie = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, _e):
        self.reinitialiser_vue()

    def poser(self, polylignes, media, deborde, tuiles=()):
        self.media = media
        self.deborde = deborde
        self.tuiles = list(tuiles)
        self.polygones = [QPolygonF([QPointF(x, y) for x, y in pts])
                          for pts, _ in polylignes]
        self.emprise = noyau.cadre(polylignes) if polylignes else None
        self.update()

    def paintEvent(self, _):
        pal = self.pal
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(pal.ardoise))

        # Cadrage sur l'UNION du média et du dessin : en mosaïque le dessin
        # déborde par construction, et un cadrage sur le seul média le
        # ferait sortir de l'aperçu — là même où l'on a le plus besoin de
        # le voir en entier.
        mx, my = self.media
        k, ox, oy = self._cadrage()

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

        # les tuiles de la mosaïque, par-dessus tout le reste
        if self.tuiles:
            p.setBrush(Qt.NoBrush)
            for n, (x0, y0, x1, y1) in enumerate(self.tuiles, 1):
                p.setPen(QPen(QColor(pal.accent), 1.4))
                p.drawRect(QRectF(pt(x0, y1), pt(x1, y0)))
                p.setPen(QColor(pal.accent))
                p.drawText(QRectF(pt(x0, y1), pt(x1, y0)).adjusted(5, 3, 0, 0),
                           Qt.AlignLeft | Qt.AlignTop, str(n))

        p.setPen(QColor(pal.texte_faible))
        p.drawText(8, self.height() - 8,
                   f"média {mx:.1f} × {my:.1f} mm"
                   + (f"   —   zoom ×{self.zoom:.1f}, molette pour zoomer, "
                      f"glisser pour déplacer, double-clic pour recadrer"
                      if abs(self.zoom - 1.0) > 0.01 else
                      "   —   molette pour zoomer"))


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
        h.setSpacing(10)

        self.lbl_chapeau = QLabel()
        self.lbl_chapeau.setToolTip("Atelier du Verdier")
        h.addWidget(self.lbl_chapeau)

        colonne = QVBoxLayout()
        colonne.setSpacing(0)
        titre = QLabel("Pupitre de tracé")
        titre.setObjectName("titre")
        colonne.addWidget(titre)
        sous = QLabel("Atelier du Verdier — Graphtec CE6000-60")
        sous.setObjectName("faible")
        colonne.addWidget(sous)
        h.addLayout(colonne)

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

    def _chapeau(self, hauteur=34):
        """Le chapeau de l'atelier, rendu tel qu'il est.

        **On ne le repeint pas.** Une première version teintait son corps
        selon le thème pour qu'il se détache du fond sombre — Christophe,
        le 11/08/2026 : « il est pas beau en blanc, c'est pas mon logo, il
        est noir normalement ». Adapter un logo n'est pas le colorier. Il
        porte désormais un liseré blanc, dans le fichier, qui le détache
        sans toucher à sa couleur.
        """
        chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "resources", "icons", "chapeau.svg")
        if not os.path.exists(chemin):
            return QPixmap()
        rendu = QSvgRenderer(chemin)
        if not rendu.isValid():
            return QPixmap()
        taille = rendu.defaultSize()
        largeur = int(round(hauteur * taille.width() / taille.height()))
        pix = QPixmap(largeur, hauteur)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        rendu.render(p)
        p.end()
        return pix

    def _habiller(self):
        self.setStyleSheet(feuille_de_style(self.pal))
        self.apercu.habiller(self.pal)
        if hasattr(self, "lbl_chapeau"):
            self.lbl_chapeau.setPixmap(self._chapeau())
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

        # --- nuancier
        g = QGroupBox("Nuancier de force")
        gl = QGridLayout(g)
        self.spn_nu_min = self._entier(1, 38, 8)
        self.spn_nu_max = self._entier(1, 38, 26)
        self.spn_nu_pas = self._entier(1, 10, 2)
        b_nuancier = QPushButton("Tracer le nuancier")
        b_nuancier.setToolTip(
            "Une grille de carrés, un par force, À LEVER pour juger.\n"
            "Une coupe ne se voit pas, elle se sent : le bon réglage est la\n"
            "force la plus faible où le carré se détache proprement.\n"
            "N'utilise PAS les réglages ci-dessus : chaque carré porte la\n"
            "sienne.")
        b_nuancier.clicked.connect(self._tracer_nuancier)
        self.lbl_nuancier = QLabel("à lancer sur une chute du papier visé")
        self.lbl_nuancier.setObjectName("faible")
        self.lbl_nuancier.setWordWrap(True)
        gl.addWidget(QLabel("de la force"), 0, 0); gl.addWidget(self.spn_nu_min, 0, 1)
        gl.addWidget(QLabel("à la force"), 1, 0); gl.addWidget(self.spn_nu_max, 1, 1)
        gl.addWidget(QLabel("par pas de"), 2, 0); gl.addWidget(self.spn_nu_pas, 2, 1)
        gl.addWidget(b_nuancier, 3, 0, 1, 2)
        gl.addWidget(self.lbl_nuancier, 4, 0, 1, 2)
        g_nuancier = g

        # --- mosaïque
        g = QGroupBox("Mosaïque")
        gl = QGridLayout(g)
        self.chk_mosaique = QCheckBox("découper en panneaux")
        self.chk_mosaique.setToolTip(
            "Pour un dessin plus grand que le média. Chaque panneau est\n"
            "tracé sur une feuille, et les DEUX croix de la bande de\n"
            "recouvrement servent à les raccorder : une seule ne fixerait\n"
            "que la translation, pas l'angle.")
        self.chk_mosaique.stateChanged.connect(self._recalculer)
        self.spn_pan_x = self._reel(50, 700, 330.0)
        self.spn_pan_y = self._reel(50, 700, 250.0)
        self.spn_recouv = self._reel(0, 50, 5.0)
        b_pan_media = QPushButton("Panneau = média")
        b_pan_media.setToolTip("Reprend les cotes du média, moins 10 mm de "
                               "garde sur chaque bord.")
        b_pan_media.clicked.connect(self._panneau_selon_media)
        self.lbl_mosaique = QLabel("inactive")
        self.lbl_mosaique.setObjectName("faible")
        self.lbl_mosaique.setWordWrap(True)
        gl.addWidget(self.chk_mosaique, 0, 0, 1, 2)
        gl.addWidget(QLabel("panneau L"), 1, 0); gl.addWidget(self.spn_pan_x, 1, 1)
        gl.addWidget(QLabel("panneau H"), 2, 0); gl.addWidget(self.spn_pan_y, 2, 1)
        gl.addWidget(QLabel("recouvrement"), 3, 0); gl.addWidget(self.spn_recouv, 3, 1)
        gl.addWidget(b_pan_media, 4, 0, 1, 2)
        gl.addWidget(self.lbl_mosaique, 5, 0, 1, 2)
        g_mosaique = g

        # --- perforation
        g = QGroupBox("Perforation")
        gl = QGridLayout(g)
        self.chk_perfo = QCheckBox("découper en pointillé")
        self.chk_perfo.setToolTip(
            "Coupe par tirets, pour un gabarit qui tient dans la feuille et\n"
            "se détache à la main. Le carnet d'établi note 8 mm coupés et\n"
            "0,25 laissés sur la plupart des papiers, 0,15 sur les épais.")
        self.chk_perfo.stateChanged.connect(self._recalculer)
        self.spn_coupe = self._reel(0.5, 100, 8.0)
        self.spn_saut = self._reel(0.05, 20, 0.25)
        self.spn_saut.setDecimals(2)
        for w in (self.spn_coupe, self.spn_saut):
            w.valueChanged.connect(self._recalculer)
        self.lbl_perfo = QLabel("inactive")
        self.lbl_perfo.setObjectName("faible")
        self.lbl_perfo.setWordWrap(True)
        gl.addWidget(self.chk_perfo, 0, 0, 1, 2)
        gl.addWidget(QLabel("coupé"), 1, 0); gl.addWidget(self.spn_coupe, 1, 1)
        gl.addWidget(QLabel("laissé"), 2, 0); gl.addWidget(self.spn_saut, 2, 1)
        gl.addWidget(self.lbl_perfo, 3, 0, 1, 2)
        g_perfo = g

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
        # Le carnet d'établi en tête du groupe : choisir « papier 300 g »
        # pose D'UN COUP le type d'outil, la vitesse, la force,
        # l'accélération et les passages. Le type d'outil est le plus
        # important des cinq — c'est son oubli qui a arrondi les angles
        # d'une découpe le 11/08/2026, la machine compensant le déport
        # d'une lame qui n'était pas montée.
        self.cmb_profil = QComboBox()
        self.cmb_profil.addItem("(réglage libre)", None)
        for nom in materiaux.MATERIAUX:
            self.cmb_profil.addItem(nom, nom)
        self.cmb_profil.currentIndexChanged.connect(self._appliquer_profil)
        self.lbl_profil = QLabel("")
        self.lbl_profil.setObjectName("faible")
        self.lbl_profil.setWordWrap(True)

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
        gl.addWidget(QLabel("matériau"), 0, 0); gl.addWidget(self.cmb_profil, 0, 1)
        gl.addWidget(self.lbl_profil, 1, 0, 1, 2)
        gl.addWidget(QLabel("condition"), 2, 0); gl.addWidget(self.cmb_cond, 2, 1)
        gl.addWidget(QLabel("outil"), 3, 0); gl.addWidget(self.cmb_outil, 7, 1)
        self.lbl_offset = QLabel("offset")
        gl.addWidget(self.lbl_offset, 4, 0); gl.addWidget(self.spn_offset, 4, 1)
        gl.addWidget(QLabel("vitesse"), 5, 0); gl.addWidget(self.spn_vit, 5, 1)
        gl.addWidget(QLabel("force"), 6, 0); gl.addWidget(self.spn_force, 6, 1)
        gl.addWidget(QLabel("accélération"), 7, 0); gl.addWidget(self.spn_accel, 7, 1)
        gl.addWidget(QLabel("passages"), 8, 0); gl.addWidget(self.spn_passages, 8, 1)
        self.spn_passages.setToolTip(
            "repasser sur chaque tracé rend le trait franc au stylo.\n"
            "Le carnet d'établi note 2 pour le feutre comme pour le Bic.\n"
            "Ne coûte aucun déplacement : le retour se fait à l'envers.")
        gl.addWidget(b_lire_c, 9, 0); gl.addWidget(b_appl_c, 9, 1)
        gl.addWidget(self.lbl_condition, 10, 0, 1, 2)
        gl.addWidget(self.chk_regler, 11, 0, 1, 2)
        rappel = QLabel("accélération basse = trait net,\nhaute = travail plus court")
        rappel.setObjectName("faible")
        gl.addWidget(rappel, 12, 0, 1, 2)
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
                                   g_placement, g_mosaique,
                                   g_perfo), "Dessin")
        self.onglets.addTab(onglet(g_outil, g_nuancier, g_copies), "Outil")
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

    def _tracer_nuancier(self):
        """Trace la grille de carrés à lever, chacun à sa propre force.

        Il ne passe PAS par l'aperçu : chaque carré porte un `FS` qui lui
        est propre, ce que la chaîne de polylignes ne sait pas exprimer.
        C'est le seul travail du pupitre dans ce cas, et il est annoncé.
        """
        import nuancier_force
        mini, maxi = self.spn_nu_min.value(), self.spn_nu_max.value()
        if mini >= maxi:
            QMessageBox.information(self, "Nuancier",
                                    "La force de départ doit être inférieure "
                                    "à celle d'arrivée.")
            return
        condition = self.cmb_cond.currentIndex() + 1
        programme, legende = nuancier_force.carres(
            mini, maxi, self.spn_nu_pas.value(), condition)
        rep = QMessageBox.question(
            self, "Tracer le nuancier",
            f"{len(legende)} carrés, force {mini} à {maxi} par pas de "
            f"{self.spn_nu_pas.value()}.\n\n"
            f"Charger une CHUTE du papier visé, régler la sortie de lame à "
            f"la main,\net attendre READY.\n\n"
            f"Les réglages de l'onglet ne sont pas employés : chaque carré "
            f"porte sa propre force.",
            QMessageBox.Ok | QMessageBox.Cancel)
        if rep != QMessageBox.Ok:
            return
        try:
            envoye = noyau.envoyer(programme)
        except Exception as e:
            QMessageBox.critical(self, "Envoi impossible", str(e))
            return
        forces = ", ".join(str(f) for f, _x, _y in legende)
        self.lbl_nuancier.setText(
            f"{envoye} octets envoyés — forces tracées : {forces}. "
            f"Lever chaque carré : le bon réglage est le plus FAIBLE qui "
            f"détache proprement, et le carnet garde deux crans de marge.")

    def _appliquer_profil(self):
        """Verse un profil du carnet dans les champs — sans rien envoyer.

        Poser les valeurs SANS les écrire dans la machine est délibéré :
        on peut les relire, les corriger, et c'est « Appliquer maintenant »
        ou l'envoi qui décide. Un choix dans une liste ne doit pas modifier
        une machine à l'autre bout d'un câble.
        """
        nom = self.cmb_profil.currentData()
        if not nom:
            self.lbl_profil.setText("")
            return
        m = materiaux.MATERIAUX[nom]
        outil = m.get("outil") or m.get("lame")
        if outil:
            self.cmb_outil.setCurrentText(outil)
        self.spn_vit.setValue(m["vitesse"])
        self.spn_force.setValue(m["force"])
        if m.get("acceleration") is not None:
            self.spn_accel.setValue(m["acceleration"])
        self.spn_passages.setValue(m.get("passages", 1))

        rappels = []
        if not outil:
            # Sans outil déclaré, le champ garde celui du profil précédent :
            # un réglage hérité en silence, et c'est précisément ce genre
            # d'héritage qui a arrondi les angles d'une découpe.
            rappels.append(f"AUCUN outil dans le carnet pour ce profil — "
                           f"vérifier que « {self.cmb_outil.currentText()} » "
                           f"est bien ce qui est monté")
        if m.get("hauteur_lame"):
            rappels.append(f"À LA MAIN : sortie de lame {m['hauteur_lame']} mm")
        if m.get("usage") == "rainer":
            rappels.append("RAINAGE : la lame marque, elle ne traverse pas")
        if m.get("seuil_coupe"):
            rappels.append(f"traverse dès la force {m['seuil_coupe']}, "
                           f"marge gardée")
        if m.get("perforation"):
            c, sa = m["perforation"]
            self.spn_coupe.setValue(c)
            self.spn_saut.setValue(sa)
            rappels.append(f"perforation du carnet posée : {c:g} coupés, "
                           f"{sa:g} laissés")
        self.lbl_profil.setText("  •  ".join(rappels) if rappels
                                else "valeurs posées, rien n'est encore envoyé")

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
        # Ce qu'on vient de lire ne vient plus d'un profil : le dire, sinon
        # la liste afficherait un matériau que les champs ne portent plus.
        self.cmb_profil.blockSignals(True)
        self.cmb_profil.setCurrentIndex(0)
        self.cmb_profil.blockSignals(False)
        self.lbl_profil.setText("")

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
        # Un dessin neuf mérite un cadrage neuf ; un simple réglage, non.
        self.apercu.reinitialiser_vue()
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

    def _panneau_selon_media(self):
        """Panneau = média moins 10 mm de garde sur chaque bord."""
        self.spn_pan_x.setValue(max(50.0, self.spn_mx.value() - 10))
        self.spn_pan_y.setValue(max(50.0, self.spn_my.value() - 10))

    def _panneaux(self):
        """Découpe courante, ou [] si la mosaïque est inactive."""
        if not (self.chk_mosaique.isChecked() and self.calcule):
            return []
        return mosaique.mosaique(self.calcule,
                                 (self.spn_pan_x.value(), self.spn_pan_y.value()),
                                 self.spn_recouv.value())

    def _recalculer(self):
        self.media = (self.spn_mx.value(), self.spn_my.value())
        if not self.brut:
            self.apercu.poser([], self.media, False)
            return
        self.calcule = self._pipeline()
        x0, y0, x1, y1 = noyau.cadre(self.calcule)
        deborde = x1 > self.media[0] or y1 > self.media[1]

        panneaux = self._panneaux()
        if panneaux:
            trop = [n for n, (_i, _j, r, _m) in enumerate(panneaux, 1)
                    if r[2] - r[0] > self.media[0] or r[3] - r[1] > self.media[1]]
            self.lbl_mosaique.setText(
                f"{len(panneaux)} panneau(x) de "
                f"{self.spn_pan_x.value():.0f} × {self.spn_pan_y.value():.0f} mm"
                + (f" — le(s) n° {trop} ne tient pas dans le média"
                   if trop else ", chacun tient dans le média"))
            # En mosaïque, déborder est le point de départ, pas une faute :
            # ce qui compte est que chaque PANNEAU tienne.
            deborde = bool(trop)
        else:
            self.lbl_mosaique.setText(
                "inactive" if not self.chk_mosaique.isChecked()
                else "aucun dessin à découper")

        if self.chk_perfo.isChecked():
            c, sa = self.spn_coupe.value(), self.spn_saut.value()
            longueur = sum(math.dist(a, b) for pts, _ in self.calcule
                           for a, b in zip(pts, pts[1:]))
            tirets = int(longueur / (c + sa)) if c + sa else 0
            self.lbl_perfo.setText(
                f"{c:g} coupés, {sa:g} laissés — environ {tirets} tirets "
                f"sur {longueur / 1000:.1f} m de tracé. Appliqué à l'envoi, "
                f"l'aperçu montre le trait plein.")
        else:
            self.lbl_perfo.setText("inactive")

        self.apercu.poser(self.calcule, self.media, deborde,
                          [p[2] for p in panneaux])

        n = len(self.calcule)
        texte = (f"{n} tracé(s) — emprise {x1 - x0:.1f} × {y1 - y0:.1f} mm, "
                 f"coin à {x0:.1f}, {y0:.1f}")
        if panneaux:
            texte += f"  —  {len(panneaux)} panneaux"
        if deborde:
            texte += ("  —  UN PANNEAU DÉBORDE" if panneaux
                      else "  —  LE DESSIN DÉBORDE DE LA ZONE UTILE")
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
        condition = self.cmb_cond.currentIndex() + 1
        panneaux = self._panneaux()

        # Un travail est une LISTE d'envois : un seul d'ordinaire, autant que
        # de panneaux en mosaïque. Le reste du code ne fait pas la
        # différence, ce qui évite deux chemins parallèles à maintenir.
        if panneaux:
            lots = [(f"panneau {n}/{len(panneaux)}", m)
                    for n, (_i, _j, _r, m) in enumerate(panneaux, 1)]
        else:
            lots = [("", self.calcule)]

        programmes, gains = [], []
        for nom, morceaux in lots:
            av = noyau.trajet_a_vide(morceaux)
            cand = noyau.ordonner(morceaux)
            ap = noyau.trajet_a_vide(cand)
            retenu = cand if ap < av else morceaux
            if self.chk_perfo.isChecked():
                # APRÈS le réordonnancement : le pointillé multiplie par
                # vingt le nombre de chemins, et l'ordonnancement est en n².
                retenu = noyau.perforer(retenu, self.spn_coupe.value(),
                                        self.spn_saut.value())
            prog, _ = noyau.en_hpgl(retenu, condition,
                                    self.spn_force.value(),
                                    self.spn_passages.value())
            programmes.append((nom, prog))
            gains.append((min(ap, av), (1 - min(ap, av) / av) * 100 if av else 0))
        avant = sum(g[0] for g in gains)
        apres = avant
        programme = programmes[0][1]

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
            envoye = 0
            for rang, (nom, prog) in enumerate(programmes):
                if rang:
                    rep = QMessageBox.question(
                        self, "Feuille suivante",
                        f"{nom} : charger une feuille neuve, attendre "
                        f"READY,\npuis confirmer pour l'envoyer.\n\n"
                        f"Les croix de la bande de recouvrement servent à "
                        f"raccorder les panneaux.",
                        QMessageBox.Ok | QMessageBox.Cancel)
                    if rep != QMessageBox.Ok:
                        self.info.setText(
                            f"interrompu après {rang} panneau(x) sur "
                            f"{len(programmes)}")
                        return
                envoye += noyau.envoyer(prog, fd=fd)
        except Exception as e:
            QMessageBox.critical(self, "Envoi impossible", str(e))
            return
        finally:
            if fd is not None:
                os.close(fd)
        gain = sum(g[1] for g in gains) / len(gains) if gains else 0
        combien = (f"{len(programmes)} panneaux, " if len(programmes) > 1
                   else "")
        self.info.setText(f"{regle}{combien}{envoye} octets envoyés — "
                          f"trajet à vide {avant:.0f} mm ({gain:.0f} % gagné)")


ICONE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "resources", "icons", "traceur.svg")


def main():
    app = QApplication(sys.argv)
    # Le nom de bureau doit correspondre au .desktop, sinon l'environnement
    # ne rattache pas la fenêtre à son lanceur et affiche une icône vide.
    app.setDesktopFileName("graphtec-traceur")
    app.setApplicationName("Pupitre de tracé")
    if os.path.exists(ICONE):
        app.setWindowIcon(QIcon(ICONE))
    p = Pupitre()
    p.resize(1000, 620)
    p.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
