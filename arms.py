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


A4 = (210.0, 297.0)       # mm, portrait — le sens où la feuille est chargée


def composer(polylignes, marge=25.0, branche=BRANCHE, epaisseur=1.0,
             bord=10.0, type_repere=2, page=A4, marges=None):
    """Le dessin et ses quatre repères sur une même feuille, en SVG.

    C'est la pièce qui manquait : un motif imprimé AVEC ses repères, pour
    que le traceur retrouve ensuite où il s'est réellement posé. Le banc
    d'essai du 13/08/2026 n'imprimait que les repères, seuls, parce qu'on
    ne savait pas encore si le capteur voyait quoi que ce soit.

    `polylignes` sont en convention machine : millimètres, Y vers le
    haut. `marge` est la distance entre le dessin et l'ANGLE des repères.

    `marges` permet quatre valeurs différentes, comme le panneau de
    Graphtec Studio : `(gauche, droite, bas, haut)`. Attention aux axes —
    gauche et droite sont sur la course du CHARIOT, bas et haut sur
    l'AVANCE du média. C'est la convention de la machine, pas celle d'une
    feuille posée sur une table, et les confondre a déjà coûté deux
    essais. `marge` reste le raccourci quand les quatre sont égales.

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

    `page` est le FORMAT DU PAPIER, A4 portrait par défaut, et le bloc y
    est centré. Une page taillée sur mesure autour du dessin paraissait
    plus économe, mais elle ne l'était qu'en apparence : l'imprimante
    centre ce qu'elle reçoit, donc deux dessins de tailles différentes
    posaient leurs repères à deux endroits différents du papier, décidés
    par le pilote et connus de personne. Or c'est précisément l'endroit
    des repères sur la feuille qui décide si la tête les trouve. Une page
    fixe rend la chose reproductible. `page=None` retrouve l'ancien
    comportement, pour un format non standard.

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

    gauche, droite, bas, haut = marges or (marge, marge, marge, marge)

    # Angles des quatre repères, autour de l'emprise du dessin. `bas` et
    # `haut` bornent l'AVANCE (X machine), `gauche` et `droite` la course
    # du chariot (Y machine).
    ax0, ay0, ax1, ay1 = x0 - bas, y0 - gauche, x1 + haut, y1 + droite
    ecart_x, ecart_y = ax1 - ax0, ay1 - ay0

    if type_repere not in (1, 2):
        raise ValueError("type de repère : 1 ou 2")
    sortant = (type_repere == 1)

    avertissements = []
    if not sortant:
        courtes = [(nom, v) for nom, v in
                   (("gauche", gauche), ("droite", droite),
                    ("bas", bas), ("haut", haut)) if v < branche]
        if courtes:
            detail = ", ".join(f"{nom} {v:g}" for nom, v in courtes)
            avertissements.append(
                f"marge(s) plus courte(s) que les branches ({branche:g} mm) "
                f"— {detail} : les repères vont mordre sur le dessin.")
    if ecart_x < 3 * branche or ecart_y < 3 * branche:
        avertissements.append(
            "dessin très petit devant les repères : la machine peut "
            "confondre deux repères voisins.")

    # L'encombrement du bloc. En type 2 les branches rentrent, donc les
    # angles SONT les points extrêmes. En type 1 elles sortent, et il faut
    # leur faire place — sans quoi les repères seraient rognés.
    debord = branche if sortant else 0.0
    bloc_l = ecart_x + 2*debord
    bloc_h = ecart_y + 2*debord

    if page:
        page_l, page_h = page
        if bloc_l + 2*bord > page_l or bloc_h + 2*bord > page_h:
            avertissements.append(
                f"le bloc fait {bloc_l:.0f} × {bloc_h:.0f} mm et ne tient "
                f"pas sur {page_l:.0f} × {page_h:.0f} mm avec {bord:g} mm "
                f"de bordure : réduire le dessin, la marge, ou changer de "
                f"format.")
        # CENTRÉ sur la page : c'est ce que fait de toute façon le pilote
        # d'impression, autant le décider nous-mêmes et le savoir.
        dx = (page_l - bloc_l) / 2 + debord - ax0
        dy = (page_h - bloc_h) / 2 + debord - ay0
    else:
        page_l, page_h = bloc_l + 2*bord, bloc_h + 2*bord
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
        # Position du dessin depuis l'angle du repère 1, dans l'ordre
        # machine : avance d'abord, chariot ensuite.
        "origine_dessin": (bas, gauche),
        "marges": (gauche, droite, bas, haut),
        "emprise": (x1 - x0, y1 - y0),
        "type_repere": type_repere,
        # Où l'angle du premier repère tombe sur la FEUILLE. C'est ce qui
        # décide si la tête le trouve : trop près du bord, elle rencontre
        # le bord avant lui.
        "bords": (ax0 + dx, ay0 + dy),
        "avertissements": avertissements,
    }


def tient_dans_la_zone(ecart, zone, premier=None, branche=BRANCHE):
    """Le jeu de repères est-il ATTEIGNABLE par la tête ?

    La question n'est pas de savoir s'il tient sur la feuille : c'est la
    zone que la machine peut balayer qui borne, et elle est plus petite.
    `zone` vient de `OH;`, pour le média réellement chargé.

    `premier` est la position de l'angle du premier repère dans le repère
    de la MACHINE, si on la connaît. Sans elle on suppose le cas le plus
    favorable — le premier repère à l'origine — ce qui donne un
    avertissement optimiste, et c'est dit.

    Écrit le 14/08/2026 après un « HORS SURFACE » qui se calculait :
    premier repère à 34 mm, écart de 225,9 mm, zone utile de 255,9 mm.
    Le repère opposé tombait à 259,9 mm, quatre millimètres hors
    d'atteinte. La machine l'a découvert en s'y cassant le nez ; le
    logiciel pouvait le dire avant d'imprimer la feuille.
    """
    ennuis = []
    ox, oy = premier or (0.0, 0.0)
    for valeur, debut, limite, axe in ((ecart[0], ox, zone[0], "l'avance"),
                                       (ecart[1], oy, zone[1], "le chariot")):
        bout = debut + valeur
        if bout > limite:
            ennuis.append(
                f"sur {axe} : le repère opposé tombe à {bout:.1f} mm alors "
                f"que la machine n'atteint que {limite:.1f} mm — "
                f"{bout - limite:.1f} mm de trop. Réduire la marge de "
                f"{(bout - limite) / 2:.0f} mm au moins, ou le dessin.")
        elif bout > limite - branche:
            ennuis.append(
                f"sur {axe} : le repère opposé est à {limite - bout:.1f} mm "
                f"du bord de la zone utile, moins qu'une branche de repère "
                f"({branche:g} mm). Le capteur risque de manquer de place.")
    if ennuis and premier is None:
        ennuis.append(
            "calculé en supposant le premier repère À L'ORIGINE machine ; "
            "s'il en est écarté, c'est pire d'autant.")
    return ennuis


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

# `TB55` n'est PAS le numéro du type affiché : c'est un CODE. Le binaire
# de Cutting Master 3 porte une méthode `RegMarkType_Studio_to_PCode`,
# une table de conversion entre le type montré à l'utilisateur et la
# valeur envoyée — relevée le 14/08/2026, voir notes/cutting_master_3.md.
#
# Ça explique que Studio dessine des repères de TYPE 2 dans son propre
# PDF tout en envoyant `TB55,1`, ce qu'on prenait pour une incohérence.
# La correspondance exacte reste à établir ; l'essai de `TB55,2` du
# 13/08/2026 n'avait donc aucune raison d'aboutir, et n'a rien changé.
TB55_DOUTEUX = ("TB55 vaut 1 chez Studio alors que son gabarit est de "
                "type 2, et c'est une CONSTANTE dans Cutting Master 3 : "
                "ce champ ne porte pas le type de repère.")

# `TB57` est le seul paramètre dont un binaire officiel dise qu'il porte
# un mode — `AccumPCode_TB57_MODE` dans Cutting Master 3 — et il n'y
# figure pas parmi les chaînes constantes, donc il est construit à
# l'exécution. C'est le candidat qui reste, et celui qu'on n'a jamais
# essayé : on envoie `TB57,1,1` depuis le début sans savoir ce que ça
# demande.
TB57_PORTE_UN_MODE = True


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
                  type_repere=1, tb57=(1, 1), tb50=None, queue=False):
    """Les commandes `TB` d'une détection, dans l'ordre de la capture.

    Les valeurs qui portent une cote sont CALCULÉES à partir des
    millimètres, jamais recopiées de la capture : un chiffre recopié
    vieillit. `TB51,800` vaut 800 parce que 20 mm font 800 unités, pas
    parce qu'on l'a lu quelque part.

    `ecart_x` est l'axe d'AVANCE, `ecart_y` celui du chariot — l'ordre de
    `TB124` dans la capture du 13/08/2026.

    `tb57` est le seul paramètre dont on sache qu'il porte un MODE, et le
    seul qu'on n'ait jamais fait varier. Le binaire de Cutting Master 3
    nomme une routine `AccumPCode_TB57_MODE`, et `TB57` n'y figure pas
    parmi les chaînes constantes : il est donc construit à l'exécution,
    ses valeurs changent selon ce qu'on demande. Voir
    `notes/cutting_master_3.md`.

    `type_repere` part dans `TB55`. On sait maintenant que c'est
    probablement inutile de le faire varier — `TB55,1` est une CONSTANTE
    dans CM3 comme dans Studio, quel que soit le type de repère du
    travail. Le réglage reste offert parce qu'un essai coûte moins qu'une
    certitude empruntée.
    """
    u = UNITES_PAR_MM
    tete = [f"TB50,{tb50}", "TB50,0"] if tb50 is not None else []
    fin = ["TB123", "TB23"] if queue else []
    return (["TB99"] + tete + [
        f"TB57,{tb57[0]},{tb57[1]}", "TB59,0,0", "TB52,1",
        f"TB51,{round(branche * u)}",
        f"TB53,{round(epaisseur * u)}",
        f"TB55,{type_repere}",
        "TB54,0,0",
        f"TB124,{round(ecart_x * u)},{round(ecart_y * u)}",
    ] + fin + ["TB99"])


def scanner(ecart_x, ecart_y, branche=BRANCHE, epaisseur=1.0,
            type_repere=1, periph=None, patience=90.0, journal=None,
            tb57=(1, 1), depart=None, tb50=None, queue=False,
            depart_avant_declenchement=False):
    # `type_repere` part dans `TB55`. Sa numérotation n'est PAS établie :
    # voir TB55_DOUTEUX. C'est pour ça qu'il est réglable et non deviné.
    """Lance une détection depuis le PC. NON ÉPROUVÉ — voir l'en-tête.

    `depart_avant_declenchement` place le déplacement ENTRE les paramètres
    et le `TB99` final, au lieu d'avant toute la séquence. C'est l'ordre
    du panneau, décrit par Christophe le 14/08/2026 : la machine prend ses
    paramètres, PUIS demande de positionner, PUIS part sur [ENTER]. Le
    second `TB99` est très probablement ce [ENTER].

    `depart` amène la POINTE de l'outil en (x, y) millimètres avant de
    lancer la séquence. C'est ce que le panneau fait faire à la main —
    « positionnez le chariot dans la zone de détection du 1er repère » —
    et c'est la seule chose que notre code n'ait jamais faite, en
    automatique comme en manuel. Sans elle la machine cherche depuis là
    où elle dort, et rencontre le bord de la feuille avant le repère.

    Rend `(annonces, journal)`. Une annonce est `(instant, texte)`. La
    seule forme connue à ce jour est `1,254`, laissée par un scan qui a
    ÉCHOUÉ ; celle d'une réussite n'a jamais été observée.
    """
    journal = journal if journal is not None else []
    fd = os.open(periph or conditions.PERIPH, os.O_RDWR | os.O_NONBLOCK)
    depart_t = time.monotonic()
    ecoute = Ecoute(fd, journal)
    try:
        # Ce qui dort dans le tampon vient du coup précédent : un scan
        # lancé au panneau y laisse parfois son annonce, qui attend un
        # lecteur. On la ramasse au lieu de la jeter.
        ecoute.guetter(depart_t, 0.5)

        libre = ecoute.demander(ETAT_SIMPLE, depart_t)
        if libre not in ("0", ""):
            journal.append(f"la machine n'est pas libre (C1 = {libre}) — "
                           f"le scan risque de ne pas partir")

        def aller():
            # Le déplacement passe par HP-GL, sur le MÊME descripteur :
            # rouvrir le périphérique rendrait la machine muette.
            dx, dy = round(depart[0] * UNITES_PAR_MM), \
                round(depart[1] * UNITES_PAR_MM)
            conditions._ecrire(fd, f"SP1;PU{dx},{dy};")
            # ATTENDRE QU'ELLE SOIT ARRIVÉE, et non un délai fixe. Deux
            # essais identiques du 14/08/2026 ont donné 4,8 s et 7,6 s de
            # recherche : avec une attente aveugle de 1,5 s, le scan
            # partait pendant que le chariot roulait encore, et la vraie
            # position de départ dépendait d'où il venait.
            t0 = time.monotonic()
            while time.monotonic() - t0 < 20.0:
                if ecoute.demander(ETAT_SIMPLE, depart_t, delai=0.5) == "0":
                    break
                time.sleep(0.2)
            arrivee = time.monotonic() - t0
            journal.append(f"tête amenée à {depart[0]:g} ; {depart[1]:g} mm "
                           f"— immobile après {arrivee:.1f} s")

        if depart and not depart_avant_declenchement:
            aller()

        conditions._ecrire(fd, PREAMBULE)
        conditions._ecrire(fd, PREAMBULE)
        sequence = sequence_scan(ecart_x, ecart_y, branche, epaisseur,
                                 type_repere, tb57, tb50, queue)
        # Le DERNIER TB99 est très probablement le déclencheur — l'écran
        # du panneau demande de positionner juste avant son équivalent,
        # la touche ENTER.
        for commande in sequence[:-1]:
            conditions._ecrire(fd, f"\x1b.v:{commande}\x03")
        if depart and depart_avant_declenchement:
            aller()
        conditions._ecrire(fd, f"\x1b.v:{sequence[-1]}\x03")

        sens = {"0": "au repos", "1": "elle cherche",
                "6": "terminé", "10": "terminé"}
        precedent, cherche = None, False
        while time.monotonic() - depart_t < patience:
            valeur = ecoute.demander(ETAT_RICHE, depart_t, delai=0.6)
            if valeur != precedent:
                t = time.monotonic() - depart_t
                journal.append(f"{t:5.1f} s  C11 = {valeur or '?'}  "
                               f"{sens.get(valeur, '')}")
                precedent = valeur
            if valeur == "1":
                cherche = True
            if cherche and valeur in ("6", "10"):
                # L'annonce précède l'état terminal de quelques dizaines de
                # millisecondes — mais rien ne dit qu'il n'en vient qu'une.
                ecoute.guetter(depart_t, 2.0)
                break
            ecoute.guetter(depart_t, 0.3)

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
