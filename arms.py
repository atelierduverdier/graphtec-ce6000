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

import os
import select
import time

import conditions
import etat_machine

# Le CD livré avec la machine porte les gabarits de Graphtec, datés de 2008 :
# `GRAPHTEC-CD/ARMS Test Files/ARMStest_type{1,2}.pdf`. Ils valent mieux que
# tout ce qu'on redessine, et leurs cotes sont relevées sur le fichier même,
# pas recopiées d'une documentation.
CHEMIN_CD = "~/Projets/logiciels/GRAPHTEC-CD/ARMS Test Files"

# Mesuré, pas supposé : réponse de `OF;`. Recopié ici parce qu'importer
# svg2hpgl entraînerait svg_import, donc LaserAtelier, pour un seul entier.
# Un test le compare à sa source — voir test_unites_accordees.
UNITES_PAR_MM = 40

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


# ======================================================================
# LA FEUILLE À IMPRIMER : le dessin ENTOURÉ de ses repères
# ======================================================================


def _coin(x, y, sx, sy, branche, epaisseur):
    """Un L plein dont l'angle est en (x, y) et dont les branches vont
    vers (sx, sy)."""
    e, b = epaisseur, branche
    return [(x, y), (x + sx*b, y), (x + sx*b, y + sy*e), (x + sx*e, y + sy*e),
            (x + sx*e, y + sy*b), (x, y + sy*b)]


def composer(polylignes, marge=25.0, branche=BRANCHE, epaisseur=1.0,
             bord=10.0, type_repere=2):
    """Le dessin et ses quatre repères sur une même feuille, en SVG.

    C'est la pièce qui manquait : un motif imprimé AVEC ses repères, pour
    que le traceur retrouve ensuite où il s'est réellement posé. Le banc
    d'essai du 13/08/2026 n'imprimait que les repères, seuls, parce qu'on
    ne savait pas encore si le capteur voyait quoi que ce soit.

    `polylignes` sont en convention machine : millimètres, Y vers le
    haut. `marge` est la distance entre le dessin et l'ANGLE des repères.

    `type_repere` change le SENS des angles, pas leur position :

        type 2   angles vers l'extérieur, branches qui rentrent — les
                 repères sont DANS la zone de découpe, ce qui laisse la
                 plus grande surface utile
        type 1   angles vers l'intérieur, branches qui sortent — les
                 repères entourent la zone de découpe

    Ce n'est pas un détail d'aspect : la machine cherche la forme réglée
    dans `MARK TYPE`, et un désaccord la fait balayer après une forme
    absente du papier. Le type 1 déborde en outre de `branche` millimètres
    au-delà des angles, ce dont la page tient compte.

    Rend `(svg, infos)`. `infos` porte ce qu'il faudra pour la découpe :
    l'écart à annoncer à la machine, et la position du dessin par rapport
    au premier repère — c'est-à-dire l'offset que le manuel (p. 5-5) dit
    de mesurer, mais qu'on connaît ici par construction puisque c'est nous
    qui posons les deux.
    """
    if not polylignes:
        raise ValueError("aucun dessin à entourer")

    xs = [x for pts, _ in polylignes for x, _ in pts]
    ys = [y for pts, _ in polylignes for _, y in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)

    # Angles des quatre repères, autour de l'emprise du dessin.
    ax0, ay0, ax1, ay1 = x0 - marge, y0 - marge, x1 + marge, y1 + marge
    ecart_x, ecart_y = ax1 - ax0, ay1 - ay0

    if type_repere not in (1, 2):
        raise ValueError("type de repère : 1 ou 2")
    sortant = (type_repere == 1)

    avertissements = []
    if marge < branche and not sortant:
        avertissements.append(
            f"marge de {marge:g} mm plus courte que les branches "
            f"({branche:g} mm) : les repères vont mordre sur le dessin.")
    if ecart_x < 3 * branche or ecart_y < 3 * branche:
        avertissements.append(
            "dessin très petit devant les repères : la machine peut "
            "confondre deux repères voisins.")

    # La page. En type 2 les branches rentrent, donc les angles SONT les
    # points extrêmes. En type 1 elles sortent, et il faut leur faire place
    # des deux côtés — sans quoi les repères seraient rognés à l'impression.
    debord = branche if sortant else 0.0
    page_l = ecart_x + 2*(bord + debord)
    page_h = ecart_y + 2*(bord + debord)
    dx, dy = bord + debord - ax0, bord + debord - ay0

    def _svg_y(v):
        return page_h - v                    # le SVG compte Y vers le bas

    # Le sens des branches : vers le dessin en type 2, vers l'extérieur
    # en type 1. C'est toute la différence entre les deux formes.
    v = -1 if sortant else +1

    chemins = []
    for pts in (_coin(ax0, ay0, +v, +v, branche, epaisseur),
                _coin(ax1, ay0, -v, +v, branche, epaisseur),
                _coin(ax0, ay1, +v, -v, branche, epaisseur),
                _coin(ax1, ay1, -v, -v, branche, epaisseur)):
        d = "M " + " L ".join(f"{x+dx:.3f} {_svg_y(y+dy):.3f}" for x, y in pts)
        chemins.append(f'  <path d="{d} Z" fill="#000000" stroke="none"/>')

    for pts, ferme in polylignes:
        d = "M " + " L ".join(f"{x+dx:.3f} {_svg_y(y+dy):.3f}" for x, y in pts)
        if ferme:
            d += " Z"
        chemins.append(f'  <path d="{d}" fill="none" stroke="#000000" '
                       f'stroke-width="0.2"/>')

    svg = ([f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_l:.2f}mm" '
            f'height="{page_h:.2f}mm" viewBox="0 0 {page_l:.3f} {page_h:.3f}">',
            f'  <rect width="{page_l:.3f}" height="{page_h:.3f}" fill="#fff"/>']
           + chemins + ['</svg>'])

    return "\n".join(svg) + "\n", {
        "ecart": (ecart_x, ecart_y),          # avance, chariot — ordre de TB124
        "page": (page_l, page_h),
        "origine_dessin": (marge, marge),     # depuis l'angle du repère 1
        "emprise": (x1 - x0, y1 - y0),
        "type_repere": type_repere,
        "avertissements": avertissements,
    }


# ======================================================================
# LE SCAN, PILOTÉ DEPUIS LE PC — À ÉPROUVER
# ======================================================================
#
# La séquence vient de l'analyseur USB, relevée pendant que Graphtec
# Studio lançait une détection. Rejouée depuis Linux, elle fait bien
# CHERCHER la machine — mais aucune détection pilotée par le PC n'a
# encore abouti. Toutes celles qui ont réussi le 13/08/2026 ont été
# lancées au panneau.
#
# Ce n'est donc pas un chemin éprouvé, et il est nommé comme tel.

PREAMBULE = "\x1b.v:\x1b.C10:"
ETAT_RICHE = "\x1b.v:\x1b.C11:"      # 0 repos, 1 CHERCHE, 6 et 10 terminaux
ETAT_SIMPLE = "\x1b.v:\x1b.C1:"      # 8 occupée, 0 libre — trop pauvre ici

# `TB55` reste incertain : Studio envoie 1 tout en dessinant des repères
# de TYPE 2 dans son propre PDF. Soit la famille compte à partir de zéro,
# soit ce champ ne désigne pas le type. Dit plutôt que deviné — et laissé
# réglable, parce que c'est le dernier désaccord connu entre ce qu'on
# envoie et ce que la machine annonce dans son vidage (`MARK TYPE=2`).
TB55_DOUTEUX = ("TB55 vaut 1 chez Studio alors que son gabarit est de "
                "type 2 : le sens de ce champ n'est pas établi.")


class Ecoute:
    """Un tampon unique, découpé en trames, qui ne jette RIEN.

    DEUX SORTES DE TRAMES, et c'est la découverte du 13/08/2026 :

        ...\x03   une RÉPONSE à une question qu'on a posée
        ...\r     une ANNONCE que la machine pousse d'elle-même

    Le résultat d'un scan est une annonce. Aucune commande ne le rend :
    `TB50`, `TB100`, `TB124`, `TB125`, `TB126` répondent toujours vide.
    Une première version purgeait le tampon avant chaque question et
    jetait donc l'annonce à tous les coups.

    LE PIÈGE INVERSE, payé le même jour. Le vidage `TC2009,5` est un bloc
    de deux cents lignes **séparées par des CR** et terminé par un seul
    ETX. Une version qui coupait sur les CR sans regarder plus loin a
    donc rapporté deux cents annonces là où il n'y en avait aucune —
    l'instrument mentait dans l'autre sens.

    D'où la règle : **un bloc qui contient un ETX est UNE réponse**,
    quels que soient les CR qu'il porte. Ne sont des annonces que les
    trames terminées par CR sans ETX derrière.

    Cette classe ne sert qu'aux questions à réponse COURTE — les états,
    les lectures `TB`. Le vidage passe par `etat_machine`, qui sait le
    lire d'une pièce.
    """

    def __init__(self, fd, journal=None):
        self.fd = fd
        self.reste = b""
        self.annonces = []
        self.journal = journal if journal is not None else []

    def _avaler(self, delai=0.05):
        prets, _, _ = select.select([self.fd], [], [], delai)
        if not prets:
            return False
        try:
            morceau = os.read(self.fd, 64)
        except BlockingIOError:
            return False
        if not morceau:
            return False
        self.reste += morceau
        return True

    def _noter(self, texte, depart):
        texte = texte.strip()
        if texte:
            self.annonces.append((time.monotonic() - depart, texte))
            self.journal.append(f"annonce : « {texte} »")

    def recolter(self, depart=0.0):
        """Vide le tampon en l'absence de question. Rien n'est jeté en
        silence : ce qui porte un ETX est une réponse en retard, le reste
        est du non-sollicité."""
        while True:
            i_etx = self.reste.find(b"\x03")
            if i_etx >= 0:
                bloc, self.reste = self.reste[:i_etx], self.reste[i_etx + 1:]
                lignes = bloc.decode("ascii", "replace").strip()
                self.journal.append(
                    f"réponse en retard, ignorée ({len(lignes)} caractères)")
                continue
            i_cr = self.reste.find(b"\r")
            if i_cr < 0:
                return
            trame, self.reste = self.reste[:i_cr], self.reste[i_cr + 1:]
            self._noter(trame.decode("ascii", "replace"), depart)

    def demander(self, question, depart=0.0, delai=1.0):
        """Pose une question COURTE et rend sa réponse.

        Ce qui traînait avant la question est récolté ; ce qui arrive
        ensuite, terminé par CR et avant l'ETX, est une annonce poussée
        pendant l'attente — c'est ainsi que « 1,254 » est apparu.
        """
        self._avaler(0.0)
        self.recolter(depart)
        conditions._ecrire(self.fd, question)
        limite = time.monotonic() + delai
        while time.monotonic() < limite:
            self._avaler()
            i_etx = self.reste.find(b"\x03")
            if i_etx < 0:
                continue
            bloc, self.reste = self.reste[:i_etx], self.reste[i_etx + 1:]
            *avant, reponse = bloc.split(b"\r")
            for trame in avant:
                self._noter(trame.decode("ascii", "replace"), depart)
            return reponse.decode("ascii", "replace").strip()
        return ""

    def guetter(self, depart=0.0, duree=0.3):
        """N'interroge rien : écoute seulement."""
        limite = time.monotonic() + duree
        while time.monotonic() < limite:
            self._avaler()
            self.recolter(depart)


def sequence_scan(ecart_x, ecart_y, branche=BRANCHE, epaisseur=1.0,
                  type_repere=1):
    """Les commandes `TB` d'une détection, dans l'ordre de la capture.

    Les valeurs qui portent une cote sont CALCULÉES à partir des
    millimètres, jamais recopiées de la capture : un chiffre recopié
    vieillit. `TB51,800` vaut 800 parce que 20 mm font 800 unités, pas
    parce qu'on l'a lu quelque part.

    `ecart_x` est l'axe d'AVANCE, `ecart_y` celui du chariot — l'ordre de
    `TB124` dans la capture du 13/08/2026.
    """
    u = UNITES_PAR_MM
    return ["TB99", "TB57,1,1", "TB59,0,0", "TB52,1",
            f"TB51,{round(branche * u)}",
            f"TB53,{round(epaisseur * u)}",
            f"TB55,{type_repere}",
            "TB54,0,0",
            f"TB124,{round(ecart_x * u)},{round(ecart_y * u)}",
            "TB99"]


def scanner(ecart_x, ecart_y, branche=BRANCHE, epaisseur=1.0,
            type_repere=1, periph=None, patience=90.0, journal=None):
    # `type_repere` part dans `TB55`. Sa numérotation n'est PAS établie :
    # voir TB55_DOUTEUX. C'est pour ça qu'il est réglable et non deviné.
    """Lance une détection depuis le PC. NON ÉPROUVÉ — voir l'en-tête.

    Rend `(annonces, journal)`. Une annonce est `(instant, texte)`. La
    seule forme connue à ce jour est `1,254`, laissée par un scan qui a
    ÉCHOUÉ ; celle d'une réussite n'a jamais été observée.
    """
    journal = journal if journal is not None else []
    fd = os.open(periph or conditions.PERIPH, os.O_RDWR | os.O_NONBLOCK)
    depart = time.monotonic()
    ecoute = Ecoute(fd, journal)
    try:
        # Ce qui dort dans le tampon vient du coup précédent : un scan
        # lancé au panneau y laisse parfois son annonce, qui attend un
        # lecteur. On la ramasse au lieu de la jeter.
        ecoute.guetter(depart, 0.5)

        libre = ecoute.demander(ETAT_SIMPLE, depart)
        if libre not in ("0", ""):
            journal.append(f"la machine n'est pas libre (C1 = {libre}) — "
                           f"le scan risque de ne pas partir")

        conditions._ecrire(fd, PREAMBULE)
        conditions._ecrire(fd, PREAMBULE)
        for commande in sequence_scan(ecart_x, ecart_y, branche,
                                      epaisseur, type_repere):
            conditions._ecrire(fd, f"\x1b.v:{commande}\x03")

        sens = {"0": "au repos", "1": "elle cherche",
                "6": "terminé", "10": "terminé"}
        precedent, cherche = None, False
        while time.monotonic() - depart < patience:
            valeur = ecoute.demander(ETAT_RICHE, depart, delai=0.6)
            if valeur != precedent:
                t = time.monotonic() - depart
                journal.append(f"{t:5.1f} s  C11 = {valeur or '?'}  "
                               f"{sens.get(valeur, '')}")
                precedent = valeur
            if valeur == "1":
                cherche = True
            if cherche and valeur in ("6", "10"):
                # L'annonce précède l'état terminal de quelques dizaines de
                # millisecondes — mais rien ne dit qu'il n'en vient qu'une.
                ecoute.guetter(depart, 2.0)
                break
            ecoute.guetter(depart, 0.3)

        if not cherche:
            journal.append("elle n'a jamais cherché : machine occupée, ou "
                           "réglages du panneau incompatibles avec le gabarit")
        return ecoute.annonces, journal
    finally:
        os.close(fd)


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
