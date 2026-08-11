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

    Le carnet sort TOUJOURS la lame au-delà de l'épaisseur, de +0,05 à
    +0,10 — il faut traverser. Sauf une ligne : le vinyle, +0,03
    seulement. Ce n'est pas une distraction, c'est l'autre métier de la
    machine — on coupe le film et on effleure son support, et c'est ce
    régime-là, et lui seul, que décrit la table du manuel.
  - **la perforation**, tant qu'elle n'est pas faite en logiciel. Notée
    `(coupé, laissé)` en mm : `(8, 0.25)` coupe 8 mm puis épargne 0,25.

Le `passages` est en revanche gratuit chez nous : retracer le même chemin
deux fois est une affaire de trois lignes, et c'est ce que Christophe
faisait pour ses plumes — d'où le trait pâle de notre premier essai, dont
la réponse était dans ce carnet.

`REFERENCE_CONSTRUCTEUR`, plus bas, vient du manuel et ne se mélange PAS
avec ce carnet : voir le commentaire qui l'introduit.
"""

MATERIAUX = {
    # Nuancier en carrés du 11/08/2026, sur chutes de 80 g : la force 8
    # traverse déjà, la 10 est celle qui se détache le mieux. On garde 10,
    # et le seuil est noté — un réglage posé SUR son seuil finit par
    # lâcher : le papier varie, la lame s'émousse. Les deux crans de marge
    # du carnet ne sont pas du gaspillage.
    #
    # Mon critère annoncé était « la force la plus faible qui détache »,
    # ce qui aurait retenu 8. Le carnet avait raison contre le critère.
    #
    # La valeur venait de Graphtec Studio sous Windows ; la retrouver par
    # notre chaîne prouve que `FS` produit le même effet physique que le
    # réglage du logiciel d'origine.
    "papier 80-90 g": dict(
        vitesse=20, force=10, acceleration=None, passages=1, seuil_coupe=8,
        epaisseur=(0.10, 0.15), hauteur_lame=0.25, perforation=(8.0, 0.25),
        lame="CB09U"),
    # Nuancier du 11/08/2026 sur chute de 300 g, lame à 0,55 : la force 16
    # laisse le carré tenir par un coin, 18 traverse. On garde le 25 du
    # carnet -- sept crans de marge, comme le 80 g en garde deux. La marge
    # est ce qui fait qu'une coupe réussit encore quand la lame s'émousse.
    "papier 300 g": dict(
        vitesse=7, force=25, acceleration=None, passages=1, seuil_coupe=18,
        epaisseur=(0.40, 0.45), hauteur_lame=0.55, perforation=(8.0, 0.25),
        # 0,42 mm : c'est la plage de la CB15U (0,25 à 0,5), pas celle de la
        # CB09U (jusqu'à 0,25). Coupé à la CB09U le 11/08/2026 -- ça marche,
        # mais avec une lame sous-dimensionnée qui s'usera plus vite.
        lame="CB15U"),
    # Les quatre profils qui suivent n'ont pas été rejoués au nuancier, et
    # ils n'ont pas à l'être : Christophe, le 11/08/2026, « ce sont mes
    # paramètres testés ». Ils viennent de l'usage réel de la machine sous
    # Windows, ce qui est une mesure — et une meilleure que celle qu'on
    # referait, puisqu'elle porte sur du papier qu'on n'a plus. Les
    # rejouer ne validerait rien qu'ils ne disent déjà.
    "aquarelle 200 g": dict(
        vitesse=20, force=14, acceleration=None, passages=1,
        epaisseur=(0.30, 0.30), hauteur_lame=0.35, perforation=(8.0, 0.25)),
    # CE N'EST PAS UNE DÉCOUPE. Force 2 sur du 224 g paraissait aberrant --
    # l'aquarelle de même épaisseur en demande 14, le 300 g en demande 25 --
    # et j'ai cru à un zéro oublié. Christophe : « c'est juste pour marquer
    # le papier afin de mieux le plier ». La lame RAINE, elle ne traverse
    # pas. Corriger aurait effacé un réglage utile et rendu la ligne de pli
    # impossible à retrouver.
    "canson 224 g — rainage pour pli": dict(
        vitesse=20, force=2, acceleration=2, passages=1, usage="rainer",
        epaisseur=(0.30, 0.30), hauteur_lame=0.40, perforation=(8.0, 0.15)),
    "ingres 80 g": dict(
        vitesse=40, force=10, acceleration=1, passages=1,
        epaisseur=(0.10, 0.10), hauteur_lame=0.17, perforation=(8.0, 0.15)),
    "vinyle 0,20 mm": dict(
        vitesse=20, force=12, acceleration=2, passages=1,
        epaisseur=(0.10, 0.10), hauteur_lame=0.13, perforation=None),
    # `outil` compte autant que la force : déclarer une lame alors qu'une
    # plume est montée fait compenser à la machine un déport qui n'existe
    # pas, et les angles s'arrondissent. C'est la faute symétrique du
    # « Stylo feutre » oublié qui a arrondi une découpe le 11/08/2026.
    "feutre Staedtler": dict(
        vitesse=27, force=15, acceleration=None, passages=2,
        outil="Stylo feutre",
        epaisseur=None, hauteur_lame=None, perforation=None),
    "stylo Bic": dict(
        vitesse=30, force=10, acceleration=2, passages=2,
        outil="Stylo feutre",
        epaisseur=None, hauteur_lame=None, perforation=None),
}


# Table du manuel CE6000 (« Conditions de découpe (lame) pour chaque type de
# matière »). Elle est TENUE À PART du carnet, et pas par scrupule de
# rangement : ce ne sont pas les mêmes découpes.
#
# Le manuel ne parle que de FILMS adhésifs, qu'on effleure — la lame traverse
# le film sans entamer son support, et le manuel le dit ailleurs en toutes
# lettres : « la longueur de la lame doit être légèrement plus courte que
# l'épaisseur de la matière ». Le carnet, lui, TRAVERSE du papier de part en
# part et sort donc la lame PLUS que l'épaisseur : 0,10 mm de papier, 0,17 de
# lame. Les deux règles sont justes, chacune chez elle ; appliquer celle du
# manuel à du papier ne couperait rien.
#
# (épaisseur mini, maxi) en mm, lames possibles, (force mini, maxi),
# (vitesse mini, maxi) en cm/s, accélération.
REFERENCE_CONSTRUCTEUR = {
    "film pour l'extérieur":       ((0.05, 0.08), ("CB09U",), (10, 14), (1, 30), 2),
    "film décoratif":              ((0.08, 0.10), ("CB09U",), (14, 17), (1, 30), 2),
    "film transparent":            ((0.08, 0.10), ("CB09U",), (14, 20), (1, 30), 2),
    "film réfléchissant":          ((0.08, 0.10), ("CB09U",), (14, 20), (1, 30), 2),
    "film fluorescent":            ((0.20, 0.25), ("CB09U", "CB15U"), (20, 24), (10, 20), 2),
    "film pour véhicule":          ((0.05, 0.08), ("CB09U",), (14, 20), (5, 15), 2),
}


def encadrer(nom):
    """Situe un profil du carnet dans la table du manuel, sans le corriger.

    Rend une phrase, ou None si l'épaisseur ne tombe dans aucune ligne du
    manuel — ce qui est le cas de la plupart des papiers, le manuel ne
    couvrant que les films. C'est un repère, PAS un correcteur : le carnet
    a été mesuré sur la vraie machine avec le vrai papier, la table ne l'a
    pas été. En cas de désaccord, le carnet gagne.
    """
    m = MATERIAUX.get(nom)
    if not m or not m.get("epaisseur"):
        return None
    ep = m["epaisseur"][1]
    for matiere, (plage, lames, forces, _, _) in REFERENCE_CONSTRUCTEUR.items():
        if plage[0] <= ep <= plage[1]:
            dedans = forces[0] <= m["force"] <= forces[1]
            return (f"{ep:g} mm — le manuel range « {matiere} » là, "
                    f"force {forces[0]} à {forces[1]} ({'compatible' if dedans else 'hors plage'}), "
                    f"lame {'/'.join(lames)}. Table pour films effleurés, "
                    f"pas pour du papier traversé.")
    return None


def appliquer(nom, condition=1, fd=None):
    """Pousse un profil dans la machine et RELIT chaque valeur.

    Règle AUSSI le type d'outil quand le profil le nomme. L'oublier
    laisserait la machine compenser le déport d'une lame qui n'est pas
    montée — et cette fonction ne réglait que vitesse, force et
    accélération jusqu'au 11/08/2026.

    Ne touche pas à ce qui ne se pilote pas : la hauteur de lame reste à
    faire à la main, et la fonction le rappelle dans son compte rendu.
    """
    import os
    import conditions
    m = MATERIAUX[nom]
    rendu = []
    # UN seul descripteur pour tout : le rouvrir entre deux étapes rend la
    # machine muette (voir conditions.appliquer).
    propre = fd is None
    if propre:
        fd = os.open(conditions.PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        outil = m.get("outil") or m.get("lame")
        if outil in conditions.OUTILS:
            conditions.regler_outil(fd, conditions.OUTILS[outil],
                                    condition=condition)
            relu = conditions.lire(fd, conditions.OUTIL, condition)
            obtenu = relu[0] if relu else None
            attendu = conditions.OUTILS[outil]
            rendu.append(("outil", attendu, obtenu, obtenu == attendu))
        rendu += conditions.appliquer(vitesse=m["vitesse"], force=m["force"],
                                      acceleration=m["acceleration"],
                                      condition=condition, fd=fd)
    finally:
        if propre:
            os.close(fd)
    return rendu, m.get("hauteur_lame")


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
    if m.get("seuil_coupe"):
        texte += f"  |  traverse dès {m['seuil_coupe']}, marge gardée"
    if m.get("lame"):
        texte += f"  |  lame {m['lame']}"
    if m.get("usage") == "rainer":
        texte += "  |  RAINAGE, ne traverse pas"
    return texte
