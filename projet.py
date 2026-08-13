#!/usr/bin/env python3
"""Enregistrer un travail : le dessin ET tous ses réglages.

Écrit parce qu'un placement patiemment ajusté n'existait que dans la
fenêtre ouverte. Le 13/08/2026, un premier print & cut a été perdu ainsi :
le dessin avait été recadré après l'export, la feuille imprimée ne
correspondait plus, et la découpe est tombée à côté sans qu'on puisse
même dire de combien — la mesure était polluée par deux causes mêlées.

LE SVG EST RECOPIÉ DANS LE PROJET, pas seulement son chemin. Un chemin
absolu vieillit : il suffit de ranger ses dossiers pour que le projet ne
retrouve plus rien, et un chemin périmé ressemble exactement à un fichier
corrompu. Le chemin est gardé aussi, mais à titre d'indication.

L'EMPREINTE DU PLACEMENT sert au pupitre à savoir si le dessin a bougé
depuis l'export de la feuille à imprimer. C'est précisément ce qui a
gâché la manche : rien ne signalait que la feuille imprimée ne valait
plus.
"""

import hashlib
import json
import os

VERSION = 1
EXTENSION = ".traceur"

# Les réglages enregistrés, avec le widget qui les porte. Une TABLE plutôt
# que deux fonctions symétriques : deux fonctions dérivent l'une de l'autre
# au premier ajout, et un réglage oublié ne se voit jamais — il reprend
# simplement sa valeur par défaut, en silence.
#
# `tests/test_pupitre.py` exige que tout réglage de l'interface figure ici.
REGLAGES = [
    # média
    ("spn_mx", "reel"), ("spn_my", "reel"),
    # placement
    ("spn_x", "reel"), ("spn_y", "reel"), ("cmb_rot", "texte"),
    ("chk_mx", "bool"), ("chk_my", "bool"), ("spn_ech", "reel"),
    # copies
    ("spn_rang", "entier"), ("spn_col", "entier"),
    ("spn_ex", "reel"), ("spn_ey", "reel"),
    # mosaïque
    ("chk_mosaique", "bool"), ("spn_pan_x", "reel"), ("spn_pan_y", "reel"),
    ("spn_recouv", "reel"),
    # perforation
    ("chk_perfo", "bool"), ("spn_coupe", "reel"), ("spn_saut", "reel"),
    # contour de découpe
    ("chk_contour", "bool"), ("spn_retrait", "reel"), ("chk_trous", "bool"),
    # print & cut
    ("chk_arms", "bool"), ("spn_ecart_av", "reel"), ("spn_ecart_ch", "reel"),
    ("spn_marge_arms", "reel"), ("spn_trait_arms", "reel"),
    ("cmb_type_arms", "texte"),
    # outil
    ("cmb_profil", "texte"), ("cmb_cond", "entier_liste"),
    ("cmb_outil", "texte"), ("spn_offset", "entier"), ("spn_debord", "reel"),
    ("spn_vit", "entier"), ("spn_force", "entier"), ("spn_accel", "entier"),
    ("spn_passages", "entier"), ("chk_regler", "bool"),
    # nuancier
    ("spn_nu_min", "entier"), ("spn_nu_max", "entier"), ("spn_nu_pas", "entier"),
]

# Ce qui décide de l'endroit où le dessin se pose. Si l'un de ces réglages
# change après l'export, la feuille imprimée ne vaut plus.
PLACEMENT = ["spn_x", "spn_y", "cmb_rot", "chk_mx", "chk_my", "spn_ech",
             "spn_rang", "spn_col", "spn_ex", "spn_ey",
             "spn_marge_arms", "chk_contour", "spn_retrait", "chk_trous"]


def empreinte(reglages):
    """Signature courte des réglages qui décident du placement.

    Deux exports du même dessin aux mêmes réglages donnent la même ; un
    recadrage entre les deux la change. C'est tout ce qu'on lui demande.
    """
    morceaux = [f"{nom}={reglages.get(nom)!r}" for nom in PLACEMENT]
    return hashlib.sha256("|".join(morceaux).encode()).hexdigest()[:12]


def enregistrer(chemin, reglages, svg=None, source=None, empreinte_export=None):
    """Écrit un projet. `svg` est le CONTENU du fichier, pas son chemin."""
    if not chemin.endswith(EXTENSION):
        chemin += EXTENSION
    projet = {
        "version": VERSION,
        "source": source,                 # indicatif : un chemin vieillit
        "svg": svg,                       # le dessin lui-même
        "reglages": reglages,
        "empreinte": empreinte(reglages),
        "empreinte_export": empreinte_export,
    }
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(projet, f, ensure_ascii=False, indent=1)
    return chemin


def charger(chemin):
    """Rend le projet. Lève ValueError si ce n'en est pas un."""
    with open(chemin, encoding="utf-8") as f:
        projet = json.load(f)
    if not isinstance(projet, dict) or "reglages" not in projet:
        raise ValueError(f"{os.path.basename(chemin)} n'est pas un projet")
    if projet.get("version", 0) > VERSION:
        raise ValueError(
            f"projet en version {projet['version']}, ce logiciel lit "
            f"jusqu'à {VERSION} — mettre le logiciel à jour")
    return projet


def a_bouge_depuis_export(projet_reglages, empreinte_export):
    """Le dessin a-t-il été déplacé depuis que la feuille a été exportée ?

    Rend False quand aucune feuille n'a été exportée : on ne peut pas
    signaler un désaccord avec une référence qui n'existe pas.
    """
    if not empreinte_export:
        return False
    return empreinte(projet_reglages) != empreinte_export
