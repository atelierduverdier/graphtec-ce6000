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

## Dessiner et couper au quotidien : Inkscape

**Aucun plugin à installer.** Inkscape 1.4 embarque déjà l'équivalent du
Cutting Master de Graphtec : *Extensions → Exporter → Tracer*, qui envoie
directement au port. Vérifié le 10/08/2026 — carré de 60 mm sorti à 60,0 mm,
coins nets.

| Champ | Valeur | Pourquoi |
|---|---|---|
| Type de port | **Port parallèle** | |
| Port parallèle | **`/dev/usb/lp0`** | le défaut proposé est `lp2` |
| Langage | **HPGL** | ce que dit `COMMAND` au panneau |
| Résolution X et Y | **1016** dpi | 1016 ÷ 25,4 = 40 unités/mm, la valeur mesurée |
| Plume | **1** | sélectionne la CONDITION 1 |
| Force / Vitesse | **0** / **0** | 0 = ne rien envoyer, le panneau garde la main |
| Surcoupe | **0** | déjà fait par le firmware |
| Correction d'offset d'outil | **0** | déjà fait par le firmware |
| Précoupe | **décochée** | |
| Rotation / miroirs / origine centrée | aucun | le repère est vérifié, ne pas le contrarier |
| Alignement automatique | décoché | sinon il pousse le dessin dans le coin |

Deux réglages par défaut à corriger impérativement, et ce sont les deux plus
dangereux :

- **« Correction d'offset d'outil » vaut 0,25 mm** et **« Surcoupe » vaut
  1,00 mm** d'origine. Or la machine fait déjà ces deux corrections dans son
  firmware. Les laisser actifs compense **deux fois** : les coins sortent avec
  de petites cornes au lieu d'être nets. Le contrôle est visuel — un carré,
  puis on regarde les angles.
- **« Alignement automatique » déplace le dessin** dans le coin du média et
  jette la position du SVG. À décocher pour maîtriser la mise en page.

Ce que le logiciel natif faisait et qu'Inkscape ne fait pas : les marques de
repérage ARMS (print & cut), les lignes de dégagement, le pavage des grands
dessins et la duplication en série. C'est le territoire d'**Inkcut**, absent
des dépôts (AUR seulement, et ses dépendances enaml/atom suivent mal les
Python récents).

## Tracer une planche TechDraw au stylo

Le cas d'usage principal : sortir un plan FreeCAD au stylo, éventuellement à
l'échelle 1 pour servir de gabarit sur la planche de bois. L'axe chariot
accepte 600 mm, l'axe d'avance est illimité en rouleau.

**Export depuis FreeCAD.** Sélectionner la planche dans l'arbre, puis
*TechDraw → Page → Exporter la page en SVG*. Pour plusieurs planches :

```python
import FreeCAD, TechDrawGui, os
doc = FreeCAD.getDocument("Tonnelle")
dossier = os.path.join(os.path.dirname(doc.FileName), "planches_svg")
os.makedirs(dossier, exist_ok=True)
for p in doc.Objects:
    if p.isDerivedFrom("TechDraw::DrawPage"):
        TechDrawGui.exportPageAsSvg(p, os.path.join(dossier, p.Name + ".svg"))
```

L'échelle sort juste sans réglage : une planche A3 est lue à 420,0 × 297,0 mm.

**Préparation.** Une planche exportée contient trois familles d'éléments qui
ne se tracent pas telles quelles — sur `Plan_Debit` du meuble à balais :
430 `<rect>`, 2 `<circle>`, 10 `<text>`, soit les tableaux et le cartouche.

1. `python3 preparer_planche.py planche.svg` — retire les commentaires XML.
   **Indispensable** : TechDraw en écrit quatre par planche et l'extension
   Texte Hershey plante dessus (`'_Comment' object has no attribute
   'transform'`).
2. Dans Inkscape, tout sélectionner puis *Chemin → Objet en chemin* pour les
   `<rect>` et `<circle>`.
3. **Sélectionner le dessin SEUL, pas le cartouche**, puis *Extensions →
   Texte → Texte Hershey*. Hershey ne traite que la sélection quand il y en
   a une, et c'est ce qui sauve : les champs du cartouche vivent hors du
   groupe `DrawingContent` et de son transform, donc Hershey ignore le
   facteur 10 du `viewBox` et les rend **dix fois trop grands** — ils
   débordent alors de 185 mm hors de la page. Les cotes, elles, sont dans le
   groupe transformé et sortent justes.

Le cartouche se traite ensuite à part : *Objet en chemin* donne des lettres
creuses, acceptable pour quelques mots.

**Pourquoi passer par `svg2hpgl.py` plutôt que par l'export d'Inkscape**, sur
une planche réelle :

| Planche | Trajet à vide | Après réordonnancement |
|---|---|---|
| Plan_Ensemble | 38 418 mm | **4 809 mm** (−87 %) |
| Plan_Debit | 24 413 mm | **8 852 mm** (−64 %) |

33 mètres de déplacement à vide évités sur une seule planche : du temps de
tracé et de l'usure de courroie. L'exporteur d'Inkscape ne réordonne pas.

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

## Quand utiliser quoi

- **Inkscape** pour dessiner et couper au quotidien, réglé comme ci-dessus.
- **`sonde_ce6000.py`** dès que la machine ne répond plus : c'est le premier
  réflexe, et il ne fait rien bouger.
- **`svg2hpgl.py`** pour ce qu'Inkscape ne fait pas : refuser d'envoyer hors
  `READY`, vérifier que le dessin tient dans la zone utile interrogée à la
  machine, et traiter en lot depuis un terminal.
- **vpype** (`write --format hpgl`) si un traitement de chemins plus poussé
  devient nécessaire.
