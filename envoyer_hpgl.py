#!/usr/bin/env python3
"""Envoie un fichier HP-GL déjà écrit au traceur.

Le chaînon qui manquait : `svg2hpgl.py --mosaique` écrit un fichier par
panneau sans les envoyer — il le faut, puisqu'il faut repositionner le média
entre deux panneaux — mais rien ne savait ensuite envoyer ces fichiers.

Reprend les deux garde-fous du reste du dépôt : le contrôle de flux sur
l'endpoint de 8 octets, et le refus d'envoyer quand la machine ne répond
pas à `OH;` — hors de l'état READY elle avale les octets sans rien tracer.
"""

import argparse
import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8
UNITES_PAR_MM = 40


def _ecrire(fd, texte, delai=20.0):
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


def zone_utile(fd, delai=2.0):
    """`OH;` -> (largeur, hauteur) en mm, ou None si la machine se tait."""
    while True:                                   # repartir propre
        prets, _, _ = select.select([fd], [], [], 0.05)
        if not prets:
            break
        try:
            if not os.read(fd, 64):
                break
        except BlockingIOError:
            break
    _ecrire(fd, "OH;")
    reponse = b""
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        prets, _, _ = select.select([fd], [], [], 0.05)
        if not prets:
            continue
        try:
            reponse += os.read(fd, 64)
        except BlockingIOError:
            pass
        if b"\r" in reponse:
            break
    try:
        x0, y0, x1, y1 = (float(v) for v in
                          reponse.decode("ascii", "replace").strip().split(","))
    except ValueError:
        return None
    return (x1 - x0) / UNITES_PAR_MM, (y1 - y0) / UNITES_PAR_MM


def emprise(programme):
    """Rectangle occupé par le programme, en mm — lu dans ses coordonnées."""
    import re
    xs, ys = [], []
    for verbe, args in re.findall(r"(PU|PD)([-\d,]*);", programme):
        v = [int(a) for a in args.split(",") if a]
        xs += v[0::2]
        ys += v[1::2]
    if not xs:
        return None
    return (min(xs) / UNITES_PAR_MM, min(ys) / UNITES_PAR_MM,
            max(xs) / UNITES_PAR_MM, max(ys) / UNITES_PAR_MM)


def main():
    ap = argparse.ArgumentParser(
        description="Envoie un fichier HP-GL au Graphtec CE6000-60.")
    ap.add_argument("fichier", nargs="+", help="fichier(s) .hpgl")
    ap.add_argument("--forcer", action="store_true",
                    help="envoie même si le dessin déborde de la zone utile")
    args = ap.parse_args()

    for chemin in args.fichier:
        if not os.path.exists(chemin):
            sys.exit(f"fichier introuvable : {chemin}")

    if not os.path.exists(PERIPH):
        sys.exit(f"{PERIPH} absent : traceur allumé et branché ?")

    for chemin in args.fichier:
        with open(chemin, encoding="ascii", errors="replace") as f:
            programme = f.read()

        fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
        try:
            limites = zone_utile(fd)
            boite = emprise(programme)
            nom = os.path.basename(chemin)

            if limites is None:
                sys.exit(f"{nom} : la machine ne répond pas à OH;. Média "
                         f"chargé et panneau sur READY ?")
            print(f"{nom} : {len(programme)} octets, "
                  f"zone utile {limites[0]:.1f} × {limites[1]:.1f} mm")
            if boite:
                print(f"   emprise {boite[2]-boite[0]:.1f} × "
                      f"{boite[3]-boite[1]:.1f} mm, coin à "
                      f"{boite[0]:.1f}, {boite[1]:.1f}")
                if (boite[2] > limites[0] or boite[3] > limites[1]) \
                        and not args.forcer:
                    sys.exit("   IL DÉBORDE — envoi annulé (--forcer pour "
                             "passer outre)")

            envoye = _ecrire(fd, programme)
            print(f"   envoyé {envoye} octets")
        finally:
            os.close(fd)

        if chemin is not args.fichier[-1]:
            input("   repositionner le média, puis Entrée pour le suivant… ")


if __name__ == "__main__":
    main()
