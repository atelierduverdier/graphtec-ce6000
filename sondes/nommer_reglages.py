#!/usr/bin/env python3
"""Nomme les réglages MACHINE tout seul, sans toucher au panneau.

Depuis qu'on sait écrire (`TC1004,<p>,<v>`) et lire en clair
(`etat_machine.py`), nommer un paramètre ne demande plus qu'on aille
manipuler la machine : on écrit une valeur, on relit le vidage, et la ligne
qui a changé **se nomme elle-même**.

C'est la troisième méthode essayée pour ce problème, et la première qui
n'occupe personne :

  1. changer la lame et comparer — muet quand la valeur ne bouge pas ;
  2. changer un réglage au panneau et comparer les nombres — ne trouve rien
     si le réglage n'est pas dans la famille balayée, ce qui a fait manquer
     le Step Pass ;
  3. écrire soi-même et relire le vidage nommé — celle-ci.

**Précautions, parce que ça ÉCRIT dans la machine :**

  - un vidage complet est enregistré avant de commencer ;
  - la perturbation est minimale : valeur actuelle + 1, jamais une valeur
    arbitraire, pour qu'un paramètre mal deviné ne parte pas au loin ;
  - la valeur d'origine est remise après CHAQUE essai, et vérifiée ;
  - si une remise en place échoue, tout s'arrête immédiatement.

    python3 nommer_reglages.py --voir        # ne fait qu'afficher, n'écrit rien
    python3 nommer_reglages.py --nommer
"""

import argparse
import os
import sys
import time

# Le paquet vit un cran au-dessus : ces sondes sont rangées à part
# parce qu'elles ont servi à COMPRENDRE la machine, pas à s'en servir.
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
import conditions as C                                      # noqa: E402
import etat_machine as E                                    # noqa: E402

# Déjà nommés, à ne pas re-sonder — la table vit dans conditions.py.
CONNUS = {p: nom for p, (nom, _, _) in C.REGLAGES_MACHINE.items()}


def _dump_plat(fd):
    return E.aplatir(E.analyser(E.lire(fd=fd)))


def _difference(a, b):
    return {k: (a.get(k), b.get(k)) for k in set(a) | set(b)
            if a.get(k) != b.get(k)}


def sonder(fd, parametre, avant_plat, attente=0.4):
    """Écrit une valeur voisine, voit quelle ligne nommée bouge, remet tout.

    Le pas ESCALADE : 1, puis 10, puis 100. La première version s'en tenait
    à +1 et cinq paramètres sur neuf sont restés muets — parce qu'une
    valeur est souvent stockée à l'échelle. `TOOL UP SPEED` vaut 400 dans
    la machine et s'affiche `40` : écrire 401 ne change RIEN à l'affichage,
    et l'absence de différence ressemblait à un échec alors que l'écriture
    avait pris.

    On vérifie donc aussi que l'écriture a été RETENUE, en relisant le
    paramètre. Ça sépare les deux raisons d'un silence : « refusé » et
    « accepté mais invisible ».

    Rend `(nom, origine, remise_ok, diagnostic)`.
    """
    actuel = C.lire_machine(fd, parametre)
    if not actuel:
        return None, None, True, "illisible"
    if len(actuel) > 1:
        return "(plusieurs champs, à sonder à part)", actuel, True, ""

    origine = actuel[0]
    noms, retenu = [], False
    # Un réglage à deux états refuse toute valeur voisine : 1 + 1 = 2 est
    # hors plage, et les trois pas échouaient en bloc. Ce n'est pas un
    # silence, c'est un refus -- que le diagnostic sait maintenant dire.
    # Pour ceux-là on écrit l'AUTRE état.
    essais = [1 - origine] if origine in (0, 1) else [origine + 1,
                                                      origine + 10,
                                                      origine + 100]
    for valeur in essais:
        pas = abs(valeur - origine)
        C.regler_machine(fd, parametre, valeur)
        time.sleep(attente)
        relu = C.lire_machine(fd, parametre)
        pris = bool(relu) and relu[0] == valeur
        retenu = retenu or pris
        change = _difference(avant_plat, _dump_plat(fd))
        noms = [f"[{s}] {k}" for s, k in change]
        if noms:
            break

    C.regler_machine(fd, parametre, origine)
    time.sleep(attente)
    remis = C.lire_machine(fd, parametre)
    ok = bool(remis) and remis[0] == origine

    if len(noms) == 1:
        return noms[0], origine, ok, f"pas de {pas}"
    if noms:
        return " + ".join(sorted(noms)), origine, ok, f"pas de {pas}"
    return (None, origine, ok,
            "écriture retenue mais aucune ligne du vidage ne bouge"
            if retenu else "écriture REFUSÉE par la machine")


def main():
    ap = argparse.ArgumentParser(
        description="Nomme les réglages machine en les écrivant et en "
                    "relisant le vidage en clair.")
    ap.add_argument("--voir", action="store_true",
                    help="affiche les paramètres et leurs valeurs, sans "
                         "rien écrire")
    ap.add_argument("--nommer", action="store_true",
                    help="sonde chaque paramètre inconnu (ÉCRIT dans la "
                         "machine, puis remet en place)")
    ap.add_argument("--jusqu-a", type=int, default=12, dest="jusqua")
    ap.add_argument("--sauvegarde", default="etat_avant_sondage.txt")
    args = ap.parse_args()

    if not os.path.exists(C.PERIPH):
        sys.exit(f"{C.PERIPH} absent : traceur allumé ?")

    fd = os.open(C.PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        C.lire_machine(fd, 3)                     # le coup pour rien
        presents = {}
        for p in range(1, args.jusqua + 1):
            v = C.lire_machine(fd, p)
            if v:
                presents[p] = v

        print(f"Famille TC{C.MACHINE_LECTURE} — {len(presents)} paramètre(s) :")
        for p, v in presents.items():
            print(f"   TC{C.MACHINE_LECTURE},{p:<3} {str(v):<14} "
                  f"{CONNUS.get(p, '')}")

        if not args.nommer:
            if not args.voir:
                print("\n(--voir pour ne faire que ça, --nommer pour sonder)")
            return

        texte = E.lire(fd=fd)
        open(args.sauvegarde, "w").write(texte)
        print(f"\nÉtat complet sauvegardé dans {args.sauvegarde}.")
        print("Sondage : valeur + 1, relecture du vidage, remise en place.\n")

        avant_plat = E.aplatir(E.analyser(texte))
        for p in presents:
            if p in CONNUS:
                print(f"   TC{C.MACHINE_LECTURE},{p:<3} déjà nommé : "
                      f"{CONNUS[p]}")
                continue
            nom, origine, ok, diag = sonder(fd, p, avant_plat)
            if not ok:
                print(f"   TC{C.MACHINE_LECTURE},{p:<3} REMISE EN PLACE "
                      f"ÉCHOUÉE — arrêt immédiat.")
                print(f"   Valeur d'origine : {origine}. "
                      f"Vidage d'avant dans {args.sauvegarde}.")
                return
            if nom is None:
                print(f"   TC{C.MACHINE_LECTURE},{p:<3} = {origine} : "
                      f"{diag}.")
            else:
                print(f"   TC{C.MACHINE_LECTURE},{p:<3} = {origine} -> "
                      f"**{nom}**   ({diag})")

        reste = E.lire(fd=fd)
        if reste != texte:
            print("\nATTENTION : l'état final diffère de la sauvegarde.")
            print(f"Comparer : python3 etat_machine.py --comparer "
                  f"{args.sauvegarde}")
        else:
            print("\nÉtat final identique à l'état de départ, au caractère près.")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
