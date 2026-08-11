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

    2  type d'outil (voir OUTILS) ET retouche d'offset, deux champs
    3  vitesse, en cm/s × 10   (250 = 25 cm/s), maximum 640
    4  force, 1 à 38
    5  accélération, 1 à 3 SEULEMENT

**`TC2002` est la LECTURE** du même jeu : `TC2002,<paramètre>,<condition>`
et la machine répond `<condition>, <valeur>…`. Toute écriture est donc
vérifiable, et `appliquer` la vérifie.

Restent inconnus 8, 9, 14, 15, le reste de `TC1002,6` et les familles
`TC2004,6`, `TC2006,13`. Pour les nommer : `chercher_parametre.py` relève
tout, laisse changer une seule chose, relève de nouveau, et la différence
désigne le paramètre.

**L'offset a été nommé ainsi le 11/08/2026**, et il n'était pas là où on
le cherchait : c'est le SECOND champ de `TC1002,2`, celui qu'on avait
laissé de côté comme « inexpliqué ». Offset porté à 3 au panneau, seul
`TC2002,2` bouge, de `[1, 0]` à `[1, 3]`.

Deux essais avaient échoué avant. Changer CB15U → CB09U ne montre rien,
parce que la retouche vaut 0 pour les deux lames — le déport réel (19 et
29) est appliqué par le firmware d'après le type, et un paramètre qui
vaut 0 avant comme après ne se voit dans aucune différence. Et le relevé
lui-même mentait tant qu'il ne jetait pas sa première interrogation.

Ce qui laisse une leçon plus utile que le numéro trouvé : le champ était
visible depuis le début, il passait de 0 à 1 dans la capture USB pendant
que le logiciel Graphtec parcourait ses outils, et les captures d'écran
de ce logiciel affichaient « Offset : 1 ». J'avais écarté les deux d'une
phrase — « un état du logiciel, pas une propriété du réglage » — au lieu
de chercher ce qu'ils avaient en commun.

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

OUTIL = 2                 # forme particulière : type de lame ET offset

# Le second champ de TC1002,2 est la RETOUCHE d'offset, et non le déport.
# Le déport réel (19 pour la CB09U, 29 pour la CB15U) est appliqué par le
# firmware d'après le type de lame ; ce champ ne fait que l'ajuster. Gamme
# lue sur le panneau le 11/08/2026, conforme au manuel.
DEPORT_MINI, DEPORT_MAXI = -5, 5

# Déport intrinsèque de chaque lame, en unités machine (manuel CE6000).
# Donné pour comprendre ce que la retouche retouche : on ne l'écrit pas.
DEPORTS_LAME = {"CB09U": 19, "CB09U-K60": 19, "CB15U": 29, "CB15UB": 29,
                "Stylo feutre": 0}

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


def regler(fd, parametre, valeur, condition=1, patience=30, famille=1002):
    """Écrit un paramètre et attend la fin du traitement.

    `famille` : `1002` écrit une condition de découpe (le second argument
    est alors le numéro de condition) ; `1004` écrit un réglage MACHINE,
    qui ne dépend d'aucune condition — et là le second argument n'est plus
    un numéro de condition mais fait partie de l'adresse. D'où
    `regler_machine`, qui évite la confusion.

    Rend la liste des états observés — utile pour comprendre, et pour
    prouver que la transaction s'est bien déroulée : on doit y voir des
    `8` puis un `0`.
    """
    mini, maxi = BORNES.get(parametre, (None, None))
    if mini is not None and not mini <= int(valeur) <= maxi:
        raise ValueError(
            f"paramètre {parametre} : {valeur} hors de [{mini}, {maxi}] — "
            f"la machine écrêterait en silence")
    _ecrire(fd, f"\x1b.v:TC{famille},{parametre},{condition},{valeur}\x03")
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
                rendu["offset"] = valeurs[1]
        return rendu
    finally:
        os.close(fd)


def regler_outil(fd, code, condition=1, offset=None, patience=30):
    """Choisit le type d'outil : `TC1002,2,<condition>,<code>,<offset>`.

    Cette commande porte DEUX valeurs là où les autres n'en ont qu'une : le
    type de lame ET sa retouche d'offset. C'est ce qui lui vaut sa fonction
    propre — et ce qui la rend dangereuse.

    `offset=None` **relit la valeur en place et la conserve**. Il le faut :
    la commande écrit les deux champs d'un coup, donc choisir un outil en
    passant l'offset en dur l'EFFACE. C'est ce que faisait cette fonction,
    qui envoyait 0 systématiquement — le réglage patiemment posé au panneau
    disparaissait au premier `appliquer` d'un profil.

    Le second champ est resté « inexpliqué » une journée entière. Il a été
    nommé le 11/08/2026 par un relevé encadrant : offset porté à 3 sur le
    panneau (`[COND/TEST]`, `[2]` OUTIL, `[3]` OFFSET), et seul
    `TC2002,2` a bougé, de `[1, 0]` à `[1, 3]`.

    Rétrospectivement il se donnait à voir dans la capture USB, où il
    passait de 0 à 1 pendant que le logiciel Graphtec parcourait la liste
    des outils — et les captures d'écran de ce logiciel affichaient
    « Offset : 1 ». J'avais conclu que c'était « un état du logiciel, pas
    une propriété du réglage ». Deux indices concordants écartés d'une
    phrase, faute d'avoir cherché ce qu'ils avaient en commun.
    """
    if offset is None:
        actuel = lire(fd, OUTIL, condition)
        offset = actuel[1] if len(actuel) > 1 else 0
    elif not DEPORT_MINI <= int(offset) <= DEPORT_MAXI:
        raise ValueError(
            f"offset {offset} hors de [{DEPORT_MINI}, {DEPORT_MAXI}] — "
            f"gamme confirmée au panneau le 11/08/2026")
    _ecrire(fd, f"\x1b.v:TC1002,{OUTIL},{condition},{code},{offset}\x03")
    etats = []
    for _ in range(patience):
        e = _etat(fd)
        etats.append(e)
        if e == "0":
            break
        time.sleep(0.1)
    return etats


# Réglages MACHINE, hors conditions. Forme trouvée le 11/08/2026 :
#
#     ESC.v:TC1004,<paramètre>,<valeur>␃      écriture, PAS de condition
#     ESC.v:TC2004,<paramètre>␃               lecture
#
# La structure du protocole reflète celle du panneau : ce qui se règle sous
# [COND/TEST] vit dans TC1002/TC2002 avec un numéro de condition, ce qui se
# règle sous [PAUSE/MENU] vit dans TC1004/TC2004 sans. Écrire un réglage
# machine à la forme des conditions ne produit RIEN — la transaction se
# déroule normalement, l'état passe par 8 puis 0, et la valeur ne bouge pas.
MACHINE = 1004
MACHINE_LECTURE = 2004

# Nommés en écrivant une valeur et en relisant le vidage en clair de
# `etat_machine.py`, qui désigne la ligne par son nom. Aucune manipulation
# au panneau n'a été nécessaire.
PAS = 3                   # STEP PASS, lissage des courbes, 0 à 20
FORCE_DEPORT = 4          # OFFSET FORCE
ANGLE_DEPORT = 5          # OFFSET ANGLE, stocké × 100
VITESSE_RELEVE = 7        # TOOL UP SPEED, stocké × 10 : la vitesse des
                          # trajets à vide, donc la durée d'un travail
PRIORITE_CONDITION = 8    # 1 = PROGRAM, 0 = MANUEL. Sur MANUEL, `VS` est
                          # silencieusement ignoré — le piège d'une soirée
LAME_INITIALE = 10        # INITIAL BLADE, 2 mm en-deçà / dehors
DEPLACEMENT_RELEVE = 11   # TOOL UP MOVE, activé / désactivé

# (nom dans le vidage, facteur d'échelle, commentaire). L'échelle compte :
# `TOOL UP SPEED` s'affiche 40 et se stocke 400, `OFFSET ANGLE` s'affiche 30
# et se stocke 3000. Écrire la valeur affichée réglerait la machine à un
# dixième ou un centième de ce qu'on croit, sans le moindre avertissement.
REGLAGES_MACHINE = {
    PAS:                ("STEP PASS", 1, "lissage des courbes, 0 à 20"),
    FORCE_DEPORT:       ("OFFSET FORCE", 1, "0 à 20"),
    ANGLE_DEPORT:       ("OFFSET ANGLE", 100, "en degrés"),
    VITESSE_RELEVE:     ("TOOL UP SPEED", 10, "cm/s, trajets à vide"),
    PRIORITE_CONDITION: ("CONDITION PRIORITY", 1, "1 = PROGRAM, 0 = MANUEL"),
    LAME_INITIALE:      ("INITIAL BLADE", 1, "position de contrôle initiale"),
    DEPLACEMENT_RELEVE: ("TOOL UP MOVE", 1, "0/1"),
}

# Restent sans nom dans cette famille, et c'est dit plutôt que deviné :
#   TC2004,1  — l'écriture est RETENUE mais aucune ligne du vidage ne bouge.
#   TC2004,6  — deux champs, à sonder autrement qu'en valeur simple.
#   `DATA SORT` du vidage n'est rattaché à aucun paramètre.


def regler_machine(fd, parametre, valeur, patience=30):
    """Écrit un réglage machine — celui-là ne dépend d'aucune condition."""
    _ecrire(fd, f"\x1b.v:TC{MACHINE},{parametre},{valeur}\x03")
    etats = []
    for _ in range(patience):
        e = _etat(fd)
        etats.append(e)
        if e == "0":
            break
        time.sleep(0.1)
    return etats


def lire_machine(fd, parametre, delai=0.8):
    """Lit un réglage machine : `TC2004,<paramètre>`, sans condition.

    Rend la liste des champs, TOUS conservés — contrairement à `lire`, qui
    laisse tomber le premier parce qu'il y répète le numéro de condition.
    Ici il n'y en a pas, et le jeter perdrait la valeur.
    """
    while True:
        prets, _, _ = select.select([fd], [], [], 0.02)
        if not prets:
            break
        try:
            if not os.read(fd, 64):
                break
        except BlockingIOError:
            break

    _ecrire(fd, f"\x1b.v:TC{MACHINE_LECTURE},{parametre}\x03")
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
        return [int(c.strip()) for c in champs]
    except ValueError:
        return []


def regler_offset(fd, offset, condition=1):
    """Règle la seule retouche d'offset, sans toucher au type de lame.

    La commande écrivant les deux champs ensemble, on relit le type en
    place et on le réécrit tel quel. Sans cette précaution, ajuster
    l'offset changerait la lame déclarée — la faute symétrique de celle
    que `regler_outil` faisait sur l'offset.
    """
    actuel = lire(fd, OUTIL, condition)
    if not actuel:
        raise RuntimeError("type d'outil illisible — la machine est-elle "
                           "sur READY ?")
    return regler_outil(fd, actuel[0], condition, offset=offset)


def appliquer(vitesse=None, force=None, acceleration=None, offset=None,
              condition=1, periph=PERIPH):
    """Règle vitesse (cm/s), force et accélération, et RELIT chaque valeur.

    Rend une liste de `(nom, demandé, obtenu, conforme)`. Le dernier champ
    est le seul qui compte : il vient de la machine, pas de nous.
    """
    if all(v is None for v in (vitesse, force, acceleration, offset)):
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
        if offset is not None:
            regler_offset(fd, offset, condition)
            relu = lire(fd, OUTIL, condition)
            obtenu = relu[1] if len(relu) > 1 else None
            rendu.append(("offset", int(offset), obtenu, obtenu == int(offset)))
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
