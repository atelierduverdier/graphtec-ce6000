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

from PySide6.QtCore import Qt, QPointF, QRectF               # noqa: E402
from PySide6.QtGui import QPainter, QPen, QColor, QPolygonF  # noqa: E402
from PySide6.QtWidgets import (                              # noqa: E402
    QApplication, QWidget, QLabel, QPushButton, QSpinBox, QDoubleSpinBox,
    QComboBox, QCheckBox, QGridLayout, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFileDialog, QMessageBox, QSizePolicy)


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

        principal = QHBoxLayout(self)
        principal.addWidget(self._colonne_reglages(), 0)
        droite = QVBoxLayout()
        droite.addWidget(self.apercu, 1)
        droite.addWidget(self.info, 0)
        principal.addLayout(droite, 1)

        self._habiller()
        self._interroger_media(silencieux=True)

    def _habiller(self):
        self.setStyleSheet(feuille_de_style(self.pal))
        self.apercu.habiller(self.pal)

    def _basculer_theme(self):
        self.pal = CLAIR if self.pal is SOMBRE else SOMBRE
        self.b_theme.setText("Thème clair" if self.pal is SOMBRE
                             else "Thème sombre")
        self._habiller()

    # ---------------------------------------------------------------- UI
    def _colonne_reglages(self):
        boite = QWidget()
        boite.setFixedWidth(320)
        v = QVBoxLayout(boite)

        b_ouvrir = QPushButton("Ouvrir un SVG…")
        b_ouvrir.clicked.connect(self._ouvrir)
        v.addWidget(b_ouvrir)
        self.lbl_fichier = QLabel("—")
        self.lbl_fichier.setWordWrap(True)
        v.addWidget(self.lbl_fichier)

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
        v.addWidget(g)

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
        v.addWidget(g)

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
        v.addWidget(g)

        # --- outil
        g = QGroupBox("Outil")
        gl = QGridLayout(g)
        self.cmb_cond = QComboBox()
        self.cmb_cond.addItems([f"condition {i}" for i in range(1, 9)])
        self.spn_force = self._entier(1, 38, 12)
        # La vitesse passe par le protocole propriétaire TC : le `VS` du
        # HP-GL est ignoré par cette machine. Elle MODIFIE DURABLEMENT la
        # condition enregistrée, comme le fait le logiciel Graphtec.
        self.spn_vit = self._entier(1, 64, 10, suffixe=" cm/s")
        # L'accélération n'a que TROIS crans sur cette machine : demander 4
        # est écrêté à 3 sans un mot. La borne est dans conditions.BORNES.
        self.spn_accel = self._entier(1, 3, 2)
        self.chk_regler = QCheckBox("régler la machine à l'envoi")
        self.chk_regler.setChecked(True)
        gl.addWidget(QLabel("condition"), 0, 0); gl.addWidget(self.cmb_cond, 0, 1)
        gl.addWidget(QLabel("vitesse"), 1, 0); gl.addWidget(self.spn_vit, 1, 1)
        gl.addWidget(QLabel("force"), 2, 0); gl.addWidget(self.spn_force, 2, 1)
        gl.addWidget(QLabel("accélération"), 3, 0); gl.addWidget(self.spn_accel, 3, 1)
        gl.addWidget(self.chk_regler, 4, 0, 1, 2)
        rappel = QLabel("accélération basse = trait net,\nhaute = travail plus court")
        rappel.setObjectName("faible")
        gl.addWidget(rappel, 5, 0, 1, 2)
        v.addWidget(g)

        self.b_envoyer = QPushButton("Envoyer au traceur")
        self.b_envoyer.setObjectName("principal")
        self.b_envoyer.setEnabled(False)
        self.b_envoyer.clicked.connect(self._envoyer)
        v.addWidget(self.b_envoyer)

        self.b_theme = QPushButton("Thème clair")
        self.b_theme.clicked.connect(self._basculer_theme)
        v.addWidget(self.b_theme)
        v.addStretch(1)
        return boite

    def _reel(self, mini, maxi, val, suffixe=" mm"):
        s = QDoubleSpinBox()
        s.setRange(mini, maxi); s.setDecimals(1); s.setValue(val)
        s.setSuffix(suffixe)
        s.valueChanged.connect(self._recalculer)
        return s

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
        elif not silencieux:
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
        programme, _ = noyau.en_hpgl(chemins, condition, self.spn_force.value())

        regle = ""
        try:
            if self.chk_regler.isChecked():
                import conditions
                rendu = conditions.appliquer(vitesse=self.spn_vit.value(),
                                             acceleration=self.spn_accel.value(),
                                             condition=condition)
                douteux = [n for n, _, e in rendu if e != "0"]
                regle = (f"condition {condition} réglée à "
                         f"{self.spn_vit.value()} cm/s, accél. "
                         f"{self.spn_accel.value()}"
                         + (f" (états douteux : {douteux})" if douteux else "")
                         + " — ")
            envoye = noyau.envoyer(programme)
        except Exception as e:
            QMessageBox.critical(self, "Envoi impossible", str(e))
            return
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
