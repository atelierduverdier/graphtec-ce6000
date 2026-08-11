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
| Langage | `INTERFACE` → `COMMANDE` est sur **AUTO** : la machine reconnaît HP-GL et GP-GL à la volée, rien à basculer |
| Émulation | **7586** (`OI;` → `7586`), et non 7550 |
| Résolution | **40 unités/mm** sur les deux axes (`OF;` → `40,40`) |
| Repère | origine coin bas-gauche, aucun miroir |
| Axes | **X = avance du média, Y = course du chariot** |
| Zone utile | `OH;`, dépend du média chargé (A4 → ~256,8 × 187,1 mm) |

Réglages du panneau : `COMMAND` → `HP-GL`, `MODEL EMULATED` → `7586`
(le 7550 est un traceur de bureau A3 dont l'espace de coordonnées est petit),
`HP-GL ORIGIN POINT` → coin.

### La vitesse SE pilote — par le protocole propriétaire `TC`

**Correction du 11/08/2026.** Ce fichier a d'abord affirmé, en gras, que la
vitesse ne se pilotait pas depuis le PC. C'était vrai des trois commandes
essayées et faux comme conclusion : la bonne était introuvable par
supposition, il fallait regarder ce que le logiciel d'origine envoie.

```
ESC . v : TC1002,3,<condition>,<vitesse en cm/s × 10> ␃
```

puis **continuer d'interroger l'état** — `ESC.v:ESC.C1:`, qui répond `8` tant
que la machine traite et `0` quand c'est fini. **C'est la partie qu'on
oubliait** : envoyée seule, la commande fait réagir la machine et ne règle
rien. Menée à son terme, la valeur change sous les yeux, sur le panneau.

Relevé en capturant le flux USB de Graphtec Studio pendant qu'on tournait
la molette de vitesse : trois crans, trois commandes, `,270` puis `,260`
puis `,250`. La valeur est lisible en clair, ce qui rend l'identification
immédiate — d'où le choix d'une valeur inhabituelle (25) pour la chercher.

`sonde_gpgl.py --tc 25` reproduit la transaction complète.

**La même méthode nommera les autres réglages** : une capture en changeant
un champ, et la commande se désigne elle-même par sa valeur. `TC1002,1,…`,
`TC1002,6,…`, `TC2002`, `TC2006`, `TC2008`, `TC2009` sont déjà visibles dans
les captures, sans qu'on sache encore ce qu'ils portent.

### `VS` fonctionne AUSSI — mais un réglage de panneau le gouverne

**Seconde correction du 11/08/2026.** `PARAM OUTIL` → `CONDITION PRIORITE`
décide qui l'emporte entre le panneau et le fichier. Il était sur `MANUEL`,
et dans cet état **`VS` est silencieusement ignoré**. Basculé sur
`PROGRAMME`, le même essai donne enfin deux durées distinctes :

| | Demandé | Mesuré | |
|---|---|---|---|
| `VS5` | 50 mm/s | **46,5 mm/s** | 93 % de la consigne |
| `VS40` | 400 mm/s | 85,3 mm/s | = la vitesse de la condition |

D'où le modèle : **`VS` ralentit sous la vitesse de la condition, il ne la
dépasse jamais.** Et il ne vaut que le temps d'un travail, là où `TC` modifie
durablement la condition enregistrée — les deux sont donc complémentaires.

Curiosité constatée sans explication : `FS` (force) fonctionnait déjà sous
`MANUEL`, quand `VS` ne fonctionnait pas. Le réglage ne filtre pas les deux
de la même façon.

**Ce que ça coûte de croire une mesure sans connaître ses conditions** : les
durées identiques mesurées la veille étaient exactes, et la conclusion
qu'on en tirait était fausse. La machine n'était pas sourde, elle avait
reçu l'ordre de ne pas écouter.

### Ce qui a échoué avant, et pourquoi c'est instructif

Trois commandes essayées à l'aveugle, deux langages, aucune n'agit — **avec
`CONDITION PRIORITE` sur `MANUEL`, ce que nous ignorions alors**. Le même
parcours de 2 560 mm, chronométré à la montre :

| Commande envoyée | Durée |
|---|---|
| HP-GL `VS5` … `VS40` | 30 s partout |
| GP-GL `!5` … `!40` | 30 s et 28 s |
| GP-GL `S5` (la lettre du panneau) | 21 s = inchangé |

**Seul le panneau commande**, et sa courbe sature — parce que le vrai
plafond est l'**accélération**, pas la vitesse :

| Vitesse au panneau | Durée | Vitesse réelle | Rendement |
|---|---|---|---|
| S10 | 30 s | 85 mm/s | 85 % |
| S30 | 22 s | 116 mm/s | 39 % |
| S64 (max) | 21 s | 122 mm/s | 19 % |

Consigne multipliée par 6,4, temps gagné : 30 %. Au-delà de S30, monter la
vitesse ne sert plus à rien sur un parcours à virages — c'est `ACCEL` qu'il
faut regarder. Et Graphtec règle l'accélération à **2** pour son outil
« Stylo feutre » : une plume qui repart brutalement bave dans les angles.
Garder une condition « plan soigné » et une « rapide » est le bon usage des
huit emplacements.

Le détour par le GP-GL n'aura donc rien donné sur la vitesse. Il aura prouvé
que la machine l'accepte : rectangle de 60 × 30 mm exact, syntaxe `M`/`D`,
séparateur retour-ligne, pas de 0,1 mm (`sonde_gpgl.py`).

**C'est cette impasse qui a mené à la capture USB**, et elle a tout débloqué
en une heure là où trois suppositions avaient échoué. La leçon vaut au-delà
du traceur : quand deux ou trois essais à l'aveugle échouent sur une question
fermée, il est temps d'aller regarder ce que fait celui qui sait déjà.

Les chiffres d'accélération ci-dessus restent valables : c'est bien elle qui
plafonne les temps de tracé. Sa commande a été identifiée depuis
(`TC1002,5`), mais elle n'a que **trois crans** — le levier existe et il est
très court.

### Récapitulatif : quatre voies, et quand prendre chacune

| Réglage | Voie | Portée | Condition |
|---|---|---|---|
| vitesse | `TC1002,3` | **durable** | aucune |
| vitesse | HP-GL `VS` | le temps du travail | `CONDITION PRIORITE` = `PROGRAMME`, et jamais au-dessus de la condition |
| force | `TC1002,4` | **durable** | aucune |
| force | HP-GL `FS` | le temps du travail | fonctionne même sous `MANUEL` |

`TC` est la voie sûre : il s'applique toujours, et se **relit** (`TC2002`).
`VS`/`FS` sont plus élégants pour un travail ponctuel puisqu'ils ne touchent
pas aux conditions enregistrées — mais `VS` dépend d'un réglage de panneau
qui, mal placé, le rend muet sans le moindre signe.

Les scripts du dépôt utilisent `TC` par défaut, pour cette raison.

`sonde_vitesse.py` garde la trace de la méthode, et surtout **des deux qui
ont échoué avant** : `OA;` rend la position **logique**, pas celle du
chariot, donc il ne mesure aucun mouvement ; et le contrôle de flux ne mord
pas — 15 ko partent en 3,8 s quelle que soit la vitesse, soit 4 ko/s, qui
est le débit de l'USB avec ses paquets de 8 octets. Le tampon de la machine
avale au moins 15 ko. La seule mesure qui a tranché est un **chronomètre à
la main**.

Piège de raisonnement à ne pas refaire : la première version du verdict
regardait l'**étendue** des durées, pas leur ordre — n'importe quel bruit la
satisfaisait, et elle a annoncé un résultat faux avec aplomb. Un verdict doit
exiger la **croissance**, et se taire quand les mesures ne sont ni
constantes ni croissantes.

## Les quatre pièges

1. **Hors de l'état `READY`, la machine ne lit pas son tampon d'interface.**
   Elle avale les octets sans répondre ni bouger — le symptôme est identique à
   une panne de liaison. Après un redémarrage elle redemande le type de média ;
   tant qu'on n'a pas répondu, rien ne se passe. `svg2hpgl.py` refuse d'envoyer
   si `OH;` reste muet, précisément pour ça.

2. **L'endpoint d'envoi fait 8 octets et refuse les données quand la machine
   sature** (`EAGAIN` en `O_NONBLOCK`). Écrire sans attendre tronque les gros
   fichiers en silence. C'est le contrôle de flux du port série sous une autre
   forme — l'USB ne l'a pas supprimé.

3. **« Charger le vinyle » qui ne part pas : la feuille est trop étroite.**
   Les capteurs de média sont sur la table, et une feuille qui ne les couvre
   pas n'est jamais détectée — le levier descend, tout a l'air normal, et la
   machine réclame indéfiniment. Vérifier aussi que chaque galet presseur est
   **à la fois** sur le papier et au-dessus d'une bande d'entraînement
   granuleuse : un galet qui pince dans le vide donne le même symptôme.

4. **Les réponses se terminent par `\r` et s'accumulent.** Sans vider le tampon
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

### Un gabarit de page taillé pour le traceur

Une planche **A3 au 1:1 ne tient pas sur du A3** : les galets et les marges
mangent 39 mm dans le sens d'avance et 11 mm en largeur. `gabarit_traceur.py`
fabrique `gabarits/A3_Traceur_TD.svg`, une page de **375 × 280 mm** qui laisse
~5 mm de garde pour les variations de chargement.

```bash
python3 gabarit_traceur.py            # -> gabarits/A3_Traceur_TD.svg
```

Dans FreeCAD, pointer le modèle de la planche dessus :

```python
page.Template.Template = "/home/christophe/Projets/graphtec-ce6000/gabarits/A3_Traceur_TD.svg"
page.KeepUpdated = True
```

Il reprend les **dix mêmes noms de champs** que le gabarit A3 de l'atelier
(`FC-Title`, `AuthorName`, `scale`…), donc les remplissages automatiques de
TechDraw fonctionnent à l'identique. Vérifié : format lu 375,0 × 280,0 mm,
10 champs reconnus, date et titre remplis seuls.

Sa particularité : **tous les textes fixes sont en monotrait**, dessinés
glyphe par glyphe depuis les polices de LaserAtelier. Un gabarit ordinaire
écrit ses libellés en `<text>`, qu'il faut convertir en chemins — ce qui donne
des lettres **creuses**, parcourues deux fois par la plume. Ici seuls les dix
champs remplis par TechDraw restent du texte. Emprise mesurée sur une planche
vide : 365 × 270 mm, 290 tracés.

**Il ne convient pas aux planches A3 existantes** : leurs vues sont placées en
coordonnées absolues et leurs échelles choisies pour 420 × 297. Les y faire
entrer changerait l'échelle, donc le cartouche mentirait. Pour celles-là, c'est
l'A2 ou le rouleau.

**Piège :** une planche dont `KeepUpdated` est faux, ou qui n'a jamais été
ouverte, s'exporte **vide** — 975 octets au lieu de 29 000, sans erreur.

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

## `pupitre.py` — voir le dessin posé sur le média

```bash
python3 pupitre.py
```

Le seul écran que le logiciel Graphtec avait vraiment en plus (sa fenêtre
« Page »). Il interroge le média à la machine par `OH;` — comme le faisait
l'original, dont la capture affiche *« Automatique (CE6000-60 (Taille de la
sonde)) 187,20 × 257,00 mm »*, exactement nos chiffres — puis montre le
dessin dessus.

Réglages : origine X/Y, rotation par quarts de tour, miroirs, échelle libre
ou ajustée au média, **copies matricielles** (rangées × colonnes, écarts),
condition, **vitesse et force**. L'envoi se refuse tant que le dessin déborde.

Vitesse, force et accélération passent par `conditions.py` et le protocole
`TC` — elles **modifient durablement** la condition enregistrée dans la
machine, exactement comme le fait Graphtec Studio, d'où la case « régler la
machine à l'envoi » qu'on peut décocher.

| Paramètre | Commande | Plage |
|---|---|---|
| vitesse | `TC1002,3,<cond>,<cm/s × 10>` | 1 à 640, soit 64 cm/s |
| force | `TC1002,4,<cond>,<n>` | 1 à 38 |
| accélération | `TC1002,5,<cond>,<n>` | **1 à 3 seulement** |
| type d'outil | `TC1002,2,<cond>,<code>,<indicateur>` | voir la table ci-dessous |

Les codes d'outil ont été relevés en parcourant la liste du logiciel Graphtec
**deux fois de haut en bas** — la même suite les deux fois, donc une mesure
reproduite et non une déduction sur un seul passage :

| Outil | Code | | Outil | Code |
|---|---|---|---|---|
| CB09U | 1 | | CB15UB | 3 |
| CB09U-K60 | 10 | | Autre | 6 |
| CB15U | 2 | | Stylo feutre | 9 |

Le second champ de cette commande **reste inexpliqué**, et c'est le second
essai qui l'a montré : il ne dépend pas de l'outil. Au premier parcours il
valait 0 puis a basculé à 1 en cours de route sans plus en bouger — le code 6
est apparu avec les deux valeurs. C'est un état du logiciel Graphtec, pas une
propriété du réglage. `conditions.regler_outil` le laisse à 0.

**`TC2002` est la LECTURE du même jeu** : `TC2002,<paramètre>,<condition>`,
et la machine répond `<condition>, <valeur>…`. On peut donc **vérifier** un
réglage au lieu de le supposer appliqué — et `conditions.appliquer` relit
systématiquement ce qu'il vient d'écrire. Toute cette enquête a buté sur
l'absence de cette vérification : une soirée entière passée à croire la
machine sourde parce que rien ne disait ce qu'elle avait retenu.

`conditions.lire_condition(n)` rend l'état complet d'une condition, et les
huit se listent d'un coup — utile pour retrouver ses préréglages.

**La machine ÉCRÊTE sans un mot** : une accélération 4 demandée est appliquée
à 3, ce qui ressemble d'abord à un décalage d'une unité. `conditions.BORNES`
refuse la valeur plutôt que de laisser croire qu'on a réglé ce qu'on n'a pas.

Trois crans d'accélération seulement, c'est peu — et c'est pourtant elle qui
plafonne les temps de tracé (voir plus bas). Attendre plus de ~12 cm/s
effectifs sur un parcours à virages est illusoire.

Le réordonnancement du trajet ne tourne qu'à l'envoi : il est en n², donc
trop lourd à rejouer à chaque mouvement d'un réglage, et il ne change rien à
ce que l'aperçu montre.

`theme.py` porte les couleurs — **celles du visualiseur G-code**, recopiées
plutôt qu'importées d'un dépôt à l'autre pour une question d'habillage.
Sombre par défaut, clair pour les captures, accent `#ff8a00`, l'orange de
l'atelier. Quand le dessin déborde, les tracés, l'emprise et le message
passent au rouge **et** le bouton d'envoi se grise : un message d'alerte sous
un style neutre ne se lit pas comme un refus.

**La mosaïque** est dans `mosaique.py`, et s'appelle depuis la ligne de
commande :

```bash
python3 svg2hpgl.py gabarit.svg --mosaique 380x280 --recouvrement 15
```

Elle écrit **un fichier par panneau, sans rien envoyer** : entre deux
panneaux il faut repositionner le média, et l'automatiser ferait tracer le
second par-dessus le premier. `envoyer_hpgl.py` prend le relais :

```bash
python3 envoyer_hpgl.py gabarit_p??.hpgl     # s'arrête entre chaque panneau
```

Il reprend les deux garde-fous du dépôt — contrôle de flux, et refus
d'envoyer si `OH;` reste muet — plus un troisième : il lit l'emprise du
fichier HP-GL et refuse s'il déborde de la zone utile réellement mesurée. Le découpage est un Liang-Barsky par
segment : une polyligne qui traverse la frontière est coupée EXACTEMENT
dessus, et ce qui dépasse disparaît. Un contour fermé coupé devient ouvert —
ce n'est plus un contour.

**La propriété qui compte, c'est que rien ne se perde**, et elle est
vérifiée par deux mesures indépendantes du code testé : un dessin de 25 m
découpé en 20 panneaux **sans** recouvrement redonne 25 563,307 mm, contre
25 563,307 mm à l'original — écart nul au millionième. Et la longueur
retenue dans un panneau donné correspond, à 0,045 mm près sur 3 m, à ce que
donne un échantillonnage du dessin tous les 0,05 mm.

Les **repères en croix** sont posés au MILIEU des bandes de recouvrement,
donc au même endroit physique sur les deux voisins : on superpose, on colle,
le trait est continu. Une croix posée sur le bord d'un panneau, elle, ne
serait pas sur l'autre.

### Ce que le logiciel d'origine faisait, et où on en est

Relevé sur 18 captures de Graphtec Studio v2.70.

**Déjà porté par la machine**, rien à écrire : les 8 conditions, que le
fichier sélectionne par `SP1`..`SP8` ; la compensation d'offset de lame et
son angle, faits dans le firmware. **Déjà mesuré comme exact chez nous** :
l'ajustement de distance X/Y (`OF;` donne 40,00 et le carré de 60 mm l'a
confirmé sur papier).

**Pas encore nécessaire, mais à reprendre le jour où on découpe** — la
découpe de gabarits papier est le besoin d'origine, elle est seulement
remise à plus tard :

| | |
|---|---|
| Nuancier de force jugé au décollement | **fait** : `nuancier_force.py --carres`, une grille de carrés à lever |
| Styles de perforation | une ligne pointillée fait un gabarit détachable — utile, et la machine sait le faire seule |
| Test de découpe / de force | équivalents déjà couverts par le nuancier |
| Cadre d'échenillage | propre au vinyle, sans objet sur papier |
| Repères d'alignement (ARMS) | seulement pour découper au contour un motif **imprimé** ; commandes mal documentées hors SDK |

Deux relevés utiles au passage : le logiciel a un type d'outil **« Stylo
feutre »** dont les valeurs d'usine sont vitesse 10 cm/s, **accélération 2**,
force 2. L'accélération se règle au panneau (`CONDITION` → `ACCEL`) et
n'apparaît dans aucune commande HP-GL — une plume qui accélère fort dérape au
départ de chaque segment.

### La compensation d'offset, vérifiée sur des pointes

`sonde_offset.py` découpe quatre triangles dont le sommet se ferme — 90°,
60°, 45°, 30° — plus un carré témoin. Vérifié le 11/08/2026 sur du 300 g
avec une CB09U : **toutes les pointes sortent franches, jusqu'à 30°**. La
compensation du firmware fait son travail, et le type d'outil `TC1002,2`
est bien ce qui la commande.

**Le carré témoin ne prouve rien**, et c'est pour ça qu'il est là : un
angle droit pardonne tout, et sur 12 mm le défaut se devine à peine. Le
même réglage jugé sur un carré donnait « difficile à dire ».

**Ce qui avait causé les coins arrondis** : nos propres essais du protocole
`TC` avaient laissé le type d'outil sur « Stylo feutre ». Un feutre n'a pas
de déport, donc la machine n'appliquait **aucune** compensation — sans
erreur ni alerte, elle faisait exactement ce qu'on lui avait demandé
plusieurs heures plus tôt.

**Le petit crochet isolé** près du départ n'est pas une bavure : la machine
oriente sa lame par un court mouvement préalable avant d'attaquer
(`PARAM OUTIL` → `LAME INITIALE`, « 2 mm en-deçà » ou « dehors »).

## Les réglages de l'établi

`materiaux.py` porte le carnet de Christophe — huit matériaux réglés à
l'usage, sous Windows, avant tout ce travail. Ce ne sont pas des valeurs
calculées : elles ont été trouvées en coupant du papier.

| Matériau | Vitesse | Force | Épaisseur | Lame |
|---|---|---|---|---|
| ingres 80 g | 40 | 10 | 0,10 | 0,17 |
| vinyle 0,20 mm | 20 | 12 | 0,10 | 0,13 |
| papier 80-90 g | 20 | 10 | 0,10-0,15 | 0,25 |
| aquarelle 200 g | 20 | 14 | 0,30 | 0,35 |
| canson 224 g | 20 | **2 ?** | 0,30 | 0,40 |
| papier 300 g | 7 | 25 | 0,40-0,45 | 0,55 |
| feutre Staedtler | 27 | 15 | — | 2 passages |
| stylo Bic | 30 | 10 | — | 2 passages |

Trois choses qu'on n'aurait pas devinées :

**La hauteur de lame suit l'épaisseur** — 0,10 mm de papier demande 0,17 de
lame, 0,42 en demande 0,55. C'est un réglage **physique sur le porte-lame**,
qu'aucune commande ne touche et qu'aucune force ne rattrape.

**La perforation s'écrit `8 mm / 0,25 mm`** : longueur coupée, longueur
laissée. Voilà ce que sont les « Style 1 à 9 » du logiciel Graphtec.

**Les plumes se tracent en DEUX passages.** La réponse au trait pâle de nos
premiers essais était dans ce carnet.

Une valeur reste douteuse et n'est pas corrigée en douce : le canson 224 g
à force **2**, quand l'aquarelle de même épaisseur en demande 14 et le 300 g
en demande 25. Probable faute de recopie pour 20 — à retrouver au nuancier.

## Quand utiliser quoi

- **Inkscape** pour dessiner et couper au quotidien, réglé comme ci-dessus.
- **`sonde_ce6000.py`** dès que la machine ne répond plus : c'est le premier
  réflexe, et il ne fait rien bouger.
- **`svg2hpgl.py`** pour ce qu'Inkscape ne fait pas : refuser d'envoyer hors
  `READY`, vérifier que le dessin tient dans la zone utile interrogée à la
  machine, et traiter en lot depuis un terminal.
- **vpype** (`write --format hpgl`) si un traitement de chemins plus poussé
  devient nécessaire.
