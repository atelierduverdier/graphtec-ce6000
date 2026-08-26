#!/usr/bin/env python3
"""Ce que la préparation d'une planche doit garantir, et qu'on a payé.

`preparer_planche.py` remplace l'ancien détour par Inkscape : il retire
les commentaires XML, VECTORISE les textes et convertit les formes
simples en chemins, pour que `svg2hpgl` puisse tout lire.

Chaque propriété rejoue une faute réelle du 25-26/08/2026 :

  - un `<text>` laissé tel quel est simplement IGNORÉ par svg2hpgl : le
    cartouche ne se traçait pas ;
  - une forme sans trait NI fond ne doit rien tracer — le gabarit de
    l'atelier pose un `<rect>` de page entier en `fill:none;stroke:none`,
    qui serait sorti en rectangle de 210 x 297 à la plume ;
  - les ancres `text-anchor` middle/end doivent être respectées, sinon un
    titre centré part en biais ;
  - le monotrait `--police hershey` est plus large que l'osifont : une
    mise en page calée sur l'un déborde avec l'autre, et cela se mesure
    ici plutôt qu'à l'impression.

Aucun n'a besoin du traceur. `python3 tests/test_preparer_planche.py`
"""

import os
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import preparer_planche as pp                                # noqa: E402
import svg2hpgl as noyau                                     # noqa: E402

TMP = tempfile.mkdtemp(prefix="preparer-")
_N = [0]

PHRASE = "rainure 16.0 de profond sur 10.3 de large, languette 14 x 8"


def _svg(corps, larg=210, haut=297):
    _N[0] += 1
    chemin = os.path.join(TMP, "e%d.svg" % _N[0])
    open(chemin, "w").write(
        '<?xml version="1.0"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%dmm" height="%dmm"'
        ' viewBox="0 0 %d %d">%s</svg>' % (larg, haut, larg, haut, corps))
    return chemin


def _preparer(corps, police="osifont", **kw):
    """(chemin prepare, (commentaires, textes, formes))."""
    src = _svg(corps, **kw)
    dst = src[:-4] + "_p.svg"
    return dst, pp.nettoyer(src, dst, pp.charger_police(police))


def _abscisses(chemin):
    polys, avert = noyau.charger(chemin)
    return [p[0] for pts, _f in polys for p in pts], polys, avert


# ---------------------------------------------------------------- proprietes

def test_texte_vectorise():
    """Un <text> devient des chemins, que svg2hpgl sait lire."""
    dst, (_com, txt, _formes) = _preparer(
        '<text x="20" y="40" style="font-size:5px">ATELIER</text>')
    assert txt == 1, "aucun texte vectorise"
    assert "<text" not in open(dst).read(), "il reste un <text>"
    _xs, polys, avert = _abscisses(dst)
    assert not avert, "svg2hpgl proteste : %s" % avert
    assert len(polys) >= 7, "sept lettres, %d polylignes" % len(polys)


def test_forme_invisible_ne_trace_rien():
    """Sans trait NI fond, une forme ne se voit pas — et ne se trace pas."""
    dst, _ = _preparer(
        '<rect x="0" y="0" width="210" height="297"'
        ' style="fill:none;stroke:none;stroke-width:0"/>'
        '<rect x="20" y="10" width="180" height="277"'
        ' style="fill:none;stroke:#000000;stroke-width:0.7"/>')
    n = open(dst).read().count("<path")
    assert n == 1, "%d chemins au lieu du seul cadre visible" % n
    xs, _polys, _avert = _abscisses(dst)
    assert min(xs) >= 19.5 and max(xs) <= 200.5, \
        "le trace deborde du cadre visible : %.1f a %.1f" % (min(xs), max(xs))


def test_ancres_respectees():
    """text-anchor middle/end place le texte, sinon un titre centre derive."""
    mesures = {}
    for ancre in ("start", "middle", "end"):
        dst, _ = _preparer('<text x="100" y="40" style="font-size:5px;'
                           'text-anchor:%s">VERDIER</text>' % ancre)
        xs, _p, _a = _abscisses(dst)
        mesures[ancre] = (min(xs), max(xs))
    assert mesures["start"][0] > 99.0, "start ne commence pas a x"
    assert abs(sum(mesures["middle"]) / 2.0 - 100.0) < 1.0, "middle non centre"
    assert mesures["end"][1] < 101.0, "end ne finit pas a x"


def test_formes_simples_converties():
    """Les six formes que svg2hpgl ne lit pas deviennent des chemins."""
    dst, (_com, _txt, formes) = _preparer(
        '<rect x="10" y="10" width="20" height="10" style="stroke:#000"/>'
        '<circle cx="60" cy="20" r="8" style="stroke:#000"/>'
        '<ellipse cx="100" cy="20" rx="10" ry="5" style="stroke:#000"/>'
        '<line x1="10" y1="40" x2="50" y2="40" style="stroke:#000"/>'
        '<polyline points="10,60 30,70 50,60" style="stroke:#000;fill:none"/>'
        '<polygon points="80,60 100,70 120,60" style="stroke:#000;fill:none"/>')
    assert formes == 6, "%d formes converties sur 6" % formes
    _xs, polys, avert = _abscisses(dst)
    assert not avert, "svg2hpgl proteste : %s" % avert
    assert len(polys) == 6, "%d polylignes au lieu de 6" % len(polys)


def test_monotrait_plus_large_que_osifont():
    """Le chiffre, pas l'intuition : une mise en page calee sur l'osifont
    deborde en monotrait. Mesure du 26/08/2026 : x1,24."""
    largeurs = dict((nom, pp.charger_police(nom).largeur(PHRASE, 2.9))
                    for nom in ("osifont", "hershey"))
    ratio = largeurs["hershey"] / largeurs["osifont"]
    assert 1.15 <= ratio <= 1.40, \
        "rapport hershey/osifont = %.2f (%.0f mm contre %.0f)" \
        % (ratio, largeurs["hershey"], largeurs["osifont"])


def test_commentaires_retires():
    """TechDraw en ecrit quatre par planche ; l'extension Hershey mourait
    dessus, et un flux sans commentaire ne gene personne d'autre."""
    dst, (com, _txt, _formes) = _preparer(
        '<!-- Working space --><text x="20" y="40"'
        ' style="font-size:4px">X</text>')
    assert com == 1, "%d commentaire(s) compte(s)" % com
    assert "<!--" not in open(dst).read(), "un commentaire a survecu"


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    rates = []
    for t in TESTS:
        try:
            t()
            print("  OK    %s" % t.__name__)
        except AssertionError as e:
            print("  RATE  %s : %s" % (t.__name__, e))
            rates.append(t.__name__)
    print("")
    print("BILAN : %d proprietes, %d en echec" % (len(TESTS), len(rates)))
    return 1 if rates else 0


if __name__ == "__main__":
    sys.exit(main())
