# Graphtec CE6000-60 sous Linux

Piloter le traceur de découpe **Graphtec CE6000-60** depuis Linux, sans aucun
driver, et convertir un SVG en HP-GL prêt à couper.

Le CE6000 n'est pas une imprimante à pilote propriétaire : c'est un traceur qui
lit des commandes texte. Le « driver » Windows (Cutting Master / Graphtec Studio)
ne fait que traduire des courbes en HP-GL et pousser le résultat sur le port.
Tout ce travail se refait en Python.

## Ce qui a été mesuré sur la machine

Relevé à l'établi le 10/08/2026, en interrogeant le traceur et au pied à
coulisse — pas recopié d'une documentation.

| Fait | Valeur |
|---|---|
| USB | `0b4d:1122`, classe imprimante, **bidirectionnel** |
| Périphérique | `/dev/usb/lp0` (`root:lp`) — ni udev, ni libusb, ni pyusb |
| Endpoints | EP1 OUT **8 octets**, EP2 IN 64 octets |
| Langage | HP-GL, émulation **7586** (`OI;` → `7586`) |
| Résolution | **40 unités/mm** sur les deux axes (`OF;` → `40,40`) |
| Repère | origine coin bas-gauche, aucun miroir |
| Axes | **X = avance du média, Y = course du chariot** |
| Zone utile | `OH;`, dépend du média chargé (A4 → ~256,8 × 187,1 mm) |

Réglages du panneau : `COMMAND` → `HP-GL`, `MODEL EMULATED` → `7586`
(le 7550 est un traceur de bureau A3 dont l'espace de coordonnées est petit),
`HP-GL ORIGIN POINT` → coin.

## Les trois pièges

1. **Hors de l'état `READY`, la machine ne lit pas son tampon d'interface.**
   Elle avale les octets sans répondre ni bouger — le symptôme est identique à
   une panne de liaison. Après un redémarrage elle redemande le type de média ;
   tant qu'on n'a pas répondu, rien ne se passe. `svg2hpgl.py` refuse d'envoyer
   si `OH;` reste muet, précisément pour ça.

2. **L'endpoint d'envoi fait 8 octets et refuse les données quand la machine
   sature** (`EAGAIN` en `O_NONBLOCK`). Écrire sans attendre tronque les gros
   fichiers en silence. C'est le contrôle de flux du port série sous une autre
   forme — l'USB ne l'a pas supprimé.

3. **Les réponses se terminent par `\r` et s'accumulent.** Sans vider le tampon
   d'entrée avant chaque requête, elles se chevauchent.

## Ce qui n'est PAS fait ici

- **La compensation d'offset de lame** : le firmware s'en charge (réglage
  `OFFSET` de la condition de coupe). On lui envoie la polyligne nominale, il
  place la lame. Ne pas la recalculer côté PC.
- **La force de coupe** : elle se trouve sur une chute du vrai matériau, en
  montant jusqu'à ce que le film se détache sans entamer le support. Aucun
  calcul ne donne ce nombre. Par défaut le programme dit `SP1..SP8` et la
  machine applique la condition réglée au panneau — c'est le choix
  recommandé. `FS` fonctionne néanmoins (voir `nuancier_force.py`), d'où
  l'option `--force` pour les cas où l'on veut piloter depuis le PC.

  **La plage utile va de 1 à 38.** Au stylo, la progression ne se voit que
  jusqu'à ~10 puis sature : un stylo dépose son encre dès qu'il touche, et
  appuyer plus fort n'y change rien. La force n'est vraiment un réglage
  continu qu'avec une lame, où elle fixe la profondeur de coupe — c'est donc
  sur du vinyle, à la lame, que le nuancier prend son sens.
- **L'ARMS** (détection des marques de repérage, print & cut) : commandes mal
  documentées hors SDK Graphtec.

## Les outils

### `sonde_ce6000.py` — interroger la machine

N'envoie que des requêtes de lecture : aucun mouvement.

```bash
python3 sonde_ce6000.py
```

Rend l'émulation active, la zone utile, la position, le statut et la
résolution. C'est le premier réflexe quand quelque chose ne répond plus.

### `trace_controle.py` — un F dans un rectangle de 100 × 50 mm

**Fait bouger le chariot.** À n'exécuter qu'avec un stylo monté.

```bash
python3 trace_controle.py --simuler   # affiche le HP-GL, n'envoie rien
python3 trace_controle.py             # trace
```

Le F n'est pas décoratif : c'est la seule lettre qui trahit d'un coup d'œil une
rotation *et* un miroir, là où un rectangle seul ne dit rien. Le rectangle se
contrôle au pied à coulisse — un écart de 2 % ne se voit pas à l'œil et se
retrouve ensuite sur chaque pièce.

### `svg2hpgl.py` — convertir un SVG

```bash
python3 svg2hpgl.py dessin.svg                    # écrit dessin.hpgl
python3 svg2hpgl.py dessin.svg --envoyer          # + envoie à la machine
python3 svg2hpgl.py dessin.svg --pivoter --marge 5,5
```

| Option | Effet |
|---|---|
| `--sortie` | fichier `.hpgl` (défaut : à côté du SVG) |
| `--outil N` | condition de coupe du panneau, 1 à 8 |
| `--vitesse N` | vitesse en cm/s (défaut : celle de la condition) |
| `--force N` | force 1 à 38 (défaut : celle de la condition) |
| `--marge X,Y` | décalage du dessin en mm |
| `--pivoter` | rotation 90°, met le grand côté dans l'avance |
| `--brut` | garde l'ordre du SVG au lieu d'optimiser le trajet |
| `--envoyer` | envoi réel — sans cette option, rien ne part |

Il réutilise `parse_svg_file()` de **LaserAtelier**
(`~/.local/share/FreeCAD/v1-1/Mod/LaserAtelier/svg_import.py`) : ses points
sortent déjà en millimètres, déjà en Y-vers-le-haut, déjà ramenés à l'origine
du viewBox — c'est-à-dire déjà dans la convention HP-GL. Le retournement d'axe
écrit pour FreeCAD sert ici tel quel.

**Attention : `svg_import.py` ne convertit que les `<path>`.** Un `<rect>`,
`<circle>` ou `<polygon>` serait traversé sans géométrie et sans avertissement —
le SVG sortirait vide, en silence. `svg2hpgl.py` les détecte et le dit. Dans
Inkscape : *Chemin → Objet en chemin*.

L'optimisation de trajet est un plus-proche-voisin, donc glouton : il ne voit
pas le retour final et peut sortir un ordre pire que celui du SVG. Le script
mesure les deux et ne garde le sien que s'il gagne — sur 3 chemins il déclare
forfait, sur 40 pastilles dispersées il économise 70 % du déplacement à vide.

## Alternatives toutes faites

Si ces scripts ne suffisent pas : **vpype** (`write --format hpgl`), l'extension
**Tracer** intégrée à Inkscape, ou **Inkcut** (interface complète, mise en page,
chenillage).
