#!/usr/bin/env python3
"""Le print & cut : ce que la machine attend d'une feuille imprimée.

ARMS lit des repères imprimés pour retrouver où le dessin s'est réellement
posé, puis découpe dessus. Ce module ne pilote rien — il **lit** les
réglages de la machine et signale ce qui contredit la feuille qu'on
s'apprête à employer.

Il existe parce que le 13/08/2026, `MARK TYPE=2` est resté invisible des
heures dans un vidage de configuration pendant qu'on cherchait ailleurs.
Un réglage qui décide de tout et que personne ne regarde vaut une panne.

CE QUI EST MESURÉ, ET CE QUI NE L'EST PAS. Le point de chute du type 2 a
été relevé sur le papier, en trois croix comparées à celle du gabarit. Le
type 1 ne l'a pas été. Les deux sont ici, mais pas au même titre.
"""

import etat_machine

# Le CD livré avec la machine porte les gabarits de Graphtec, datés de 2008 :
# `GRAPHTEC-CD/ARMS Test Files/ARMStest_type{1,2}.pdf`. Ils valent mieux que
# tout ce qu'on redessine, et leurs cotes sont relevées sur le fichier même,
# pas recopiées d'une documentation.
CHEMIN_CD = "~/Projets/logiciels/GRAPHTEC-CD/ARMS Test Files"

PAGE = (208.8, 296.3)     # mm — ce n'est PAS de l'A4, d'où le piège ci-dessous
BRANCHE = 20.0            # longueur d'une branche de L
CROIX = 40.0              # la croix témoin au centre des quatre repères

# Boîte englobante des quatre repères, identique pour les deux types.
BOITE = (150.0, 160.0)

GABARITS = {
    1: dict(fichier="ARMStest_type1.pdf",
            angles="vers l'intérieur — repères HORS de la zone de découpe",
            # L'angle du L est au coin INTÉRIEUR de la boîte : la distance
            # d'angle à angle vaut donc 110 x 120, pas 150 x 160. NON VÉRIFIÉ
            # sur la machine — ne pas s'en servir comme d'un fait.
            ecarts=None,
            chute=None),
    2: dict(fichier="ARMStest_type2.pdf",
            angles="vers l'extérieur — repères DANS la zone de découpe",
            ecarts=(150.0, 160.0),
            # MESURÉ le 13/08/2026 en trois croix : le centre des quatre
            # repères tombe à 75 ; 75 mm de l'origine posée par la détection.
            # La géométrie en prédisait 75 ; 80 — les 5 mm de l'axe d'avance
            # restent INEXPLIQUÉS. Voir notes/protocole_arms.md.
            chute=(75.0, 75.0)),
}

# Les clés du vidage `TC2009,5` qui décident d'une détection, et leur nom
# en clair. L'ordre est celui dans lequel on veut les lire, pas celui de
# la machine.
UTILES = [
    ("MARK TYPE", "type de repère"),
    ("NUMBER OF POINTS", "nombre de points"),
    ("MARK SIZE", "taille des repères (mm)"),
    ("MARK AUTO SCAN", "recherche automatique"),
    ("SENSING LEVEL(X,Y)", "niveau de détection"),
    ("MARK DISTANCE x,y", "distance entre repères"),
    ("MARK OFFSET x,y", "offset origine / repère"),
    ("MARK SCAN MODE", "mode de balayage"),
    ("RM SENSOR LEVEL ADJ SELECT", "calibration employée"),
]


def reglages(sections):
    """Section `[ARMS]` d'un vidage -> [(libellé, clé, valeur)].

    `sections` vient de `etat_machine.analyser()`. Rend une liste plutôt
    qu'un dictionnaire : l'ordre de lecture porte du sens, le type de
    repère d'abord parce que c'est lui qui fait rater une détection sans
    qu'on comprenne pourquoi.
    """
    arms = sections.get("ARMS", {})
    return [(libelle, cle, arms.get(cle, "?")) for cle, libelle in UTILES]


def lire(periph=None, fd=None):
    """Interroge la machine et rend ses réglages ARMS.

    Passe par `TC2009,5`, qui rend la configuration entière en clair. Ne
    PAS appeler juste avant un envoi : une grosse lecture laisse la
    machine muette si l'on referme le périphérique derrière.
    """
    texte = (etat_machine.lire(periph, fd) if periph
             else etat_machine.lire(fd=fd))
    return reglages(etat_machine.analyser(texte))


def _nombre(texte):
    """Premier nombre d'une valeur du vidage, ou None. `20.0` -> 20.0."""
    chiffres = ""
    for c in str(texte):
        if c.isdigit() or (c == "." and "." not in chiffres):
            chiffres += c
        elif chiffres:
            break
    try:
        return float(chiffres)
    except ValueError:
        return None


def desaccords(reglages_lus, type_gabarit=2, branche=BRANCHE):
    """Ce qui, dans la machine, contredit le gabarit qu'on va employer.

    Rend une liste de phrases. Vide = rien à signaler, ce qui ne veut pas
    dire que la détection réussira : ce module ne voit que les réglages,
    pas la feuille.
    """
    lu = {cle: valeur for _, cle, valeur in reglages_lus}
    ennuis = []

    type_machine = _nombre(lu.get("MARK TYPE"))
    if type_machine is not None and int(type_machine) != int(type_gabarit):
        ennuis.append(
            f"la machine cherche des repères de TYPE {int(type_machine)}, "
            f"le gabarit porte du TYPE {int(type_gabarit)} — elle balaiera "
            f"en cherchant une forme absente du papier, et s'arrêtera sur "
            f"le bord de la feuille, qui offre le même contraste.")

    taille = _nombre(lu.get("MARK SIZE"))
    if taille is not None and abs(taille - branche) > 0.05:
        ennuis.append(
            f"MARK SIZE vaut {taille:g} mm, les branches du gabarit font "
            f"{branche:g} mm.")

    if lu.get("MARK AUTO SCAN") == "OFF":
        ennuis.append(
            "MARK AUTO SCAN est sur OFF : il faudra amener la pointe de "
            "l'outil dans l'angle du premier repère avant de lancer la "
            "détection (menu ARMS, LECTURE MANUELLE REPERES).")

    return ennuis


def marche_a_suivre(type_gabarit=2):
    """Les étapes, dans l'ordre où elles ont fini par marcher."""
    g = GABARITS.get(type_gabarit, GABARITS[2])
    etapes = [
        f"Imprimer {g['fichier']} À L'ÉCHELLE 1. Sa page fait "
        f"{PAGE[0]:g} × {PAGE[1]:g} mm et NON de l'A4 : toute « mise à "
        f"l'échelle » ou « ajuster à la page » fausse la géométrie.",
        "Vérifier au pied à coulisse qu'une branche fait bien "
        f"{BRANCHE:g} mm avant de charger.",
        "Charger la feuille et attendre READY.",
        "Détecter au panneau : [PAUSE/MENU] > [2] ARMS > "
        "[1] LECT. AUTO REPERES.",
        "Envoyer la découpe en mode repérage, pour que IN; ne soit pas "
        "émis — il effacerait l'origine que la détection vient de poser.",
    ]
    if g["chute"]:
        x, y = g["chute"]
        etapes.append(
            f"Repère : le centre des quatre repères tombe à {x:g} ; {y:g} mm "
            f"de l'origine posée par la détection (mesuré le 13/08/2026).")
    return etapes


if __name__ == "__main__":
    import sys
    try:
        lus = lire()
    except Exception as e:                              # pragma: no cover
        sys.exit(f"lecture impossible : {e}")
    print("Réglages ARMS de la machine :\n")
    for libelle, _, valeur in lus:
        print(f"  {libelle:<28} {valeur}")
    ennuis = desaccords(lus)
    print()
    if ennuis:
        print("À CORRIGER avant de scanner :")
        for e in ennuis:
            print(f"  • {e}")
    else:
        print("Rien à signaler du côté des réglages.")
    print("\nMarche à suivre :")
    for i, etape in enumerate(marche_a_suivre(), 1):
        print(f"  {i}. {etape}")
