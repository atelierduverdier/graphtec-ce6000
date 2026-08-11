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

### La machine dit TOUT d'elle-même, en clair, en une commande

**Trouvé le 11/08/2026, et ça relativise la journée entière qui précède.**

```
ESC . v : TC2009,5 ␃
```

rend **quatre kilo-octets de configuration en texte lisible** : les huit
conditions de découpe, les réglages d'outil, l'ARMS, la surface, le média,
l'interface, les commandes, l'avancé. Chaque ligne est nommée en clair.

```
[TOOLS]
STEP PASS=7
OFFSET FORCE=30
OFFSET ANGLE=30
DATA SORT=OFF
TOOL UP SPEED=40
CONDITION PRIORITY=PROGRAM
INITIAL BLADE=2mm BELOW
TOOL UP MOVE=DISABLED
```

`etat_machine.py` la lit, l'analyse, met les huit conditions en tableau,
enregistre un vidage et **compare deux états** — donc nomme un réglage sans
qu'on ait à deviner dans quelle famille numérique il se cache.

```bash
python3 etat_machine.py --conditions
python3 etat_machine.py --section TOOLS
python3 etat_machine.py --comparer etat_2026-08-11.txt
```

Et `TC2010,9` rend le **journal d'erreurs horodaté**, nos propres bêtises
comprises : `HP-GL ERREUR 1 INSTRUCTION INCONNUE`, `DANGER COMMANDE = AUTO`,
`ERREUR REPLACER GALETS`. Les horodatages sont négatifs — des heures écoulées
depuis maintenant.

**Ce que le vidage confirme d'un coup**, après qu'on l'eut établi
péniblement : `HP-GL MODEL EMULATED=7586`, `HP-GL ORIGIN=LOWER LEFT`,
`COMMAND=AUTO`, `GP-GL STEP SIZE=0.100 mm`, `CONDITION PRIORITY=PROGRAM` — ce
dernier ayant coûté une soirée à comprendre. Toutes les mesures étaient
justes. Toutes tenaient en une ligne que la machine savait dire.

**Comment il a été trouvé, et pourquoi si tard.** Un premier balayage des
familles `TC2000`–`TC2020` n'avait interrogé que leurs paramètres 1 à 3 et
conclu que deux familles répondaient — alors qu'on savait déjà que `TC2004` ne
répond qu'au 6 et `TC2006` au 13. Une sonde trop courte rend des absences qui
ressemblent à des faits. Le balayage refait sur 1 à 25 a trouvé **60
paramètres** et six familles, dont celle-ci.

**Ce qu'il ne fait pas** : il ne LIT que. L'écriture reste `TC1002`, et le
relevé encadrant garde son usage — trouver comment écrire un réglage qu'on
sait maintenant lire. Il ne dit rien non plus de l'état courant du chariot ni
du média chargé.

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

### « HP-GL ERREUR 1 INSTRUCTION INCONNUE » : réelle, sans effet, sans cause connue

Le panneau l'affiche à chaque envoi, et le journal de la machine
(`etat_machine.py --journal`) la confirme, horodatée à la seconde.

**Elle ne bloque rien.** Vérifié pas à pas le 11/08/2026 : après chacune,
la machine reste sur `READY`, répond à `OH;`, aux lectures `TC` et au
vidage. Les deux panneaux du porte-manteau ont été tracés avec.

**Sa cause n'est PAS établie**, et deux explications avancées ici ont été
retirées après mesure :

- « elle sort la machine de `READY`, d'où les silences d'`OH;` » — faux, la
  machine répond après chacune ;
- « les commandes `TC` commencent par `ESC.` et l'analyseur HP-GL les
  refuse » — un détecteur par horodatage, celui-là fiable, ne trouve RIEN :
  ni `OH;`, ni `IN;/SP/PU`, ni l'état `TC`, ni une lecture `TC2002`, ni une
  écriture `TC1002`, ni un choix d'outil, ni le vidage, ni l'ouverture-
  fermeture du périphérique.

Ce qui en produit une, en revanche, c'est **un envoi complet qui trace
réellement**. Reste donc une seule chose non éprouvée : le `PD`, plume
baissée. L'essai du fichier entier avait été fait plume levée, tous les
`PD` remplacés par des `PU` — sans erreur. Trancher coûte une feuille :
envoyer un panneau SANS `--materiau`, puis regarder l'horodatage du haut.

**Ce compteur s'est trompé deux fois, et la seconde est la plus
instructive.** D'abord un journal lu VIDE compté comme zéro erreur, d'où un
verdict de `+13` puis `-13`. Puis, une fois cette panne bouchée, il a
encore conclu « aucune erreur » sur une séquence qui en produisait deux —
visibles dans le journal six minutes plus tard, horodatées.

La raison : **le journal est un tampon circulaire**. Une entrée nouvelle
en chasse une ancienne, donc le NOMBRE d'« instruction inconnue » ne
bouge pas pendant qu'elles se renouvellent. Compter une grandeur qui ne
peut pas varier, c'est mesurer avec certitude quelque chose qui n'existe
pas.

La bonne mesure est l'**horodatage du haut** : une entrée plus jeune que
l'action qu'on vient de faire est une entrée neuve. Ce détecteur-là a été
validé avant de servir — 25 secondes d'attente sans rien envoyer, l'entrée
du haut a vieilli de 26 secondes et aucune n'est née.

Et c'est Christophe qui l'a débusqué, en lançant simplement la commande
qu'on lui avait donnée : la ligne du haut affichait 35 secondes là où mon
compteur venait de jurer que rien ne s'était produit.

Pour savoir si un envoi vient d'en produire une, regarder l'horodatage du
haut : négatif, il compte en arrière depuis maintenant.

```bash
python3 etat_machine.py --journal | head -3
```

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
condition, **type d'outil**, vitesse, force et accélération.

Les **icônes d'outil** (`icones.py`) sont dessinées d'après ce qui distingue
les lames : la largeur de la pointe suit le diamètre, son angle suit celui
de la lame. Ce n'est pas décoratif — le type déclaré doit correspondre à
l'outil monté, et un « Stylo feutre » oublié a arrondi tous les angles d'une
découpe le 11/08/2026. La plume n'a pas de pointe triangulaire, parce
qu'elle n'a pas de déport. L'envoi se refuse tant que le dessin déborde.

Vitesse, force et accélération passent par `conditions.py` et le protocole
`TC` — elles **modifient durablement** la condition enregistrée dans la
machine, exactement comme le fait Graphtec Studio, d'où la case « régler la
machine à l'envoi » qu'on peut décocher.

| Paramètre | Commande | Plage |
|---|---|---|
| vitesse | `TC1002,3,<cond>,<cm/s × 10>` | 1 à 640, soit 64 cm/s |
| force | `TC1002,4,<cond>,<n>` | 1 à 38 |
| accélération | `TC1002,5,<cond>,<n>` | **1 à 3 seulement** |
| type d'outil **+ offset** | `TC1002,2,<cond>,<code>,<offset>` | voir la table ci-dessous ; offset −5 à +5 |

Les codes d'outil ont été relevés en parcourant la liste du logiciel Graphtec
**deux fois de haut en bas** — la même suite les deux fois, donc une mesure
reproduite et non une déduction sur un seul passage :

| Outil | Code | | Outil | Code |
|---|---|---|---|---|
| CB09U | 1 | | CB15UB | 3 |
| CB09U-K60 | 10 | | Autre | 6 |
| CB15U | 2 | | Stylo feutre | 9 |

#### Le second champ est l'offset — et il était visible depuis le début

Longtemps porté ici comme « inexpliqué ». Nommé le 11/08/2026 par un relevé
encadrant : offset porté à 3 au panneau (`[COND/TEST]`, `[2]` OUTIL, `[3]`
OFFSET), et de onze paramètres relevés **un seul bouge**, `TC2002,2`, de
`[1, 0]` à `[1, 3]`. Gamme lue sur l'écran : **−5 à +5**, conforme au manuel.

Il s'écrit depuis le PC, négatifs compris — `−2`, `5`, `0` demandés, les trois
relus conformes.

Deux tentatives avaient échoué avant, chacune pour sa raison. Changer
CB15U → CB09U ne montre rien : la retouche vaut 0 pour les deux lames, et un
paramètre identique avant et après ne se voit dans aucune différence. Et le
relevé lui-même mentait tant qu'il ne jetait pas sa première interrogation.

Mais la leçon n'est pas là. **Le champ se donnait à voir depuis le premier
jour** : dans la capture USB il passait de 0 à 1 pendant que le logiciel
Graphtec parcourait sa liste d'outils, et les captures d'écran de ce même
logiciel affichaient « Offset : 1 ». Deux indices concordants, écartés d'une
phrase — « un état du logiciel, pas une propriété du réglage » — faute d'avoir
cherché ce qu'ils avaient en commun. La mesure qui a fini par trancher n'a rien
appris que ces deux indices ne disaient déjà.

**Et ça cachait un bug.** `regler_outil` envoyait ce champ à 0 en dur : comme
la commande écrit les deux valeurs d'un coup, **choisir un outil effaçait
l'offset**. Le réglage posé au panneau disparaissait au premier profil appliqué,
sans rien afficher. Corrigé : `offset=None` relit la valeur en place et la
conserve, `regler_offset()` fait la symétrique (changer l'offset sans toucher à
la lame). Vérifié en posant 4, en choisissant un outil, et en relisant 4.

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

Relevé sur 18 captures de Graphtec Studio v2.70. Christophe, le 11/08/2026 :
« ça me paraît léger les réglages par rapport au logiciel officiel ». Il avait
raison, et le compte exact suit.

Studio avait **trois** panneaux là où le pupitre n'en a qu'un.

#### Panneau « Condition » — celui qu'on couvre

| Réglage de Studio | Chez nous |
|---|---|
| Type d'outil | **oui**, avec icônes dessinées d'après le diamètre et l'angle |
| Offset | **oui** depuis le 11/08/2026, −5 à +5, grisé pour un stylo |
| Vitesse | **oui** |
| Accélération | **oui** |
| Force de coupe | **oui** |
| Motif de ligne de découpe (styles 1-9 + 3 utilisateur) | **autrement** : perforation logicielle en longueurs exactes, `--perforation 8,0.25`. Studio lui-même offrait le choix entre « perforation du cutter » et « du logiciel » |
| Passages | **non** — présent dans `materiaux.py` (2 pour les plumes) mais pas branché dans la chaîne. C'est la réponse au trait pâle du premier essai |

#### Panneau « Paramètres outil » — celui qu'on ne couvre pas du tout

| Réglage de Studio | Valeur vue sur la capture | État |
|---|---|---|
| Passe-pas (Step Pass) | 1 | **lu** : `[TOOLS] STEP PASS` |
| Force d'offset | 30 | **lu** : `OFFSET FORCE` |
| Angle d'offset | 30° | **lu** : `OFFSET ANGLE` |
| Position initiale de la lame | 2 mm en-deçà / dehors | **lu** : `INITIAL BLADE` |
| **Vitesse outil relevé** | 40 cm/s | **lu** : `TOOL UP SPEED`, et probablement `TC2008,2` qui vaut 400 |
| Déplacer activé/désactivé | — | **lu** : `TOOL UP MOVE` |

Tous lisibles depuis `etat_machine.py`. Reste à trouver comment les **écrire** :
le relevé encadrant sert encore à ça, et il est maintenant beaucoup plus rapide
puisqu'on peut vérifier d'un coup d'œil que la manipulation a pris.

#### Panneau « Avancé » et média

| Réglage | État |
|---|---|
| Mode média épais (tangentiel) : désactivé / mode 1 / mode 2 | **lu** par condition : `TANGENTIAL MODE`, à 1 sur la n° 8 |
| Ajustement de la distance X / Y | **lu** : `D. ADJ.=OFF` avec `X=0.59`, `Y=0.00` sur la condition 1 — désactivé, la capture Studio disait vrai, et notre carré de 60 mm sort juste sans lui |
| Pré-alimentation automatique | **lu** : `[MEDIA] AUTO PRE FEED=OFF`, `AUTO PRE FEED LENGTH=500.0mm` |
| Langue, unité, taille du pas, ventilateur, capteurs, bip | réglages de machine, pas de travail — le panneau les porte très bien |

#### Ce qu'on a en plus

Le compte serait malhonnête sans l'autre colonne : mosaïque avec repères
d'assemblage, perforation aux longueurs voulues plutôt que neuf motifs figés,
réordonnancement des chemins pour raccourcir les trajets à vide, relecture
systématique de chaque réglage écrit, et un gabarit TechDraw à la taille utile
du traceur.

#### Comment combler le reste

Onze paramètres répondent sur la condition 1, **cinq sont nommés**. Les six
autres sont très probablement dans les tableaux ci-dessus. `chercher_parametre.py`
les nomme un par un, en trois minutes chacun :

```bash
python3 chercher_parametre.py --debut
```

changer UNE chose au panneau, revenir à `READY`, puis :

```bash
python3 chercher_parametre.py --fin "step pass"
```

`--reste` liste ce qui manque.

#### Ce que le Step Pass a appris en n'étant pas là où on le croyait

`TC2002,15` valait 1 et le Step Pass a 1 pour défaut : la coïncidence était
belle. Step Pass porté à **7** au panneau le 11/08/2026, relevé encadrant sur
les quatre familles — **aucun des onze paramètres ne bouge**. L'hypothèse
tombe, et elle apprend plus que si elle avait tenu.

Le chemin au panneau dit dans quelle famille chercher :

| Réglage | Chemin au panneau | Famille |
|---|---|---|
| offset, vitesse, force, accélération, outil | **`[COND/TEST]`** — écran des conditions | `TC1002`/`TC2002`, indexés par condition |
| Step Pass | **`[PAUSE/MENU]` → `[1]` TOOL → `[2]` PAS** — menu machine | ailleurs |

Les quatre familles balayées sont **toutes indexées par condition**. Un réglage
qui ne dépend pas de la condition ne peut pas y être, quel que soit le soin du
relevé. Autrement dit : la structure des menus de la machine est une carte du
protocole, et on cherchait dans la mauvaise page.

**Et le premier balayage de familles ne prouvait rien non plus** : il
interrogeait les paramètres 1 à 3 de chaque famille, alors qu'on savait déjà
que `TC2004` ne répond qu'au 6 et `TC2006` au 13. Ses « familles muettes »
étaient un artefact de son étroitesse — une sonde trop courte rend des
absences qui ressemblent à des faits.

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
| Styles de perforation | **fait en logiciel** : `--perforation 8,0.25` |
| Test de découpe / de force | équivalents déjà couverts par le nuancier |
| Cadre d'échenillage | propre au vinyle, sans objet sur papier |
| Repères d'alignement (ARMS) | seulement pour découper au contour un motif **imprimé** ; commandes mal documentées hors SDK |

Deux relevés utiles au passage : le logiciel a un type d'outil **« Stylo
feutre »** dont les valeurs d'usine sont vitesse 10 cm/s, **accélération 2**,
force 2. L'accélération se règle au panneau (`CONDITION` → `ACCEL`) et
n'apparaît dans aucune commande HP-GL — une plume qui accélère fort dérape au
départ de chaque segment.

### Le gabarit en deux passes : l'origine tient

Vérifié le 11/08/2026 sur du 80 g A3 : contour tracé au stylo, changement
d'outil **sans décharger le média**, puis le même contour coupé à la lame.
**La coupe tombe sur le trait.** Changer d'outil ne déplace donc pas
l'origine, et un gabarit peut porter ses repères à l'encre et son contour à
la lame.

Le piège à éviter, sinon on conclut de travers : **le type d'outil déclaré
doit correspondre à ce qui est physiquement monté**. Avec `CB09U` déclaré
pendant qu'un stylo est en place, la machine applique une compensation
d'offset à un outil qui n'en a pas et décale le tracé d'un demi-millimètre
— ce qui ressemble exactement à une origine qui bouge.

Second piège, physique celui-là : **la hauteur de lame ne suit pas le
profil**. Elle reste où on l'a laissée, et une lame sortie à 0,55 mm pour du
300 g laboure un 80 g quelle que soit la force. Aucune commande ne la
corrige.

### La perforation, faite en logiciel

```bash
python3 svg2hpgl.py gabarit.svg --perforation 8,0.25 --envoyer
```

8 mm coupés, 0,25 laissés — les cotes du carnet d'établi. C'est ce que le
logiciel Graphtec appelle « Style 1 à 9 » ; le faire ici donne **les
longueurs exactes** au lieu de neuf motifs figés, et Graphtec lui-même
offrait le choix entre « perforation du cutter » et « du logiciel ».

Le découpage se fait en **abscisse curviligne** : un tiret enjambe
plusieurs segments d'une courbe aplatie, et le motif franchit les angles
sans se remettre à zéro. Vérifié sur une ligne de 100 mm — 97,000 mm
coupés là où 8/8,25 en prédit 96,970.

**Vérifié sur le papier le 11/08/2026** : un carré de 60 mm perforé tient
dans la feuille et se détache à la main. La réserve annoncée — 0,25 mm
paraissant trop court pour lever une lame — était infondée, et c'est le
papier qui l'a tranché.

La perforation est appliquée **après** le réordonnancement : la faire
avant multiplierait par vingt le nombre de chemins, et l'ordonnancement
est en n².

### La compensation d'offset, vérifiée sur des pointes

`sonde_offset.py` découpe quatre triangles dont le sommet se ferme — 90°,
60°, 45°, 30° — plus un carré témoin. Vérifié le 11/08/2026 sur du 300 g
avec une CB09U : **toutes les pointes sortent franches, jusqu'à 30°**. La
compensation du firmware fait son travail, et le type d'outil `TC1002,2`
est bien ce qui la commande.

La retouche d'offset — le second champ de cette même commande — valait **0**
pendant cet essai, sa valeur d'usine. Des pointes franches à 30° avec une
retouche nulle veulent dire qu'il n'y a rien à retoucher pour ce couple
lame/papier. Si un jour une pointe bavait ou rentrait, c'est ce champ-là qu'il
faudrait bouger, d'un cran à la fois, dans la gamme −5 à +5.

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
