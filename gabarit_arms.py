#!/usr/bin/env python3
"""Fabrique un gabarit de repères ARMS que le traceur dessine lui-même.

Cotes RELEVÉES le 13/08/2026 sur les PDF engendrés par Graphtec Studio,
mesurées au pixel sur un rendu à 300 dpi — le manuel ne les donne qu'en
image, illisible par extraction :

    forme        un L, deux branches à angle droit
    branches     20,0 mm  (= le MARK SIZE de la machine)
    épaisseur    1,0 mm
    aire         38 mm², ce qui recoupe 2 x 20 x 1 moins le coin

POURQUOI LE TRACEUR PLUTÔT QU'UNE IMPRIMANTE. Il n'y en a pas toujours
une sous la main, et le traceur pose la géométrie au dixième. On trace les
contours au stylo, on les remplit au marqueur noir : le capteur demande du
NOIR sur du BLANC, pas une impression particulière.

Le remplissage peut aussi se faire à la machine, en hachures serrées
(`--hachures`) — plus long, et le noir d'un stylo bille reste gris. À
n'employer que pour voir la géométrie.

    python3 gabarit_arms.py --media 210x297 -o repere.svg
"""

import argparse

BRANCHE = 20.0            # longueur d'une branche, mm
EPAISSEUR = 1.0           # largeur du trait, mm


def coin(x, y, sx, sy):
    """Un L dont l'angle est en (x, y) et qui s'ouvre vers (sx, sy).

    `sx`/`sy` valent +1 ou -1 : c'est la direction dans laquelle partent
    les branches. Les quatre repères d'une planche ont donc les quatre
    combinaisons, chacun encadrant son coin de la zone utile.
    """
    e, b = EPAISSEUR, BRANCHE
    return [
        # branche horizontale
        [(x, y), (x + sx * b, y), (x + sx * b, y + sy * e), (x, y + sy * e), (x, y)],
        # branche verticale
        [(x, y), (x + sx * e, y), (x + sx * e, y + sy * b), (x, y + sy * b), (x, y)],
    ]


def planche(largeur, hauteur, marge, hachures=False, ecart=None,
            ancrage="centre"):
    """Quatre repères aux coins d'une zone utile centrée.

    `ecart` impose la distance entre les ANGLES des L, au lieu de la
    déduire d'une marge. C'est ce que demande la machine : la capture du
    13/08/2026 montre Graphtec Studio annoncer `TB124,10280,6800`, soit
    257,0 × 170,0 mm — et une détection échoue si le tracé ne respecte pas
    cet écart au millimètre. La marge, elle, ne veut rien dire tant qu'on
    n'a pas dit « marge par rapport à quoi ».
    """
    if ecart:
        # CENTRÉ par défaut, mais la machine ne cherche pas au centre : la
        # capture du 13/08/2026 ne montre AUCUNE commande de positionnement
        # avant la salve TB. Elle balaye donc depuis son ORIGINE, et un
        # gabarit centré met le premier repère quinze millimètres plus
        # loin — assez pour qu'elle scanne le bord de la feuille et ne
        # trouve rien.
        if ancrage == "origine":
            x0 = y0 = 0.0
        else:
            x0 = (largeur - ecart[0]) / 2.0
            y0 = (hauteur - ecart[1]) / 2.0
        x1, y1 = x0 + ecart[0], y0 + ecart[1]
        if x0 < 0 or y0 < 0:
            raise SystemExit(
                f"écart {ecart[0]:g} × {ecart[1]:g} mm impossible sur "
                f"{largeur:g} × {hauteur:g} : la machine n'y atteint pas.")
    else:
        x0, y0 = marge, marge
        x1, y1 = largeur - marge, hauteur - marge
    formes = (coin(x0, y0, +1, +1) + coin(x1, y0, -1, +1)
              + coin(x0, y1, +1, -1) + coin(x1, y1, -1, -1))
    if hachures:
        formes += _hachures(formes)
    return formes


def _hachures(contours, pas=0.35):
    """Remplissage par balayage, pour ceux qui n'ont pas de marqueur.

    Grossier à dessein : chaque rectangle est balayé dans sa largeur. Le
    noir d'un stylo reste gris, le capteur risque de ne pas mordre — c'est
    un pis-aller, pas une solution.
    """
    traits = []
    for c in contours:
        xs = [p[0] for p in c]; ys = [p[1] for p in c]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        vertical = (x1 - x0) < (y1 - y0)
        n = int(((x1 - x0) if vertical else (y1 - y0)) / pas)
        for i in range(1, max(1, n)):
            if vertical:
                x = x0 + i * pas
                traits.append([(x, y0), (x, y1)])
            else:
                y = y0 + i * pas
                traits.append([(x0, y), (x1, y)])
    return traits


def en_svg(formes, largeur, hauteur):
    chemins = []
    for pts in formes:
        d = "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in pts)
        chemins.append(f'  <path d="{d}" fill="none" stroke="#000" '
                       f'stroke-width="0.1"/>')
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!-- Repères ARMS, type 1, 4 points. Branches {BRANCHE:g} mm,\n'
            f'     épaisseur {EPAISSEUR:g} mm. Cotes relevées sur les PDF de\n'
            f'     Graphtec Studio le 13/08/2026.\n'
            f'     À REMPLIR AU MARQUEUR NOIR : le capteur veut du noir\n'
            f'     franc sur du blanc, un contour au stylo ne suffit pas. -->\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}mm" '
            f'height="{hauteur}mm" viewBox="0 0 {largeur:g} {hauteur:g}">\n'
            + "\n".join(chemins) + "\n</svg>\n")


def main():
    ap = argparse.ArgumentParser(
        description="Gabarit de repères ARMS pour le CE6000-60.")
    # PIÈGE : la taille de la FEUILLE n'est pas la zone atteignable. Sur
    # un A4 chargé, les galets et les marges ramènent 210 x 297 à 256,8 x
    # 197,7 -- un gabarit fait aux cotes du papier ne rentre pas, et on ne
    # s'en aperçoit qu'au moment d'envoyer.
    ap.add_argument("--media", default=None,
                    help="cotes de la ZONE UTILE en mm, ex. 256x197. "
                         "Par défaut, elle est demandée à la machine.")
    ap.add_argument("--marge", type=float, default=20.0,
                    help="distance du bord au coin des repères, mm (défaut 20)")
    ap.add_argument("--ecart", metavar="XxY", default=None,
                    help="distance entre les angles des repères, en mm — "
                         "celle que la machine attend, lisible dans le "
                         "TB124 d'une capture. Prime sur --marge.")
    ap.add_argument("--ancrage", choices=("centre", "origine"),
                    default="centre",
                    help="où poser le PREMIER repère. « origine » le met en "
                         "0,0 : c'est là que la machine commence à balayer, "
                         "faute de commande de positionnement.")
    ap.add_argument("--hachures", action="store_true",
                    help="remplit les L par balayage au lieu du marqueur — "
                         "gris, donc peu sûr pour le capteur")
    ap.add_argument("-o", "--sortie", default="reperes_arms.svg")
    args = ap.parse_args()

    if args.media:
        try:
            L, H = (float(v) for v in args.media.lower().split("x"))
        except ValueError:
            raise SystemExit("--media attend LARGEURxHAUTEUR, ex. 256x197")
    else:
        import svg2hpgl
        limites = svg2hpgl.limites_machine()
        if not limites:
            raise SystemExit(
                "la machine ne répond pas — allumée, média chargé, READY ?\n"
                "Sinon donner la zone utile à la main : --media 256x197")
        L, H = limites
        print(f"zone utile demandée à la machine : {L:.1f} × {H:.1f} mm")

    ecart = None
    if args.ecart:
        try:
            ecart = tuple(float(v) for v in args.ecart.lower().split("x"))
        except ValueError:
            raise SystemExit("--ecart attend XxY en mm, ex. 227x140")
        if ecart[0] + BRANCHE > L or ecart[1] + BRANCHE > H:
            raise SystemExit(
                f"écart {ecart[0]:g} × {ecart[1]:g} + {BRANCHE:g} mm de "
                f"branches dépasse la zone utile {L:.1f} × {H:.1f} mm.\n"
                f"Réduire l'écart, donc AUGMENTER les marges dans Studio.")
    formes = planche(L, H, args.marge, args.hachures, ecart, args.ancrage)
    open(args.sortie, "w", encoding="utf-8").write(en_svg(formes, L, H))
    utile = (ecart if ecart else
             (L - 2 * args.marge - BRANCHE, H - 2 * args.marge - BRANCHE))
    print(f"écrit {args.sortie}")
    print(f"  média {L:g} × {H:g} mm, repères à {args.marge:g} mm des bords")
    print(f"  branches {BRANCHE:g} mm, épaisseur {EPAISSEUR:g} mm")
    print(f"  écart entre les angles : {utile[0]:.1f} × {utile[1]:.1f} mm")
    print("\n  Tracer au stylo, PUIS REMPLIR AU MARQUEUR NOIR.")
    print("  Le capteur exige du noir franc sur du blanc, et le manuel")
    print("  limite la détection aux matières de 0,3 mm au plus.")


if __name__ == "__main__":
    main()
