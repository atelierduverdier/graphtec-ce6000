#!/usr/bin/env python3
"""Un vernier pour lire l'écart entre la découpe et l'impression.

Comparer deux traits distants de quelques dixièmes ne se fait pas de
mémoire. Le 14/08/2026, trois essais successifs empilés sur la même croix
sont devenus illisibles — quatre traits dans un demi-millimètre.

Un vernier règle ça d'un seul passage : on trace ONZE traits parallèles
au trait imprimé, décalés de deux dixièmes chacun, de −1 à +1 mm. Celui
qui se trouve dans le PROLONGEMENT du trait imprimé donne l'écart, et il
se lit d'un coup d'œil parce qu'un alignement se voit là où une distance
se devine.

C'est le principe du pied à coulisse, appliqué au papier.
"""

import sys

PAS = 0.2                 # entre deux traits du vernier, mm
PORTEE = 1.0              # de −PORTEE à +PORTEE
LONGUEUR = 3.0            # longueur d'un trait du vernier, mm
REPERE = 5.0              # longueur du trait de ZÉRO, plus long


def _echelle():
    n = int(round(PORTEE / PAS))
    return [i * PAS for i in range(-n, n + 1)]


def vernier(centre, bras=20.0, axe="chariot"):
    """Les traits du vernier, en polylignes machine.

    `centre` est le centre de la croix imprimée, en millimètres depuis
    l'origine posée par la détection. `axe` dit lequel on mesure :

        "chariot"  les traits sont parallèles à l'AVANCE, décalés en
                   travers — on lit l'écart sous le chariot
        "avance"   l'inverse

    Le trait de zéro est plus long : sans lui on compte les crans, et on
    se trompe d'un.
    """
    cx, cy = centre
    valeurs = _echelle()
    # Répartis le long du trait imprimé, sans le recouvrir tout à fait.
    etendue = 2 * bras - 6.0
    pas_long = etendue / (len(valeurs) - 1)
    debut = -bras + 3.0

    traces = []
    for i, v in enumerate(valeurs):
        long = REPERE if abs(v) < 1e-9 else LONGUEUR
        d = debut + i * pas_long
        if axe == "chariot":
            # parallèle à l'avance (X), décalé sous le chariot (Y)
            traces.append(([(cx + d, cy + v),
                            (cx + d + long, cy + v)], False))
        else:
            traces.append(([(cx + v, cy + d),
                            (cx + v, cy + d + long)], False))
    return traces


def legende(axe="chariot"):
    valeurs = _echelle()
    return (f"vernier {axe} : {len(valeurs)} traits de "
            f"{valeurs[0]:+.1f} à {valeurs[-1]:+.1f} mm par {PAS:g} — "
            f"le trait LONG est le zéro, il est au milieu")


if __name__ == "__main__":
    import svg2hpgl as noyau
    axe = sys.argv[1] if len(sys.argv) > 1 else "chariot"
    cx = float(sys.argv[2]) if len(sys.argv) > 2 else 90.0
    cy = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
    traces = vernier((cx, cy), axe=axe)
    print(legende(axe))
    print(f"centre de la croix : {cx:g} ; {cy:g} mm")
    programme, _ = noyau.en_hpgl(traces, reperage=True)
    sortie = f"/tmp/vernier_{axe}.hpgl"
    open(sortie, "w").write(programme)
    print(f"écrit : {sortie}  ({len(traces)} traits)")
