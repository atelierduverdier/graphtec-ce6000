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
import contour
import projet as fichier_projet
import impression
import roles as roles_couleur
import svg2hpgl as noyau
import mosaique                                    # noqa: E402
import materiaux                                   # noqa: E402
import etat_machine                                # noqa: E402
from theme import SOMBRE, CLAIR, feuille_de_style           # noqa: E402
import conditions as machine                                # noqa: E402
import icones                                               # noqa: E402

from PySide6.QtCore import (Qt, QPointF, QRectF, QSize, QTimer,
                            QEvent, QObject)        # noqa: E402
from PySide6.QtGui import (QPainter, QPen, QColor, QPolygonF,  # noqa: E402
                           QIcon, QPixmap)
from PySide6.QtSvg import QSvgRenderer                        # noqa: E402
from PySide6.QtWidgets import (                              # noqa: E402
    QApplication, QWidget, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QComboBox, QCheckBox, QGridLayout, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFileDialog, QMessageBox, QSizePolicy, QTabWidget, QFrame,
    QScrollArea)


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
        self.roles = []
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

    def poser(self, polylignes, media, deborde, tuiles=(), roles=None):
        """`roles` donne, en parallèle des polylignes, le rôle de chacune.

        Sans lui tout se peint de la même couleur, et une couleur mal
        rangée ne se voit qu'en changeant le sélecteur d'envoi pour la
        faire disparaître. Christophe : « et je les vois comment ces
        traits ? » — il ne les voyait pas.
        """
        self.media = media
        self.deborde = deborde
        self.tuiles = list(tuiles)
        self.roles = list(roles) if roles else []
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

        # le dessin, PAR RÔLE. Un contour de découpe et un motif à tracer
        # ne se font pas avec le même outil ; les peindre pareil oblige à
        # deviner lequel est lequel.
        if self.polygones:
            p.setBrush(Qt.NoBrush)
            defaut = QColor(pal.alerte if self.deborde else pal.trace)
            # Quatre rôles, quatre couleurs DISTINCTES. Le rainage et le
            # contour partageaient l'orange, ce qui rendait la légende
            # menteuse — deux traits de même couleur pour deux outils
            # différents.
            couleurs = {"tracer": defaut,
                        "decouper": QColor(pal.alerte),
                        "rainer": QColor("#7ac74f"),
                        "contour": QColor(pal.accent)}
            for i, poly in enumerate(self.polygones):
                role = self.roles[i] if i < len(self.roles) else None
                teinte = defaut if self.deborde else couleurs.get(role, defaut)
                epaisseur = 2 if role in ("decouper", "contour") else 1
                p.setPen(QPen(teinte, epaisseur))
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

class _MoletteNonVoleuse(QObject):
    """Empêche les champs numériques de voler la molette.

    Un QSpinBox saisit l'événement de molette même sans avoir le focus :
    on fait défiler la colonne, le curseur passe au-dessus d'un champ, le
    défilement s'arrête net et la VALEUR CHANGE. Christophe l'a signalé
    le 14/08/2026 — c'est une faute d'usage sournoise, parce qu'elle
    modifie un réglage sans qu'on l'ait voulu et sans rien dire.

    Le remède : ne traiter la molette que si le champ a le focus, et
    sinon la renvoyer à la zone défilante qui le porte.
    """

    def eventFilter(self, objet, evenement):
        if evenement.type() != QEvent.Wheel or objet.hasFocus():
            return False
        zone = objet.parent()
        while zone is not None and not isinstance(zone, QScrollArea):
            zone = zone.parent()
        if zone is not None:
            barre = zone.verticalScrollBar()
            pas = evenement.angleDelta().y()
            barre.setValue(barre.value() - pas)
        return True


class Pupitre(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pupitre de tracé — Graphtec CE6000-60")
        self.brut = []                    # polylignes du SVG, jamais modifiées
        # Le CONTOUR est gardé à part du dessin : on IMPRIME le motif et on
        # DÉCOUPE le tour. Les confondre ferait imprimer le trait de coupe
        # sur l'autocollant, ou découper le dessin lui-même.
        self.contour = []
        # Le contenu du SVG, gardé pour être recopié dans un projet : un
        # chemin absolu vieillit dès qu'on range ses dossiers.
        self.svg_source = None
        # Couleur de chaque tracé, en parallèle de `brut`. Sert à donner
        # un RÔLE à chacun : le motif qu'on imprime, le contour qu'on
        # découpe, les plis qu'on raine.
        self.couleurs = []
        self.correspondance = {}          # couleur arrondie -> rôle
        self.reperes = set()              # indices reconnus comme repères
        # Empreinte du placement au moment du dernier export de feuille.
        # Sert à prévenir quand le dessin a bougé depuis — c'est ce qui
        # manquait le 13/08/2026, et une manche y est passée.
        self.empreinte_export = None
        # Vrai pendant qu'un projet repose ses réglages : sans ça chaque
        # widget déclenche un recalcul complet, soit quarante pour rien.
        self._silence = False
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
        # Naître plus petit que l'écran, marges du gestionnaire de
        # fenêtres comprises. Une fenêtre plus haute que le bureau se
        # retrouve avec sa barre de titre hors d'atteinte.
        ecran = self.screen().availableGeometry() if self.screen() else None
        if ecran:
            self.resize(min(1120, ecran.width() - 80),
                        min(720, ecran.height() - 80))
        else:
            self.resize(1120, 720)

        # Un champ numérique n'a pas besoin de la moitié de la colonne :
        # à 182 px il poussait les groupes hors de la zone visible.
        for classe in (QSpinBox, QDoubleSpinBox):
            for champ in self.findChildren(classe):
                champ.setMaximumWidth(120)

        # La molette ne doit pas changer un réglage en passant dessus.
        self._molette = _MoletteNonVoleuse(self)
        for classe in (QSpinBox, QDoubleSpinBox, QComboBox):
            for champ in self.findChildren(classe):
                champ.setFocusPolicy(Qt.StrongFocus)
                champ.installEventFilter(self._molette)

        self._habiller()
        # RIEN qui parle à la machine ici. Le constructeur interrogeait le
        # traceur avant que la fenêtre s'affiche, et surtout il lisait le
        # vidage complet TC2009,5 puis refermait le périphérique — ce que
        # la règle 5 du dépôt interdit : la machine reste alors muette des
        # dizaines de secondes. Le programme sabotait son propre premier
        # envoi, et mettait plusieurs secondes à apparaître.
        #
        # La zone utile est demandée dès que la fenêtre est à l'écran ;
        # les conditions attendent qu'on ouvre l'onglet Outil.
        self._conditions_lues = False
        self.onglets.currentChanged.connect(self._onglet_change)
        QTimer.singleShot(0, self._ajuster_largeurs)
        QTimer.singleShot(0, lambda: self._interroger_media(silencieux=True))
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
        # Un champ numérique n'a pas besoin de la moitié de la colonne :
        # à 182 px il poussait les groupes hors de la zone visible.
        for classe in (QSpinBox, QDoubleSpinBox):
            for champ in self.findChildren(classe):
                champ.setMaximumWidth(120)

        # La molette ne doit pas changer un réglage en passant dessus.
        self._molette = _MoletteNonVoleuse(self)
        for classe in (QSpinBox, QDoubleSpinBox, QComboBox):
            for champ in self.findChildren(classe):
                champ.setFocusPolicy(Qt.StrongFocus)
                champ.installEventFilter(self._molette)

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
        # PAS de largeur figée. Elle valait 360 px, décidée quand la
        # colonne portait six cadres ; elle en porte neuf, dont un de
        # vingt-cinq lignes. Tout ce qui dépassait était rogné, et aucune
        # correction en aval ne pouvait rien y faire — c'est ici que ça se
        # décidait. `_ajuster_largeurs` pose maintenant le minimum d'après
        # ce que le contenu réclame vraiment, une fois la mise en page
        # faite.
        self.colonne = boite
        v = QVBoxLayout(boite)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        b_ouvrir = QPushButton("Ouvrir un SVG…")
        b_ouvrir.clicked.connect(self._ouvrir)
        b_ouvrir_projet = QPushButton("Ouvrir un projet…")
        b_ouvrir_projet.setToolTip(
            "Rouvre un travail avec TOUS ses réglages : placement,\n"
            "échelle, rotation, contour, repères. Le SVG est recopié\n"
            "dans le projet, donc il survit à un rangement de dossiers.")
        b_ouvrir_projet.clicked.connect(self._ouvrir_projet)
        b_enregistrer = QPushButton("Enregistrer le projet…")
        b_enregistrer.setToolTip(
            "Garde le dessin ET son placement. Sans ça, un cadrage\n"
            "patiemment ajusté ne vit que dans cette fenêtre — c'est\n"
            "ainsi qu'un print & cut a été perdu le 13/08/2026.")
        b_enregistrer.clicked.connect(self._enregistrer_projet)
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

        # --- print & cut, en TROIS cadres
        #
        # Ils étaient un seul, qui a grandi de quatre lignes à vingt-cinq
        # en une nuit. Christophe a fini par demander si les marges
        # servaient à la détection : elles n'ont rien à y voir, elles
        # disent où poser les repères sur la feuille à imprimer. L'ordre
        # d'apparition ne disait plus ce qui allait avec quoi.

        def grille(titre):
            cadre = QGroupBox(titre)
            disposition = QGridLayout(cadre)
            rang = [0]

            def pose(gauche, droite=None):
                if droite is None:
                    disposition.addWidget(gauche, rang[0], 0, 1, 2)
                else:
                    disposition.addWidget(gauche, rang[0], 0)
                    disposition.addWidget(droite, rang[0], 1)
                rang[0] += 1
            return cadre, pose

        # ============ 1. LA FEUILLE À IMPRIMER ============
        g_feuille, pose = grille("Feuille à imprimer")
        rappel_arms = QLabel(
            "à l'échelle 1, jamais « ajuster à la page » : 4 % déplacent "
            "un repère de 8 mm")
        rappel_arms.setObjectName("faible")
        rappel_arms.setWordWrap(True)
        pose(rappel_arms)

        self.spn_marge_arms = self._reel(5, 200, 25.0)
        self.spn_marge_arms.setToolTip(
            "distance entre le dessin et l'ANGLE des repères.\n"
            "En dessous de la longueur des branches (20 mm), les repères\n"
            "mordent sur le dessin.")
        pose(QLabel("marge repères"), self.spn_marge_arms)

        self.chk_marges4 = QCheckBox("quatre marges séparées")
        self.chk_marges4.setToolTip(
            "Comme le panneau de Graphtec Studio.\n\n"
            "ATTENTION aux axes : gauche et droite bornent la course du\n"
            "CHARIOT, bas et haut l'AVANCE du média. Ce sont les axes de\n"
            "la machine, pas ceux d'une feuille posée sur une table.")
        self.chk_marges4.stateChanged.connect(self._recalculer)
        pose(self.chk_marges4)
        self.spn_mg = self._reel(1, 200, 25.0)
        self.spn_md = self._reel(1, 200, 25.0)
        self.spn_mb = self._reel(1, 200, 25.0)
        self.spn_mh = self._reel(1, 200, 25.0)
        for nom, w in (("gauche (chariot)", self.spn_mg),
                       ("droite (chariot)", self.spn_md),
                       ("bas (avance)", self.spn_mb),
                       ("haut (avance)", self.spn_mh)):
            pose(QLabel(nom), w)

        self.spn_trait_arms = self._reel(0.3, 3.0, 1.0)
        self.spn_trait_arms.setDecimals(1)
        self.spn_trait_arms.setToolTip(
            "épaisseur du trait des repères.\n"
            "Le manuel donne 0,3 à 1 mm ; au-delà on sort de la plage\n"
            "annoncée, mais un trait plus gros donne plus de signal au\n"
            "capteur. C'est la feuille qui tranche, pas la notice.")
        pose(QLabel("trait repères"), self.spn_trait_arms)

        self.cmb_type_arms = QComboBox()
        self.cmb_type_arms.addItems(["type 2 — branches vers le dessin",
                                     "type 1 — branches vers le bord"])
        self.cmb_type_arms.setToolTip(
            "Doit correspondre au MARK TYPE réglé dans la machine.\n"
            "Un désaccord la fait balayer après une forme absente du\n"
            "papier, puis s'arrêter sur le bord de la feuille.")
        pose(QLabel("type de repère"), self.cmb_type_arms)

        b_feuille = QPushButton("Exporter la feuille…")
        b_feuille.setToolTip(
            "Écrit le dessin ENTOURÉ de ses quatre repères, à imprimer\n"
            "tel quel à l'échelle 1. Règle ensuite le placement pour que\n"
            "la découpe retombe sur l'impression.")
        b_feuille.clicked.connect(self._exporter_feuille)
        pose(b_feuille)

        self.cmb_imprimante = QComboBox()
        self.cmb_imprimante.addItems(impression.imprimantes() or ["(aucune)"])
        self.chk_gris = QCheckBox("noir seul")
        ligne_imp = QHBoxLayout()
        ligne_imp.addWidget(self.cmb_imprimante, 1)
        ligne_imp.addWidget(self.chk_gris)
        boite_imp = QWidget()
        boite_imp.setLayout(ligne_imp)
        pose(boite_imp)
        b_imprimer = QPushButton("Imprimer la feuille")
        b_imprimer.setToolTip(
            "Compose la feuille et l'envoie à l'imprimante À L'ÉCHELLE 1.\n"
            "Les options qui l'interdisent sont posées par le logiciel,\n"
            "pas laissées à ce qu'on pense à cocher.")
        b_imprimer.clicked.connect(self._imprimer_feuille)
        pose(b_imprimer)

        b_arms = QPushButton("Lire les réglages ARMS")
        b_arms.setToolTip(
            "Interroge la machine et signale ce qui contredit le gabarit.\n"
            "Le 13/08/2026, un MARK TYPE mal réglé est resté invisible des\n"
            "heures dans un vidage de configuration.\n\n"
            "À ne PAS faire juste avant un envoi : une grosse lecture\n"
            "laisse la machine muette si l'on referme derrière.")
        b_arms.clicked.connect(self._lire_arms)
        pose(b_arms)
        self.lbl_arms = QLabel("réglages non lus")
        self.lbl_arms.setObjectName("faible")
        self.lbl_arms.setWordWrap(True)
        pose(self.lbl_arms)

        # ============ 2. LA DÉCOUPE QUI SUIT ============
        g_decoupe, pose = grille("Découpe après détection")
        self.chk_arms = QCheckBox("après une détection de repères")
        self.chk_arms.setToolTip(
            "À cocher quand la machine vient de détecter les repères d'une\n"
            "feuille imprimée. Le travail part alors SANS IN;, qui\n"
            "réinitialiserait le traceur et effacerait l'origine que la\n"
            "détection vient de poser — la découpe repartirait du coin de\n"
            "la feuille au lieu du dessin, sans aucun message.")
        self.chk_arms.stateChanged.connect(self._recalculer)
        pose(self.chk_arms)
        rappel_dec = QLabel("détecter au panneau : [PAUSE/MENU] > [2] ARMS "
                            "> [1] LECT. AUTO REPERES, pointe sur le 1er "
                            "repère")
        rappel_dec.setObjectName("faible")
        rappel_dec.setWordWrap(True)
        pose(rappel_dec)

        self.spn_corr_av = self._reel(-20.0, 20.0, 0.0)
        self.spn_corr_ch = self._reel(-20.0, 20.0, 0.0)
        for w in (self.spn_corr_av, self.spn_corr_ch):
            w.setDecimals(1)
            w.setToolTip(
                "Écart MESURÉ entre la découpe et l'impression, à "
                "retrancher.\n\n"
                "Se lit sur la pièce : l'espace entre le dessin et le\n"
                "contour d'un côté, puis de l'autre. La MOITIÉ de leur\n"
                "différence est le décalage.\n\n"
                "N'agit que sur la DÉCOUPE, jamais sur la feuille à\n"
                "imprimer : l'appliquer au dessin déplacerait aussi les\n"
                "repères, donc recréerait l'écart qu'on corrige.")
        pose(QLabel("correction avance"), self.spn_corr_av)
        pose(QLabel("correction chariot"), self.spn_corr_ch)

        # ============ 3. LES ESSAIS DE PROTOCOLE ============
        g_essais, pose = grille("Essais de protocole")
        avert = QLabel(
            "AUCUN scan piloté depuis le PC n'a jamais abouti — neuf "
            "variantes. La détection se fait au panneau. Ceci sert à "
            "reprendre l'enquête, pas à travailler.")
        avert.setObjectName("faible")
        avert.setWordWrap(True)
        pose(avert)

        self.spn_ecart_av = self._reel(20, 900, 160.0)
        self.spn_ecart_ch = self._reel(20, 600, 150.0)
        pose(QLabel("écart avance"), self.spn_ecart_av)
        pose(QLabel("écart chariot"), self.spn_ecart_ch)

        self.spn_tb57a = self._entier(0, 9, 1)
        self.spn_tb57b = self._entier(0, 9, 1)
        self.spn_tb55 = self._entier(0, 9, 1)
        for w in (self.spn_tb57a, self.spn_tb57b):
            w.setToolTip(
                "TB57 porte un MODE — Cutting Master 3 nomme une routine\n"
                "AccumPCode_TB57_MODE, et ne garde pas TB57 en constante.\n"
                "C'est le paramètre qu'il reste à éprouver.")
        self.spn_tb55.setToolTip(
            "TB55 ne porte PAS le type de repère : c'est une constante\n"
            "valant 1 dans Cutting Master 3 comme dans Graphtec Studio.")
        rang_tb = QHBoxLayout()
        rang_tb.addWidget(QLabel("TB57"))
        rang_tb.addWidget(self.spn_tb57a)
        rang_tb.addWidget(self.spn_tb57b)
        rang_tb.addWidget(QLabel("TB55"))
        rang_tb.addWidget(self.spn_tb55)
        cadre_tb = QWidget()
        cadre_tb.setLayout(rang_tb)
        pose(cadre_tb)

        self.chk_depart = QCheckBox("amener la tête avant de chercher")
        self.chk_depart.setToolTip(
            "Le manuel demande de « positionner le chariot dans la zone\n"
            "de détection du 1er repère » — pour la détection AUTOMATIQUE\n"
            "comme pour la manuelle.")
        pose(self.chk_depart)
        self.spn_dep_av = self._reel(0, 600, 35.0)
        self.spn_dep_ch = self._reel(0, 600, 30.0)
        for w in (self.spn_dep_av, self.spn_dep_ch):
            w.setToolTip(
                "Position de l'angle du PREMIER REPÈRE dans le repère de\n"
                "la machine, mesurée sur la feuille chargée.\n\n"
                "Sert deux fois : à amener la tête avant le scan, et à\n"
                "vérifier à l'export que le repère opposé reste dans la\n"
                "zone que la machine peut atteindre.")
        pose(QLabel("1er repère, avance"), self.spn_dep_av)
        pose(QLabel("1er repère, chariot"), self.spn_dep_ch)

        b_scan = QPushButton("Lancer une détection  (à éprouver)")
        b_scan.setToolTip(
            "Déclenche le balayage depuis le PC, au lieu du panneau.\n"
            "CE CHEMIN N'A JAMAIS ABOUTI.")
        b_scan.clicked.connect(self._scanner_arms)
        pose(b_scan)

        # --- rôles des couleurs
        g = QGroupBox("Rôles des couleurs")
        gl = QVBoxLayout(g)
        self.cmb_travail = QComboBox()
        self.cmb_travail.addItems(["tout, sauf les repères", "tracer",
                                   "rainer", "découper"])
        self.cmb_travail.setToolTip(
            "Ce qui part au traceur MAINTENANT. Un fichier peut porter\n"
            "le motif et son contour : on envoie l'un, on change d'outil,\n"
            "on envoie l'autre.\n\n"
            "Les repères ARMS ne sont jamais envoyés — les découper\n"
            "trancherait la feuille en travers de ce qui vient de servir.")
        self.cmb_travail.currentIndexChanged.connect(self._recalculer)
        ligne = QHBoxLayout()
        ligne.addWidget(QLabel("envoyer"))
        ligne.addWidget(self.cmb_travail, 1)
        gl.addLayout(ligne)
        # Rempli à l'ouverture d'un fichier : une ligne par couleur trouvée.
        self.zone_couleurs = QWidget()
        self.grille_couleurs = QGridLayout(self.zone_couleurs)
        self.grille_couleurs.setContentsMargins(0, 4, 0, 0)
        gl.addWidget(self.zone_couleurs)
        self.lbl_roles = QLabel("aucun dessin")
        self.lbl_roles.setObjectName("faible")
        self.lbl_roles.setWordWrap(True)
        gl.addWidget(self.lbl_roles)
        g_roles = g

        # --- contour de découpe
        g = QGroupBox("Contour de découpe")
        gl = QGridLayout(g)
        self.chk_contour = QCheckBox("découper autour du dessin")
        self.chk_contour.setToolTip(
            "Fabrique le tour d'un autocollant : on imprime le motif, on\n"
            "découpe AUTOUR, à quelques millimètres.\n\n"
            "Vrai décalage de polygone, pas une boîte englobante — une\n"
            "étoile garde ses creux. Les formes qui se touchent donnent un\n"
            "seul contour.")
        self.chk_contour.stateChanged.connect(self._recalculer)
        self.spn_retrait = self._reel(0.5, 30.0, 3.0)
        self.chk_trous = QCheckBox("garder les trous intérieurs")
        self.chk_trous.setToolTip(
            "Par défaut le contour ne garde que le tour EXTÉRIEUR : un\n"
            "autocollant se détache d'un seul morceau. Cocher pour\n"
            "évider aussi l'intérieur des formes creuses.")
        self.chk_trous.stateChanged.connect(self._recalculer)
        self.spn_retrait.valueChanged.connect(self._recalculer)
        self.lbl_contour = QLabel("inactif")
        self.lbl_contour.setObjectName("faible")
        self.lbl_contour.setWordWrap(True)
        gl.addWidget(self.chk_contour, 0, 0, 1, 2)
        gl.addWidget(QLabel("retrait"), 1, 0)
        gl.addWidget(self.spn_retrait, 1, 1)
        gl.addWidget(self.chk_trous, 2, 0, 1, 2)
        gl.addWidget(self.lbl_contour, 3, 0, 1, 2)
        g_contour = g

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
        self.cmb_cond.setToolTip(
            "Les huit conditions vivent dans la machine. Le point marque "
            "celle\nqu'elle emploie quand le fichier ne dit rien.")
        self.resume_conditions = {}
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
        # Débordement : la pointe de la lame TRAÎNE derrière l'axe du
        # porte-outil. Sans lui, un contour qui se referme s'arrête juste
        # avant son point de départ et laisse une languette non coupée, qui
        # se déchire quand on pousse la pièce — toujours au même coin, et
        # dès les forces les plus faibles. Mesuré le 13/08/2026 : à zéro,
        # tous les carrés d'un nuancier se déchiraient ; à 0,2 mm ils se
        # détachent proprement. Stocké à 200 unités par millimètre.
        self.spn_debord = self._reel(0, 2.0, 0.2)
        self.spn_debord.setDecimals(2)
        self.spn_debord.setToolTip(
            "Prolonge la coupe au-delà du point de fermeture, pour\n"
            "rattraper la traîne de la pointe. À ZÉRO, chaque contour\n"
            "laisse une languette qui se déchire au coin de départ.\n"
            "0,2 mm est la valeur que Graphtec emploie lui-même.")
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
        b_lire_c.clicked.connect(lambda: (self._resumer_conditions(),
                                          self._lire_condition()))
        b_appl_c = QPushButton("Appliquer maintenant")
        b_appl_c.clicked.connect(self._appliquer_condition)
        self.lbl_condition = QLabel("condition non lue")
        self.lbl_condition.setObjectName("faible")
        self.lbl_condition.setWordWrap(True)
        gl.addWidget(QLabel("matériau"), 0, 0); gl.addWidget(self.cmb_profil, 0, 1)
        gl.addWidget(self.lbl_profil, 1, 0, 1, 2)
        gl.addWidget(QLabel("condition"), 2, 0); gl.addWidget(self.cmb_cond, 2, 1)
        gl.addWidget(QLabel("outil"), 3, 0); gl.addWidget(self.cmb_outil, 3, 1)
        self.lbl_offset = QLabel("offset")
        gl.addWidget(self.lbl_offset, 4, 0); gl.addWidget(self.spn_offset, 4, 1)
        gl.addWidget(QLabel("débordement"), 5, 0)
        gl.addWidget(self.spn_debord, 5, 1)
        gl.addWidget(QLabel("vitesse"), 6, 0); gl.addWidget(self.spn_vit, 6, 1)
        gl.addWidget(QLabel("force"), 7, 0); gl.addWidget(self.spn_force, 7, 1)
        gl.addWidget(QLabel("accélération"), 8, 0); gl.addWidget(self.spn_accel, 8, 1)
        gl.addWidget(QLabel("passages"), 9, 0); gl.addWidget(self.spn_passages, 9, 1)
        self.spn_passages.setToolTip(
            "repasser sur chaque tracé rend le trait franc au stylo.\n"
            "Le carnet d'établi note 2 pour le feutre comme pour le Bic.\n"
            "Ne coûte aucun déplacement : le retour se fait à l'envers.")
        gl.addWidget(b_lire_c, 10, 0); gl.addWidget(b_appl_c, 10, 1)
        gl.addWidget(self.lbl_condition, 11, 0, 1, 2)
        gl.addWidget(self.chk_regler, 12, 0, 1, 2)
        rappel = QLabel("accélération basse = trait net,\nhaute = travail plus court")
        rappel.setObjectName("faible")
        gl.addWidget(rappel, 13, 0, 1, 2)
        self._offset_utile(self.cmb_outil.currentText())
        g_outil = g

        def onglet(*cadres):
            """Un onglet DÉFILANT.

            Sans lui, chaque cadre ajouté allonge la colonne et finit par
            pousser la fenêtre hors de l'écran — c'est arrivé le
            13/08/2026 avec le cadre Print & cut. Un panneau qui grandit
            est normal ; une fenêtre qu'on ne peut plus refermer parce que
            sa barre de titre est sortie du bureau ne l'est pas.
            """
            w = QWidget()
            lay = QVBoxLayout(w)
            lay.setContentsMargins(10, 12, 10, 10)
            lay.setSpacing(10)
            for c in cadres:
                lay.addWidget(c)
            lay.addStretch(1)
            zone = QScrollArea()
            zone.setWidget(w)
            zone.setWidgetResizable(True)
            zone.setFrameShape(QFrame.NoFrame)
            # La barre horizontale reparaît AU BESOIN. Elle était
            # interdite, ce qui paraissait plus propre : en réalité le
            # contenu était rogné en SILENCE, et Christophe a perdu les
            # flèches de ses champs sans qu'aucune barre ne le signale.
            # Mieux vaut une barre visible qu'un champ invisible.
            zone.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            # Sans largeur minimale, la barre de défilement verticale mange
            # la place et la colonne se retrouve ROGNÉE : les libellés
            # perdent leur début, « largeur » devient « eur ». Vu sur une
            # capture de Christophe, pas dans le code.
            # La largeur minimale est posée plus tard, par
            # `_ajuster_largeurs` : ici le contenu ne connaît pas encore
            # sa taille, et un sizeHint pris trop tôt rogne les champs de
            # quelques pixels — assez pour manger leurs flèches.
            return zone

        self.onglets = QTabWidget()
        self.onglets.addTab(onglet(b_ouvrir, b_ouvrir_projet,
                                   b_enregistrer, self.lbl_fichier, g_media,
                                   g_placement, g_mosaique,
                                   g_perfo, g_roles, g_contour,
                                   g_feuille, g_decoupe, g_essais), "Dessin")
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
             "Force de la découpe LÉGÈRE qui oriente la lame avant chaque\n"
             "départ — pas la force de coupe. Défaut du manuel : 4, et il\n"
             "demande « la plus faible possible ».\n\n"
             "À 30 — la valeur qu'y écrivait Graphtec Studio — elle\n"
             "DÉCHIRE le papier 80 g au départ. Mesuré le 13/08/2026 sur\n"
             "deux carrés jumeaux."),
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
            (M.TRI_DONNEES, "tri des chemins",
             {0: "par le logiciel", 1: "par la machine"},
             "Le pupitre réordonne déjà les chemins avant l'envoi, et son\n"
             "gain est mesuré : 53 % de trajet à vide en moins sur le\n"
             "gabarit du porte-manteau. Deux tris superposés, c'est un tri\n"
             "dont on ne sait plus lequel agit."),
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
        if m.get("mesure"):
            rappels.append(f"mesuré {m['mesure']}")
        if not outil:
            # Sans outil déclaré, le champ garde celui du profil précédent :
            # un réglage hérité en silence, et c'est précisément ce genre
            # d'héritage qui a arrondi les angles d'une découpe.
            rappels.append(f"AUCUN outil dans le carnet pour ce profil — "
                           f"vérifier que « {self.cmb_outil.currentText()} » "
                           f"est bien ce qui est monté")
        if m.get("hauteur_lame"):
            rappels.append(
                f"À LA MAIN : sortie de lame {m['hauteur_lame']} mm — la "
                f"machine sait la MESURER : [COND/TEST] → CONDITION (3/3) "
                f"→ [3] AJUSTEMENT LAME")
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

    def _resumer_conditions(self, silencieux=True):
        """Écrit le contenu des huit conditions DANS la liste déroulante.

        « condition 5 » ne dit rien de ce qu'on choisit. La machine les
        garde toutes les huit et les rend d'un coup en clair : les afficher
        là où on choisit évite d'aller les lire ailleurs — ou pire, de
        deviner. La condition ACTIVE est marquée : c'est celle que la
        machine emploie quand le fichier ne dit rien.
        """
        import conditions as M
        if not os.path.exists(M.PERIPH):
            return
        try:
            sections = etat_machine.analyser(etat_machine.lire())
        except Exception as e:
            if not silencieux:
                QMessageBox.warning(self, "Traceur", str(e))
            return
        self.resume_conditions = {}
        for i in range(self.cmb_cond.count()):
            c = sections.get(f"No.{i + 1}")
            if not c:
                continue
            actif = " ●" if "*active*" in c else ""
            court = (f"{i + 1}{actif} · {c.get('TOOL', '?')} · "
                     f"{c.get('SPEED', '?')} cm/s · F{c.get('FORCE', '?')}")
            self.cmb_cond.setItemText(i, court)
            self.resume_conditions[i] = (
                f"condition {i + 1}"
                + ("  (active)" if actif else "")
                + f" : {c.get('TOOL', '?')}, {c.get('SPEED', '?')} cm/s, "
                  f"force {c.get('FORCE', '?')}, accél. {c.get('ACCEL.', '?')}"
                + (f", offset {c.get('OFFSET')}" if c.get("OFFSET") else ""))

        # Le menu déroulant est plus large que sa colonne : sans ça les
        # résumés sortent tronqués (« 1 ● — PEN, 1…/s, force 12 »), et un
        # résumé tronqué ne renseigne pas mieux qu'un numéro nu.
        metrique = self.cmb_cond.fontMetrics()
        largeur = max((metrique.horizontalAdvance(self.cmb_cond.itemText(i))
                       for i in range(self.cmb_cond.count())), default=0)
        self.cmb_cond.view().setMinimumWidth(largeur + 44)

    def _lire_arms(self):
        """Lit les réglages ARMS et dit ce qui contredit le gabarit.

        Le type de repère est le premier montré parce que c'est celui qui
        fait rater une détection sans qu'on comprenne pourquoi : la machine
        balaie en cherchant une forme absente du papier, puis s'arrête sur
        le bord de la feuille, qui offre exactement le même contraste.
        """
        import conditions as M
        import arms
        if not os.path.exists(M.PERIPH):
            QMessageBox.information(self, "Traceur absent",
                                    f"{M.PERIPH} n'existe pas.")
            return
        try:
            lus = arms.lire()
        except Exception as e:
            QMessageBox.warning(self, "Traceur",
                                f"{e}\n\nLa machine est-elle sur READY ?")
            return
        lignes = [f"{libelle} : {valeur}" for libelle, _, valeur in lus]
        self.lbl_arms.setText("   ·   ".join(lignes[:4]))
        ennuis = arms.desaccords(lus, type_gabarit=self._type_arms())
        texte = "\n".join(f"  {lib:<28} {val}" for lib, _, val in lus)
        if ennuis:
            texte += "\n\nÀ CORRIGER avant de scanner :\n"
            texte += "\n".join(f"  • {e}" for e in ennuis)
        else:
            texte += "\n\nRien à signaler du côté des réglages —"
            texte += "\nce qui ne dit rien de la feuille elle-même."
        texte += "\n\nMarche à suivre :\n"
        texte += "\n".join(f"  {i}. {e}" for i, e
                          in enumerate(arms.marche_a_suivre(self._type_arms()), 1))
        QMessageBox.information(self, "Print & cut (ARMS)", texte)

    # ------------------------------------------------------- le projet
    def _lire_reglages(self):
        """Tous les réglages de l'interface, selon la table de `projet`."""
        valeurs = {}
        for nom, genre in fichier_projet.REGLAGES:
            w = getattr(self, nom, None)
            if w is None:
                continue
            if genre == "bool":
                valeurs[nom] = w.isChecked()
            elif genre == "texte":
                valeurs[nom] = w.currentText()
            elif genre == "entier_liste":
                valeurs[nom] = w.currentIndex()
            else:
                valeurs[nom] = w.value()
        return valeurs

    def _poser_reglages(self, valeurs):
        """Remet les réglages. Ce qui manque est LAISSÉ TEL QUEL plutôt que
        remis par défaut : un projet ancien ne doit pas effacer en silence
        des réglages qu'il ne connaissait pas."""
        self._silence = True
        try:
            for nom, genre in fichier_projet.REGLAGES:
                if nom not in valeurs:
                    continue
                w = getattr(self, nom, None)
                if w is None:
                    continue
                v = valeurs[nom]
                if genre == "bool":
                    w.setChecked(bool(v))
                elif genre == "texte":
                    w.setCurrentText(str(v))
                elif genre == "entier_liste":
                    w.setCurrentIndex(int(v))
                elif genre == "entier":
                    w.setValue(int(v))
                else:
                    w.setValue(float(v))
        finally:
            self._silence = False
        self._recalculer()

    def _enregistrer_projet(self):
        if not self.brut:
            QMessageBox.information(self, "Enregistrer",
                                    "Ouvre d'abord un dessin.")
            return
        depart = os.path.splitext(self.chemin or "travail")[0] \
            + fichier_projet.EXTENSION
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le projet", depart,
            f"Projet traceur (*{fichier_projet.EXTENSION})")
        if not chemin:
            return
        try:
            ecrit = fichier_projet.enregistrer(
                chemin, self._lire_reglages(), svg=self.svg_source,
                source=self.chemin, empreinte_export=self.empreinte_export,
                correspondance={",".join(f"{c:.3f}" for c in rgb): role
                                for rgb, role in self.correspondance.items()})
        except OSError as e:
            QMessageBox.warning(self, "Enregistrer", str(e))
            return
        self.lbl_fichier.setText(f"{os.path.basename(ecrit)} — enregistré")

    def _ouvrir_projet(self):
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un projet", os.path.expanduser("~"),
            f"Projet traceur (*{fichier_projet.EXTENSION})")
        if not chemin:
            return
        try:
            projet = fichier_projet.charger(chemin)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Ouvrir un projet", str(e))
            return

        svg = projet.get("svg")
        if not svg:
            QMessageBox.warning(self, "Ouvrir un projet",
                                "Ce projet ne porte pas de dessin.")
            return
        # Le SVG est recopié dans un fichier temporaire parce que le
        # parseur lit un chemin, pas une chaîne. Le projet reste la source.
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False,
                                         encoding="utf-8") as f:
            f.write(svg)
            provisoire = f.name
        couleurs_relues = []
        try:
            self.brut, avertissements = noyau.charger(
                provisoire, couleurs=couleurs_relues)
        except Exception as e:
            QMessageBox.warning(self, "Ouvrir un projet", str(e))
            return
        finally:
            os.unlink(provisoire)
        if not self.brut:
            QMessageBox.warning(self, "Ouvrir un projet",
                                "Aucune géométrie exploitable.")
            return

        self.svg_source = svg
        self.couleurs = couleurs_relues
        self.correspondance = {
            tuple(float(x) for x in cle.split(",")): role
            for cle, role in (projet.get("correspondance") or {}).items()}
        self.reperes = roles_couleur.reperes_arms(self.brut)
        self.chemin = projet.get("source")
        self.empreinte_export = projet.get("empreinte_export")
        self._poser_reglages(projet.get("reglages", {}))
        self._refaire_liste_couleurs()
        self.b_envoyer.setEnabled(True)
        self.apercu.reinitialiser_vue()
        self.lbl_fichier.setText(
            os.path.basename(chemin)
            + ("\n⚠ " + "\n⚠ ".join(avertissements) if avertissements else ""))
        self._recalculer()

    def _refaire_liste_couleurs(self):
        """Une ligne par couleur du fichier, avec son rôle.

        Reconstruite à chaque ouverture : les couleurs d'un fichier ne
        sont pas celles du précédent, et garder d'anciennes lignes ferait
        croire à des tracés qui n'existent plus.
        """
        while self.grille_couleurs.count():
            item = self.grille_couleurs.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._combos_couleur = {}
        if not self.couleurs:
            self.lbl_roles.setText("aucun dessin")
            return
        for rang, (rgb, nombre) in enumerate(
                roles_couleur.couleurs_presentes(self.couleurs)):
            pastille = QLabel("■")
            r, v, b = (round(c * 255) for c in rgb)
            pastille.setStyleSheet(f"color: rgb({r},{v},{b}); font-size: 16px;")
            cmb = QComboBox()
            cmb.addItems([roles_couleur.LIBELLES[x]
                          for x in roles_couleur.ROLES])
            choisi = self.correspondance.get(rgb) \
                or roles_couleur.role_par_defaut(rgb)
            cmb.setCurrentText(roles_couleur.LIBELLES[choisi])
            cmb.currentIndexChanged.connect(self._roles_changes)
            self._combos_couleur[rgb] = cmb
            self.grille_couleurs.addWidget(pastille, rang, 0)
            self.grille_couleurs.addWidget(
                QLabel(f"{roles_couleur.nom_couleur(rgb)} ({nombre})"), rang, 1)
            self.grille_couleurs.addWidget(cmb, rang, 2)
        self._roles_changes()

    def _roles_changes(self):
        """Relit les listes déroulantes et recalcule."""
        inverse = {v: k for k, v in roles_couleur.LIBELLES.items()}
        self.correspondance = {rgb: inverse[cmb.currentText()]
                               for rgb, cmb in
                               getattr(self, "_combos_couleur", {}).items()}
        self._recalculer()

    def _retenus(self):
        """Les tracés que le travail choisi doit envoyer.

        Les repères ARMS sont écartés dans TOUS les cas — c'est le point
        3 de la demande de Christophe, et la raison en est physique :
        les découper trancherait la feuille en travers des repères qui
        viennent de servir à la détection.
        """
        if not self.couleurs or len(self.couleurs) != len(self.brut):
            self._roles_retenus = ["tracer"] * len(self.brut)
            return self.brut
        par_role = roles_couleur.classer(self.brut, self.couleurs,
                                         self.correspondance, self.reperes)
        choix = self.cmb_travail.currentText()
        if choix.startswith("tout"):
            garde = ["tracer", "rainer", "decouper"]
        else:
            garde = {"tracer": ["tracer"], "rainer": ["rainer"],
                     "découper": ["decouper"]}[choix]
        retenus, self._roles_retenus = [], []
        for role in garde:
            retenus += par_role[role]
            self._roles_retenus += [role] * len(par_role[role])
        return retenus

    def _type_arms(self):
        """2 ou 1, selon la liste — l'ordre de la liste met le 2 d'abord,
        parce que c'est celui des gabarits officiels et celui que la
        machine de l'atelier attend."""
        return 2 if self.cmb_type_arms.currentIndex() == 0 else 1

    def _caler_sur_la_feuille(self, infos):
        """Pose le placement d'après la feuille, PUIS scelle l'empreinte.

        Un seul geste, appelé par l'export comme par l'impression, parce
        que l'ordre importe et qu'un ordre qui importe ne doit pas être
        laissé à la mémoire de celui qui écrit le second appel.

        L'export DÉPLACE lui-même le dessin — il le pose à la distance
        connue du premier repère. Sceller avant revenait à figer un état
        que l'export allait aussitôt changer : l'alerte « le dessin a
        bougé » criait dès l'envoi suivant, sans que personne n'ait rien
        touché. C'est le « je n'ai rien touché » de Christophe, le
        14/08/2026, qui l'a trouvée — mon premier diagnostic accusait la
        case du contour.
        """
        ox, oy = infos["origine_dessin"]
        self.spn_x.setValue(ox)
        self.spn_y.setValue(oy)
        self.chk_arms.setChecked(True)
        ax, ay = infos["ecart"]
        self.spn_ecart_av.setValue(ax)
        self.spn_ecart_ch.setValue(ay)
        self.empreinte_export = fichier_projet.empreinte(self._lire_reglages())

    def _exporter_feuille(self):
        """Écrit le dessin entouré de ses repères, et cale la découpe.

        L'offset entre l'origine des repères et celle du dessin est ce que
        le manuel (p. 5-5) dit de MESURER. Ici on n'a pas à le mesurer :
        c'est nous qui posons les deux, donc on le connaît — c'est la
        marge. Reste à régler le placement pour que la découpe parte du
        même point, et c'est ce que fait ce bouton.
        """
        import arms
        if not self.calcule:
            QMessageBox.information(self, "Feuille à imprimer",
                                    "Ouvre d'abord un dessin.")
            return
        marge = self.spn_marge_arms.value()
        try:
            quatre = None
            if self.chk_marges4.isChecked():
                quatre = (self.spn_mg.value(), self.spn_md.value(),
                          self.spn_mb.value(), self.spn_mh.value())
            svg, infos = arms.composer(
                self.calcule, marge=marge, marges=quatre,
                epaisseur=self.spn_trait_arms.value(),
                type_repere=self._type_arms())
        except ValueError as e:
            QMessageBox.warning(self, "Feuille à imprimer", str(e))
            return

        depart = os.path.splitext(self.chemin or "feuille")[0] + "_a_imprimer.svg"
        chemin, _ = QFileDialog.getSaveFileName(
            self, "Écrire la feuille à imprimer", depart, "SVG (*.svg)")
        if not chemin:
            return
        with open(chemin, "w", encoding="utf-8") as f:
            f.write(svg)

        # Un PDF à côté quand rsvg-convert est là : c'est lui qu'on
        # imprime, et il ne se laisse pas remettre à l'échelle aussi
        # facilement qu'un SVG ouvert dans un navigateur.
        pdf = os.path.splitext(chemin)[0] + ".pdf"
        try:
            import subprocess
            subprocess.run(["rsvg-convert", "-f", "pdf", "-o", pdf, chemin],
                           check=True, capture_output=True)
        except Exception:
            pdf = None

        self._caler_sur_la_feuille(infos)
        ax, ay = infos["ecart"]

        # Le jeu de repères est-il ATTEIGNABLE ? La zone utile est plus
        # petite que la feuille, et elle rétrécit quand on rapproche les
        # galets. Un « HORS SURFACE » se calcule ici plutôt que de se
        # découvrir sur la machine, feuille déjà imprimée.
        hors = arms.tient_dans_la_zone(
            infos["ecart"], (self.spn_mx.value(), self.spn_my.value()),
            premier=(self.spn_dep_av.value(), self.spn_dep_ch.value()))

        pl, ph = infos["page"]
        texte = (f"Feuille écrite : {os.path.basename(chemin)}\n"
                 + (f"PDF : {os.path.basename(pdf)}\n" if pdf else "")
                 + f"\npage {pl:.1f} × {ph:.1f} mm\n"
                 f"écart entre repères {ax:.1f} × {ay:.1f} mm\n"
                 f"dessin à {marge:g} ; {marge:g} mm du premier repère\n\n"
                 "Placement et mode repérage réglés en conséquence.\n\n"
                 "1. imprimer À L'ÉCHELLE 1 — jamais « ajuster à la page »\n"
                 "2. vérifier au pied à coulisse qu'une branche fait 20 mm\n"
                 "3. charger la feuille, attendre READY\n"
                 "4. détecter au panneau : [PAUSE/MENU] > [2] ARMS >\n"
                 "   [1] LECT. AUTO REPERES\n"
                 "5. revenir ici et envoyer au traceur")
        for a in infos["avertissements"]:
            texte += f"\n\nATTENTION : {a}"
        for a in hors:
            texte += f"\n\nHORS D'ATTEINTE : {a}"
        if hors:
            QMessageBox.warning(self, "Feuille à imprimer", texte)
        else:
            QMessageBox.information(self, "Feuille à imprimer", texte)

    def _imprimer_feuille(self):
        """Compose et imprime, à l'échelle exacte.

        Le même contrôle qu'à l'export : inutile d'imprimer une feuille
        dont les repères seront hors d'atteinte de la tête.
        """
        import arms
        import tempfile
        if not self.calcule:
            QMessageBox.information(self, "Imprimer", "Ouvre d'abord un dessin.")
            return
        nom = self.cmb_imprimante.currentText()
        if nom.startswith("("):
            QMessageBox.warning(self, "Imprimer",
                                "Aucune imprimante connue du système.")
            return
        marge = self.spn_marge_arms.value()
        quatre = None
        if self.chk_marges4.isChecked():
            quatre = (self.spn_mg.value(), self.spn_md.value(),
                      self.spn_mb.value(), self.spn_mh.value())
        try:
            svg, infos = arms.composer(
                self.calcule, marge=marge, marges=quatre,
                epaisseur=self.spn_trait_arms.value(),
                type_repere=self._type_arms())
        except ValueError as e:
            QMessageBox.warning(self, "Imprimer", str(e))
            return

        hors = arms.tient_dans_la_zone(
            infos["ecart"], (self.spn_mx.value(), self.spn_my.value()),
            premier=(self.spn_dep_av.value(), self.spn_dep_ch.value()))
        ax, ay = infos["ecart"]
        question = (f"Imprimer sur {nom} à l'échelle 1.\n\n"
                    f"écart entre repères {ax:.1f} × {ay:.1f} mm\n"
                    f"dessin à {infos['origine_dessin'][0]:g} ; "
                    f"{infos['origine_dessin'][1]:g} mm du premier repère")
        for a in infos["avertissements"] + hors:
            question += f"\n\nATTENTION : {a}"
        if hors:
            question += ("\n\nCes repères seront HORS D'ATTEINTE de la "
                         "tête : la feuille sera imprimée pour rien.")
        question += "\n\nContinuer ?"
        rep = QMessageBox.question(self, "Imprimer la feuille", question,
                                   QMessageBox.Ok | QMessageBox.Cancel)
        if rep != QMessageBox.Ok:
            return

        with tempfile.TemporaryDirectory() as dossier:
            chemin_svg = os.path.join(dossier, "feuille.svg")
            chemin_pdf = os.path.join(dossier, "feuille.pdf")
            with open(chemin_svg, "w", encoding="utf-8") as f:
                f.write(svg)
            try:
                import subprocess
                subprocess.run(["rsvg-convert", "-f", "pdf",
                                "-o", chemin_pdf, chemin_svg],
                               check=True, capture_output=True, timeout=30)
                travail = impression.imprimer(
                    chemin_pdf, nom, copies=1,
                    gris=self.chk_gris.isChecked())
            except Exception as e:
                QMessageBox.warning(self, "Imprimer", str(e))
                return

        self._caler_sur_la_feuille(infos)
        self.lbl_arms.setText(f"feuille envoyée à {nom} — {travail}")

    def _scanner_arms(self):
        """Déclenche une détection depuis le PC. Chemin NON ÉPROUVÉ.

        La tête se met à balayer : on demande avant, comme pour tout ce qui
        fait descendre un outil sur du papier posé par quelqu'un.
        """
        import conditions as M
        import arms
        if not os.path.exists(M.PERIPH):
            QMessageBox.information(self, "Traceur absent",
                                    f"{M.PERIPH} n'existe pas.")
            return
        av = self.spn_ecart_av.value()
        ch = self.spn_ecart_ch.value()
        rep = QMessageBox.question(
            self, "Lancer une détection",
            f"La tête va balayer la feuille pendant une vingtaine de "
            f"secondes, à la recherche de repères espacés de "
            f"{av:g} mm dans l'avance et {ch:g} mm sous le chariot.\n\n"
            f"Protocole : TB57,{self.spn_tb57a.value()},"
            f"{self.spn_tb57b.value()} et TB55,{self.spn_tb55.value()}.\n\n"
            f"Ce chemin N'A JAMAIS ABOUTI : la machine cherche, mais aucune "
            f"détection pilotée par le PC n'a été menée à son terme. Celles "
            f"qui ont réussi sont passées par le panneau.\n\n"
            f"Continuer ?",
            QMessageBox.Ok | QMessageBox.Cancel)
        if rep != QMessageBox.Ok:
            return
        try:
            annonces, journal = arms.scanner(
                av, ch, epaisseur=self.spn_trait_arms.value(),
                type_repere=self.spn_tb55.value(),
                tb57=(self.spn_tb57a.value(), self.spn_tb57b.value()),
                depart=((self.spn_dep_av.value(), self.spn_dep_ch.value())
                        if self.chk_depart.isChecked() else None))
        except Exception as e:
            QMessageBox.warning(self, "Traceur", str(e))
            return
        texte = "\n".join(journal) or "(la machine n'a rien dit)"
        if annonces:
            texte += "\n\nAnnonces recueillies :\n"
            texte += "\n".join(f"  {t:5.1f} s   « {a} »" for t, a in annonces)
            texte += ("\n\nSeule forme connue à ce jour : « 1,254 », "
                      "laissée par un scan qui a ÉCHOUÉ. Celle d'une "
                      "réussite n'a jamais été observée — si celle-ci "
                      "diffère, elle vaut d'être notée.")
        else:
            texte += "\n\nAucune annonce poussée."
        self.lbl_arms.setText(
            f"scan : {len(annonces)} annonce(s)" if annonces
            else "scan : aucune annonce")
        QMessageBox.information(self, "Détection ARMS", texte)

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
        if etat.get("debordement") is not None:
            self.spn_debord.setValue(etat["debordement"] / 200.0)
        self.lbl_condition.setText(
            getattr(self, "resume_conditions", {}).get(
                self.cmb_cond.currentIndex(),
                f"condition {self.cmb_cond.currentIndex() + 1} lue"))
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
            d = int(round(self.spn_debord.value() * 200))
            M.regler(fd, M.DEBORDEMENT, f"{d},{d}", condition=cond)
            rendu = M.appliquer(vitesse=self.spn_vit.value(),
                                force=self.spn_force.value(),
                                acceleration=self.spn_accel.value(),
                                condition=cond, fd=fd)
        finally:
            os.close(fd)
        rates = [n for n, _d, _o, ok in rendu if not ok]
        self._resumer_conditions()
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
        fo = lus.get(M.FORCE_DEPORT)
        alerte = ("   ⚠ force d'offset à %d : elle déchire le papier au "
                  "départ dès qu'elle approche la force de coupe. "
                  "Le défaut est 4." % fo) if fo and fo > 10 else ""

        texte = f"{len(lus)} réglage(s) lus sur la machine" + alerte
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
            self.couleurs = []
            self.brut, avertissements = noyau.charger(
                chemin, couleurs=self.couleurs)
        except Exception as e:
            QMessageBox.warning(self, "Lecture impossible", str(e))
            return
        if not self.brut:
            QMessageBox.warning(self, "Rien à tracer",
                                "Aucune géométrie exploitable dans ce SVG.\n\n"
                                + "\n".join(avertissements))
            return
        self.correspondance = {}
        self.reperes = roles_couleur.reperes_arms(self.brut)
        self.chemin = chemin
        try:
            self.svg_source = open(chemin, encoding="utf-8").read()
        except OSError:
            self.svg_source = None
        # Couleur de chaque tracé, en parallèle de `brut`. Sert à donner
        # un RÔLE à chacun : le motif qu'on imprime, le contour qu'on
        # découpe, les plis qu'on raine.
        self.couleurs = []
        self.correspondance = {}          # couleur arrondie -> rôle
        self.reperes = set()              # indices reconnus comme repères
        self.empreinte_export = None      # un dessin neuf n'a pas de feuille
        self.lbl_fichier.setText(os.path.basename(chemin) +
                                 ("\n⚠ " + "\n⚠ ".join(avertissements)
                                  if avertissements else ""))
        self.b_envoyer.setEnabled(True)
        self._refaire_liste_couleurs()
        # Un dessin neuf mérite un cadrage neuf ; un simple réglage, non.
        self.apercu.reinitialiser_vue()
        self._recalculer()

    def _ajuster_largeurs(self):
        """Donne à la colonne la largeur que son contenu réclame.

        Une fois la mise en page faite, et pas avant : un `sizeHint` pris
        dans le constructeur vaut moins que la réalité, et la colonne se
        retrouve rognée de quelques pixels — assez pour manger les flèches
        des champs. Vu sur une capture de Christophe le 14/08/2026, pas
        dans le code.
        """
        besoin = 0
        for i in range(self.onglets.count()):
            zone = self.onglets.widget(i)
            if not isinstance(zone, QScrollArea):
                continue
            besoin = max(besoin,
                         zone.widget().sizeHint().width()
                         + zone.verticalScrollBar().sizeHint().width()
                         + 2 * zone.frameWidth() + 4)
        if besoin:
            self.onglets.setMinimumWidth(besoin + 6)
            # La contrainte doit remonter jusqu'à la colonne, sinon elle
            # reste large comme le veut la fenêtre et le contenu se rogne.
            self.colonne.setMinimumWidth(besoin + 6)
            self.colonne.setMaximumWidth(besoin + 60)

    def _onglet_change(self, index):
        """Lit les conditions à la PREMIÈRE ouverture de l'onglet Outil.

        Le vidage TC2009,5 coûte plusieurs secondes et laisse la machine
        muette derrière lui. Le faire au démarrage, c'était le faire même
        quand on vient seulement tracer un dessin.
        """
        if self._conditions_lues or self.onglets.tabText(index) != "Outil":
            return
        self._conditions_lues = True
        self._resumer_conditions()

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
        retenus = self._retenus()
        if not retenus:
            # Un rôle sans aucun tracé — « découper » sur un fichier qui
            # n'a pas de rouge. Le recadrage calcule une emprise, et une
            # emprise de rien n'existe pas : sortir avant.
            return []
        p = noyau.tourner(retenus,
                          int(self.cmb_rot.currentText().rstrip("°")))
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
        if getattr(self, "_silence", False):
            return
        self.media = (self.spn_mx.value(), self.spn_my.value())
        if not self.brut:
            self.apercu.poser([], self.media, False)
            return
        self.calcule = self._pipeline()
        if not self.calcule:
            # Un rôle sans aucun tracé : « découper » sur un fichier qui
            # n'a pas de rouge. Rien à montrer, et surtout rien à envoyer.
            self.contour = []
            self.apercu.poser([], self.media, False)
            self.lbl_roles.setText(
                f"aucun tracé pour « {self.cmb_travail.currentText()} » — "
                f"rien ne partira au traceur")
            self.b_envoyer.setEnabled(False)
            self.info.setText("aucun tracé pour ce travail")
            return
        self.contour = []
        if self.chk_contour.isChecked():
            try:
                self.contour = contour.contour(
                    self.calcule, self.spn_retrait.value(),
                    trous=self.chk_trous.isChecked())
                self.lbl_contour.setText(
                    f"{len(self.contour)} contour(s), "
                    f"{contour.longueur(self.contour):.0f} mm de coupe à "
                    f"{self.spn_retrait.value():g} mm du dessin. "
                    f"C'est LUI qui part au traceur, pas le motif.")
            except Exception as e:
                self.lbl_contour.setText(f"contour impossible : {e}")
        else:
            self.lbl_contour.setText("inactif")

        if self.couleurs and len(self.couleurs) == len(self.brut):
            par_role = roles_couleur.classer(
                self.brut, self.couleurs, self.correspondance, self.reperes)
            resume = ", ".join(f"{len(v)} à {roles_couleur.LIBELLES[k].split(' ')[0]}"
                               for k, v in par_role.items() if v)
            envoyes = len(self._retenus())
            self.lbl_roles.setText(
                f"{resume}. {envoyes} tracé(s) partiront au traceur."
                + (f" {len(self.reperes)} repère(s) ARMS reconnu(s) et "
                   f"écarté(s)." if self.reperes else ""))
        x0, y0, x1, y1 = noyau.cadre(self.calcule + self.contour)
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

        # Le rôle de chaque tracé, dans le même ordre que les polylignes.
        # L'appariement se fait par l'ORDRE et non par l'identité des
        # objets : le pipeline reconstruit les listes de points à chaque
        # étape, donc les identités ne survivent pas. `dupliquer` recopie
        # le lot entier, d'où la répétition.
        base = getattr(self, "_roles_retenus", []) or \
            ["tracer"] * len(self.brut)
        copies = max(1, self.spn_rang.value()) * max(1, self.spn_col.value())
        roles_traces = base * copies
        if len(roles_traces) != len(self.calcule):
            roles_traces = ["tracer"] * len(self.calcule)
        roles_traces = roles_traces + ["contour"] * len(self.contour)

        self.apercu.poser(self.calcule + self.contour, self.media, deborde,
                          [p[2] for p in panneaux], roles_traces)

        n = len(self.calcule)
        texte = (f"{n} tracé(s) — emprise {x1 - x0:.1f} × {y1 - y0:.1f} mm, "
                 f"coin à {x0:.1f}, {y0:.1f}")
        if panneaux:
            texte += f"  —  {len(panneaux)} panneaux"
        if deborde:
            texte += ("  —  UN PANNEAU DÉBORDE" if panneaux
                      else "  —  LE DESSIN DÉBORDE DE LA ZONE UTILE")
        presents = []
        for role, mot in (("tracer", "tracé"), ("rainer", "rainage"),
                          ("decouper", "découpe"), ("contour", "contour")):
            if role in roles_traces:
                presents.append(mot)
        if len(presents) > 1:
            texte += "  —  " + " · ".join(presents)
        self.info.setText(texte)
        # Un message d'alerte doit aussi en avoir la couleur : un texte
        # rouge sous un style neutre ne se lit pas comme un refus.
        self.info.setObjectName("alerte" if deborde else "faible")
        self.info.setStyleSheet(feuille_de_style(self.pal))
        self.b_envoyer.setEnabled(bool(self.brut) and not deborde)

    def _envoyer(self):
        # Le dessin a-t-il bougé depuis que la feuille a été imprimée ?
        # Rien ne le signalait le 13/08/2026, et la manche y est passée :
        # l'écart mesuré ensuite mêlait deux causes et ne disait rien.
        if self.chk_arms.isChecked() and fichier_projet.a_bouge_depuis_export(
                self._lire_reglages(), self.empreinte_export):
            suite = QMessageBox.warning(
                self, "Le dessin a bougé",
                "Le placement a changé depuis que la feuille a été "
                "exportée.\n\nLes repères disent où était le dessin au "
                "moment de l'export, pas où il est maintenant : la "
                "découpe ne retombera pas sur l'impression.\n\n"
                "Envoyer quand même ?",
                QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
            if suite != QMessageBox.Ok:
                return

        # La correction mesurée : elle ne touche QUE ce qui part au
        # traceur. L'appliquer au pipeline déplacerait aussi la feuille à
        # imprimer, donc corrigerait un écart en le recréant.
        cav, cch = self.spn_corr_av.value(), self.spn_corr_ch.value()

        def corriger(polylignes):
            if not (cav or cch) or not self.chk_arms.isChecked():
                return polylignes
            return [([(x + cav, y + cch) for x, y in pts], f)
                    for pts, f in polylignes]

        # Le réordonnancement ne tourne qu'ici : il est en n², donc trop
        # lourd à rejouer à chaque mouvement d'un réglage, et il ne change
        # rien à ce que l'aperçu montre.
        condition = self.cmb_cond.currentIndex() + 1
        panneaux = self._panneaux()

        # Un travail est une LISTE d'envois : un seul d'ordinaire, autant que
        # de panneaux en mosaïque. Le reste du code ne fait pas la
        # différence, ce qui évite deux chemins parallèles à maintenir.
        if panneaux:
            lots = [(f"panneau {n}/{len(panneaux)}", corriger(m))
                    for n, (_i, _j, _r, m) in enumerate(panneaux, 1)]
        else:
            # Ce qui part au traceur : le contour SEUL quand il est demandé.
            # Découper aussi le motif trancherait l'autocollant en deux.
            lots = [("", corriger(self.contour if self.contour
                                  else self.calcule))]

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
                                    self.spn_passages.value(),
                                    self.chk_arms.isChecked())
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
                d = int(round(self.spn_debord.value() * 200))
                conditions.regler(fd, conditions.DEBORDEMENT, f"{d},{d}",
                                  condition=condition)
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
