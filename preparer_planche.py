#!/usr/bin/env python3
"""Prépare une planche TechDraw pour le traçage au stylo.

Retire les commentaires XML du SVG. C'est le seul traitement, et il est
indispensable : l'extension **Texte Hershey** d'Inkscape parcourt les
nœuds enfants en supposant que chacun porte un attribut `transform`, ce
qu'un commentaire n'a pas. Elle s'arrête sur :

    AttributeError: 'lxml.etree._Comment' object has no attribute 'transform'

TechDraw en écrit quatre dans chaque planche exportée (« Working space »,
« Title block », « DrawingContent »…), donc la panne est systématique.

Le reste de la préparation se fait dans Inkscape, et lui seul sait le
faire :
  - Tout sélectionner puis Chemin > Objet en chemin, pour convertir les
    <rect> et <circle> du cartouche et des tableaux ;
  - Extensions > Texte > Texte Hershey pour les cotes et annotations,
    qui donne des lettres MONOTRAIT. « Objet en chemin » sur du texte
    produirait des lettres creuses, dessinées par leur contour.
"""

import argparse
import os
import sys

try:
    from lxml import etree
except ImportError:                                     # pragma: no cover
    sys.exit("lxml requis : pacman -S python-lxml")


def nettoyer(source, destination):
    """Copie le SVG sans ses commentaires. Rend le nombre retiré."""
    avant = etree.parse(source)
    retires = len(avant.getroot().xpath("//comment()"))

    arbre = etree.parse(source, etree.XMLParser(remove_comments=True))
    arbre.write(destination, xml_declaration=True,
                encoding="utf-8", pretty_print=False)
    return retires


def main():
    ap = argparse.ArgumentParser(
        description="Retire les commentaires XML d'une planche TechDraw, "
                    "qui font planter l'extension Texte Hershey d'Inkscape.")
    ap.add_argument("svg", nargs="+", help="planche(s) exportée(s) de TechDraw")
    ap.add_argument("-o", "--sortie",
                    help="fichier de sortie (une seule planche) ; par défaut "
                         "un suffixe _propre à côté de l'original")
    args = ap.parse_args()

    if args.sortie and len(args.svg) > 1:
        sys.exit("--sortie ne vaut que pour une seule planche")

    for source in args.svg:
        if not os.path.exists(source):
            print(f"  absent : {source}", file=sys.stderr)
            continue
        racine, ext = os.path.splitext(source)
        destination = args.sortie or f"{racine}_propre{ext}"
        retires = nettoyer(source, destination)
        print(f"{os.path.basename(source)} -> {os.path.basename(destination)}"
              f"   ({retires} commentaire(s) retiré(s))")


if __name__ == "__main__":
    main()
