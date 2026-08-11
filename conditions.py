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

    2  type d'outil (voir OUTILS), avec un second champ inexpliqué
    3  vitesse, en cm/s × 10   (250 = 25 cm/s), maximum 640
    4  force, 1 à 38
    5  accélération, 1 à 3 SEULEMENT

**`TC2002` est la LECTURE** du même jeu : `TC2002,<paramètre>,<condition>`
et la machine répond `<condition>, <valeur>…`. Toute écriture est donc
vérifiable, et `appliquer` la vérifie.

Restent inconnus 6, 8, 9, 14, 15 et les familles `TC1004`, `TC1006`,
`TC1010`. Pour les nommer : `chercher_parametre.py` relève tout, laisse
changer une seule chose, relève de nouveau, et la différence désigne le
paramètre.

**Le déport de lame est parmi ces inconnus, et le relevé ne pouvait pas
le trouver.** Changer CB15U → CB09U n'a modifié que le type d'outil, d'où
la conclusion hâtive qu'aucun paramètre ne le portait. Le manuel donne la
vraie raison : le champ OFFSET n'est pas le déport mais une RETOUCHE de
±5 autour, et il vaut **0 par défaut pour les deux lames** — le déport
réel (19 pour la CB09U, 29 pour la CB15U) est appliqué par le firmware
d'après le type. Un paramètre qui vaut 0 avant et 0 après ne se voit pas
dans une différence.

Pour le nommer, il faut donc changer la RETOUCHE et non la lame : sur le
panneau, `CONDITION` puis la touche `[3]` (OFFSET), la porter à 3, et
relancer `chercher_parametre.py`.

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

OUTIL = 2                 # forme particulière : deux valeurs, pas une

# Codes relevés en parcourant la liste du logiciel Graphtec DEUX FOIS de
# haut en bas : la même suite les deux fois, donc une mesure reproduite et
# non une déduction sur un seul passage.
OUTILS = {
    "CB09U": 1,
    "CB09U-K60": 10,
    "CB15U": 2,
    "CB15UB": 3,
    "Autre": 6,
    "Stylo feutre": 9,
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


def lire(fd, parametre, condition=1, delai=1.5, famille=2002):
    """Lit un paramètre : `TC2002,<paramètre>,<condition>`.

    `famille` permet d'interroger les autres jeux relevés à la capture USB
    (`TC1004`, `TC1006`, `TC1010` en écriture, donc `TC2004`, `TC2006`,
    `TC2010` en lecture) : une manipulation au panneau se cherche alors
    dans TOUTES les familles à la fois, plutôt que d'être refaite pour
    chacune.

    La machine répond `<condition>, <valeur>[, <valeur>…]` en ETX, les
    nombres cadrés à droite sur des espaces. Rend la liste des valeurs
    APRÈS le numéro de condition, en entiers.

    C'est le pendant lecture de `TC1002`, et il change la nature du
    dialogue : on peut désormais VÉRIFIER qu'un réglage a été appliqué
    au lieu de le supposer. Toute cette enquête a buté là-dessus.
    """
    # Vider d'abord : une écriture laisse derrière elle les réponses de son
    # sondage d'état, et les lire comme si elles répondaient à la question
    # suivante décale tout. C'est le piège des toutes premières sondes, revenu
    # ici parce que `lire` avait été écrit sans lui.
    while True:
        prets, _, _ = select.select([fd], [], [], 0.02)
        if not prets:
            break
        try:
            if not os.read(fd, 64):
                break
        except BlockingIOError:
            break

    _ecrire(fd, f"\x1b.v:TC{famille},{parametre},{condition}\x03")
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
    champs = reponse.decode("ascii", "replace").strip("\x03 \r\n").split(",")
    try:
        return [int(c.strip()) for c in champs][1:]
    except ValueError:
        return []


def lire_condition(condition=1, periph=PERIPH):
    """Rend {nom: valeur} pour tous les paramètres connus d'une condition."""
    noms = {"outil": OUTIL, "vitesse": VITESSE,
            "force": FORCE, "acceleration": ACCELERATION}
    fd = os.open(periph, os.O_RDWR | os.O_NONBLOCK)
    try:
        rendu = {}
        for nom, param in noms.items():
            valeurs = lire(fd, param, condition)
            rendu[nom] = valeurs[0] if valeurs else None
            if nom == "outil" and len(valeurs) > 1:
                rendu["outil_indicateur"] = valeurs[1]
        return rendu
    finally:
        os.close(fd)


def regler_outil(fd, code, condition=1, indicateur=0, patience=30):
    """Choisit le type d'outil : `TC1002,2,<condition>,<code>,<indicateur>`.

    Cette commande porte DEUX valeurs là où les autres n'en ont qu'une, d'où
    sa fonction propre.

    L'`indicateur` reste à 0 faute de savoir ce qu'il fait. Ce qu'on sait :
    il ne dépend PAS de l'outil. Sur deux parcours de la liste, il valait 0
    puis a basculé à 1 en cours de route et n'en a plus bougé — le code 6 est
    apparu avec les deux valeurs. C'est un état du logiciel Graphtec, pas une
    propriété du réglage.
    """
    _ecrire(fd, f"\x1b.v:TC1002,{OUTIL},{condition},{code},{indicateur}\x03")
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
    """Règle vitesse (cm/s), force et accélération, et RELIT chaque valeur.

    Rend une liste de `(nom, demandé, obtenu, conforme)`. Le dernier champ
    est le seul qui compte : il vient de la machine, pas de nous.
    """
    if vitesse is None and force is None and acceleration is None:
        return []
    demandes = []
    if vitesse is not None:
        demandes.append(("vitesse", VITESSE, int(round(vitesse * 10))))
    if force is not None:
        demandes.append(("force", FORCE, int(force)))
    if acceleration is not None:
        demandes.append(("accélération", ACCELERATION, int(acceleration)))

    rendu = []
    fd = os.open(periph, os.O_RDWR | os.O_NONBLOCK)
    try:
        for nom, param, valeur in demandes:
            regler(fd, param, valeur, condition)
            # CHAQUE écriture est relue. La machine sait dire ce qu'elle a
            # retenu (TC2002) : s'en priver reviendrait à supposer, et c'est
            # une supposition de ce genre qui a fait croire une soirée
            # entière que la vitesse n'était pas pilotable.
            relu = lire(fd, param, condition)
            obtenu = relu[0] if relu else None
            rendu.append((nom, valeur, obtenu, obtenu == valeur))
    finally:
        os.close(fd)
    return rendu


def instantane(condition=1, plage=range(1, 21), periph=PERIPH,
               familles=(2002,)):
    """Relève TOUS les paramètres lisibles d'une condition.

    L'idée est de Christophe, et elle vaut mieux que la précédente : la
    RELECTURE sert d'afficheur à la place du panneau. On photographie l'état,
    on change une chose, on rephotographie, et la différence nomme le
    paramètre — y compris pour les réglages que la machine n'affiche NULLE
    PART, comme le déport de lame.
    """
    fd = os.open(periph, os.O_RDWR | os.O_NONBLOCK)
    try:
        # Interrogation JETÉE. La toute première après ouverture revient
        # décalée : le 11/08/2026, trois relevés d'affilée donnaient 11
        # paramètres rigoureusement identiques, mais celui qui les précédait
        # n'en voyait que 7 -- et y lisait l'accélération (2) à l'index 10
        # au lieu de 5. Toutes les réponses glissées d'un cran, exactement
        # la désynchronisation que `lire` purge déjà, mais qui a besoin d'un
        # aller-retour pour se manifester.
        #
        # Sans ce coup pour rien, deux relevés encadrant une manipulation
        # diffèrent de paramètres qu'on n'a pas touchés, et la différence
        # désigne n'importe quoi avec la même assurance.
        lire(fd, 3, condition, delai=0.7)

        etat = {}
        for f in familles:
            for p in plage:
                valeurs = lire(fd, p, condition, delai=0.7, famille=f)
                if valeurs:
                    etat[(f, p) if len(familles) > 1 else p] = valeurs
        return etat
    finally:
        os.close(fd)


def difference(avant, apres):
    """Ce qui a changé entre deux instantanés : {paramètre: (avant, après)}."""
    change = {}
    for p in sorted(set(avant) | set(apres)):
        a, b = avant.get(p), apres.get(p)
        if a != b:
            change[p] = (a, b)
    return change
