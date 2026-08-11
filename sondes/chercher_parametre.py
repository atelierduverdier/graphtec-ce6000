#!/usr/bin/env python3
"""Nomme un réglage inconnu en photographiant la machine avant et après.

L'idée est de Christophe : plutôt que d'écrire une valeur au hasard et de
guetter un écran, on RELÈVE tous les paramètres, on change une seule chose,
on relève de nouveau — et la différence désigne le paramètre.

Elle a nommé l'offset le 11/08/2026, là où deux autres approches avaient
échoué. Elle vaut mieux qu'elles sur trois points. Elle n'exige aucun
affichage : elle nomme donc aussi les réglages que la machine ne montre
nulle part. Elle ne modifie rien par elle-même. Et elle balaye TOUTES les
familles à la fois, donc une seule manipulation au panneau suffit.

Le relevé se fait en deux temps, pour laisser le temps d'aller au panneau :

    python3 chercher_parametre.py --debut
    (aller changer UNE chose sur la machine, revenir à READY)
    python3 chercher_parametre.py --fin "step pass"

  sudo n'est pas nécessaire ; la machine doit être sur READY.

Variante sans quitter le clavier, quand le changement se fait par commande :

    python3 chercher_parametre.py --outil CB15U
"""

import argparse
import json
import os
import sys

# Le paquet vit un cran au-dessus : ces sondes sont rangées à part
# parce qu'elles ont servi à COMPRENDRE la machine, pas à s'en servir.
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
import conditions as C                                      # noqa: E402

ETAPE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     ".releve_en_cours.json")

NOMS = {
    (2002, 2): "type d'outil + offset",
    (2002, 3): "vitesse",
    (2002, 4): "force",
    (2002, 5): "accélération",
}

# Réglages décrits au chapitre 6 du manuel et pas encore rattachés à un
# paramètre. Les plages viennent du manuel ; elles servent à ÉCARTER une
# hypothèse, pas à la confirmer — un paramètre qui vaut 37 n'est pas le
# Step Pass, mais un paramètre qui vaut 1 n'en est pas un pour autant.
A_NOMMER = {
    "step pass":            "lissage des courbes, 0 à 20, défaut 1",
    "angle offset":         "0 à 60",
    "débordement":          "avant et après la découpe, 0 à 0,9 mm chacun",
    "force offset":         "0 à 20",
    "mode tangentiel":      "désactivé / mode 1 / mode 2",
    "ligne de découpe":     "8 motifs perforés, 0 à 7",
    "ajuster les distances": "correction de longueur",
    "presse-papier":        "activé / désactivé",
    "position lame initiale": "2 mm en-deçà / dehors",
    "pré-alimentation":     "activée / désactivée, plus une longueur",
}

FAMILLES = (2002, 2004, 2006, 2010)


def _cles(etat):
    return {f"{f},{p}": v for (f, p), v in etat.items()}


def _decles(brut):
    return {tuple(int(x) for x in k.split(",")): v for k, v in brut.items()}


def relever(condition, jusqua):
    etat = C.instantane(condition, range(1, jusqua + 1), familles=FAMILLES)
    if not etat:
        sys.exit("aucun paramètre ne répond — panneau sur READY ?")
    return etat


def montrer(etat, titre):
    print(f"\n{titre} — {len(etat)} paramètre(s) :")
    for (f, p), v in sorted(etat.items()):
        print(f"   TC{f},{p:<3} {str(v):<16} {NOMS.get((f, p), '')}")


def conclure(avant, apres, intitule):
    change = C.difference(avant, apres)
    print("\n" + "=" * 60)
    if not change:
        print("RIEN n'a changé.")
        print("Trois lectures possibles, et aucune ne permet de conclure :")
        print("  - le réglage n'est pas stocké par condition ;")
        print("  - il vaut la même chose avant et après (le piège de")
        print("    l'offset : 0 pour les deux lames, donc invisible) ;")
        print("  - la manipulation n'a pas pris.")
        print("Vérifier au panneau que la valeur a bien changé, puis")
        print("recommencer en la poussant plus loin.")
        return
    print(f"{len(change)} paramètre(s) ont changé :")
    for (f, p), (a, b) in sorted(change.items()):
        print(f"   TC{f},{p:<3} {str(a):<16} -> {str(b):<16} "
              f"{NOMS.get((f, p), '')}")
    inconnus = [k for k in change if k not in NOMS]
    print()
    if len(inconnus) == 1:
        f, p = inconnus[0]
        print(f"Un seul inconnu : **TC1002,{p}** (famille {f}) porte "
              f"« {intitule} ».")
        print("Le consigner dans conditions.py — un numéro retenu de tête")
        print("est un numéro perdu.")
    elif inconnus:
        print(f"Plusieurs inconnus : {inconnus}.")
        print("La manipulation en a touché plus d'un, ou un réglage en")
        print("entraîne un autre. Recommencer en ne changeant qu'une chose.")
    else:
        print("Tout ce qui a changé était déjà nommé : la manipulation n'a")
        print("pas touché ce qu'on croyait.")


def main():
    ap = argparse.ArgumentParser(
        description="Nomme un réglage en comparant deux relevés de la machine.",
        epilog="Réglages du manuel encore sans numéro : "
               + ", ".join(A_NOMMER))
    ap.add_argument("--condition", type=int, default=1)
    ap.add_argument("--jusqu-a", type=int, default=25, dest="jusqua",
                    help="dernier numéro de paramètre interrogé (défaut 25)")
    ap.add_argument("--debut", action="store_true",
                    help="relève l'état et l'enregistre, puis rend la main "
                         "pour aller manipuler le panneau")
    ap.add_argument("--fin", metavar="INTITULÉ",
                    help="relève de nouveau et compare au relevé enregistré")
    ap.add_argument("--outil", metavar="NOM",
                    help="change la lame entre les deux relevés, sans quitter "
                         "le clavier")
    ap.add_argument("--reste", action="store_true",
                    help="liste les réglages du manuel encore sans numéro")
    args = ap.parse_args()

    if args.reste:
        print("Réglages décrits au manuel et pas encore rattachés :")
        for nom, quoi in A_NOMMER.items():
            print(f"   {nom:<24} {quoi}")
        return

    if not os.path.exists(C.PERIPH):
        sys.exit(f"{C.PERIPH} absent : traceur allumé ?")

    if args.debut:
        etat = relever(args.condition, args.jusqua)
        json.dump({"condition": args.condition, "jusqua": args.jusqua,
                   "etat": _cles(etat)}, open(ETAPE, "w"))
        montrer(etat, "AVANT, enregistré")
        print("\nVa changer UNE SEULE chose sur la machine, reviens à READY,")
        print('puis : python3 chercher_parametre.py --fin "ce que tu as changé"')
        return

    if args.fin:
        if not os.path.exists(ETAPE):
            sys.exit("aucun relevé en cours — commencer par --debut")
        sauve = json.load(open(ETAPE))
        avant = _decles(sauve["etat"])
        apres = relever(sauve["condition"], sauve["jusqua"])
        montrer(apres, "APRÈS")
        conclure(avant, apres, args.fin)
        os.remove(ETAPE)
        return

    # Sans --debut/--fin : les deux relevés dans la même exécution.
    avant = relever(args.condition, args.jusqua)
    montrer(avant, "AVANT")

    if args.outil:
        if args.outil not in C.OUTILS:
            sys.exit(f"outil inconnu ; au choix : {', '.join(C.OUTILS)}")
        fd = os.open(C.PERIPH, os.O_RDWR | os.O_NONBLOCK)
        try:
            C.regler_outil(fd, C.OUTILS[args.outil], args.condition)
        finally:
            os.close(fd)
        intitule = f"lame {args.outil}"
        print(f"\noutil passé à {args.outil}.")
    else:
        intitule = "la manipulation au panneau"
        print("\nChange UNE SEULE chose sur la machine, puis reviens à READY.")
        input("Entrée quand c'est fait… ")

    apres = relever(args.condition, args.jusqua)
    conclure(avant, apres, intitule)


if __name__ == "__main__":
    main()
