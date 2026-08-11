#!/usr/bin/env python3
"""Lit la configuration ENTIÈRE du CE6000 en texte clair, et la compare.

`ESC.v:TC2009,5␃` rend quatre kilo-octets décrivant tout ce que la machine
sait d'elle-même : les huit conditions de découpe, les réglages d'outil,
l'ARMS, la surface, le média, l'interface, les commandes. Chaque ligne est
nommée en clair — `STEP PASS=7`, `TOOL UP SPEED=40`, `HP-GL MODEL
EMULATED=7586`.

**Cette commande rend inutile presque toute l'enquête qui a précédé.** On a
passé une journée à nommer des paramètres numériques un par un, en changeant
un réglage au panneau et en comparant deux relevés. La machine savait tout
dire d'un coup, en français, et personne ne le lui avait demandé.

Elle a été trouvée en balayant les familles `TC2000` à `TC2020` sur leurs
paramètres 1 à 25 — après qu'un premier balayage, limité aux paramètres 1
à 3, eut conclu à tort que seules deux familles répondaient.

Ce que la découverte laisse debout de l'enquête :
  - l'ÉCRITURE reste par `TC1002` ; ce vidage ne fait que lire ;
  - le relevé encadrant reste la méthode pour trouver comment ÉCRIRE un
    réglage qu'on sait maintenant lire ;
  - `TC2009,5` ne montre pas non plus tout : il ne dit rien de l'état
    courant du chariot ni du média chargé.

    python3 etat_machine.py                 # tout
    python3 etat_machine.py --section TOOLS
    python3 etat_machine.py --conditions    # les 8 conditions en tableau
    python3 etat_machine.py --enregistrer reference.txt
    python3 etat_machine.py --comparer reference.txt
    python3 etat_machine.py --journal       # le journal d'erreurs horodaté
"""

import argparse
import os
import select
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conditions as C                                      # noqa: E402

VIDAGE = "\x1b.v:TC2009,5\x03"
JOURNAL = "\x1b.v:TC2010,9\x03"


def _lire_long(fd, commande, delai=6.0):
    """Envoie une requête et lit une réponse longue, jusqu'à l'ETX.

    Le délai est généreux : la réponse fait plusieurs kilo-octets là où
    tout le reste du protocole tient en quelques octets, et la couper au
    milieu donnerait un texte plausible mais tronqué -- le pire des
    résultats, puisqu'il s'analyse sans erreur.
    """
    while True:                          # vider ce qui traîne
        prets, _, _ = select.select([fd], [], [], 0.02)
        if not prets:
            break
        try:
            if not os.read(fd, 64):
                break
        except BlockingIOError:
            break

    C._ecrire(fd, commande)
    reponse = b""
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        prets, _, _ = select.select([fd], [], [], 0.05)
        if not prets:
            continue
        try:
            reponse += os.read(fd, 4096)
        except BlockingIOError:
            pass
        if b"\x03" in reponse:
            break
    return reponse.decode("ascii", "replace").strip("\x03")


def lire(periph=C.PERIPH):
    """Rend le vidage complet, en texte."""
    fd = os.open(periph, os.O_RDWR | os.O_NONBLOCK)
    try:
        texte = _lire_long(fd, VIDAGE)
    finally:
        os.close(fd)
    if "CONDITIONS" not in texte:
        raise RuntimeError("réponse inattendue — la machine est-elle sur "
                           f"READY ? Reçu : {texte[:80]!r}")
    return texte


def lire_journal(periph=C.PERIPH):
    """Rend le journal d'erreurs horodaté de la machine.

    Les horodatages sont NÉGATIFS : ce sont des heures écoulées depuis
    maintenant, pas des dates. `-3:22:06` veut dire il y a trois heures.
    """
    fd = os.open(periph, os.O_RDWR | os.O_NONBLOCK)
    try:
        return _lire_long(fd, JOURNAL)
    finally:
        os.close(fd)


def analyser(texte):
    """Vidage -> {section: {clé: valeur}}, en gardant l'ordre.

    Les huit conditions deviennent les sections `No.1`..`No.8`. L'étoile
    qui marque la condition ACTIVE est retenue à part, sous la clé
    `*active*` : c'est elle que la machine emploie quand le fichier ne dit
    rien, donc la perdre serait perdre la moitié du sens.
    """
    sections, courante = {}, None
    for ligne in texte.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        ligne = ligne.rstrip()
        if not ligne:
            continue
        if ligne.startswith("["):
            nom = ligne[1:].split("]")[0]
            actif = "*" in ligne.split("]", 1)[-1]
            courante = sections.setdefault(nom, {})
            if actif:
                courante["*active*"] = "oui"
            continue
        if courante is None:               # l'en-tête, avant toute section
            courante = sections.setdefault("ENTETE", {})
            courante["version"] = ligne.strip()
            continue
        if "=" in ligne:
            cle, valeur = ligne.split("=", 1)
            courante[cle.strip()] = valeur.strip()
    return sections


def aplatir(sections):
    """{(section, clé): valeur} — la forme qui se compare."""
    return {(s, k): v for s, contenu in sections.items()
            for k, v in contenu.items()}


def comparer(avant, apres):
    """Rend {(section, clé): (avant, après)} pour ce qui diffère."""
    a, b = aplatir(analyser(avant)), aplatir(analyser(apres))
    change = {}
    for cle in sorted(set(a) | set(b), key=lambda c: (c[0], c[1])):
        if a.get(cle) != b.get(cle):
            change[cle] = (a.get(cle), b.get(cle))
    return change


COLONNES = ["TOOL", "OFFSET", "SPEED", "FORCE", "ACCEL.",
            "CUT LINE PATTERN", "LTYPE DWN", "LTYPE UP",
            "TANGENTIAL MODE", "OVERCUT S.E."]


def tableau_conditions(sections):
    """Les huit conditions côte à côte, plutôt qu'en huit blocs."""
    lignes = []
    noms = [s for s in sections if s.startswith("No.")]
    if not noms:
        return "aucune condition dans ce vidage."
    entete = f"{'':<18}" + "".join(f"{n:>12}" for n in noms)
    lignes.append(entete)
    lignes.append(f"{'active':<18}" +
                  "".join(f"{('  <<<' if '*active*' in sections[n] else ''):>12}"
                          for n in noms))
    lignes.append("-" * len(entete))
    for col in COLONNES:
        if not any(col in sections[n] for n in noms):
            continue
        lignes.append(f"{col:<18}" +
                      "".join(f"{sections[n].get(col, '-'):>12}" for n in noms))
    return "\n".join(lignes)


def main():
    ap = argparse.ArgumentParser(
        description="Lit toute la configuration du CE6000 en texte clair.")
    ap.add_argument("--section", metavar="NOM",
                    help="n'afficher qu'une section (TOOLS, MEDIA, AREA, "
                         "COMMAND, ARMS, Advance, No.1 à No.8…)")
    ap.add_argument("--conditions", action="store_true",
                    help="les huit conditions en tableau comparatif")
    ap.add_argument("--journal", action="store_true",
                    help="le journal d'erreurs horodaté de la machine")
    ap.add_argument("--brut", action="store_true",
                    help="le vidage tel quel, sans analyse")
    ap.add_argument("--enregistrer", metavar="FICHIER",
                    help="écrit le vidage pour pouvoir y revenir")
    ap.add_argument("--comparer", metavar="FICHIER",
                    help="compare l'état actuel à un vidage enregistré")
    args = ap.parse_args()

    if not os.path.exists(C.PERIPH):
        sys.exit(f"{C.PERIPH} absent : traceur allumé ?")

    if args.journal:
        texte = lire_journal()
        print(texte if texte.strip() else "journal vide.")
        print("\nLes horodatages sont NÉGATIFS : des heures écoulées depuis")
        print("maintenant, pas des dates.")
        return

    texte = lire()

    if args.enregistrer:
        open(args.enregistrer, "w").write(texte)
        print(f"vidage écrit dans {args.enregistrer} "
              f"({len(texte)} caractères).")
        return

    if args.comparer:
        if not os.path.exists(args.comparer):
            sys.exit(f"{args.comparer} introuvable.")
        change = comparer(open(args.comparer).read(), texte)
        if not change:
            print("Rien n'a changé depuis ce vidage.")
            return
        print(f"{len(change)} réglage(s) ont changé :\n")
        for (sect, cle), (a, b) in change.items():
            print(f"   [{sect}] {cle}")
            print(f"        {a}  ->  {b}")
        return

    if args.brut:
        print(texte)
        return

    sections = analyser(texte)

    if args.conditions:
        print(tableau_conditions(sections))
        return

    if args.section:
        nom = next((s for s in sections
                    if s.lower() == args.section.lower()), None)
        if nom is None:
            sys.exit(f"section inconnue ; au choix : {', '.join(sections)}")
        print(f"[{nom}]")
        for cle, valeur in sections[nom].items():
            print(f"   {cle:<28} {valeur}")
        return

    for nom, contenu in sections.items():
        print(f"\n[{nom}]" + ("   <<< condition active"
                             if "*active*" in contenu else ""))
        for cle, valeur in contenu.items():
            if cle == "*active*":
                continue
            print(f"   {cle:<28} {valeur}")


if __name__ == "__main__":
    main()
