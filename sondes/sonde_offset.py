#!/usr/bin/env python3
"""Juge la compensation d'offset de lame, sur des angles qui l'amplifient.

Un carré est un mauvais juge : ses angles droits sont ce qu'une lame
traînante encaisse le plus facilement, et sur 12 mm le défaut se voit à
peine. Une POINTE AIGUË, elle, exagère tout — plus l'angle se ferme, plus
la lame doit pivoter, et plus l'erreur devient lisible.

D'où quatre triangles de 20 mm de base dont le sommet se ferme : 90°, 60°,
45°, 30°. Le même défaut d'offset qui se devine à peine à 90° saute aux
yeux à 30°.

LES TROIS SIGNATURES, à reconnaître une fois pour toutes :

  - sommet ARRONDI, coupé avant la pointe : offset trop FAIBLE, la lame
    n'a pas fini de pivoter ;
  - sommet NET : offset juste ;
  - petites CORNES qui dépassent de part et d'autre du sommet : offset
    trop FORT, la machine sur-corrige.

ATTENTION : découpe réellement. Lame montée, hauteur réglée pour le média.
"""

import argparse
import math
import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8
UNITES_PAR_MM = 40

BASE = 20.0
ANGLES = (90, 60, 45, 30)
ECART = 8.0
MARGE = 6.0


def u(mm):
    return int(round(mm * UNITES_PAR_MM))


def figure(condition):
    """Les quatre triangles, plus un carré de référence."""
    lignes = ["IN;", f"SP{condition};"]
    legende = []
    x = MARGE
    for angle in ANGLES:
        # sommet d'angle `angle` : demi-base / hauteur = tan(angle/2)
        hauteur = (BASE / 2.0) / math.tan(math.radians(angle / 2.0))
        y = MARGE
        lignes.append(f"PU{u(x)},{u(y)};")
        for px, py in ((x + BASE, y), (x + BASE / 2.0, y + hauteur), (x, y)):
            lignes.append(f"PD{u(px)},{u(py)};")
        legende.append((angle, x, hauteur))
        x += BASE + ECART

    lignes.append(f"PU{u(x)},{u(MARGE)};")          # carré de référence
    for dx, dy in ((BASE, 0), (BASE, BASE), (0, BASE), (0, 0)):
        lignes.append(f"PD{u(x + dx)},{u(MARGE + dy)};")
    legende.append(("carré", x, BASE))

    lignes += ["PU0,0;", "SP0;"]
    return "\n".join(lignes) + "\n", legende, x + BASE + MARGE


def ecrire(fd, texte, delai=20.0):
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError("le traceur n'accepte plus de données")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.005)
    return envoye


def main():
    ap = argparse.ArgumentParser(
        description="Juge la compensation d'offset sur des pointes aiguës.")
    ap.add_argument("--condition", type=int, default=1,
                    help="condition du panneau à utiliser (défaut 1)")
    ap.add_argument("--envoyer", action="store_true",
                    help="découpe réellement")
    args = ap.parse_args()

    programme, legende, largeur = figure(args.condition)
    print(f"{len(legende)} formes, emprise {largeur:.0f} mm de large\n")
    print("  forme        position X   hauteur")
    for nom, x, h in legende:
        print(f"  {str(nom):<12} {x:>8.0f}   {h:>6.1f} mm")
    print("\nÀ JUGER sur les SOMMETS, du plus ouvert au plus fermé :")
    print("  sommet arrondi        -> offset trop FAIBLE")
    print("  sommet net            -> offset juste")
    print("  cornes qui dépassent  -> offset trop FORT")
    print("Le carré de droite sert de témoin : il masque le défaut,")
    print("c'est pour cela qu'il ne suffisait pas.")

    if not args.envoyer:
        print("\n(rien n'a été envoyé ; ajouter --envoyer)")
        return
    if not os.path.exists(PERIPH):
        sys.exit(f"{PERIPH} absent : traceur allumé et sur READY ?")
    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        print(f"\nenvoyé {ecrire(fd, programme)} octets")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
