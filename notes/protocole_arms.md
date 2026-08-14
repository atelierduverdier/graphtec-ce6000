# L'ARMS : la famille `TB`

Capturée le 13/08/2026 sur `usbmon1` pendant que Graphtec Studio lançait
une détection de repères. Une seule tentative, isolée du reste — c'est ce
qui rend la lecture immédiate.

## La séquence, en clair

    ESC.v:ESC.C10:          deux fois — mise en mode, pas une question
    TB99 ␃                  ouverture
    TB57,1,1 ␃
    TB59,0,0 ␃
    TB52,1 ␃
    TB51,800 ␃              longueur des branches : 800/40 = 20,0 mm
    TB53,40 ␃               épaisseur : 40/40 = 1,0 mm
    TB55,1 ␃                type de repère : 1
    TB54,0,0 ␃
    TB124,10280,6800 ␃      ÉCART entre repères : 257,0 × 170,0 mm
    TB99 ␃                  fermeture — et probablement le déclenchement

**`TB` est une famille neuve.** On ne connaissait que `TC`, et le binaire
de Studio ne portait que `TC33`/`TC35`/`TC2009` en clair — `TB` n'y
apparaît pas, il se construit à l'exécution.

Trois paramètres se décodent sans ambiguïté parce qu'ils recoupent des
cotes connues : `TB51` vaut 800 pour les 20 mm mesurés au pixel sur les
PDF de Studio, `TB53` vaut 40 pour le 1 mm, `TB55` vaut 1 pour le type 1.
L'échelle est celle de la machine, 40 unités par millimètre.

`TB57`, `TB59`, `TB52`, `TB54` restent sans signification établie — dit
plutôt que deviné.

## Les états, enfin distingués

    ESC.v:ESC.C1:     -> 8 (occupée) ou 0 (libre)      celui qu'on connaissait
    ESC.v:ESC.C11:    -> 0, 1, 6, 10                   un SECOND état, plus riche

Apparier chaque question à sa réponse était nécessaire : les valeurs se
mélangeaient dans le flux et on lisait `6` ou `10` en croyant interroger
`C1`. Le pilote de Studio nomme une quinzaine d'états (`cd_status_paused`,
`cd_status_registering`, `cd_status_cutting`…) — reste à les rattacher aux
nombres.

## Pourquoi la détection a échoué

`TB124,10280,6800` annonce des repères espacés de **257 × 170 mm** :
l'A4 de Studio, 297 × 210, moins les marges de 20 mm de chaque côté.

Or `gabarit_arms.py` les avait posés dans la **zone utile de la machine**,
256,8 × 197,7 — donc espacés de 216,8 × 157,7. La machine cherchait à
**quarante millimètres** de l'endroit où ils étaient.

Ce n'est ni le marqueur ni le capteur : c'est un désaccord de repère entre
deux logiciels qui parlaient chacun de « 20 mm de marge » sans parler de la
même chose.

## Seconde capture : la convention de Studio, vérifiée

Marges portées de 20 à 35 mm dans Studio, et `TB124` devient
**`9080,5600`** — soit **227,0 × 140,0 mm**, exactement l'écart que
`gabarit_arms.py --ecart 227x140` produit.

La convention supposée était donc juste : **écart = feuille − 2 × marge**,
la feuille étant l'A4 dans le sens où elle est chargée. Elle n'est plus
supposée, elle est vérifiée par la machine.

## Le préambule de Studio, et la famille `ESC.C31`

La seconde capture montre ce que Studio demande AVANT de scanner :

    ESC.v:ESC.C31;9:       -> 'CE6000-60, V2.70'   modèle et micrologiciel
    ESC.v:ESC.C31;9;5:     -> 'STD'                la variante
    ESC.v:ESC.C31;60:      -> '0'
    ESC.v:ESC.C31;16:      -> '3'
    ESC.v:ESC.C31;20:      -> '0'
    ESC.v:ESC.C31;29:      -> '4'
    ESC.v:TC2008,1,3   TC2009,5   TC2002,1   TC2006,1

`ESC.C31;<n>:` est une famille d'**identification** qu'on ne connaissait
pas. Notre `sondes/sonde_ce6000.py` se contente d'`OI;`, qui rend `7586` —
le modèle ÉMULÉ, pas la machine. `ESC.C31;9:` donne son vrai nom et sa
version de micrologiciel.

## Le piège « Par rapport à : Tâche »

Le panneau de Studio place les repères **relativement au DESSIN** par
défaut (« Par rapport à : Tâche »), et non au média. Déplacer ou changer
le motif déplace donc les repères avec lui, et `TB124` change sans qu'on
ait touché aux marges.

Constaté le 13/08/2026 sur quatre captures : `227,0 × 140,0 mm` trois fois
de suite, puis **`115,6 × 105,2`** — c'est-à-dire l'emprise de l'ellipse
qui servait de motif, après que Christophe l'eut changée et déplacée.

Pour un gabarit fixe, mettre **« Par rapport à : Support »**. Sans quoi
chaque retouche du dessin invalide les repères déjà tracés.

`TB124` accepte d'ailleurs des **décimales** — `TB124,4622.80,4209.60` —
ce que les valeurs entières des premières captures ne laissaient pas voir.

## Les états pendant un scan

Suivis pas à pas dans la capture, du déclenchement à l'échec :

    ESC.C1:   -> 8 sans interruption            « occupée », rien de plus
    ESC.C11:  -> 0, puis 1 pendant tout le
                 balayage, puis 6               1 = elle CHERCHE, 6 = fini/échoué

`ESC.C11` est donc l'état utile : c'est lui qui distingue la recherche du
reste, là où `ESC.C1` se contente de dire « occupée ».

## Pourquoi un repère au marqueur ne suffit pas

**Établi par élimination le 13/08/2026**, en six captures. La dernière est
la seule où TOUT concordait :

    écart demandé par Studio : 227,0 × 140,0 mm
    gabarit tracé            : 227,0 × 140,0 mm

Et elle échoue comme les autres. Or les autres variables ont été
contrôlées une à une :

| | vérifié |
|---|---|
| position | premier repère à l'origine, là où la machine balaye |
| place | 256,5 × 197,7 disponibles pour 227 × 140 |
| inclinaison | feuille droite |
| cotes | 20 mm de branche, 1 mm d'épaisseur — mesurées au pixel ET confirmées par `TB51`/`TB53` |

Reste le **noir**. Un marqueur ne donne ni la densité ni la netteté de bord
d'une impression, et le capteur est réglé serré : `SENSING LEVEL(X,Y)=22,24`.
Le manuel prévient d'ailleurs que « les repères ne pourront pas être
détectés si l'impression est de mauvaise qualité ».

**Le banc d'essai sans imprimante a donc une limite**, et c'est celle-là.
Il aura permis de décoder tout le protocole — ce qui était son but — mais
pas d'obtenir une détection réussie. Pour la réponse d'un scan qui
aboutit, il faudra une vraie impression.

## Un scan ARMS piloté par NOTRE code

**Le 13/08/2026, la séquence a été rejouée depuis Linux**, sans Graphtec
Studio, et la machine a cherché :

    ESC.v:ESC.C10:  (deux fois)
    TB99 / TB57,1,1 / TB59,0,0 / TB52,1 / TB51,800
    TB53,40 / TB55,1 / TB54,0,0 / TB124,9080,5600 / TB99

    0,1 s -> C11 = 1     elle cherche
    7,7 s -> C11 = 6
   18,0 s -> C11 = 1     elle cherche encore
   24,0 s -> C11 = 10

Vingt-quatre secondes de balayage, deux phases de recherche — ce qui
ressemble à deux repères successifs. **Le protocole est donc utilisable
en l'état** : ce qui manque n'est plus la commande, c'est la détection.

## Pourquoi un repère TRACÉ ne se détecte pas

Le niveau de détection descendu à **30 %**, le minimum que la machine
accepte, ne change rien. Ce n'est donc pas une affaire de seuil.

Le manuel le dit en toutes lettres :

> « Le capteur est réglé pour scanner des repères **imprimés** en noir sur
> un fond blanc. Réajustez le niveau de détection en fonction de la couleur
> et de la **brillance** de la matière. »

La brillance. Un feutre laisse un noir qui réfléchit ; un toner diffuse.
Le noir « uniforme à l'œil » ne l'est pas pour le capteur.

**Le seul essai restant** : la calibration du capteur emploie les valeurs
UTILISATEUR (`USER SENSOR GAIN=14`, `USER BASE LEVEL=532`) et non celles
d'usine (`gain 15`, `base 0`) — quelqu'un l'a réglée un jour sur une
matière inconnue. `RM SENSOR LEVEL ADJ SELECT` la bascule. S'il échoue
aussi, il faudra une impression.

## Ce que ça ouvre

`TB124` **dit exactement où Studio attend les repères**. Le gabarit peut
donc être engendré à partir de la capture plutôt que deviné : on lit ce que
Studio demande, on le trace, et la détection a une chance d'aboutir.

Reste à obtenir une capture d'un scan RÉUSSI pour connaître la réponse qui
porte les coordonnées trouvées — la moitié du protocole qui manque encore.

## Le résultat est POUSSÉ, pas lu — 13/08/2026

Ce qui manquait n'était pas une commande de lecture : **il n'y en a pas.**
La machine annonce l'issue du scan d'elle-même, sur l'endpoint d'entrée,
quelques dizaines de millisecondes avant de passer à l'état terminal.

    17,522 s   C11 = 1        elle cherche
    22,952 s   « 1,254 »      poussé SPONTANÉMENT, terminé par un CR
    23,034 s   C11 = 10       fini

Deux traits distinguent cette trame de toutes les autres :

* elle finit par **`\r`**, là où chaque réponse à une question finit par
  `\x03` ;
* elle arrive **sans qu'on ait rien demandé**.

Interroger `TB50`, `TB100`, `TB124`, `TB125`, `TB126` — en écriture comme
en lecture, et leurs variantes `TB2xxx` — ne rend jamais rien. C'était la
bonne question posée au mauvais mécanisme.

### Pourquoi ça a échappé à treize captures

Notre boucle vidait le tampon avant chaque question, pour ne pas lire la
réponse précédente. Elle jetait donc l'annonce à tous les coups. La trame
n'est apparue que le jour où la purge a été rendue **bavarde** — elle
affiche ce qu'elle ramasse au lieu de l'avaler.

C'est le même piège que les cinq détecteurs cassés du 11/08 : l'instrument
détruisait ce qu'il était censé mesurer.

### Les deux formes connues

    1,254                     scan lancé depuis le PC, échoué
    1,1,0,1,1,1,0,1           laissé par un scan lancé au PANNEAU

Deux champs contre huit : ce ne sont pas les mêmes messages. Le sens de
`254` (0xFE) n'est pas établi — dit plutôt que deviné. La forme que prend
un scan RÉUSSI, celle qui portera les coordonnées, reste à voir.

### Un scan lancé au panneau n'émet rien sur l'USB

Vérifié le 13/08/2026 : capture ouverte pendant une détection déclenchée
aux touches, 116 trames pour le traceur, **toutes nos propres questions**.
On ne capturera donc jamais une détection réussie par cette voie. En
revanche la machine LAISSE son annonce dans le tampon, où elle attend le
premier lecteur — c'est de là que venait `1,1,0,1,1,1,0,1`.

### La géométrie, et pourquoi 227 déborde

`OH;` rend **255,8 × 197,7 mm** de zone utile pour un A4 chargé par le
petit côté. Un écart de 227 mm dans l'avance ne laisse que 28,8 mm au-delà
du premier repère, et il en faut 20 rien que pour la branche du dernier.
Le scan au panneau l'a montré sur la pièce : **deux repères détectés, le
troisième hors zone**.

Un écart de **190 × 140** passe quel que soit le décalage de l'origine
machine sur la feuille — décalage qu'on n'a pas encore mesuré.

### Le toner passe, le feutre non

Établi le 13/08/2026 : sur repères IMPRIMÉS, le scan au panneau en trouve
deux. Sur repères au marqueur, jamais aucun, à tous les niveaux de
détection. La limite était bien celle qu'annonçait le manuel — la
brillance de la matière — et elle est franchie.

Piège d'imprimante à noter : une laser qui a dormi laisse des **images
fantômes** répétées à la circonférence du tambour (~74 mm), assez franches
pour que le capteur les prenne pour des repères.

## ARMS FONCTIONNE — vérifié sur le papier le 13/08/2026

Fin de la chasse. Avec le gabarit **officiel de Graphtec** imprimé au
toner, la détection aboutit et l'origine est posée.

La preuve n'est pas un état lu dans un registre, c'est une croix tracée.
Le gabarit `ARMStest_type2.pdf` porte une croix de 40 mm exactement au
centre de ses quatre repères ; après détection, on a fait tracer une croix
au même endroit calculé. **Elle est tombée à 5 mm.**

### Le gabarit officiel

`GRAPHTEC-CD/ARMS Test Files/ARMStest_type{1,2}.pdf`, datés de 2008. Ils
valent mieux que tout ce qu'on redessine :

    page          208,8 x 296,3 mm — PAS de l'A4, donc jamais « ajuster à la page »
    branches      20,00 mm
    écarts        150,00 et 160,00 mm entre les ANGLES
    croix témoin  40 mm, au centre des quatre repères
    forme         des TRAITS, pas des aplats — l'angle mesuré est donc
                  déjà le centre de trait, la référence qu'exige le manuel

### Ce que valent nos gabarits maison

Ils étaient en **type 2** — angles vers l'extérieur — et la machine était
réglée sur type 2. Ils s'accordaient. Ce n'était pas la forme qui clochait.

### Où tomber : 75 ; 75, mesuré en trois croix

Trois essais sur la même feuille, chacun tracé après une détection
réussie, chacun comparé à la croix imprimée du gabarit :

| centre visé (avance ; chariot) | résultat |
|---|---|
| 80 ; 75 | 5 mm de trop dans l'avance |
| 75 ; 80 | avance juste, 5 mm d'écart sous le chariot |
| **75 ; 75** | **superposée** |

**Et ça ne colle pas avec la géométrie du gabarit.** Les repères officiels
sont espacés de 150 et 160 mm ; leur centre est donc à 75 et **80**. La
machine, elle, veut 75 et 75. Il y a **5 mm entre l'angle du repère et
l'origine que pose la détection**, dans le sens de l'avance uniquement.

**Et le manuel officiel dit que ça se MESURE.** Trouvé le 13/08/2026 au
soir dans `Manuel utilisateur CE6000 V01.pdf`, p. 5-5 :

> Le point d'origine du plotter sera celui défini par les repères […] et
> il est différent du point d'origine des données de découpe. La
> différence entre ces deux points s'appelle un offset.
>
> **Mesurez la distance** entre le point d'origine des données de découpe
> et le point d'origine des repères.

Ce n'est donc pas une anomalie à élucider : c'est une cote d'installation
que Graphtec lui-même prescrit de relever, et qui dépend du logiciel qui
a créé les repères — « un offset peut être généré à la création des
repères en fonction du logiciel utilisé ». Les trois croix étaient la
méthode prévue, pas un pis-aller.

Le rattrapage se règle dans `PARAM ARMS 2/4` -> `[4]` OFFSET ORIGINE AXE,
ou se soustrait côté PC. Reste utile de vérifier sur un second gabarit
d'écarts différents que la valeur ne dépend pas de l'écart.

L'hypothèse « les axes ont été intervertis » (`5 = (160-150)/2`) était
séduisante et **fausse** : elle prédisait 75 ; 80, qui a raté.

### Le rattrapage existe dans la machine

`PARAM ARMS 2/4` -> `[4]` **OFFSET ORIGINE AXE**, X et Y, de -1000 à
+1000 mm, à 0,0 chez nous. Il règle l'écart entre le repère détecté et le
point de départ de la découpe — quel que soit d'où vient le décalage.

### L'origine après détection

Le manuel (p. 5-18) la place **sur le repère point 1**, celui détecté en
premier. C'est bien la convention qu'on a supposée.

### Un scan au panneau n'émet RIEN — 3 fois sur 3

Capture ouverte pendant trois détections lancées aux touches : aucune
trame de données, et tampon vide après. Pour obtenir l'annonce qui porte
le résultat, il faut **déclencher depuis le PC**.

### La procédure manuelle, p. 5-39

`[PAUSE/MENU]` -> `[2]` ARMS -> `[2]` LECTURE MANUELLE REPERES. On amène
la **pointe de l'outil** — pas le capteur, pas le chariot — dans le quart
de surface enfermé par l'angle du L, puis ENTER, et la machine redemande
la même chose pour chaque repère.

Le manuel avertit qu'une découpe est lancée juste après la détection :
**mettre le stylo, pas la lame.**

## Pourquoi le balayage automatique trouve le BORD de la feuille

Symptôme rapporté par Christophe le 13/08/2026 : « il scanne le bord de
la feuille puis me dit HORS SURFACE », aussi bien depuis Graphtec Studio
que depuis le panneau.

Le capteur ne reconnaît pas une forme, il voit une **transition
clair/sombre**. Le bord de la feuille en est une, plus franche que
n'importe quel repère : papier blanc, puis la bande de découpe sombre en
dessous. La tête le prend pour un repère, bâtit son repère dessus, en
déduit un second point hors de la feuille — d'où `HORS SURFACE`. L'erreur
est vraie, sa cause est ailleurs.

### La cause : MARK DISTANCE à zéro

`Manuel utilisateur CE6000 V01.pdf`, p. 5-14, menu `[PAUSE/MENU]` >
`[2]` ARMS > `[4]` POSITION REPERES :

> Paramétrer la distance entre les repères permet de **ne pas scanner
> inutilement la surface entre les repères**. […] Le saut de la distance
> vers le repère suivant **ne se fera pas si la valeur est réglée à
> 0 mm**.

Le vidage de la machine donne `MARK DISTANCE x,y = 0.0mm, 0.0mm`. Aucun
saut, donc : elle balaie tout l'espace entre deux repères, bord compris.

**À régler à la vraie distance** — X dans le sens de l'avance, Y sous le
chariot. Pour le gabarit officiel chargé par le petit côté : 160 et 150.

Avertissement du manuel : la valeur X doit rester inférieure à la
longueur du média, sinon **le média est éjecté**.

### L'autre voie : la détection manuelle

`[2]` LECTURE MANUELLE REPERES (p. 5-39). On amène la **pointe de
l'outil** dans le quart de surface enfermé par l'angle du premier L —
pas sur le trait — puis ENTER, et la machine redemande la même chose
pour chaque repère. En lui montrant où chercher, elle ne peut plus
tomber sur le bord.

C'est aussi ce qui manque à NOTRE scan piloté depuis Linux : il envoie
la séquence `TB` et laisse la machine chercher depuis là où elle dort.
Même cause, même échec en cinq secondes.

## Les GALETS décident de là où la tête cherche

Trouvé par Christophe le 13/08/2026, sur la machine — pas dans le code :
**rapprocher les galets entraîneurs supprime le balayage du bord.**

Les galets bornent la course utile du chariot. Écartés, ils laissent la
tête démarrer au-delà du papier ou juste sur son bord, et la première
transition qu'elle rencontre est ce bord. Resserrés autour de la feuille,
le point de départ tombe à l'intérieur, et le bord n'est plus sur le
chemin.

Aucune ligne de configuration ne porte cette cote. Elle se règle à la
main, sur la machine, et c'est en regardant la tête qu'on la trouve.

## « NIVEAU DE SCAN INSUFFISANT » : la calibration du capteur

Symptôme suivant, une fois le bord écarté : la tête atteint le repère et
n'en tire pas assez de signal.

Le manuel utilisateur (p. 5-20) prévoit exactement ça — **AJUST NIVEAU
CAPTEUR**, qui règle le seuil AUTOMATIQUEMENT en scannant un vrai repère
sur la vraie matière :

    [PAUSE/MENU] > [2] ARMS > POSITION haut DEUX FOIS -> PARAM ARMS (3/4)
    [2] AJUST NIVEAU CAPTEUR > [1] SCAN
    amener l'outil dans la zone de détection du repère, puis [ENTER]

Le manuel demande d'employer pour ça la « mirre de réglage », c'est-à-dire
`ARMStest_type1.pdf` ou `ARMStest_type2.pdf` du CD — les mêmes fichiers
que le gabarit d'essai.

**Ça explique pourquoi changer SENSING LEVEL n'a jamais rien donné.** Le
vidage montre `USER SENSOR GAIN=14`, `USER BASE LEVEL=532`,
`RM SENSOR LEVEL ADJ SELECT=USER` : quelqu'un a lancé cette calibration
une fois, sur une matière inconnue, et la machine juge tout papier avec ce
seuil depuis. On tournait un bouton en aval d'un réglage faux en amont.

## La calibration du capteur : ce qu'elle change vraiment

Lancée par Christophe le 13/08/2026 sur une feuille sortie du composeur,
puis relevée dans le vidage avant/après :

| | avant | après |
|---|---|---|
| `USER SENSOR GAIN` | 14 | **34** |
| `USER BASE LEVEL` | 532 | 515 |
| `USER SENSING LEVEL(X,Y)` | 22, 24 | **397, 525** |

Le gain a plus que doublé. Les anciennes valeurs venaient de quelqu'un
qui avait calibré une fois, sur une matière inconnue, il y a des années.
`AJUST NIVEAU CAPTEUR` agit donc réellement — ce n'est pas un geste
symbolique.

**Bouger les galets remet `MARK DISTANCE` à zéro.** Constaté le même jour.
La machine repart de neuf quand le média change, et un réglage fait avant
un rechargement est perdu sans avertissement.

## Le dernier désaccord connu : TB55

Un scan piloté par le pupitre, sur une feuille dont l'écart concordait
(`TB124,9036,5952` = 225,9 × 148,8 mm, la valeur même du composeur), avec
le capteur fraîchement calibré : la machine cherche **8,8 secondes** puis
`C11 = 6`, sans aucune annonce.

Tout concordait sauf une chose : on envoie **`TB55,1`** alors que le
vidage annonce `MARK TYPE=2`. Studio fait pareil — d'où l'hypothèse d'une
numérotation à partir de zéro — mais c'est désormais le seul écart debout
entre ce qu'on envoie et ce que la machine dit d'elle-même.

Rendu réglable plutôt que tranché : `arms.scanner(type_repere=...)`, câblé
sur le choix du pupitre. **Reste à essayer les deux sur la même feuille**,
et à comparer. C'est un essai, pas une conclusion.

## Le scan piloté depuis le PC : ce qui a été éliminé — 14/08/2026

L'erreur exacte, lue sur une vidéo du panneau :

    E04024  ARMS
    ERREUR SCAN REPER !
    NIVEAU DE DETECTION INSUFFISANT

Ce n'est donc PAS une affaire de géométrie : la tête va où on la met, elle
balaie, et le capteur ne tire pas assez de signal. Or la détection
**manuelle au panneau réussit** sur la même feuille, avec la même
calibration. Quelque chose diffère entre les deux chemins.

Essayé, sans le moindre effet :

| essai | durée de recherche | issue |
|---|---|---|
| `TB55,2` au lieu de `TB55,1` | 9,5 s | identique |
| `TB57,2,1` au lieu de `TB57,1,1` | 8,8 s | identique |
| sans déplacement de tête | 8,8 s | identique |
| tête amenée à 35 ; 30 | 4,5 s | identique |
| tête amenée à 30 ; 35 | 6,4 s | identique |
| `TB50,1` + `TB50,0` + queue `TB123 TB23` | 4,9 s | identique |

La durée de recherche **change avec la position de départ** : la machine
tient donc compte du déplacement, le mécanisme répond. Mais l'issue est
toujours `C11 = 6`, sans annonce.

`TB50` n'écrit rien dans la calibration : les huit valeurs du vidage sont
intactes après l'avoir envoyé, gain et seuils compris. Vérifié plutôt que
supposé — et vérifié APRÈS l'avoir envoyé, ce qui était l'ordre inverse
du bon.

### Ce qui explique peut-être tout

**On n'a jamais capturé une détection RÉUSSIE.** Les six captures de
Studio du 13/08/2026 sont toutes des échecs, et c'est de l'une d'elles
qu'on a tiré notre séquence. On rejoue donc fidèlement une session qui
ratait déjà.

Le renseignement qui manque n'est pas dans un binaire — il est dans une
capture USB d'un scan qui aboutit, sous Windows, avec Cutting Master 3 ou
Studio. C'est la seule mesure qui reste à faire, et elle est à portée
maintenant que le print & cut fonctionne au panneau.

## LE PRINT & CUT EST BOUCLÉ — 14/08/2026

Croix tracée sur croix imprimée, **superposées**. La chaîne complète est
vérifiée sur le papier, du SVG ouvert dans le pupitre au tracé qui
retombe dessus.

**La correction est NULLE.** Les deux champs restent à zéro. L'écart de
2,5 et 3 mm relevé la veille venait du recadrage fait entre l'export et
l'envoi — la mesure était polluée, comme on le soupçonnait, et non d'un
défaut de la machine. C'est ce qu'a montré la mire à la croix : deux
traits qui se croisent se comparent au dixième, un dessin non.

### La recette, dans l'ordre

1. dessiner, ouvrir dans le pupitre
2. marges de repères telles que l'ensemble tienne dans la zone
   ATTEIGNABLE — le pupitre le calcule et prévient
3. exporter ou imprimer la feuille, **à l'échelle 1**
4. charger, **rapprocher les galets** juste assez
5. détecter au panneau, en amenant la tête sur le premier repère
6. envoyer, case « après une détection de repères » cochée

### Les quatre conditions, toutes nécessaires

| | pourquoi |
|---|---|
| repères imprimés au **toner** | un feutre réfléchit, le capteur ne le voit pas |
| **galets rapprochés** | sinon la tête démarre hors du papier et trouve le bord |
| **capteur recalibré** sur la matière | le seuil d'usine datait d'une matière inconnue |
| **tête posée** sur le premier repère | l'automatique l'exige aussi, pas seulement le manuel |

Aucune ne se voit dans le protocole. Trois se règlent à la main sur la
machine, et la quatrième dépend de l'encre.

### Ce qui reste ouvert

Le scan piloté **depuis le PC** n'a jamais abouti — neuf variantes, même
issue. Notre séquence vient d'une capture d'ÉCHEC de Graphtec Studio, et
aucun réglage ne peut faire aboutir ce qui ne menait pas au succès. Il
faudrait capturer une détection **réussie** sous Windows.

Mais ce n'est plus un besoin : la détection au panneau prend dix secondes
et fonctionne.

## Longueur des repères — la piste ouverte le 14/08/2026

Christophe : « pour la détection automatique, une chose que l'on n'a pas
testée, c'est des repères plus longs ».

**Le manuel donne 4 à 20 mm** (f90bbf.pdf, « Dimension des Repères »,
p. 5-12). Le gabarit était figé à 20 — donc DÉJÀ au maximum que la machine
sache déclarer. L'essai était impossible à monter, ce qui explique qu'il
n'ait jamais été fait.

Le manuel dit lui-même pourquoi il vaut le coup :

> S'il y a une inclinaison de l'impression sur la matière, il sera plus
> facile de détecter des grands repères. […] Il est plus facile de
> détecter des grands repères sur une longue page.

Et il précise que **la détection commence au repère en bas à droite**,
puis cherche les autres verticalement et horizontalement. Si l'impression
est de travers, les petits repères tombent hors de la zone de détection.
C'est très exactement le symptôme : la tête part, longe le bord et
s'arrête « hors surface ».

### Ce qui est mesuré

| | |
|---|---|
| plage annoncée | 4 à 20 mm |
| épaisseur annoncée | 0,3 à 1 mm |
| écart entre repères | **inchangé** quelle que soit la longueur — la cote à saisir au panneau reste la même |
| type 2, branches > marge | les repères **mordent sur le dessin** — signalé avant impression |
| type 1 | jamais de chevauchement, les branches sortent |

### Ce qui reste à éprouver sur papier

Imprimer une feuille avec des branches de 30 mm en laissant **MARK SIZE à
20 au panneau**, et lancer la détection automatique. La machine cherchera
un repère de 20 mm et trouvera 30 mm de matière là où elle regarde. Rien
dans la notice ne dit que ça la gêne, rien ne dit que ça l'aide : seule la
feuille tranchera.

Augmenter les marges d'autant en type 2, sans quoi les branches rentrent
dans le motif.
