#!/usr/bin/env python3
"""Nuancier de force pour le Graphtec CE6000-60.

Trace une ligne par valeur de force, pour LIRE sur le média laquelle
convient au lieu de la deviner. Même méthode que les nuanciers de tons du
laser : la planche tranche, pas le raisonnement.

Répond du même coup à une question qu'aucune lecture de code ne règle :
la commande HP-GL `FS` est-elle seulement écoutée par cette machine, ou
seul le réglage FORCE du panneau compte-t-il ? Si toutes les lignes
sortent identiques, la réponse est non.

CHAQUE LIGNE PORTE SA PROPRE ÉTIQUETTE : sa longueur vaut 20 mm + la
force. Un coup de pied à coulisse donne la valeur sans avoir à compter
les lignes depuis le bas -- ce qui serait impossible si les premières
sont trop pâles pour se voir.

ATTENTION : fait bouger le chariot et descendre l'outil.
"""

import argparse
import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
UNITES_PAR_MM = 40
TAILLE_PAQUET = 8

LONGUEUR_BASE = 20.0      # mm ; longueur = LONGUEUR_BASE + force
ECART_LIGNES = 4.0        # mm entre deux lignes
MARGE = 5.0               # mm depuis le coin


def u(mm):
    return int(round(mm * UNITES_PAR_MM))


def carres(force_min, force_max, pas, outil, cote=12.0, ecart=6.0,
           par_rangee=8):
    """Une grille de carrés, un par force, À LEVER pour juger.

    Le nuancier en LIGNES se juge à l'oeil : bon pour une plume, inutile
    pour une lame. Une coupe ne se voit pas, elle se sent — le bon réglage
    est le plus faible où le carré se détache proprement, sans que la lame
    entame la bande de coupe dessous.

    Les carrés sont identiques et rangés par force croissante : un carré
    non coupé reste visible (la lame griffe même sans traverser), donc on
    peut compter depuis le premier. La légende imprimée donne les positions.
    """
    forces = list(range(force_min, force_max + 1, pas))
    lignes = ["IN;", f"SP{outil};"]
    legende = []
    for rang, force in enumerate(forces):
        col, rangee = rang % par_rangee, rang // par_rangee
        x = MARGE + col * (cote + ecart)
        y = MARGE + rangee * (cote + ecart)
        lignes.append(f"FS{force};")
        lignes.append(f"PU{u(x)},{u(y)};")
        for dx, dy in ((cote, 0), (cote, cote), (0, cote), (0, 0)):
            lignes.append(f"PD{u(x + dx)},{u(y + dy)};")
        legende.append((force, x, y))
    lignes += ["PU0,0;", "SP0;"]
    return "\n".join(lignes) + "\n", legende


def nuancier(force_min, force_max, pas, outil):
    """Rend (programme HP-GL, [(force, longueur_mm, y_mm), ...])."""
    forces = list(range(force_min, force_max + 1, pas))
    lignes = ["IN;"]
    lignes.append(f"SP{outil};")

    legende = []
    for rang, force in enumerate(forces):
        longueur = LONGUEUR_BASE + force
        y = MARGE + rang * ECART_LIGNES
        lignes.append(f"FS{force};")
        lignes.append(f"PU{u(MARGE)},{u(y)};")
        lignes.append(f"PD{u(MARGE + longueur)},{u(y)};")
        legende.append((force, longueur, y))

    lignes += ["PU0,0;", "SP0;"]
    return "\n".join(lignes) + "\n", legende


def ecrire(fd, texte, delai=15.0):
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError("le traceur n'accepte plus de données")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.01)
    return envoye


def main():
    ap = argparse.ArgumentParser(
        description="Trace un nuancier de force sur le Graphtec CE6000-60.")
    ap.add_argument("--min", type=int, default=1, help="force la plus basse (défaut 1)")
    ap.add_argument("--max", type=int, default=31, help="force la plus haute (défaut 31)")
    ap.add_argument("--pas", type=int, default=2, help="incrément (défaut 2)")
    ap.add_argument("--outil", type=int, default=1, help="condition du panneau (défaut 1)")
    ap.add_argument("--carres", action="store_true",
                    help="carrés À LEVER au lieu de lignes : le seul jugement "
                         "valable pour une lame, une coupe ne se voyant pas")
    ap.add_argument("--cote", type=float, default=12.0,
                    help="côté des carrés en mm (défaut 12)")
    ap.add_argument("--envoyer", action="store_true",
                    help="envoie à la machine (mouvement réel de l'outil)")
    args = ap.parse_args()

    if args.min < 1 or args.max < args.min or args.pas < 1:
        sys.exit("plage de force incohérente")

    if args.carres:
        programme, legende = carres(args.min, args.max, args.pas,
                                    args.outil, args.cote)
    else:
        programme, legende = nuancier(args.min, args.max, args.pas,
                                      args.outil)

    if args.carres:
        xs = [x for _, x, _ in legende]; ys = [y for _, _, y in legende]
        print(f"{len(legende)} carrés de {args.cote:.0f} mm, force {args.min} "
              f"à {args.max} par pas de {args.pas}")
        print(f"emprise {max(xs) + args.cote + MARGE:.0f} x "
              f"{max(ys) + args.cote + MARGE:.0f} mm\n")
        print("  force        position (x, y)")
        for force, x, y in legende:
            print(f"  {force:>5}   {x:>10.1f}, {y:.1f}")
        print("\nLecture AU DOIGT : le bon réglage est la force la PLUS FAIBLE")
        print("dont le carré se détache proprement. Au-delà, on n'y gagne rien")
        print("et la lame entame la bande de coupe -- qui, elle, s'use.")
    else:
        hauteur = legende[-1][2] + MARGE
        largeur = MARGE + LONGUEUR_BASE + args.max
        print(f"{len(legende)} lignes, force {args.min} à {args.max} par pas de {args.pas}")
        print(f"emprise {largeur:.0f} x {hauteur:.0f} mm\n")
        print("  force   longueur   position Y")
        for force, longueur, y in legende:
            print(f"  {force:>5}   {longueur:>6.0f} mm   {y:>6.1f} mm")
        print("\nLecture : mesurer la longueur d'une ligne au pied à coulisse,")
        print(f"          la force vaut cette longueur moins {LONGUEUR_BASE:.0f} mm.")

    if not args.envoyer:
        print("\n(rien n'a été envoyé ; ajouter --envoyer pour tracer)")
        return

    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        envoye = ecrire(fd, programme)
    finally:
        os.close(fd)
    print(f"\nenvoyé {envoye} octets à {PERIPH}")


if __name__ == "__main__":
    main()
