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

VERSION = 2
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
    ("spn_larg", "reel"), ("spn_haut", "reel"), ("chk_prop", "bool"),
    # copies
    ("spn_rang", "entier"), ("spn_col", "entier"),
    ("spn_ex", "reel"), ("spn_ey", "reel"),
    # mosaïque
    ("chk_mosaique", "bool"), ("spn_pan_x", "reel"), ("spn_pan_y", "reel"),
    ("spn_recouv", "reel"),
    # perforation
    ("chk_perfo", "bool"), ("spn_coupe", "reel"), ("spn_saut", "reel"),
    # rôles des couleurs
    ("cmb_travail", "texte"),
    # contour de découpe
    ("chk_contour", "bool"), ("spn_retrait", "reel"), ("chk_trous", "bool"),
    # print & cut
    ("chk_arms", "bool"), ("spn_ecart_av", "reel"), ("spn_ecart_ch", "reel"),
    ("spn_marge_arms", "reel"), ("spn_trait_arms", "reel"),
    ("cmb_type_arms", "texte"),
    ("spn_corr_av", "reel"), ("spn_corr_ch", "reel"),
    ("spn_tb57a", "entier"), ("spn_tb57b", "entier"), ("spn_tb55", "entier"),
    ("chk_marges4", "bool"), ("spn_mg", "reel"), ("spn_md", "reel"),
    ("spn_mb", "reel"), ("spn_mh", "reel"),
    ("chk_depart", "bool"), ("spn_dep_av", "reel"), ("spn_dep_ch", "reel"),
    ("cmb_imprimante", "texte"), ("chk_gris", "bool"),
    # outil
    ("cmb_profil", "texte"), ("cmb_cond", "entier_liste"),
    ("cmb_outil", "texte"), ("spn_offset", "entier"), ("spn_debord", "reel"),
    ("spn_vit", "entier"), ("spn_force", "entier"), ("spn_accel", "entier"),
    ("spn_passages", "entier"), ("chk_regler", "bool"),
    # nuancier
    ("spn_nu_min", "entier"), ("spn_nu_max", "entier"), ("spn_nu_pas", "entier"),
]

# Ce qui décide de l'endroit où le DESSIN se pose sur la feuille. Si l'un
# de ces réglages change après l'export, la feuille imprimée ne vaut plus.
#
# N'Y FIGURENT PAS le contour, son retrait ni les trous : ils ajoutent un
# tracé AUTOUR du dessin sans le déplacer, et la feuille imprimée reste
# valable. Les y avoir mis faisait crier l'alerte dès qu'on cochait
# « découper autour du dessin » — c'est-à-dire au moment le plus normal du
# travail. Un garde-fou qui crie pour rien finit par ne plus être lu, et
# c'est alors qu'il manque le vrai déplacement.
PLACEMENT = ["spn_x", "spn_y", "cmb_rot", "chk_mx", "chk_my", "spn_ech",
             "spn_larg", "spn_haut", "chk_prop",
             "spn_rang", "spn_col", "spn_ex", "spn_ey",
             "spn_marge_arms",
             "chk_marges4", "spn_mg", "spn_md", "spn_mb", "spn_mh"]


def empreinte(reglages):
    """Signature courte des réglages qui décident du placement.

    Deux exports du même dessin aux mêmes réglages donnent la même ; un
    recadrage entre les deux la change. C'est tout ce qu'on lui demande.
    """
    morceaux = [f"{nom}={reglages.get(nom)!r}" for nom in PLACEMENT]
    return hashlib.sha256("|".join(morceaux).encode()).hexdigest()[:12]


def enregistrer(chemin, reglages, svg=None, source=None, empreinte_export=None,
                correspondance=None, image=None, extension=None):
    """Écrit un projet. `svg` est le CONTENU du fichier, pas son chemin.

    `correspondance` associe une couleur à un rôle. Elle est enregistrée
    à part des réglages parce qu'elle n'a pas de widget fixe : ses lignes
    naissent du fichier ouvert.

    `image` porte les OCTETS d'un fichier matriciel, encodés en base64,
    quand le dessin vient d'un PNG ou d'un JPG. Un tel fichier ne se lit
    pas comme du texte, et le ranger dans `svg` donnait un projet sans
    dessin — qui refusait de se rouvrir en annonçant qu'il était vide.
    `extension` dit de quel format il s'agit, pour le relire pareil.
    """
    if not chemin.endswith(EXTENSION):
        chemin += EXTENSION
    projet = {
        "version": VERSION,
        "source": source,                 # indicatif : un chemin vieillit
        "svg": svg,                       # le dessin lui-même
        "reglages": reglages,
        "empreinte": empreinte(reglages),
        "empreinte_export": empreinte_export,
        "correspondance": correspondance or {},
        "image": image,                   # base64, pour un PNG ou un JPG
        "extension": extension,           # ".png", ".jpg"…
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
    if not projet.get("svg") and not projet.get("image"):
        raise ValueError(
            f"{os.path.basename(chemin)} ne porte aucun dessin — il a "
            f"probablement été écrit par une version qui ne savait pas "
            f"enregistrer les images.")
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
