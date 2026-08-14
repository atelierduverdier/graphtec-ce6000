#!/usr/bin/env python3
"""Imprimer la feuille de repères, à l'échelle EXACTE.

Le print & cut ne tolère aucune mise à l'échelle : la machine cherche les
repères à la distance qu'on lui annonce, et un « ajuster à la page » de
4 % déplace un repère de huit millimètres. C'est le piège qui a coûté le
plus cher le 13/08/2026, et il ne se voit pas — la feuille sort belle.

Ce module existe pour que ce piège ne dépende plus de ce que quelqu'un
pense à cocher : les options qui l'écartent sont écrites ici, une fois, et
un test vérifie qu'elles y sont.
"""

import subprocess

# Les options qui garantissent le 1:1. `fit-to-page=false` interdit
# l'ajustement, `scaling=100` fixe l'échelle. Les deux, parce qu'un
# pilote peut n'écouter que l'une des deux.
SANS_MISE_A_ECHELLE = ["-o", "fit-to-page=false", "-o", "scaling=100"]


def imprimantes():
    """Les files d'impression connues du système, la première étant celle
    par défaut si `lpstat` la désigne."""
    try:
        sortie = subprocess.run(["lpstat", "-a"], capture_output=True,
                                text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    noms = [l.split()[0] for l in sortie.splitlines() if l.split()]
    try:
        defaut = subprocess.run(["lpstat", "-d"], capture_output=True,
                                text=True, timeout=5).stdout
        nom = defaut.rsplit(":", 1)[-1].strip()
        if nom in noms:
            noms.remove(nom)
            noms.insert(0, nom)
    except (OSError, subprocess.SubprocessError):
        pass
    return noms


def commande(chemin, imprimante=None, media="A4", copies=1, gris=False):
    """La ligne de commande, rendue plutôt qu'exécutée — pour qu'un test
    puisse vérifier qu'elle écarte bien la mise à l'échelle."""
    cmd = ["lp"]
    if imprimante:
        cmd += ["-d", imprimante]
    if copies > 1:
        cmd += ["-n", str(copies)]
    cmd += ["-o", f"media={media}"] + SANS_MISE_A_ECHELLE
    if gris:
        # Relevé sur la CP1515n : force le noir seul, sans passer par les
        # cartouches couleur.
        cmd += ["-o", "CMAndResolution=Gray600x600dpi"]
    return cmd + [chemin]


def imprimer(chemin, imprimante=None, media="A4", copies=1, gris=False):
    """Envoie le fichier. Rend l'identifiant du travail, ou lève OSError."""
    cmd = commande(chemin, imprimante, media, copies, gris)
    fait = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if fait.returncode != 0:
        raise OSError(fait.stderr.strip() or "l'impression a échoué")
    return fait.stdout.strip()
