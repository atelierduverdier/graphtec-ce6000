#!/usr/bin/env python3
"""Explore le GP-GL, le langage natif du Graphtec.

POURQUOI. En HP-GL, cette machine écoute `FS` (force) mais **ignore `VS`**
(vitesse) : mesuré le 10/08/2026, même parcours à VS5 puis VS40, 30 s dans
les deux cas. Or l'émulation HP-GL n'est qu'une émulation. L'écran « Avancé »
du logiciel Graphtec affiche une **« Taille du pas : 0,100 mm »** — un
réglage qui n'a de sens qu'en GP-GL, puisque le HP-GL a ses 40 unités/mm
figées. Le logiciel d'origine pilote donc probablement la machine dans son
langage natif, où la vitesse a sa propre commande.

CE QUE JE NE SAIS PAS, et qu'il faut donc mesurer plutôt que supposer :

  - l'ordre des paramètres (`M x,y` ou `M y,x`) ;
  - le séparateur attendu entre commandes ;
  - la lettre exacte des commandes de vitesse et de force.

D'où la marche à suivre : **une inconnue à la fois**. `--rectangle` n'envoie
que des déplacements, sans vitesse ni force. S'il sort un rectangle de
60 × 30 mm, la syntaxe ET le pas sont bons, et le côté qui mesure 60 dit
quel paramètre est quel axe. Alors seulement on ajoute la vitesse.

Si rien ne bouge, rien n'est cassé : rebasculer le panneau sur HP-GL.

PRÉALABLE : panneau sur `COMMAND` → `GP-GL`.
"""

import argparse
import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8
PAS_PAR_MM = 10           # « Taille du pas : 0,100 mm » vu dans le logiciel

SEPARATEURS = {
    "nl": "\n",           # le plus courant
    "etx": "\x03",        # certains analyseurs GP-GL l'exigent
    "cr": "\r",
    "aucun": "",
}


def ecrire(fd, texte, delai=30.0):
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    debut = time.monotonic()
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError("le traceur n'accepte plus de données")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.003)
    return time.monotonic() - debut


def programme_rectangle(pas_par_mm, sep):
    """Rectangle 60 × 30 mm, plus un ergot de 20 mm sur le premier axe.

    L'asymétrie est volontaire : un carré ne dirait pas quel paramètre
    commande quel axe, et c'est justement l'inconnue.
    """
    def p(mm):
        return int(round(mm * pas_par_mm))

    cmd = [
        f"M{p(20)},{p(20)}",                 # se placer, outil levé
        f"D{p(80)},{p(20)}",                 # 60 mm sur le PREMIER paramètre
        f"D{p(80)},{p(50)}",                 # 30 mm sur le SECOND
        f"D{p(20)},{p(50)}",
        f"D{p(20)},{p(20)}",
        f"M{p(20)},{p(10)}",                 # ergot : 20 mm, premier axe
        f"D{p(40)},{p(10)}",
        "M0,0",
    ]
    return sep.join(cmd) + sep


def programme_zigzag(vitesse, commande_vitesse, pas_par_mm, sep):
    """Long parcours dense, à chronométrer à la montre."""
    def p(mm):
        return int(round(mm * pas_par_mm))

    cmd = []
    if vitesse:
        cmd.append(f"{commande_vitesse}{vitesse}")
    cmd.append(f"M{p(20)},{p(20)}")
    longueur = 0.0
    y = 20.0
    gauche = True
    while y <= 60.0:
        arrivee = 140.0 if gauche else 20.0
        depart = 20.0 if gauche else 140.0
        x = depart
        step = 2.0 if arrivee > depart else -2.0
        while (x < arrivee) if step > 0 else (x > arrivee):
            x = min(x + step, arrivee) if step > 0 else max(x + step, arrivee)
            cmd.append(f"D{p(x)},{p(y)}")
        longueur += 120.0
        y += 2.0
        if y <= 60.0:
            cmd.append(f"D{p(arrivee)},{p(y)}")
            longueur += 2.0
        gauche = not gauche
    cmd.append("M0,0")
    return sep.join(cmd) + sep, longueur


def main():
    ap = argparse.ArgumentParser(
        description="Explore le GP-GL sur le Graphtec CE6000-60.")
    ap.add_argument("--rectangle", action="store_true",
                    help="essai de syntaxe : un rectangle 60 × 30 mm, "
                         "sans vitesse ni force")
    ap.add_argument("--vitesse", type=int,
                    help="zigzag à chronométrer, à cette vitesse")
    ap.add_argument("--commande-vitesse", default="!",
                    help="lettre de la commande de vitesse (défaut « ! »)")
    ap.add_argument("--pas", type=int, default=PAS_PAR_MM,
                    help=f"pas par millimètre (défaut {PAS_PAR_MM}, "
                         f"soit 0,1 mm par pas)")
    ap.add_argument("--separateur", default="nl", choices=list(SEPARATEURS),
                    help="séparateur entre commandes (défaut « nl »)")
    ap.add_argument("--envoyer", action="store_true",
                    help="envoie à la machine ; sans lui, rien ne part")
    args = ap.parse_args()

    sep = SEPARATEURS[args.separateur]

    if args.vitesse:
        programme, longueur = programme_zigzag(
            args.vitesse, args.commande_vitesse, args.pas, sep)
        attendu = longueur / (args.vitesse * 10.0)
        entete = (f"zigzag {longueur:.0f} mm à {args.commande_vitesse}"
                  f"{args.vitesse} — si la commande passe, environ "
                  f"{attendu:.0f} s")
    elif args.rectangle:
        programme = programme_rectangle(args.pas, sep)
        longueur = None
        entete = ("rectangle 60 × 30 mm plus un ergot de 20 mm ; "
                  "AUCUNE vitesse ni force n'est envoyée")
    else:
        sys.exit("choisir --rectangle (essai de syntaxe) ou --vitesse N")

    print(entete)
    print(f"{len(programme)} octets, séparateur « {args.separateur} », "
          f"{args.pas} pas/mm")
    if not args.envoyer:
        print("\n" + repr(programme[:120]) + " …")
        print("\n(rien n'a été envoyé ; ajouter --envoyer)")
        return

    if not os.path.exists(PERIPH):
        sys.exit(f"{PERIPH} absent : traceur allumé et sur READY ?")
    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        duree = ecrire(fd, programme)
    finally:
        os.close(fd)
    print(f"\nenvoyé en {duree:.1f} s d'écriture.")
    if args.rectangle:
        print("À mesurer au pied à coulisse :")
        print("  60 mm sur le PREMIER paramètre, 30 mm sur le SECOND.")
        print("  Le côté de 60 mm est-il le long de l'AVANCE du média,")
        print("  comme en HP-GL, ou en travers ? C'est cela qui dit quel")
        print("  paramètre est quel axe.")
        print("  Rien du tout : changer --separateur (etx, cr, aucun).")


if __name__ == "__main__":
    main()
