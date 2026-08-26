#!/usr/bin/env python3
"""Ce que la préparation d'une planche doit garantir, et qu'on a payé.

`preparer_planche.py` remplace l'ancien détour par Inkscape : il retire
les commentaires XML, VECTORISE les textes et convertit les formes
simples en chemins, pour que `svg2hpgl` puisse tout lire.

Chaque contrôle rejoue une faute réelle du 25-26/08/2026 :

  - un `<text>` laissé tel quel est simplement IGNORÉ par svg2hpgl : le
    cartouche ne se traçait pas ;
  - une forme sans trait NI fond ne doit rien tracer — le gabarit de
    l'atelier pose un `<rect>` de page entier en `fill:none;stroke:none`,
    qui serait sorti en rectangle de 210 x 297 à la plume ;
  - les ancres `text-anchor` middle/end doivent être respectées, sinon un
    titre centré part en biais ;
  - le monotrait `--police hershey` est 24 % plus large que l'osifont :
    une mise en page calée sur l'un déborde avec l'autre, et c'est
    mesurable ici plutôt qu'à l'impression.

`python3 tests/test_preparer_planche.py`
"""

import os
import re
import sys
import tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import preparer_planche as pp                                # noqa: E402
import svg2hpgl as noyau                                     # noqa: E402

TMP = tempfile.mkdtemp(prefix="preparer-")
oks = []


def ok(nom, cond):
    oks.append((nom, bool(cond)))
    print("  %s  %s" % ("OK " if cond else "RATE", nom))


def svg(corps, larg=210, haut=297):
    chemin = os.path.join(TMP, "e%d.svg" % len(os.listdir(TMP)))
    open(chemin, "w").write(
        '<?xml version="1.0"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="%dmm" height="%dmm"'
        ' viewBox="0 0 %d %d">%s</svg>' % (larg, haut, larg, haut, corps))
    return chemin


def preparer(corps, police="osifont", **kw):
    src = svg(corps, **kw)
    dst = src[:-4] + "_p.svg"
    infos = pp.nettoyer(src, dst, pp.charger_police(police))
    return dst, infos


# 1. Un texte devient des chemins, et svg2hpgl le lit.
dst, (com, txt, formes) = preparer(
    '<text x="20" y="40" style="font-size:5px">ATELIER</text>')
ok("un <text> est vectorise (%d)" % txt, txt == 1)
ok("il ne reste plus de <text>", "<text" not in open(dst).read())
polys, avert = noyau.charger(dst)
ok("svg2hpgl lit le resultat sans avertissement (%d polylignes)" % len(polys),
   not avert and len(polys) >= 7)

# 2. Une forme invisible ne trace RIEN.
dst, _ = preparer(
    '<rect x="0" y="0" width="210" height="297"'
    ' style="fill:none;stroke:none;stroke-width:0"/>'
    '<rect x="20" y="10" width="180" height="277"'
    ' style="fill:none;stroke:#000000;stroke-width:0.7"/>')
ok("le rect de page invisible ne devient pas un chemin",
   open(dst).read().count("<path") == 1)
polys, _ = noyau.charger(dst)
xs = [p[0] for pts, _f in polys for p in pts]
ok("le trace se limite au cadre visible (x de %.0f a %.0f)"
   % (min(xs), max(xs)), min(xs) >= 19.5 and max(xs) <= 200.5)

# 3. Les ancres.
for ancre, juge in (("start", lambda a, b: a > 99),
                    ("middle", lambda a, b: abs((a + b) / 2 - 100) < 1.0),
                    ("end", lambda a, b: b < 101)):
    dst, _ = preparer('<text x="100" y="40" style="font-size:5px;'
                      'text-anchor:%s">VERDIER</text>' % ancre)
    polys, _ = noyau.charger(dst)
    xs = [p[0] for pts, _f in polys for p in pts]
    ok("ancre %-6s respectee (%.1f a %.1f pour un x de 100)"
       % (ancre, min(xs), max(xs)), juge(min(xs), max(xs)))

# 4. Les formes simples, toutes converties.
dst, (com, txt, formes) = preparer(
    '<rect x="10" y="10" width="20" height="10" style="stroke:#000"/>'
    '<circle cx="60" cy="20" r="8" style="stroke:#000"/>'
    '<ellipse cx="100" cy="20" rx="10" ry="5" style="stroke:#000"/>'
    '<line x1="10" y1="40" x2="50" y2="40" style="stroke:#000"/>'
    '<polyline points="10,60 30,70 50,60" style="stroke:#000;fill:none"/>'
    '<polygon points="80,60 100,70 120,60" style="stroke:#000;fill:none"/>')
ok("les six formes simples deviennent des chemins (%d)" % formes, formes == 6)
polys, avert = noyau.charger(dst)
ok("svg2hpgl les lit toutes, sans avertissement (%d)" % len(polys),
   not avert and len(polys) == 6)

# 5. Le monotrait est PLUS LARGE que l'osifont — le chiffre, pas l'intuition.
phrase = "rainure 16.0 de profond sur 10.3 de large, languette 14 x 8"
larg = {}
for nom in ("osifont", "hershey"):
    larg[nom] = pp.charger_police(nom).largeur(phrase, 2.9)
ratio = larg["hershey"] / larg["osifont"]
ok("hershey est plus large que l'osifont (x%.2f : %.0f mm contre %.0f)"
   % (ratio, larg["hershey"], larg["osifont"]), 1.15 <= ratio <= 1.40)

# 6. Les commentaires XML partent (l'extension Hershey d'Inkscape mourait dessus).
dst, (com, _t, _f) = preparer('<!-- Working space --><text x="20" y="40"'
                              ' style="font-size:4px">X</text>')
ok("les commentaires XML sont retires (%d)" % com, com == 1)

rates = [n for n, c in oks if not c]
print("")
print("BILAN : %d controles, %d rate(s)" % (len(oks), len(rates)))
sys.exit(1 if rates else 0)
