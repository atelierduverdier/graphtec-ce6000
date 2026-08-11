#!/usr/bin/env python3
"""Sonde le Graphtec CE6000-60 sur /dev/usb/lp0.

N'envoie QUE des requetes de lecture HP-GL : aucun deplacement du chariot,
aucune descente de lame.

Trois precautions apprises a la premiere tentative :
  - le canal d'envoi fait 8 octets par paquet et refuse les donnees quand le
    tampon de la machine est plein (EAGAIN) : on ecrit par petits morceaux en
    attendant que le peripherique redevienne disponible ;
  - les reponses se terminent par un retour chariot et s'accumulent : on vide
    le tampon d'entree avant chaque requete, sinon elles se chevauchent ;
  - ce retour chariot ecrase la ligne a l'affichage : on l'echappe.
"""

import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8        # wMaxPacketSize de l'endpoint 1 OUT
DELAI = 2.0              # attente d'une reponse, en secondes
UNITES_PAR_MM = 40.0     # HP-GL : 1 unite = 0,025 mm

# Requetes purement passives. Aucune n'entraine de mouvement.
REQUETES = [
    ("OI;", "identification du modele emule"),
    ("OH;", "limites de la zone de coupe"),
    ("OA;", "position courante du chariot"),
    ("OS;", "octet de statut"),
    ("OF;", "resolution : unites par millimetre"),
]


def ecrire(fd, texte, delai=5.0):
    """Envoie en respectant la taille de paquet et le controle de flux."""
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError(f"le traceur n'accepte plus de donnees ({texte!r})")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.01)          # tampon plein : on laisse respirer
    return envoye


def vider(fd, delai=0.2):
    """Jette ce qui traine dans le tampon d'entree."""
    reste = b""
    while True:
        prets, _, _ = select.select([fd], [], [], delai)
        if not prets:
            return reste
        try:
            bloc = os.read(fd, 64)
        except BlockingIOError:
            return reste
        if not bloc:
            return reste
        reste += bloc


def lire(fd, delai=DELAI):
    """Lit une reponse jusqu'au retour chariot, sans jamais bloquer."""
    morceaux = []
    while True:
        prets, _, _ = select.select([fd], [], [], delai)
        if not prets:
            break
        try:
            bloc = os.read(fd, 64)
        except BlockingIOError:
            break
        if not bloc:
            break
        morceaux.append(bloc)
        if b"\r" in bloc or b"\n" in bloc or b"\x03" in bloc:
            break
        delai = 0.3               # la suite d'une reponse arrive vite
    return b"".join(morceaux)


def lisible(donnees):
    """Rend la reponse affichable : plus de retour chariot qui ecrase la ligne."""
    return (donnees.decode("ascii", "replace")
            .replace("\r", "<CR>").replace("\n", "<LF>").replace("\x03", "<ETX>")
            .strip())


def en_mm(texte):
    """Traduit une reponse en millimetres si c'est une liste de nombres."""
    champs = [c.strip() for c in texte.replace("<CR>", "").split(",")]
    try:
        valeurs = [float(c) for c in champs if c]
    except ValueError:
        return None
    if len(valeurs) < 2:
        return None
    return ", ".join(f"{v / UNITES_PAR_MM:.1f}" for v in valeurs) + " mm"


def main():
    if not os.path.exists(PERIPH):
        sys.exit(f"{PERIPH} absent : le traceur est-il allume et branche ?")

    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        trainard = vider(fd, delai=0.5)
        if trainard:
            print(f"(tampon vide au demarrage : {lisible(trainard)})\n")

        # Un point-virgule seul ferme une commande restee incomplete dans le
        # tampon de la machine : sans lui, elle collerait au debut de la
        # premiere requete et le parseur jetterait les deux.
        ecrire(fd, ";")
        vider(fd, delai=0.5)

        for requete, libelle in REQUETES:
            # On ne jette plus en silence : une reponse trouvee ici est une
            # reponse tardive a la question precedente, pas une absence.
            retard = vider(fd)
            if retard:
                print(f"{'':<5} (arrive en retard : {lisible(retard)})")

            ecrire(fd, requete)
            brut = lire(fd, delai=6.0)      # large : la machine peut trainer
            texte = lisible(brut) or "(pas de reponse)"
            print(f"{requete:<5} {libelle:<32} -> {texte}")
            converti = en_mm(texte)
            if converti:
                print(f"{'':<5} {'soit':<32}    {converti}")

        # Dernier ramassage : une reponse a la toute derniere question.
        tardif = vider(fd, delai=3.0)
        if tardif:
            print(f"\n(arrive apres coup : {lisible(tardif)})")
    finally:
        os.close(fd)

    print(
        "\nLa reponse a OH; donne les deux coins de la zone utile.\n"
        "Sa largeur et sa hauteur sont ce qui va dans la definition machine,\n"
        "et elles dependent du media charge, pas seulement du modele."
    )


if __name__ == "__main__":
    main()
