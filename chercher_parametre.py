#!/usr/bin/env python3
"""Nomme un réglage inconnu en photographiant la machine avant et après.

L'idée est de Christophe : plutôt que d'écrire une valeur au hasard et de
guetter un écran, on RELÈVE tous les paramètres, on change une seule chose,
on relève de nouveau — et la différence désigne le paramètre.

Elle vaut mieux que la méthode précédente sur deux points. Elle n'exige
aucun affichage : elle nomme donc aussi les réglages que la machine ne
montre nulle part, comme le déport de lame. Et elle ne modifie rien par
elle-même : on lit, on laisse l'opérateur ou une autre commande agir, on
relit.

  sudo n'est pas nécessaire ; la machine doit être sur READY.

  python3 chercher_parametre.py                    # à la main, au panneau
  python3 chercher_parametre.py --outil CB15U      # en changeant la lame
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conditions as C                                      # noqa: E402

NOMS = {2: "type d'outil", 3: "vitesse", 4: "force", 5: "accélération"}


def montrer(etat, titre):
    print(f"\n{titre} — {len(etat)} paramètre(s) :")
    for p, v in sorted(etat.items()):
        print(f"   TC2002,{p:<3} {str(v):<20} {NOMS.get(p, '')}")


def main():
    ap = argparse.ArgumentParser(
        description="Nomme un réglage en comparant deux relevés de la machine.")
    ap.add_argument("--condition", type=int, default=1)
    ap.add_argument("--jusqu-a", type=int, default=20, dest="jusqua",
                    help="dernier numéro de paramètre interrogé (défaut 20)")
    ap.add_argument("--outil", metavar="NOM",
                    help="change la lame entre les deux relevés, au lieu de "
                         "demander une manipulation. Le paramètre qui suit ce "
                         "changement EST le déport, puisque c'est la lame qui "
                         "le détermine.")
    args = ap.parse_args()

    if not os.path.exists(C.PERIPH):
        sys.exit(f"{C.PERIPH} absent : traceur allumé ?")

    plage = range(1, args.jusqua + 1)
    avant = C.instantane(args.condition, plage)
    if not avant:
        sys.exit("aucun paramètre ne répond — panneau sur READY ?")
    montrer(avant, "AVANT")

    if args.outil:
        if args.outil not in C.OUTILS:
            sys.exit(f"outil inconnu ; au choix : {', '.join(C.OUTILS)}")
        fd = os.open(C.PERIPH, os.O_RDWR | os.O_NONBLOCK)
        try:
            C.regler_outil(fd, C.OUTILS[args.outil], args.condition)
        finally:
            os.close(fd)
        print(f"\noutil passé à {args.outil}.")
    else:
        print("\nChange UNE SEULE chose sur la machine, puis reviens à READY.")
        input("Entrée quand c'est fait… ")

    apres = C.instantane(args.condition, plage)
    if not apres:
        sys.exit("plus de réponse — es-tu bien revenu à READY ?")

    change = C.difference(avant, apres)
    print(f"\n{'='*56}")
    if not change:
        print("RIEN n'a changé. Soit le réglage n'est pas dans cette famille,")
        print("soit il n'est pas stocké par condition, soit la manipulation")
        print("n'a pas pris. Ne rien conclure.")
        return
    print(f"{len(change)} paramètre(s) ont changé :")
    for p, (a, b) in change.items():
        print(f"   TC2002,{p:<3} {str(a):<18} -> {str(b):<18} {NOMS.get(p, '')}")
    inconnus = [p for p in change if p not in NOMS]
    if len(inconnus) == 1:
        print(f"\nUn seul inconnu : **TC1002,{inconnus[0]}** porte ce que tu "
              f"viens de changer.")
    elif inconnus:
        print(f"\nPlusieurs inconnus ({inconnus}) : la manipulation en a touché")
        print("plus d'un. Recommencer en ne changeant qu'une chose.")


if __name__ == "__main__":
    main()
