#!/usr/bin/env python3
"""Prépare une planche TechDraw pour le traçage au stylo — sans Inkscape.

Cinq traitements, dans cet ordre :

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
   chemins (tableaux de débit : 430 `<rect>` sur Plan_Debit) ;
4. **retire les cachés confondus** : TechDraw exporte le contour d'une
   pièce deux fois, arête visible et arête cachée superposées. À l'écran
   le tireté disparaît sous le plein ; à la plume, le traceur repassait
   dessus pour rien ;
5. **découpe les traits interrompus en VRAIS segments**. `stroke-dasharray`
   est un style, et `svg2hpgl` lit la géométrie : les lignes cachées de
   TechDraw sortaient en trait CONTINU à la plume, indiscernables d'une
   arête réelle sur une planche d'atelier.

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

`--police hershey` (ou toute clé de `--liste-polices`) vectorise plutôt
en MONOTRAIT, avec les polices de LaserAtelier : une passe de plume par
branche de lettre — pour les planches à grands titres, qu'osifont sort
en lettres creuses.

Rien ne disparaît en silence : les glyphes absents de la police sont
NOMMÉS sur la console et remplacés par une avance d'un demi-cadratin.
"""

import argparse
import math
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
# Le parseur de chemins de LaserAtelier : il aplatit courbes et arcs en
# polylignes, ce qu'il faut pour decouper un pointille. Pas de second
# tokeniseur maison — c'est deja celui que svg2hpgl emprunte.
_ATELIER = os.path.expanduser("~/.local/share/FreeCAD/v1-1/Mod/LaserAtelier")
if _ATELIER not in sys.path:
    sys.path.insert(0, _ATELIER)
try:
    import svg_import
except ImportError:                                     # pragma: no cover
    sys.exit(f"svg_import.py introuvable dans {_ATELIER}")
POLICE = os.path.join(ICI, "resources", "osifont-lgpl3fe.ttf")
CHEMIN_ATELIER = os.path.expanduser(
    "~/.local/share/FreeCAD/v1-1/Mod/LaserAtelier")
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
#  Les polices monotrait de LaserAtelier (--police hershey)
# =============================================================================

# Repli typographique minimal — la version complète (deplier_texte) vit dans
# laser_core, qui tire FreeCAD ; ici on reste autonome. Ce qui manque encore
# après repli est NOMMÉ sur la console, jamais avalé.
REPLIS = {"œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE", "ß": "ss",
          "’": "'", "‘": "'", "“": '"', "”": '"', "…": "...",
          " ": " ", " ": " ", "—": "-", "–": "-"}


class Hershey(object):
    """Texte -> chemins MONOTRAIT, mêmes appels que `Osifont`.

    Les polices sont les modules de données de LaserAtelier
    (`polices_monotrait/hershey_font[_clé].py` : GLYPHES, CAP_HEIGHT,
    ADV_DEFAULT ; ligne de base à y = 0, Y vers le HAUT). Chaque lettre est
    l'axe du trait : au stylo, une passe par branche — les grands titres ne
    sortent plus en lettres creuses. L'échelle est calée pour qu'une
    capitale ait la même hauteur qu'en osifont à la même font-size.

    Éviter les variantes Med/Bold : leur fût est CONTOURNÉ, la plume passe
    deux fois (c'est étiqueté ainsi dans LaserAtelier).
    """

    RAPPORT_CAPITALE = 0.72     # capitale/em d'osifont, mesuré sur la TTF

    def __init__(self, cle="sans"):
        if CHEMIN_ATELIER not in sys.path:
            sys.path.insert(0, CHEMIN_ATELIER)
        nom = "polices_monotrait.hershey_font" + ("" if cle in ("", "sans")
                                                  else "_" + cle)
        try:
            import importlib
            self.hf = importlib.import_module(nom)
        except ImportError:
            sys.exit(f"police monotrait « {cle} » introuvable ({nom}) — "
                     f"--liste-polices donne les clés, LaserAtelier attendu "
                     f"dans {CHEMIN_ATELIER}")
        try:
            fonte = TTFont(POLICE)
            self.RAPPORT_CAPITALE = (fonte["OS/2"].sCapHeight
                                     / float(fonte["head"].unitsPerEm))
        except Exception:
            pass                                # 0.72 reste une bonne mesure
        self.manquants = {}

    def _glyphe(self, c):
        g = self.hf.GLYPHES.get(c)
        if g is None and c in REPLIS:
            morceaux = [self._glyphe(r) for r in REPLIS[c]]
            if all(m is not None for m in morceaux):
                avance = sum(m[0] for m in morceaux)
                traits, x = [], 0.0
                for m in morceaux:
                    traits += [[(px + x, py) for px, py in t] for t in m[1]]
                    x += m[0]
                return (avance, traits)
            return None
        return g

    def _echelle(self, taille):
        return taille * self.RAPPORT_CAPITALE / float(self.hf.CAP_HEIGHT)

    def largeur(self, texte, taille):
        ech = self._echelle(taille)
        total = 0.0
        for c in texte:
            g = self._glyphe(c)
            total += g[0] if g else self.hf.ADV_DEFAULT
        return total * ech

    def chemin(self, texte, x, y, taille):
        """(d, avance_mm) — baseline en (x, y), l'axe Y du SVG descend."""
        ech = self._echelle(taille)
        morceaux, avance = [], 0.0
        for c in texte:
            g = self._glyphe(c)
            if g is None:
                self.manquants[c] = self.manquants.get(c, 0) + 1
                avance += self.hf.ADV_DEFAULT
                continue
            for trait in g[1]:
                if len(trait) < 2:
                    continue
                pts = [(x + (avance + px) * ech, y - py * ech)
                       for px, py in trait]
                morceaux.append("M " + " L ".join(
                    f"{px:.4f} {py:.4f}" for px, py in pts))
            avance += g[0]
        return " ".join(morceaux), avance * ech


def charger_police(nom):
    """« osifont » (défaut), « hershey » (= sans), ou une clé monotrait."""
    if nom in ("", None, "osifont"):
        return Osifont()
    return Hershey("sans" if nom == "hershey" else nom)


def lister_polices():
    import glob as _glob
    cles = ["osifont (défaut — la police des cotes, à contours)",
            "hershey (= sans)"]
    for f in sorted(_glob.glob(os.path.join(
            CHEMIN_ATELIER, "polices_monotrait", "hershey_font_*.py"))):
        cles.append(os.path.basename(f)[len("hershey_font_"):-3])
    return cles


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


def _ne_peint_rien(el):
    """Forme sans trait NI remplissage : elle ne se voit pas, elle ne doit
    pas se tracer non plus.

    Le gabarit de l'atelier pose un `<rect>` de page entier en
    `fill:none;stroke:none` — converti sans discernement, il devenait un
    rectangle de 210 x 297 tracé à la plume, hors surface utile.
    """
    trait = _propriete(el, "stroke", "none")
    fond = _propriete(el, "fill", "none")
    return trait in ("none", "") and fond in ("none", "")


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


# =============================================================================
#  Les traits interrompus, decoupes en VRAIS segments
# =============================================================================

def _motif(valeur):
    """« 30,7.5 » -> [30.0, 7.5]. None si le motif ne pointille rien."""
    if not valeur or valeur.strip() in ("none", "0"):
        return None
    bouts = [float(v) for v in re.split(r"[,\s]+", valeur.strip()) if v]
    bouts = [abs(v) for v in bouts if _est_nombre(v)]
    if not bouts or sum(bouts) <= 0:
        return None
    # Un motif impair se parcourt deux fois (regle SVG) : 5 -> plein 5, vide 5.
    return bouts if len(bouts) % 2 == 0 else bouts * 2


def _est_nombre(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _pointiller(points, motif, decalage=0.0):
    """Decoupe une polyligne selon `motif`. Rend une liste de polylignes.

    On avance le long du trace en alternant plein et vide, exactement comme
    le fait un rendu SVG — mais en GEOMETRIE, pas en style : c'est la seule
    forme qu'un traceur comprenne.
    """
    if len(points) < 2:
        return []
    total = sum(motif)
    pos = decalage % total
    i, plein = 0, True
    while pos >= motif[i]:                  # ou en est-on dans le motif ?
        pos -= motif[i]
        i = (i + 1) % len(motif)
        plein = not plein
    reste = motif[i] - pos

    morceaux, courant = [], ([points[0]] if plein else [])
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        seg = math.hypot(dx, dy)
        parcouru = 0.0
        while seg - parcouru > reste:
            parcouru += reste
            t = parcouru / seg
            coupe = (a[0] + dx * t, a[1] + dy * t)
            if plein:
                courant.append(coupe)
                morceaux.append(courant)
                courant = []
            else:
                courant = [coupe]
            plein = not plein
            i = (i + 1) % len(motif)
            reste = motif[i]
        reste -= seg - parcouru
        if plein:
            courant.append(b)
    if plein and len(courant) >= 2:
        morceaux.append(courant)
    return [m for m in morceaux if len(m) >= 2]


def _d_polylignes(polylignes):
    return " ".join("M " + " L ".join("%.4f %.4f" % (x, y) for x, y in p)
                    for p in polylignes)


def _transform_cumule(el):
    """Matrice du repere de `el` vers celui de la racine.

    Les transforms s'empilent de la racine vers la feuille : on remonte,
    puis on compose dans l'ordre parent · enfant (matrix_mul applique le
    second d'abord).
    """
    chaine = []
    cur = el
    while cur is not None:
        t = cur.get("transform")
        if t:
            chaine.append(svg_import.parse_transform(t))
        cur = cur.getparent()
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for t in reversed(chaine):          # de la racine vers la feuille
        m = svg_import.matrix_mul(m, t)
    return m


def _signature(points, tol):
    """Empreinte d'une polyligne, INDEPENDANTE du sens de parcours.

    TechDraw exporte la meme arete a l'endroit dans les visibles et a
    l'envers dans les cachees — sans cela, la moitie des doublons
    passerait au travers.
    """
    q = tuple((round(x / tol), round(y / tol)) for x, y in points)
    return min(q, q[::-1])


def retirer_caches_confondus(racine, tol=0.02):
    """Supprime les traces POINTILLES confondus avec un trace PLEIN.

    TechDraw exporte le contour d'une piece DEUX fois : une fois en arete
    visible, une fois en arete cachee (la face arriere se projette au meme
    endroit). A l'ecran le tirete disparait sous le plein ; a la plume, le
    traceur repasse dessus pour rien — 640 mm sur la seule traverse.

    On ne retire que si TOUS les sous-traces du pointille sont confondus :
    un recouvrement partiel garde l'information.

    A LANCER AVANT `pointiller_traits` : apres decoupe, la geometrie du
    pointille n'est plus celle du plein et plus rien ne se ressemble.
    """
    pleins = set()
    dashes = []
    for el in list(racine.iter(f"{{{SVG}}}path")):
        if _dans_defs(el) or _invisible(el) or not el.get("d"):
            continue
        sous, _a = svg_import.path_d_to_subpaths(el.get("d"), 0.05)
        m = _transform_cumule(el)
        polys = [[svg_import.matrix_apply(m, x, y) for x, y in sp["points"]]
                 for sp in sous if len(sp["points"]) >= 2]
        if not polys:
            continue
        if _motif(_propriete(el, "stroke-dasharray")):
            dashes.append((el, polys))
        else:
            for p in polys:
                pleins.add(_signature(p, tol))
    retires = 0
    for el, polys in dashes:
        if all(_signature(p, tol) in pleins for p in polys):
            el.getparent().remove(el)
            retires += 1
    return retires


def pointiller_traits(racine, tol=0.05):
    """Remplace la GEOMETRIE des traces pointilles par leurs segments.

    `stroke-dasharray` est un style : svg2hpgl lit la geometrie et ne le
    voit pas, donc une ligne cachee de TechDraw sortait en trait CONTINU
    a la plume — indiscernable d'une arete reelle sur une planche
    d'atelier (mesure du 26/08/2026 : 16 attributs de tirets ignores sur
    Planche4). Rend le nombre de traces convertis.
    """
    faits = 0
    for el in list(racine.iter(f"{{{SVG}}}path")):
        if _dans_defs(el) or _invisible(el):
            continue
        motif = _motif(_propriete(el, "stroke-dasharray"))
        if not motif:
            continue
        try:
            decalage = float(_propriete(el, "stroke-dashoffset", "0") or 0.0)
        except ValueError:
            decalage = 0.0
        sous, _avert = svg_import.path_d_to_subpaths(el.get("d", ""), tol)
        segments = []
        for sp in sous:
            segments.extend(_pointiller(list(sp["points"]), motif, decalage))
        if not segments:
            el.getparent().remove(el)
            faits += 1
            continue
        el.set("d", _d_polylignes(segments))
        # Le motif est desormais DANS le trace : le laisser actif le ferait
        # appliquer une SECONDE fois par un rendu SVG. Il vit le plus souvent
        # sur le <g> parent (TechDraw groupe ses aretes cachees), qu'on ne
        # peut pas vider tant qu'il porte d'autres enfants — on le neutralise
        # donc SUR LE CHEMIN, ou l'attribut de l'enfant l'emporte.
        el.set("stroke-dasharray", "none")
        el.set("stroke-dashoffset", "0")
        st = _style_de(el)
        if "stroke-dasharray" in st or "stroke-dashoffset" in st:
            st["stroke-dasharray"] = "none"
            st["stroke-dashoffset"] = "0"
            el.set("style", ";".join("%s:%s" % kv for kv in st.items()))
        faits += 1
    return faits


def convertir_formes(racine):
    """<rect|circle|ellipse|line|polyline|polygon> -> <path>. Rend n."""
    faits = 0
    for tag in ("rect", "circle", "ellipse", "line", "polyline", "polygon"):
        for el in list(racine.iter(f"{{{SVG}}}{tag}")):
            if _dans_defs(el) or _invisible(el):
                continue
            if _ne_peint_rien(el):
                el.getparent().remove(el)
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

    Rend (commentaires, textes, formes, pointilles, doublons). `fonte` se
    partage entre planches pour ne charger la TTF qu'une fois.
    """
    arbre = etree.parse(source, etree.XMLParser(remove_comments=False))
    commentaires = len(arbre.getroot().xpath("//comment()"))
    arbre = etree.parse(source, etree.XMLParser(remove_comments=True))
    racine = arbre.getroot()
    fonte = fonte or Osifont()
    textes = vectoriser_textes(racine, fonte)
    formes = convertir_formes(racine)
    doublons = retirer_caches_confondus(racine)
    pointilles = pointiller_traits(racine)
    arbre.write(destination, xml_declaration=True,
                encoding="utf-8", pretty_print=False)
    return commentaires, textes, formes, pointilles, doublons


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
    ap.add_argument("--police", default="osifont",
                    help="police des textes vectorisés : « osifont » (défaut, "
                         "la police des cotes, à contours — les grands titres "
                         "sortent en lettres creuses) ou une police MONOTRAIT "
                         "de LaserAtelier : « hershey » (= sans), ou une clé "
                         "de --liste-polices")
    ap.add_argument("--liste-polices", action="store_true",
                    help="affiche les polices disponibles et sort")
    args = ap.parse_args()

    if args.liste_polices:
        for cle in lister_polices():
            print(" ", cle)
        print("  (les variantes gothiques et Med/Bold gravent DOUBLE — fût"
              " contourné — à éviter au stylo)")
        return

    if args.sortie and len(args.svg) > 1:
        sys.exit("--sortie ne vaut que pour une seule planche")

    fonte = charger_police(args.police)
    for source in args.svg:
        if not os.path.exists(source):
            print(f"  absent : {source}", file=sys.stderr)
            continue
        racine, ext = os.path.splitext(source)
        destination = args.sortie or f"{racine}_propre{ext}"
        com, txt, formes, pts, dbl = nettoyer(source, destination, fonte)
        print(f"{os.path.basename(source)} -> {os.path.basename(destination)}"
              f"   ({com} commentaire(s), {txt} texte(s), {formes} forme(s)"
              f" en chemins, {pts} pointille(s) decoupe(s),"
              f" {dbl} cache(s) confondu(s) retire(s))")
    if fonte.manquants:
        detail = ", ".join(f"« {c} » x{n}" for c, n in sorted(fonte.manquants.items()))
        print(f"  ATTENTION — glyphes absents d'osifont, remplacés par un blanc :"
              f" {detail}", file=sys.stderr)


if __name__ == "__main__":
    main()
