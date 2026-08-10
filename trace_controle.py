#!/usr/bin/env python3
"""Trace de controle sur le Graphtec CE6000-60 : un F dans un rectangle.

ATTENTION : ce script FAIT BOUGER le chariot et descendre l'outil.
A n'executer qu'avec un STYLO monte (ou le porte-outil vide), jamais avec
une lame, tant que l'echelle et l'orientation ne sont pas verifiees.

Le rectangle mesure 100 x 50 mm : il se controle au pied a coulisse.
Le F revele d'un coup d'oeil une rotation ou un effet miroir, ce qu'un
rectangle seul ne peut pas faire.
"""

import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8
UNITES_PAR_MM = 40


def u(mm):
    """Millimetres -> unites traceur (entiers, comme l'exige HP-GL)."""
    return int(round(mm * UNITES_PAR_MM))


def figure():
    """Rend la liste des commandes HP-GL du trace de controle."""
    cmd = [
        "IN;",        # initialisation : remet aussi a zero les bits d'erreur
        # Pas de VS : cette machine l'ignore (mesure du 10/08/2026, meme
        # parcours a VS5 et VS40, 30 s dans les deux cas). La vitesse vient
        # de la condition reglee au panneau.
        "SP1;",       # condition de coupe n1 du panneau
    ]

    # Rectangle 100 x 50 mm, coin bas-gauche a l'origine.
    cmd.append(f"PU{u(0)},{u(0)};")
    for x, y in [(100, 0), (100, 50), (0, 50), (0, 0)]:
        cmd.append(f"PD{u(x)},{u(y)};")

    # Le F : montant, barre du haut, barre du milieu.
    cmd.append(f"PU{u(10)},{u(10)};")
    cmd.append(f"PD{u(10)},{u(40)};")
    cmd.append(f"PD{u(30)},{u(40)};")
    cmd.append(f"PU{u(10)},{u(27)};")
    cmd.append(f"PD{u(25)},{u(27)};")

    cmd += ["PU0,0;", "SP0;"]      # retour a l'origine, outil range
    return cmd


def ecrire(fd, texte, delai=10.0):
    """Envoie en respectant les paquets de 8 octets et le controle de flux."""
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError("le traceur n'accepte plus de donnees")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.01)
    return envoye


def main():
    commandes = figure()
    programme = "".join(commandes)

    if "--simuler" in sys.argv:
        print("HP-GL qui SERAIT envoye (rien n'est transmis) :\n")
        for c in commandes:
            print("   ", c)
        print(f"\n{len(programme)} octets, {len(commandes)} commandes.")
        return

    if not os.path.exists(PERIPH):
        sys.exit(f"{PERIPH} absent : traceur allume et sur READY ?")

    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        ecrire(fd, programme)
    finally:
        os.close(fd)

    print(f"{len(programme)} octets envoyes.")
    print("Attendu : rectangle 100 x 50 mm, F lisible en bas a gauche,")
    print("montant du F du cote de l'origine, barres pointant vers +X.")


if __name__ == "__main__":
    main()
