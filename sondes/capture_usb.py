#!/usr/bin/env python3
"""Capture le dialogue USB avec le traceur, depuis l'hôte Linux.

POURQUOI ICI ET PAS SOUS WINDOWS. Le Windows de l'atelier tourne en machine
virtuelle KVM, et le traceur lui est passé en USB. Les transferts traversent
donc quand même la pile USB du noyau **hôte** : `usbmon` les voit d'ici,
pendant que le logiciel Graphtec pilote la machine dans la VM. Rien à
installer côté Windows.

CE QU'ON CHERCHE. Trois commandes de vitesse ont été essayées à l'aveugle et
aucune n'agit (`VS` en HP-GL, `!` et `S` en GP-GL). Plutôt que d'en deviner
une quatrième, on regarde ce que le logiciel d'origine envoie vraiment. La
méthode : **deux captures qui ne diffèrent que par un réglage**, et les
octets qui changent SONT la commande.

Demande les droits root : `usbmon` n'est lisible que par lui.

  sudo modprobe usbmon
  sudo python3 capture_usb.py --valider          # sur une charge connue
  sudo python3 capture_usb.py --capturer a.txt   # puis Ctrl-C pour arrêter
"""

import argparse
import glob
import os
import re
import select
import signal
import sys
import time

PERIPH = "/dev/usb/lp0"
VENDEUR, PRODUIT = "0b4d", "1122"
LIGNE = re.compile(r"^(\S+)\s+(\d+)\s+([SCE])\s+(\S+)\s+(-?\d+)\s+(\d+)"
                   r"(?:\s+=\s+(.*))?$")


def bus_du_traceur():
    """Numéro de bus USB du Graphtec, lu dans /sys."""
    for chemin in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        base = os.path.dirname(chemin)
        try:
            with open(chemin) as f:
                if f.read().strip() != VENDEUR:
                    continue
            with open(os.path.join(base, "idProduct")) as f:
                if f.read().strip() != PRODUIT:
                    continue
            with open(os.path.join(base, "busnum")) as f:
                return int(f.read().strip())
        except OSError:
            continue
    return None


def flux_usbmon(bus):
    chemin = f"/sys/kernel/debug/usb/usbmon/{bus}u"
    if not os.path.exists(chemin):
        sys.exit(f"{chemin} absent — as-tu lancé « sudo modprobe usbmon » ?")
    return os.open(chemin, os.O_RDONLY | os.O_NONBLOCK)


def lire_disponible(fd, tampon):
    """Vide ce qui est prêt ; rend les lignes complètes."""
    while True:
        prets, _, _ = select.select([fd], [], [], 0)
        if not prets:
            break
        try:
            bloc = os.read(fd, 65536)
        except BlockingIOError:
            break
        if not bloc:
            break
        tampon += bloc
    *lignes, reste = tampon.decode("ascii", "replace").split("\n")
    return lignes, reste.encode()


def octets(ligne):
    """(sens, données) d'une ligne usbmon, ou None."""
    m = LIGNE.match(ligne)
    if not m:
        return None
    _, _, evenement, adresse, _, _, donnees = m.groups()
    if not donnees:
        return None
    hexa = donnees.replace(" ", "")
    try:
        brut = bytes.fromhex(hexa)
    except ValueError:
        return None
    sens = "sortant" if adresse.startswith("Bo") else (
        "entrant" if adresse.startswith("Bi") else adresse[:2])
    # Un URB « S » sortant porte la charge ; un « C » entrant la ramène.
    if (sens == "sortant" and evenement == "S") or \
       (sens == "entrant" and evenement == "C"):
        return sens, brut
    return None


def valider(bus):
    """Envoie `OI;` — une requête, aucun mouvement — et le cherche."""
    fd = flux_usbmon(bus)
    tampon = b""
    lire_disponible(fd, tampon)                    # repartir propre

    lp = os.open(PERIPH, os.O_RDWR | os.O_NONBLOCK)
    try:
        os.write(lp, b"OI;")
        time.sleep(1.5)
        try:
            reponse = os.read(lp, 64)
        except BlockingIOError:
            reponse = b""
    finally:
        os.close(lp)

    lignes, _ = lire_disponible(fd, tampon)
    os.close(fd)

    trouves = [octets(l) for l in lignes]
    trouves = [t for t in trouves if t]
    sortants = b"".join(d for s, d in trouves if s == "sortant")
    entrants = b"".join(d for s, d in trouves if s == "entrant")

    print(f"bus {bus} : {len(lignes)} lignes, {len(trouves)} avec charge utile")
    print(f"  sortant : {sortants!r}")
    print(f"  entrant : {entrants!r}")
    print(f"  réponse lue en direct : {reponse!r}")
    print()
    if b"OI;" in sortants:
        print("VALIDÉ : les octets envoyés se retrouvent dans la capture.")
        if b"7586" in entrants:
            print("Et la réponse aussi — les deux sens sont lisibles.")
        else:
            print("La réponse n'y est pas : le sens entrant sera à surveiller,")
            print("mais c'est le sortant qui porte les commandes.")
        return True
    print("ÉCHEC : « OI; » est absent de la capture.")
    print("Le format texte tronque peut-être les données, ou le bus est")
    print("mauvais. Installer wireshark-cli et capturer en binaire.")
    return False


def capturer(bus, fichier):
    fd = flux_usbmon(bus)
    tampon = b""
    arret = {"demande": False}

    def stop(*_):
        arret["demande"] = True
    signal.signal(signal.SIGINT, stop)

    print(f"capture du bus {bus} vers {fichier} — Ctrl-C pour arrêter")
    n = 0
    with open(fichier, "w", encoding="utf-8") as sortie:
        while not arret["demande"]:
            lignes, tampon = lire_disponible(fd, tampon)
            for l in lignes:
                sortie.write(l + "\n")
            n += len(lignes)
            if lignes:
                sortie.flush()
            time.sleep(0.05)
    os.close(fd)
    print(f"\n{n} lignes écrites dans {fichier}")


def main():
    ap = argparse.ArgumentParser(description="Capture le dialogue USB du traceur.")
    ap.add_argument("--valider", action="store_true",
                    help="essai sur une charge connue (`OI;`, aucun mouvement)")
    ap.add_argument("--capturer", metavar="FICHIER",
                    help="enregistre le trafic jusqu'à Ctrl-C")
    ap.add_argument("--bus", type=int, help="forcer le numéro de bus")
    args = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("usbmon n'est lisible que par root : relancer avec sudo")

    bus = args.bus or bus_du_traceur()
    if bus is None:
        sys.exit(f"traceur {VENDEUR}:{PRODUIT} introuvable — allumé et branché ?")

    if args.valider:
        sys.exit(0 if valider(bus) else 1)
    if args.capturer:
        capturer(bus, args.capturer)
        return
    sys.exit("choisir --valider ou --capturer FICHIER")


if __name__ == "__main__":
    main()
