#!/usr/bin/env python3
"""Envoie un fichier HP-GL déjà écrit au traceur.

Le chaînon qui manquait : `svg2hpgl.py --mosaique` écrit un fichier par
panneau sans les envoyer — il le faut, puisqu'il faut repositionner le média
entre deux panneaux — mais rien ne savait ensuite envoyer ces fichiers.

Reprend les deux garde-fous du reste du dépôt : le contrôle de flux sur
l'endpoint de 8 octets, et le refus d'envoyer quand la machine ne répond
pas à `OH;` — hors de l'état READY elle avale les octets sans rien tracer.
"""

import argparse
import os
import select
import sys
import time

PERIPH = "/dev/usb/lp0"
TAILLE_PAQUET = 8
UNITES_PAR_MM = 40


def _ecrire(fd, texte, delai=20.0):
    donnees = memoryview(texte.encode("ascii"))
    envoye = 0
    while envoye < len(donnees):
        _, prets, _ = select.select([], [fd], [], delai)
        if not prets:
            raise TimeoutError("le traceur n'accepte plus de données")
        try:
            envoye += os.write(fd, donnees[envoye:envoye + TAILLE_PAQUET])
        except BlockingIOError:
            time.sleep(0.005)
    return envoye


def zone_utile(fd, delai=2.0, essais=4, repos=1.0):
    """`OH;` -> (largeur, hauteur) en mm, ou None.

    Rend AUSSI la réponse brute, via `zone_utile.derniere_reponse` : le
    message d'erreur disait « la machine ne répond pas » aussi bien quand
    elle se taisait que quand sa réponse ne s'analysait pas. Deux causes
    différentes derrière une seule phrase, c'est ce qui a fait chercher au
    mauvais endroit le 11/08/2026 -- `OH;` interrogé seul répondait très
    bien dans la minute qui suivait.

    Plusieurs tentatives espacées, parce que le silence est reproductible :
    une GROSSE lecture `TC` — le journal `TC2010,9` ou le vidage `TC2009,5`
    — laisse la machine muette à l'`OH;` qui suit, y compris depuis un autre
    processus. Constaté en beauté le 11/08/2026 quand la commande de
    diagnostic lancée juste avant un envoi a fait échouer cet envoi : le
    pollueur était l'instrument.

    Le mécanisme n'est pas élucidé. L'entêtement, lui, suffit.
    """
    while True:                                   # repartir propre
        prets, _, _ = select.select([fd], [], [], 0.05)
        if not prets:
            break
        try:
            if not os.read(fd, 64):
                break
        except BlockingIOError:
            break
    for tentative in range(essais):
        _ecrire(fd, "OH;")
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
            if b"\r" in reponse:
                break
        zone_utile.derniere_reponse = reponse
        try:
            x0, y0, x1, y1 = (float(v) for v in
                              reponse.decode("ascii", "replace")
                              .strip().split(","))
            return (x1 - x0) / UNITES_PAR_MM, (y1 - y0) / UNITES_PAR_MM
        except ValueError:
            if tentative + 1 < essais:
                time.sleep(repos)
    return None


zone_utile.derniere_reponse = b""


def emprise(programme):
    """Rectangle occupé par le programme, en mm — lu dans ses coordonnées."""
    import re
    xs, ys = [], []
    for verbe, args in re.findall(r"(PU|PD)([-\d,]*);", programme):
        v = [int(a) for a in args.split(",") if a]
        xs += v[0::2]
        ys += v[1::2]
    if not xs:
        return None
    return (min(xs) / UNITES_PAR_MM, min(ys) / UNITES_PAR_MM,
            max(xs) / UNITES_PAR_MM, max(ys) / UNITES_PAR_MM)


def main():
    ap = argparse.ArgumentParser(
        description="Envoie un fichier HP-GL au Graphtec CE6000-60.")
    ap.add_argument("fichier", nargs="+",
                    help="fichier(s) .hpgl — ou .svg, converti au vol")
    ap.add_argument("--forcer", action="store_true",
                    help="envoie même si le dessin déborde de la zone utile")
    ap.add_argument("--materiau", metavar="NOM",
                    help="applique d'abord un profil du carnet d'établi "
                         "(type d'outil, vitesse, force, accélération) et "
                         "RELIT chaque valeur. Sans lui, l'envoi part avec "
                         "les réglages laissés par le travail précédent — "
                         "c'est ainsi qu'un « Stylo feutre » oublié a "
                         "arrondi les angles d'une découpe.")
    ap.add_argument("--condition", type=int, default=1,
                    help="numéro de condition à régler (1 à 8, défaut 1)")
    ap.add_argument("--reperage", action="store_true",
                    help="travail lancé APRÈS une détection de repères "
                         "ARMS : omet le IN; initial, qui effacerait "
                         "l'origine posée par la détection. Sans lui la "
                         "découpe part du coin de la feuille au lieu du "
                         "dessin imprimé, sans aucun message.")
    args = ap.parse_args()

    for chemin in args.fichier:
        if not os.path.exists(chemin):
            sys.exit(f"fichier introuvable : {chemin}")

    # Un SVG est converti ICI, dans le même processus. Le faire par un tube
    # — `envoyer_hpgl <(svg2hpgl …)` — ne peut PAS marcher : les deux
    # programmes tournent alors en parallèle et se disputent
    # /dev/usb/lp0, que l'un ouvre pendant que l'autre l'interroge. Le
    # second meurt sur « Device or resource busy », son tube se referme, et
    # l'envoi part avec zéro octet en croyant avoir réussi.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    if not os.path.exists(PERIPH):
        sys.exit(f"{PERIPH} absent : traceur allumé et branché ?")

    # La zone utile se lit AVANT tout réglage, et le résultat sert ensuite.
    # Ordre voulu, pas cosmétique : `OH;` répond sans faute quand c'est la
    # première chose demandée à la machine, et reste MUET quand une salve
    # `TC` l'a précédé dans le même processus. Observé trois fois le
    # 11/08/2026, sans que le mécanisme soit élucidé -- l'état `TC` vaut
    # 8 (occupé) y compris dans les cas qui marchent, donc ce n'est pas lui.
    # On ne traverse pas une transition qu'on ne comprend pas : on l'évite.
    # UN SEUL descripteur pour toute l'exécution. Fermer et rouvrir
    # /dev/usb/lp0 entre deux étapes rend la machine muette : mesuré le
    # 11/08/2026, une lecture du journal suivie d'un OH; répond du premier
    # coup sur le même descripteur, et se tait plus de 44 secondes si on
    # referme entre les deux. Ce programme en ouvrait quatre par exécution.
    fd = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        limites = zone_utile(fd)
    except BaseException:
        os.close(fd)
        raise
    if limites is None:
        os.close(fd)
        brut = zone_utile.derniere_reponse
        sys.exit(
            f"OH; n'a pas donné de zone utile exploitable.\n"
            f"   la machine a répondu : {brut!r}\n"
            + ("   (rien du tout — média chargé et panneau sur READY ?)"
               if not brut else
               "   (réponse reçue mais illisible)"))
    print(f"zone utile {limites[0]:.1f} × {limites[1]:.1f} mm "
          f"(média actuellement chargé)")

    if args.materiau:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import materiaux
        if args.materiau not in materiaux.MATERIAUX:
            sys.exit("profil inconnu ; au choix :\n   "
                     + "\n   ".join(materiaux.MATERIAUX))
        rendu, lame = materiaux.appliquer(args.materiau, args.condition, fd=fd)
        print(f"condition {args.condition} — {materiaux.resume(args.materiau)}")
        for nom, demande, obtenu, ok in rendu:
            print(f"   {nom:<14} demandé {str(demande):<8} obtenu "
                  f"{str(obtenu):<8} {'ok' if ok else 'NON CONFORME'}")
        if any(not ok for *_, ok in rendu):
            sys.exit("   un réglage n'a pas été retenu — envoi annulé.")
        if lame:
            print(f"   À LA MAIN : sortie de lame {lame} mm")
        print()

    for chemin in args.fichier:
        if chemin.lower().endswith(".svg"):
            import svg2hpgl
            poly, avertissements = svg2hpgl.charger(chemin)
            for a in avertissements:
                print(f"   ⚠ {a}")
            if not poly:
                sys.exit(f"{chemin} : aucune géométrie exploitable.")
            programme, _ = svg2hpgl.en_hpgl(svg2hpgl.ordonner(poly),
                                            reperage=args.reperage)
            print(f"{os.path.basename(chemin)} : converti, "
                  f"{len(poly)} tracé(s)")
        else:
            with open(chemin, encoding="ascii", errors="replace") as f:
                programme = f.read()
            if args.reperage and "IN;" in programme:
                # Un .hpgl déjà écrit porte son IN; ; on le retire, mais on
                # l'annonce. Corriger un fichier de l'utilisateur en silence
                # serait pire que le défaut qu'on évite.
                programme = programme.replace("IN;", "", 1)
                print(f"   IN; retiré de {os.path.basename(chemin)} : il "
                      f"aurait effacé l'origine des repères")

        try:
            boite = emprise(programme)
            nom = os.path.basename(chemin)
            print(f"{nom} : {len(programme)} octets")
            if boite:
                print(f"   emprise {boite[2]-boite[0]:.1f} × "
                      f"{boite[3]-boite[1]:.1f} mm, coin à "
                      f"{boite[0]:.1f}, {boite[1]:.1f}")
                if (boite[2] > limites[0] or boite[3] > limites[1]) \
                        and not args.forcer:
                    sys.exit("   IL DÉBORDE — envoi annulé (--forcer pour "
                             "passer outre)")

            envoye = _ecrire(fd, programme)
            print(f"   envoyé {envoye} octets")
        except BaseException:
            os.close(fd)
            raise

        if chemin is not args.fichier[-1]:
            input("   repositionner le média, puis Entrée pour le suivant… ")
    os.close(fd)


if __name__ == "__main__":
    main()
