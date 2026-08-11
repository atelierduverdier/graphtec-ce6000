# -*- coding: utf-8 -*-
"""Réglages par matériau, relevés à l'établi.

Ces valeurs viennent du carnet de Christophe, tenu à l'usage réel de la
machine sous Windows. Elles n'ont pas été calculées : elles ont été trouvées
en coupant du papier, ce qui les rend plus sûres que n'importe quel modèle.

DEUX RÉGLAGES NE SONT PAS PILOTABLES et doivent se faire à la main :

  - **la hauteur de lame**, sur le porte-lame lui-même. C'est le
    dépassement de la pointe, et il suit l'épaisseur du support : 0,10 mm
    de papier demande 0,17 de lame, 0,42 en demande 0,55. Aucune commande
    n'y touche, et une lame mal sortie ne se rattrape par aucune force.
  - **la perforation**, tant qu'elle n'est pas faite en logiciel. Notée
    `(coupé, laissé)` en mm : `(8, 0.25)` coupe 8 mm puis épargne 0,25.

Le `passages` est en revanche gratuit chez nous : retracer le même chemin
deux fois est une affaire de trois lignes, et c'est ce que Christophe
faisait pour ses plumes — d'où le trait pâle de notre premier essai, dont
la réponse était dans ce carnet.
"""

MATERIAUX = {
    "papier 80-90 g": dict(
        vitesse=20, force=10, acceleration=None, passages=1,
        epaisseur=(0.10, 0.15), hauteur_lame=0.25, perforation=(8.0, 0.25)),
    "papier 300 g": dict(
        vitesse=7, force=25, acceleration=None, passages=1,
        epaisseur=(0.40, 0.45), hauteur_lame=0.55, perforation=(8.0, 0.25)),
    "aquarelle 200 g": dict(
        vitesse=20, force=14, acceleration=None, passages=1,
        epaisseur=(0.30, 0.30), hauteur_lame=0.35, perforation=(8.0, 0.25)),
    "canson 224 g": dict(
        # FORCE À CONFIRMER : le carnet dit 2, or l'aquarelle de même
        # épaisseur demande 14 et le 300 g en demande 25. Sept fois moins
        # à épaisseur égale ne colle pas — probable faute de recopie pour
        # 20. Laissé tel quel et signalé plutôt que corrigé en douce.
        vitesse=20, force=2, acceleration=2, passages=1, doute="force",
        epaisseur=(0.30, 0.30), hauteur_lame=0.40, perforation=(8.0, 0.15)),
    "ingres 80 g": dict(
        vitesse=40, force=10, acceleration=1, passages=1,
        epaisseur=(0.10, 0.10), hauteur_lame=0.17, perforation=(8.0, 0.15)),
    "vinyle 0,20 mm": dict(
        vitesse=20, force=12, acceleration=2, passages=1,
        epaisseur=(0.10, 0.10), hauteur_lame=0.13, perforation=None),
    "feutre Staedtler": dict(
        vitesse=27, force=15, acceleration=None, passages=2,
        epaisseur=None, hauteur_lame=None, perforation=None),
    "stylo Bic": dict(
        vitesse=30, force=10, acceleration=2, passages=2,
        epaisseur=None, hauteur_lame=None, perforation=None),
}


def resume(nom):
    """Une ligne lisible, avec ce qui reste à faire à la main."""
    m = MATERIAUX[nom]
    bouts = [f"{m['vitesse']} cm/s", f"force {m['force']}"]
    if m["acceleration"] is not None:
        bouts.append(f"accél. {m['acceleration']}")
    if m["passages"] > 1:
        bouts.append(f"{m['passages']} passages")
    texte = f"{nom} : " + ", ".join(bouts)
    if m.get("hauteur_lame"):
        texte += f"  |  À LA MAIN : lame à {m['hauteur_lame']} mm"
    if m.get("doute"):
        texte += f"  |  {m['doute'].upper()} À CONFIRMER"
    return texte
