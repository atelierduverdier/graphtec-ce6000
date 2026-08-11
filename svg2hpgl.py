#!/usr/bin/env python3
"""SVG -> HP-GL pour traceur de découpe Graphtec CE6000-60.

Réutilise le parseur `svg_import.py` de LaserAtelier : il rend des
polylignes déjà en millimètres, déjà en Y-vers-le-haut, déjà ramenées à
l'origine du viewBox -- c'est-à-dire déjà dans la convention HP-GL.

Repère vérifié au stylo sur la machine le 10/08/2026 :
  - 40 unités par millimètre sur les deux axes (confirmé par `OF;`) ;
  - origine au coin bas-gauche, aucun miroir ;
  - X = sens d'avance du média, Y = course du chariot.

La compensation d'offset de lame n'est PAS calculée ici : le firmware du
CE6000 s'en charge (réglage OFFSET de la condition de coupe). On lui
envoie la polyligne nominale, il place la lame.

Par prudence ce script N'ENVOIE RIEN par défaut : il écrit un fichier.
L'envoi vers la machine demande `--envoyer` explicitement.
"""

import argparse
import math
import os
import select
import sys
import time

CHEMIN_ATELIER = os.path.expanduser(
    "~/.local/share/FreeCAD/v1-1/Mod/LaserAtelier")
sys.path.insert(0, CHEMIN_ATELIER)
try:
    import svg_import
except ImportError:                                    # pragma: no cover
    sys.exit(f"svg_import.py introuvable dans {CHEMIN_ATELIER}")

PERIPH = "/dev/usb/lp0"
UNITES_PAR_MM = 40        # mesuré, pas supposé : réponse de `OF;`
TAILLE_PAQUET = 8         # wMaxPacketSize de l'endpoint 1 OUT
LARGEUR_LIGNE = 240       # caractères par commande PU/PD groupée


# ======================================================================
# A. GÉOMÉTRIE
# ======================================================================

# Formes que le parseur traverse sans rien produire NI rien signaler :
# il ne convertit que les <path>. Un SVG fait de <rect> sortirait vide en
# silence, ce qui ne se verrait qu'une fois le média gâché.
_FORMES_NON_CONVERTIES = ("rect", "circle", "ellipse",
                          "polygon", "polyline", "line")


def _formes_perdues(chemin):
    """Compte les formes géométriques que le parseur va laisser tomber."""
    import xml.etree.ElementTree as ET
    perdues = {}
    for elem in ET.parse(chemin).getroot().iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag in _FORMES_NON_CONVERTIES:
            perdues[tag] = perdues.get(tag, 0) + 1
    return perdues


def charger(chemin):
    """Fichier SVG -> [(points_mm, ferme), ...] + avertissements."""
    records, avertissements = svg_import.parse_svg_file(chemin)
    for tag, nombre in sorted(_formes_perdues(chemin).items()):
        avertissements.append(
            f"{nombre} <{tag}> NON converti(s) : le parseur ne lit que les "
            f"<path>. Dans Inkscape, Chemin > Objet en chemin.")
    polylignes = []
    for record in records:
        for sous in record["subpaths"]:
            points = list(sous["points"])
            if sous["closed"] and len(points) >= 3:
                if _distance(points[0], points[-1]) > 1e-9:
                    points.append(points[0])
            if len(points) >= 2:
                polylignes.append((points, sous["closed"]))
    return polylignes, avertissements


def _distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def pivoter(polylignes):
    """Rotation de 90° : échange la longueur et la largeur du dessin."""
    return [([(y, -x) for x, y in points], ferme)
            for points, ferme in polylignes]


def tourner(polylignes, degres):
    """Rotation de 0, 90, 180 ou 270°, autour de l'origine."""
    degres %= 360
    if degres == 0:
        return polylignes
    tables = {90: lambda x, y: (y, -x),
              180: lambda x, y: (-x, -y),
              270: lambda x, y: (-y, x)}
    if degres not in tables:
        raise ValueError("rotation limitée à 0, 90, 180 ou 270°")
    f = tables[degres]
    return [([f(x, y) for x, y in points], ferme)
            for points, ferme in polylignes]


def refleter(polylignes, selon_x=False, selon_y=False):
    """Miroir. `selon_x` retourne la gauche et la droite, `selon_y` le haut
    et le bas -- nommés d'après l'AXE inversé, comme dans le logiciel
    Graphtec."""
    if not (selon_x or selon_y):
        return polylignes
    sx, sy = (-1.0 if selon_x else 1.0), (-1.0 if selon_y else 1.0)
    return [([(x * sx, y * sy) for x, y in points], ferme)
            for points, ferme in polylignes]


def mettre_a_echelle(polylignes, facteur):
    if facteur == 1.0:
        return polylignes
    return [([(x * facteur, y * facteur) for x, y in points], ferme)
            for points, ferme in polylignes]


def dupliquer(polylignes, rangees, colonnes, ecart_x, ecart_y):
    """Grille de copies. Le pas est l'emprise du motif PLUS l'écart, sinon
    deux copies se chevaucheraient dès que l'écart est inférieur à la
    largeur du dessin."""
    if rangees <= 1 and colonnes <= 1:
        return polylignes
    xmin, ymin, xmax, ymax = cadre(polylignes)
    pas_x = (xmax - xmin) + ecart_x
    pas_y = (ymax - ymin) + ecart_y
    sortie = []
    for j in range(max(1, rangees)):
        for i in range(max(1, colonnes)):
            dx, dy = i * pas_x, j * pas_y
            sortie += [([(x + dx, y + dy) for x, y in points], ferme)
                       for points, ferme in polylignes]
    return sortie


def cadre(polylignes):
    """Rectangle englobant (xmin, ymin, xmax, ymax) en mm."""
    xs = [x for points, _ in polylignes for x, _ in points]
    ys = [y for points, _ in polylignes for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def recadrer(polylignes, marge_x, marge_y):
    """Ramène le dessin au coin bas-gauche, plus la marge demandée."""
    xmin, ymin, _, _ = cadre(polylignes)
    dx, dy = marge_x - xmin, marge_y - ymin
    return [([(x + dx, y + dy) for x, y in points], ferme)
            for points, ferme in polylignes]


def trajet_a_vide(polylignes):
    """Longueur totale parcourue outil levé, en mm."""
    total, position = 0.0, (0.0, 0.0)
    for points, _ in polylignes:
        total += _distance(position, points[0])
        position = points[-1]
    return total + _distance(position, (0.0, 0.0))


def ordonner(polylignes):
    """Range les chemins au plus proche voisin depuis l'origine.

    Les chemins ouverts peuvent être parcourus à l'envers ; les fermés,
    non : leur sens encode le sens de parcours du contour, et le retourner
    n'apporte rien puisqu'on repart de toute façon du même point.
    """
    restants = list(polylignes)
    ordonnees = []
    position = (0.0, 0.0)
    while restants:
        meilleur, cout_min, a_retourner = None, float("inf"), False
        for indice, (points, ferme) in enumerate(restants):
            cout = _distance(position, points[0])
            if cout < cout_min:
                meilleur, cout_min, a_retourner = indice, cout, False
            if not ferme:
                cout = _distance(position, points[-1])
                if cout < cout_min:
                    meilleur, cout_min, a_retourner = indice, cout, True
        points, ferme = restants.pop(meilleur)
        if a_retourner:
            points = points[::-1]
        ordonnees.append((points, ferme))
        position = points[-1]
    return ordonnees


# ======================================================================
# B. TRADUCTION HP-GL
# ======================================================================

def en_unites(points):
    """mm -> unités traceur entières, sans point consécutif redondant.

    L'aplatissement du parseur vise 0,02 mm de flèche alors que la machine
    ne distingue que 0,025 mm : beaucoup de points tombent sur la même
    unité. Les garder gonflerait le fichier sans rien changer au tracé.
    """
    sortie = []
    for x, y in points:
        couple = (int(round(x * UNITES_PAR_MM)), int(round(y * UNITES_PAR_MM)))
        if not sortie or couple != sortie[-1]:
            sortie.append(couple)
    return sortie


def _grouper(prefixe, couples):
    """HP-GL accepte plusieurs couples par PU/PD : on en profite."""
    lignes, courante = [], prefixe
    for x, y in couples:
        morceau = f"{x},{y},"
        if len(courante) + len(morceau) > LARGEUR_LIGNE:
            lignes.append(courante.rstrip(",") + ";")
            courante = prefixe
        courante += morceau
    if courante != prefixe:
        lignes.append(courante.rstrip(",") + ";")
    return lignes


def en_hpgl(polylignes, outil=1, force=None):
    """Rend le programme HP-GL complet.

    `FS` est bien écouté par cette machine : vérifié au nuancier du
    10/08/2026, où seules les forces basses donnaient un trait plus pâle.
    Laisser `force` à None garde le réglage de la condition du panneau,
    ce qui reste le choix par défaut : les conditions vivent dans la
    machine, réglées sur le vrai matériau.

    **`VS` n'est PAS émis, parce que cette machine l'ignore.** Mesuré le
    10/08/2026 : le même parcours de 2560 mm envoyé à VS5 puis à VS40 --
    huit fois l'écart -- a duré 30 s dans les deux cas, soit 85 mm/s, la
    vitesse de la condition réglée au panneau. Un réglage qui ne fait rien
    est pire qu'absent : il fait croire qu'on a agi.
    """
    lignes = ["IN;"]
    if force:
        lignes.append(f"FS{force};")
    lignes.append(f"SP{outil};")

    ignorees = 0
    for points, _ in polylignes:
        couples = en_unites(points)
        if len(couples) < 2:
            ignorees += 1        # tout le chemin tient dans une unité
            continue
        lignes += _grouper("PU", couples[:1])
        lignes += _grouper("PD", couples[1:])

    lignes += ["PU0,0;", "SP0;"]
    return "\n".join(lignes) + "\n", ignorees


# ======================================================================
# C. LIAISON AVEC LA MACHINE
# ======================================================================

def _ecrire_brut(fd, texte, delai=15.0):
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError("le traceur n'accepte plus de données")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.01)     # tampon plein : on laisse respirer
    return envoye


def _lire_brut(fd, delai=6.0):
    morceaux = []
    while True:
        prets, _, _ = select.select([fd], [], [], delai)
        if not prets:
            break
        try:
            bloc = os.read(fd, 64)
        except BlockingIOError:
            break
        if not bloc:
            break
        morceaux.append(bloc)
        if b"\r" in bloc or b"\n" in bloc:
            break
        delai = 0.3
    return b"".join(morceaux)


def limites_machine():
    """Interroge `OH;` -> (largeur_x_mm, largeur_y_mm), ou None."""
    if not os.path.exists(PERIPH):
        return None
    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        _ecrire_brut(fd, ";")
        _lire_brut(fd, delai=0.3)
        _ecrire_brut(fd, "OH;")
        reponse = _lire_brut(fd).decode("ascii", "replace").strip()
    finally:
        os.close(fd)
    try:
        x1, y1, x2, y2 = (float(v) for v in reponse.split(","))
    except ValueError:
        return None
    return (x2 - x1) / UNITES_PAR_MM, (y2 - y1) / UNITES_PAR_MM


def envoyer(programme):
    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        return _ecrire_brut(fd, programme)
    finally:
        os.close(fd)


# ======================================================================
# D. LIGNE DE COMMANDE
# ======================================================================

def main():
    ap = argparse.ArgumentParser(
        description="Convertit un SVG en HP-GL pour le Graphtec CE6000-60.")
    ap.add_argument("svg", help="fichier SVG à convertir")
    ap.add_argument("-o", "--sortie", help="fichier .hpgl (défaut : à côté du SVG)")
    ap.add_argument("--outil", type=int, default=1,
                    help="condition de coupe du panneau, 1 à 8 (défaut 1)")
    ap.add_argument("--force", type=int,
                    help="force de coupe 1 à 38 ; par défaut celle de la condition")
    ap.add_argument("--vitesse", type=float, metavar="CM_S",
                    help="vitesse en cm/s. Passe par le protocole propriétaire "
                         "TC (le VS du HP-GL est ignoré par cette machine) et "
                         "MODIFIE DURABLEMENT la condition enregistrée. "
                         "Demande --envoyer.")
    ap.add_argument("--marge", default="0,0", metavar="X,Y",
                    help="décalage du dessin en mm (défaut 0,0)")
    ap.add_argument("--pivoter", action="store_true",
                    help="rotation de 90° : met le grand côté dans l'avance")
    ap.add_argument("--echelle", metavar="F",
                    help="facteur d'échelle, ex. 0.9 ou 90%% (défaut : taille réelle)")
    ap.add_argument("--ajuster", action="store_true",
                    help="réduit juste ce qu'il faut pour tenir dans la zone utile")
    ap.add_argument("--mosaique", metavar="LxH",
                    help="découpe en panneaux de L x H mm et écrit un fichier "
                         "par panneau. Par défaut la zone utile de la machine.")
    ap.add_argument("--recouvrement", type=float, default=15.0, metavar="MM",
                    help="bande partagée entre panneaux voisins (défaut 15). "
                         "Des repères y sont tracés, au milieu, donc aux "
                         "mêmes points sur les deux voisins.")
    ap.add_argument("--brut", action="store_true",
                    help="garde l'ordre du SVG au lieu d'optimiser le trajet")
    ap.add_argument("--envoyer", action="store_true",
                    help="envoie à la machine (mouvement réel de l'outil)")
    args = ap.parse_args()

    polylignes, avertissements = charger(args.svg)
    for message in avertissements:
        print(f"  attention : {message}", file=sys.stderr)
    if not polylignes:
        sys.exit("aucune géométrie exploitable dans ce SVG")

    if args.pivoter:
        polylignes = pivoter(polylignes)
    try:
        marge_x, marge_y = (float(v) for v in args.marge.split(","))
    except ValueError:
        sys.exit("--marge attend deux nombres séparés par une virgule, ex. 5,5")

    if args.echelle and args.ajuster:
        sys.exit("--echelle et --ajuster se contredisent : choisir l'un des deux")

    limites = limites_machine()
    facteur = 1.0

    if args.echelle:
        try:
            texte = args.echelle.strip().rstrip("%")
            facteur = float(texte) / (100.0 if "%" in args.echelle else 1.0)
        except ValueError:
            sys.exit("--echelle attend un nombre, ex. 0.9 ou 90%")
        if facteur <= 0:
            sys.exit("--echelle attend un facteur positif")

    elif args.ajuster:
        if not limites:
            sys.exit("--ajuster a besoin de la zone utile : machine allumée et sur READY ?")
        xmin, ymin, xmax, ymax = cadre(polylignes)
        dispo_x = limites[0] - 2 * marge_x
        dispo_y = limites[1] - 2 * marge_y
        facteur = min(1.0,
                      dispo_x / (xmax - xmin) if xmax > xmin else 1.0,
                      dispo_y / (ymax - ymin) if ymax > ymin else 1.0)
        facteur *= 0.995        # la zone utile varie de quelques dixièmes

    if facteur != 1.0:
        polylignes = [([(x * facteur, y * facteur) for x, y in pts], ferme)
                      for pts, ferme in polylignes]
        print(f"échelle      x{facteur:.4f}  ({facteur * 100:.1f} %)")
        print("             ATTENTION : les cotes et le cartouche du dessin")
        print("             annoncent toujours l'échelle d'origine.")

    polylignes = recadrer(polylignes, marge_x, marge_y)

    # Le plus-proche-voisin est glouton : il ne voit pas le retour final et
    # peut sortir un ordre PIRE que celui du SVG. On le mesure au lieu de le
    # croire, et on ne garde son résultat que s'il gagne vraiment.
    avant = apres = trajet_a_vide(polylignes)
    if not args.brut:
        candidat = ordonner(polylignes)
        gain_candidat = trajet_a_vide(candidat)
        if gain_candidat < avant:
            polylignes, apres = candidat, gain_candidat

    if args.force is not None and not 1 <= args.force <= 38:
        sys.exit("--force attend une valeur de 1 à 38 (plage du CE6000-60)")
    programme, ignorees = en_hpgl(polylignes, args.outil, args.force)

    xmin, ymin, xmax, ymax = cadre(polylignes)
    largeur, hauteur = xmax - xmin, ymax - ymin
    points = sum(len(p) for p, _ in polylignes)

    print(f"{len(polylignes)} chemin(s), {points} points")
    print(f"emprise      {largeur:.1f} x {hauteur:.1f} mm"
          f"   (coin bas-gauche à {xmin:.1f}, {ymin:.1f})")
    if not args.brut:
        if apres < avant:
            gain = (1 - apres / avant) * 100
            print(f"trajet à vide {avant:.0f} mm -> {apres:.0f} mm  ({gain:.0f} % gagné)")
        else:
            print(f"trajet à vide {avant:.0f} mm  (l'ordre du SVG était déjà le meilleur)")
    if ignorees:
        print(f"{ignorees} chemin(s) plus petits qu'une unité machine, ignorés")

    # `limites` a déjà été interrogée plus haut, --ajuster en dépendant.
    if limites:
        lim_x, lim_y = limites
        print(f"zone utile   {lim_x:.1f} x {lim_y:.1f} mm (média actuellement chargé)")
        if xmax > lim_x or ymax > lim_y:
            print("\n  LE DESSIN DÉBORDE DE LA ZONE UTILE.", file=sys.stderr)
            if ymax > lim_y and xmax <= lim_y and ymax <= lim_x:
                print("  Il tiendrait avec --pivoter.", file=sys.stderr)
            print("  Ou avec --ajuster, qui réduit juste ce qu'il faut.",
                  file=sys.stderr)
            if args.envoyer:
                sys.exit("envoi annulé.")
    else:
        print("zone utile   non interrogée (machine absente ou muette)")
        if args.envoyer:
            # Hors de l'état READY, la machine avale les octets sans les lire
            # ni bouger : l'envoi paraîtrait réussir et il ne se passerait
            # rien. Si elle ne répond pas à OH;, elle n'écoute pas non plus.
            sys.exit("elle ne répond pas : média chargé et panneau sur READY ?\n"
                     "envoi annulé.")

    if args.mosaique:
        import mosaique as mos
        try:
            px, py = (float(v) for v in args.mosaique.lower().split("x"))
        except ValueError:
            sys.exit("--mosaique attend LxH, par exemple 380x280")
        racine = os.path.splitext(args.sortie or args.svg)[0]
        panneaux = mos.mosaique(polylignes, (px, py), args.recouvrement)
        print(f"\nmosaïque   {len(panneaux)} panneau(x) de {px:.0f} x {py:.0f} mm, "
              f"recouvrement {args.recouvrement:.0f} mm")
        for i, j, _, morceaux in panneaux:
            if not morceaux:
                print(f"   ({i},{j}) vide, ignoré")
                continue
            morceaux = recadrer(morceaux, marge_x, marge_y)
            if not args.brut:
                candidat = ordonner(morceaux)
                if trajet_a_vide(candidat) < trajet_a_vide(morceaux):
                    morceaux = candidat
            prog, _ = en_hpgl(morceaux, args.outil, args.force)
            nom = f"{racine}_p{i}{j}.hpgl"
            with open(nom, "w", encoding="ascii") as f:
                f.write(prog)
            x0, y0, x1, y1 = cadre(morceaux)
            print(f"   ({i},{j}) {len(morceaux):>4} tracés, "
                  f"{x1-x0:>6.1f} x {y1-y0:>6.1f} mm -> {os.path.basename(nom)}")
        print("\nTracer les panneaux l'un après l'autre, en superposant les")
        print("repères en croix des bandes de recouvrement pour les raccorder.")
        return

    sortie = args.sortie or os.path.splitext(args.svg)[0] + ".hpgl"
    with open(sortie, "w", encoding="ascii") as f:
        f.write(programme)
    print(f"écrit        {sortie}  ({len(programme)} octets)")

    if args.vitesse is not None and not args.envoyer:
        sys.exit("--vitesse règle la machine : il faut --envoyer")

    if args.envoyer:
        if args.vitesse is not None:
            import conditions
            for nom, demande, obtenu, ok in conditions.appliquer(
                    vitesse=args.vitesse, condition=args.outil):
                marque = "" if ok else f"  NON CONFORME : machine à {obtenu}"
                print(f"réglé        {nom} = {demande} sur la condition "
                      f"{args.outil} (relu {obtenu}){marque}")
        envoye = envoyer(programme)
        print(f"envoyé       {envoye} octets à {PERIPH}")


if __name__ == "__main__":
    main()
