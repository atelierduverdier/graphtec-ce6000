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

PENTE = 20.0              # 1 mm d'écart déplace le croisement de 20 mm
PORTEE = 1.0              # l'oblique va de -PORTEE à +PORTEE, mm
GRAD = 2.0                # une graduation tous les 2 mm = 0,1 mm d'écart
TIC = 1.2                 # longueur d'une graduation, mm
TIC_ZERO = 3.0            # celle du milieu, plus longue


def vernier(centre, bras=20.0, axe="chariot"):
    """L'oblique et ses graduations, en polylignes machine.

    UNE SEULE LIGNE, légèrement oblique, qui traverse le trait imprimé.
    Elle s'écarte de `PORTEE` de part et d'autre sur la longueur du bras,
    soit une pente de 1 pour 20 : **un dixième de millimètre d'écart
    déplace le croisement de deux millimètres**.

    C'est là tout le principe, et c'est ce que ma première version ratait :
    elle proposait onze traits décalés de deux dixièmes, invisibles à
    l'œil parce que l'écart à lire y restait de la taille de l'écart à
    mesurer. Un vernier ne compare pas, il AMPLIFIE.

    Lecture : là où l'oblique croise le trait imprimé, compter les
    graduations depuis la longue, au milieu. Chacune vaut 0,1 mm. Le côté
    donne le signe.
    """
    cx, cy = centre
    demi = bras - 2.0
    traces = []

    def poser(le_long, en_travers):
        """(le_long, en_travers) -> (x, y) selon l'axe mesuré."""
        if axe == "chariot":
            return (cx + le_long, cy + en_travers)
        return (cx + en_travers, cy + le_long)

    # L'oblique elle-même.
    traces.append(([poser(-demi, -PORTEE), poser(demi, PORTEE)], False))

    # Les graduations, perpendiculaires à l'oblique — donc en travers.
    n = int(demi // GRAD)
    for i in range(-n, n + 1):
        le_long = i * GRAD
        en_travers = PORTEE * le_long / demi
        long_tic = TIC_ZERO if i == 0 else TIC
        traces.append(([poser(le_long, en_travers),
                        poser(le_long, en_travers + long_tic)], False))
    return traces


def legende(axe="chariot"):
    return (f"vernier {axe} : oblique de {-PORTEE:+.1f} à {PORTEE:+.1f} mm "
            f"sur {2*(20.0-2.0):g} mm — pente 1 pour {PENTE:g}. "
            f"Une graduation ({GRAD:g} mm) vaut {GRAD/PENTE:.1f} mm d'écart. "
            f"La graduation LONGUE est le zéro.")


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
