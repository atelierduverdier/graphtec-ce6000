#!/usr/bin/env python3
"""Mesure la vitesse réelle du tracé, et dit si `VS` la pilote.

On envoie `VS` depuis le premier jour sans l'avoir vérifié. Si le panneau
commande seul, un curseur « vitesse » dans le pupitre mentirait.

DEUX MÉTHODES ONT ÉCHOUÉ AVANT CELLE-CI, et il faut les connaître pour ne
pas les refaire :

1. Placer `OA;` derrière le déplacement en supposant qu'il répondrait à la
   fin. Rendu : 250 mm en 0,13 s, soit 192 cm/s, et VS40 plus lent que VS5.
2. Interroger `OA;` en boucle pendant le trajet pour lire la pente de x(t).
   Rendu : un seul relevé, déjà à l'arrivée.

Les deux échouent pour la même raison : **`OA;` rend la position LOGIQUE**,
celle atteinte après analyse de la commande, pas celle du chariot. Ce n'est
pas un instrument de mesure du mouvement.

MÉTHODE RETENUE. Le seul mécanisme dont on ait la preuve est le contrôle de
flux : l'endpoint fait 8 octets et refuse les données quand le tampon de la
machine est plein. Passé le remplissage initial, **le débit d'écriture
épouse donc le débit de tracé**. On envoie un long parcours et on chronomètre
l'écriture elle-même.

Le tampon initial fausse la mesure d'un même nombre d'OCTETS à chaque
vitesse, jamais d'un même temps : on le rend négligeable avec un parcours
long, et on compare des rapports.

ATTENTION : fait bouger le chariot sur ~3 m de parcours. **PORTE-OUTIL VIDE
de préférence** — le mouvement est identique sans stylo, et la feuille est
épargnée.
"""

import argparse
import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8
UNITES_PAR_MM = 40

X0, Y0 = 20.0, 20.0
LARGEUR, HAUTEUR = 120.0, 40.0
PAS_MM = 2.0             # densité du zigzag ; ~3 m de parcours au total


def u(mm):
    return int(round(mm * UNITES_PAR_MM))


def ecrire(fd, texte, delai=60.0):
    """Écrit, et rend le temps passé à le faire."""
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
            time.sleep(0.002)
    return time.monotonic() - debut


PAS_ECHANT = 2.0         # découpage des lignes, en mm


def parcours(vitesse):
    """Zigzag serré, écrit point par point.

    Le découpage est le coeur de la méthode : les points sont ALIGNÉS, donc
    le mouvement reste une longue passe rectiligne que la machine parcourt à
    pleine vitesse — mais le fichier pèse trente fois plus, et le tampon
    cesse d'absorber le travail avant qu'on ait pu chronométrer.
    """
    lignes = [f"IN;SP1;VS{vitesse};", f"PU{u(X0)},{u(Y0)};"]
    longueur = 0.0
    y = Y0
    gauche = True
    while y <= Y0 + HAUTEUR:
        depart = X0 + LARGEUR if not gauche else X0
        arrivee = X0 if not gauche else X0 + LARGEUR
        pas = PAS_ECHANT if arrivee > depart else -PAS_ECHANT
        x = depart
        while (x < arrivee) if pas > 0 else (x > arrivee):
            x = min(x + pas, arrivee) if pas > 0 else max(x + pas, arrivee)
            lignes.append(f"PD{u(x)},{u(y)};")
        longueur += LARGEUR
        y += PAS_MM
        if y <= Y0 + HAUTEUR:
            lignes.append(f"PD{u(arrivee)},{u(y)};")
            longueur += PAS_MM
        gauche = not gauche
    lignes.append("PU0,0;")
    return "".join(lignes), longueur


def main():
    ap = argparse.ArgumentParser(
        description="Mesure la vitesse réelle de tracé et vérifie `VS`.")
    ap.add_argument("--vitesses", default="5,10,20,40",
                    help="vitesses à comparer, en cm/s (défaut 5,10,20,40)")
    ap.add_argument("--simuler", action="store_true")
    ap.add_argument("--une-passe", type=int, metavar="VS",
                    help="envoie UNE passe à cette vitesse et rend la main : "
                         "à chronométrer à la montre, seul instrument fiable "
                         "trouvé pour cette question")
    args = ap.parse_args()

    if args.une_passe:
        programme, longueur = parcours(args.une_passe)
        if not os.path.exists(PERIPH):
            sys.exit(f"{PERIPH} absent : traceur allumé et sur READY ?")
        fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
        try:
            ecrire(fd, programme)
        finally:
            os.close(fd)
        attendu = longueur / (args.une_passe * 10.0)
        print(f"VS{args.une_passe} : {longueur:.0f} mm envoyés.")
        print(f"Si la commande est écoutée, le tracé dure environ "
              f"{attendu:.0f} s.")
        print("Chronomètre du départ du chariot à son arrêt.")
        return

    try:
        vitesses = [int(v) for v in args.vitesses.split(",") if v.strip()]
    except ValueError:
        sys.exit("--vitesses attend des entiers séparés par des virgules")

    programme, longueur = parcours(vitesses[0])
    print(f"parcours d'essai : {longueur:.0f} mm de tracé, "
          f"{len(programme)} octets\n")
    if args.simuler:
        print(programme[:160], "…")
        print("\nRien n'a été envoyé.")
        return

    if not os.path.exists(PERIPH):
        sys.exit(f"{PERIPH} absent : traceur allumé et sur READY ?")

    mesures = []
    for v in vitesses:
        programme, longueur = parcours(v)
        fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
        try:
            duree = ecrire(fd, programme)
        finally:
            os.close(fd)
        vitesse_vue = longueur / duree if duree > 0 else 0.0
        mesures.append((v, duree, vitesse_vue))
        print(f"  VS{v:<3} demandé {v * 10:>4} mm/s   "
              f"écriture {duree:6.1f} s   "
              f"débit vu {vitesse_vue:6.1f} mm/s")
        time.sleep(2.0)          # laisser la machine finir avant l'essai suivant

    print()
    if len(mesures) < 2:
        sys.exit("pas assez de mesures pour conclure")

    # LA MONOTONIE, pas l'étendue. La première version de cette sonde
    # concluait « ça suit » à partir du seul écart entre durées, ce qui est
    # vrai de n'importe quel bruit.
    croissant = all(mesures[i + 1][2] > mesures[i][2] * 1.10
                    for i in range(len(mesures) - 1))
    debits = [d for _, _, d in mesures]
    plat = (max(debits) - min(debits)) < 0.10 * (sum(debits) / len(debits))

    if croissant:
        print("VERDICT : le débit croît avec `VS` — la commande est écoutée,")
        print("le curseur de vitesse du pupitre a un sens.")
        rapports = [d / (v * 10.0) for v, _, d in mesures]
        print(f"Débit obtenu / consigne : {min(rapports):.2f} à {max(rapports):.2f}")
        if max(rapports) < 0.75:
            print("Toujours SOUS la consigne : l'accélération réglée au")
            print("panneau limite ce que des segments courts peuvent atteindre.")
    elif plat:
        print("VERDICT : le débit ne bouge pas — `VS` est IGNORÉ. La vitesse")
        print("se règle au panneau, CONDITION > VITESSE, et le curseur doit")
        print("disparaître du pupitre plutôt que de mentir.")
    else:
        print("VERDICT : ni constant, ni croissant. Ne rien conclure — c'est")
        print("la mesure qui est en cause. Rallonger le parcours (le tampon")
        print("pèse peut-être encore trop), ou comparer moins de vitesses.")


if __name__ == "__main__":
    main()
