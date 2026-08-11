# -*- coding: utf-8 -*-
"""Régler les conditions de coupe du CE6000-60 depuis le PC.

Le protocole n'est ni HP-GL ni GP-GL : c'est celui de Graphtec, relevé le
11/08/2026 en capturant le flux USB de son propre logiciel (`capture_usb.py`).

    ESC . v : TC1002,<paramètre>,<condition>,<valeur> ␃

**Puis il faut mener la transaction à son terme** : interroger l'état par
`ESC.v:ESC.C1:`, qui répond `8` tant que la machine traite et `0` quand
c'est fini. Envoyée seule, la commande fait réagir la machine et ne règle
RIEN — c'est ce qui a fait croire pendant une soirée qu'elle était sourde.

Paramètres identifiés, chacun vérifié en le lisant sur le panneau :

    3  vitesse, en cm/s × 10   (250 = 25 cm/s), maximum 640
    4  force, 1 à 38
    5  accélération, 1 à 3 SEULEMENT

Les autres (`TC1002,2`, `TC1002,5`, `TC1002,14`, et les familles `TC1004`,
`TC1006`, `TC1010`) apparaissent dans les captures sans qu'on sache encore
ce qu'ils portent. La méthode pour les nommer est écrite dans le README :
une valeur inhabituelle, et on regarde quel champ du panneau bouge.

ATTENTION : ces réglages sont PERSISTANTS. Ils modifient la condition
enregistrée dans la machine, exactement comme le fait le logiciel Graphtec —
le panneau affichera la nouvelle valeur après le travail.
"""

import os
import select
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8

VITESSE = 3               # cm/s × 10
FORCE = 4                 # 1 à 38
ACCELERATION = 5          # 1 à 3 seulement

# Bornes relevées sur le panneau. La machine ÉCRÊTE sans rien dire : une
# accélération 4 demandée est appliquée à 3, ce qui a d'abord ressemblé à un
# décalage d'une unité. Valider ici évite de croire qu'on a réglé une valeur
# qu'on n'a pas.
BORNES = {
    VITESSE: (1, 640),    # en dixièmes de cm/s : 64 cm/s au maximum
    FORCE: (1, 38),
    ACCELERATION: (1, 3),
}

_ETAT = "\x1b.v:\x1b.C1:"


def _ecrire(fd, texte, delai=15.0):
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError("le traceur n'accepte plus de données")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.003)
    return envoye


def _etat(fd, delai=1.0):
    """Interroge l'état ; rend la chaîne renvoyée, sans son ETX."""
    _ecrire(fd, _ETAT)
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
        if b"\x03" in reponse:
            break
    return reponse.decode("ascii", "replace").strip("\x03 \r\n")


def regler(fd, parametre, valeur, condition=1, patience=30):
    """Écrit un paramètre de condition et attend la fin du traitement.

    Rend la liste des états observés — utile pour comprendre, et pour
    prouver que la transaction s'est bien déroulée : on doit y voir des
    `8` puis un `0`.
    """
    mini, maxi = BORNES.get(parametre, (None, None))
    if mini is not None and not mini <= int(valeur) <= maxi:
        raise ValueError(
            f"paramètre {parametre} : {valeur} hors de [{mini}, {maxi}] — "
            f"la machine écrêterait en silence")
    _ecrire(fd, f"\x1b.v:TC1002,{parametre},{condition},{valeur}\x03")
    etats = []
    for _ in range(patience):
        e = _etat(fd)
        etats.append(e)
        if e == "0":
            break
        time.sleep(0.1)
    return etats


def appliquer(vitesse=None, force=None, acceleration=None,
              condition=1, periph=PERIPH):
    """Règle vitesse (cm/s), force et accélération. Rend un compte rendu."""
    if vitesse is None and force is None and acceleration is None:
        return []
    rendu = []
    fd = os.open(periph, os.O_RDWR | os.O_NONBLOCK)
    try:
        if vitesse is not None:
            etats = regler(fd, VITESSE, int(round(vitesse * 10)), condition)
            rendu.append(("vitesse", vitesse, etats[-1] if etats else "?"))
        if force is not None:
            etats = regler(fd, FORCE, int(force), condition)
            rendu.append(("force", force, etats[-1] if etats else "?"))
        if acceleration is not None:
            etats = regler(fd, ACCELERATION, int(acceleration), condition)
            rendu.append(("accélération", acceleration,
                          etats[-1] if etats else "?"))
    finally:
        os.close(fd)
    return rendu
