#!/usr/bin/env python3
"""Prépare une planche TechDraw pour le traçage au stylo — sans Inkscape.

Trois traitements, dans cet ordre :

1. retire les **commentaires XML** — TechDraw en écrit quatre par planche
   (« Working space », « Title block »…) ; l'extension Texte Hershey
   d'Inkscape plantait dessus, et un flux sans commentaire ne gêne
   personne d'autre ;
2. **vectorise les `<text>` restants en OSIFONT**, la police même que
   TechDraw met dans ses cotes à l'export. Une planche exportée vectorise
   ses cotes mais recopie le cartouche et les annotations en `<text>`,
   que `svg2hpgl` ignore. Graisse NORMALE pour tout le monde, y compris
   les champs déclarés gras : au stylo, un titre gras sortait en lettres
   creuses (Christophe, 25/08/2026 : « la même police que dans les
   cotations, comme cela pas de soucis ») ;
3. convertit `<rect>`, `<circle>`, `<ellipse>`, `<line>`, `<polyline>`
   et `<polygon>` en `<path>` — le parseur de `svg2hpgl` ne lit que les
   chemins (tableaux de débit : 430 `<rect>` sur Plan_Debit).

Après quoi la chaîne est directe :

    python3 preparer_planche.py planche.svg
    python3 svg2hpgl.py planche_propre.svg …

Chaque remplacement se fait DANS le parent de l'élément remplacé, en
coordonnées locales : les transforms des groupes s'appliquent aux chemins
comme ils s'appliquaient au texte. C'est ce qui immunise contre le piège
documenté du README — les champs du cartouche vivent hors du groupe
`DrawingContent`, et l'extension Hershey, qui raisonnait globalement,
les rendait dix fois trop grands.

La police est EMBARQUÉE (`resources/osifont-lgpl3fe.ttf`, LGPL v3 avec
« font exception », licence jointe) : la planche entière porte un seul
dessin de lettre, même sur une machine sans FreeCAD.

Rien ne disparaît en silence : les glyphes absents de la police sont
NOMMÉS sur la console et remplacés par une avance d'un demi-cadratin.
"""

import argparse
import os
import re
import sys

try:
    from lxml import etree
except ImportError:                                     # pragma: no cover
    sys.exit("lxml requis : pacman -S python-lxml")

try:
    from fontTools.misc.transform import Transform
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
except ImportError:                                     # pragma: no cover
    sys.exit("fontTools requis : pacman -S python-fonttools")

ICI = os.path.dirname(os.path.abspath(__file__))
POLICE = os.path.join(ICI, "resources", "osifont-lgpl3fe.ttf")
SVG = "http://www.w3.org/2000/svg"
# Trait des lettres vectorisées : fin — c'est le stylo qui donne la largeur.
TRAIT_LETTRE = "0.18"
# Cercle par 4 cubiques : la constante classique.
_K = 0.5522847498307936


# =============================================================================
#  La police des cotes, vectorisée
# =============================================================================

class Osifont(object):
    """Texte -> chemin SVG en osifont, coordonnées ABSOLUES du repère local.

    fontTools fournit le contour de chaque glyphe ; `TransformPen` le
    bascule (l'axe Y des polices monte, celui du SVG descend), le met à
    l'échelle et le pose sur la ligne de base. Aucun attribut transform
    n'est émis : n'importe quel consommateur lit des nombres finis.
    """

    def __init__(self, chemin=POLICE):
        self.fonte = TTFont(chemin)
        self.upm = float(self.fonte["head"].unitsPerEm)
        self.cmap = self.fonte.getBestCmap()
        self.glyphes = self.fonte.getGlyphSet()
        self.manquants = {}

    def _avance(self, nom):
        return self.glyphes[nom].width

    def largeur(self, texte, taille):
        """Largeur d'encombrement, pour text-anchor middle/end."""
        ech = taille / self.upm
        total = 0.0
        for c in texte:
            nom = self.cmap.get(ord(c))
            total += self._avance(nom) if nom else self.upm / 2.0
        return total * ech

    def chemin(self, texte, x, y, taille):
        """(d, avance_mm) du texte posé en (x, y) — baseline comprise."""
        ech = taille / self.upm
        morceaux, avance = [], 0.0
        for c in texte:
            nom = self.cmap.get(ord(c))
            if nom is None:
                self.manquants[c] = self.manquants.get(c, 0) + 1
                avance += self.upm / 2.0
                continue
            stylo = SVGPathPen(self.glyphes)
            self.glyphes[nom].draw(TransformPen(
                stylo, Transform(ech, 0, 0, -ech, x + avance * ech, y)))
            d = stylo.getCommands()
            if d:
                morceaux.append(d)
            avance += self._avance(nom)
        return " ".join(morceaux), avance * ech


# =============================================================================
#  Lecture des propriétés héritées (attribut OU style, ancêtres compris)
# =============================================================================

def _style_de(el):
    d = {}
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            cle, val = part.split(":", 1)
            d[cle.strip()] = val.strip()
    return d


def _propriete(el, nom, defaut=None):
    while el is not None:
        val = el.get(nom) or _style_de(el).get(nom)
        if val:
            return val
        el = el.getparent()
    return defaut


def _taille(el):
    """font-size en unités LOCALES (TechDraw écrit des px = unités)."""
    brut = _propriete(el, "font-size", "4")
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*(px)?\s*$", brut)
    if not m:
        print(f"  font-size inhabituel « {brut} » : 4 retenu", file=sys.stderr)
        return 4.0
    return float(m.group(1))


def _nombre(el, nom, defaut=0.0):
    try:
        return float(el.get(nom, defaut))
    except (TypeError, ValueError):
        return float(defaut)


def _dans_defs(el):
    while el is not None:
        if el.tag == f"{{{SVG}}}defs":
            return True
        el = el.getparent()
    return False


def _invisible(el):
    return _style_de(el).get("display") == "none" or el.get("display") == "none"


# =============================================================================
#  <text> -> chemins osifont
# =============================================================================

def _runs_du_texte(el):
    """[(texte, x, y)] : le contenu direct, puis chaque tspan.

    Un tspan sans x/y propres continue sur la ligne de base courante ;
    l'appelant avance le curseur d'un run à l'autre.
    """
    runs = []
    x, y = _nombre(el, "x"), _nombre(el, "y")
    if (el.text or "").strip():
        runs.append([el.text, x, y, False])
    for ts in el.findall(f"{{{SVG}}}tspan"):
        propre = ts.get("x") is not None or ts.get("y") is not None
        tx = _nombre(ts, "x", x) if ts.get("x") is not None else None
        ty = _nombre(ts, "y", y) if ts.get("y") is not None else None
        if (ts.text or "").strip():
            runs.append([ts.text, tx, ty, propre])
    return runs


def vectoriser_textes(racine, fonte):
    """Remplace chaque <text> visible par ses lettres en chemins. Rend n."""
    faits = 0
    for el in list(racine.iter(f"{{{SVG}}}text")):
        if _dans_defs(el) or _invisible(el):
            continue
        taille = _taille(el)
        ancre = _propriete(el, "text-anchor", "start")
        parent = el.getparent()
        index = list(parent).index(el)
        cx, cy = _nombre(el, "x"), _nombre(el, "y")
        poses = 0
        for texte, tx, ty, propre in _runs_du_texte(el):
            x = tx if tx is not None else cx
            y = ty if ty is not None else cy
            if ancre in ("middle", "end"):
                larg = fonte.largeur(texte, taille)
                x -= larg / 2.0 if ancre == "middle" else larg
            d, avance = fonte.chemin(texte, x, y, taille)
            cx, cy = x + avance, y
            if not d:
                continue
            chemin = etree.SubElement(parent, f"{{{SVG}}}path")
            chemin.set("d", d)
            chemin.set("fill", "none")
            chemin.set("stroke", "#000000")
            chemin.set("stroke-width", TRAIT_LETTRE)
            if el.get("transform"):
                chemin.set("transform", el.get("transform"))
            parent.remove(chemin)
            parent.insert(index, chemin)
            index += 1
            poses += 1
        parent.remove(el)
        faits += 1 if poses else 0
    return faits


# =============================================================================
#  Formes simples -> <path>
# =============================================================================

def _d_rect(el):
    x, y = _nombre(el, "x"), _nombre(el, "y")
    w, h = _nombre(el, "width"), _nombre(el, "height")
    if w <= 0 or h <= 0:
        return None
    rx = _nombre(el, "rx") or _nombre(el, "ry")
    rx = min(rx, w / 2.0, h / 2.0)
    if rx <= 0:
        return (f"M {x:.4f} {y:.4f} L {x + w:.4f} {y:.4f} "
                f"L {x + w:.4f} {y + h:.4f} L {x:.4f} {y + h:.4f} Z")
    k = rx * (1.0 - _K)
    return (f"M {x + rx:.4f} {y:.4f} L {x + w - rx:.4f} {y:.4f} "
            f"C {x + w - k:.4f} {y:.4f} {x + w:.4f} {y + k:.4f} {x + w:.4f} {y + rx:.4f} "
            f"L {x + w:.4f} {y + h - rx:.4f} "
            f"C {x + w:.4f} {y + h - k:.4f} {x + w - k:.4f} {y + h:.4f} {x + w - rx:.4f} {y + h:.4f} "
            f"L {x + rx:.4f} {y + h:.4f} "
            f"C {x + k:.4f} {y + h:.4f} {x:.4f} {y + h - k:.4f} {x:.4f} {y + h - rx:.4f} "
            f"L {x:.4f} {y + rx:.4f} "
            f"C {x:.4f} {y + k:.4f} {x + k:.4f} {y:.4f} {x + rx:.4f} {y:.4f} Z")


def _d_ellipse(cx, cy, rx, ry):
    if rx <= 0 or ry <= 0:
        return None
    kx, ky = rx * _K, ry * _K
    return (f"M {cx + rx:.4f} {cy:.4f} "
            f"C {cx + rx:.4f} {cy + ky:.4f} {cx + kx:.4f} {cy + ry:.4f} {cx:.4f} {cy + ry:.4f} "
            f"C {cx - kx:.4f} {cy + ry:.4f} {cx - rx:.4f} {cy + ky:.4f} {cx - rx:.4f} {cy:.4f} "
            f"C {cx - rx:.4f} {cy - ky:.4f} {cx - kx:.4f} {cy - ry:.4f} {cx:.4f} {cy - ry:.4f} "
            f"C {cx + kx:.4f} {cy - ry:.4f} {cx + rx:.4f} {cy - ky:.4f} {cx + rx:.4f} {cy:.4f} Z")


def _d_points(el, fermer):
    brut = (el.get("points") or "").replace(",", " ").split()
    if len(brut) < 4:
        return None
    xs = [float(v) for v in brut]
    pts = list(zip(xs[0::2], xs[1::2]))
    d = "M " + " L ".join(f"{x:.4f} {y:.4f}" for x, y in pts)
    return d + (" Z" if fermer else "")


_GEOMETRIE = {"x", "y", "width", "height", "rx", "ry", "cx", "cy", "r",
              "x1", "y1", "x2", "y2", "points", "d"}


def convertir_formes(racine):
    """<rect|circle|ellipse|line|polyline|polygon> -> <path>. Rend n."""
    faits = 0
    for tag in ("rect", "circle", "ellipse", "line", "polyline", "polygon"):
        for el in list(racine.iter(f"{{{SVG}}}{tag}")):
            if _dans_defs(el) or _invisible(el):
                continue
            if tag == "rect":
                d = _d_rect(el)
            elif tag == "circle":
                r = _nombre(el, "r")
                d = _d_ellipse(_nombre(el, "cx"), _nombre(el, "cy"), r, r)
            elif tag == "ellipse":
                d = _d_ellipse(_nombre(el, "cx"), _nombre(el, "cy"),
                               _nombre(el, "rx"), _nombre(el, "ry"))
            elif tag == "line":
                d = (f"M {_nombre(el, 'x1'):.4f} {_nombre(el, 'y1'):.4f} "
                     f"L {_nombre(el, 'x2'):.4f} {_nombre(el, 'y2'):.4f}")
            else:
                d = _d_points(el, fermer=(tag == "polygon"))
            if not d:
                el.getparent().remove(el)
                continue
            chemin = etree.Element(f"{{{SVG}}}path")
            for cle, val in el.attrib.items():
                if cle not in _GEOMETRIE:
                    chemin.set(cle, val)
            chemin.set("d", d)
            parent = el.getparent()
            parent.insert(list(parent).index(el), chemin)
            parent.remove(el)
            faits += 1
    return faits


# =============================================================================
#  Le traitement complet
# =============================================================================

def nettoyer(source, destination, fonte=None):
    """Commentaires retirés, textes en osifont, formes en chemins.

    Rend (commentaires, textes, formes). `fonte` se partage entre
    planches pour ne charger la TTF qu'une fois.
    """
    arbre = etree.parse(source, etree.XMLParser(remove_comments=False))
    commentaires = len(arbre.getroot().xpath("//comment()"))
    arbre = etree.parse(source, etree.XMLParser(remove_comments=True))
    racine = arbre.getroot()
    fonte = fonte or Osifont()
    textes = vectoriser_textes(racine, fonte)
    formes = convertir_formes(racine)
    arbre.write(destination, xml_declaration=True,
                encoding="utf-8", pretty_print=False)
    return commentaires, textes, formes


def main():
    ap = argparse.ArgumentParser(
        description="Prépare une planche TechDraw pour svg2hpgl : retire les "
                    "commentaires XML, vectorise les <text> en osifont (la "
                    "police des cotes), convertit les formes simples en "
                    "<path>. Plus besoin d'Inkscape.")
    ap.add_argument("svg", nargs="+", help="planche(s) exportée(s) de TechDraw")
    ap.add_argument("-o", "--sortie",
                    help="fichier de sortie (une seule planche) ; par défaut "
                         "un suffixe _propre à côté de l'original")
    args = ap.parse_args()

    if args.sortie and len(args.svg) > 1:
        sys.exit("--sortie ne vaut que pour une seule planche")

    fonte = Osifont()
    for source in args.svg:
        if not os.path.exists(source):
            print(f"  absent : {source}", file=sys.stderr)
            continue
        racine, ext = os.path.splitext(source)
        destination = args.sortie or f"{racine}_propre{ext}"
        com, txt, formes = nettoyer(source, destination, fonte)
        print(f"{os.path.basename(source)} -> {os.path.basename(destination)}"
              f"   ({com} commentaire(s), {txt} texte(s) en osifont,"
              f" {formes} forme(s) en chemins)")
    if fonte.manquants:
        detail = ", ".join(f"« {c} » x{n}" for c, n in sorted(fonte.manquants.items()))
        print(f"  ATTENTION — glyphes absents d'osifont, remplacés par un blanc :"
              f" {detail}", file=sys.stderr)


if __name__ == "__main__":
    main()
