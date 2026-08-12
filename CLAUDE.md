# CLAUDE.md

Ce qui doit être vrai à **chaque** session sur ce dépôt.

Le `README.md` est long et complet : il raconte l'enquête, les mesures et le
protocole. **Ce fichier ne le recopie pas.** Il porte les quelques règles qui
gouvernent la façon de travailler ici, et renvoie au README pour le détail.

## Ce que c'est

Piloter le traceur de découpe **Graphtec CE6000-60** depuis Linux, sans driver.
La machine n'est pas une imprimante propriétaire : c'est un traceur qui lit des
commandes texte. Au bout, une application — `pupitre.py` — qui ouvre un SVG, le
place, le découpe en panneaux, le perfore, règle la machine et l'envoie.

Le reste du dépôt est ce qu'il a fallu comprendre pour l'écrire, **y compris le
protocole propriétaire `TC` de Graphtec**, relevé en capturant le flux USB de
son propre logiciel.

## Non négociable

### 1. Un seul descripteur par exécution

**Fermer et rouvrir `/dev/usb/lp0` entre deux étapes rend la machine muette**,
pour des dizaines de secondes — 44 mesurées. Une lecture du journal suivie d'un
`OH;` répond du premier coup sur un même descripteur, et se tait si l'on
referme entre les deux.

Toute une journée de chasse aux « pannes intermittentes » se réduit à ça. Chaque
programme ouvre donc le périphérique **une fois** et passe son descripteur. Tout
code nouveau qui parle à la machine doit suivre cette règle, sans exception.

### 2. `COMMANDE` sur `HP-GL`, jamais `AUTO`

En `AUTO`, la machine devine le langage d'après ce qu'elle reçoit ; quand elle
se trompe, elle **écrit les octets en toutes lettres, à la plume, sur le
média**, puis affiche « hors surface ». Une conséquence qu'on prend volontiers
pour la cause. La machine met elle-même en garde dans son journal :
`W06001 DANGER COMMANDE = AUTO`.

C'est un réglage de panneau, pas une commande : on ne peut que le vérifier et
le rappeler à l'utilisateur.

### 3. Ne jamais envoyer si la machine ne répond pas

Hors de l'état `READY`, elle **avale les octets sans répondre ni bouger** — le
symptôme est identique à une panne de liaison. `svg2hpgl.py` refuse d'envoyer
si `OH;` reste muet ; garder ce garde-fou dans tout nouveau chemin d'envoi.

Et l'endpoint fait 8 octets : écrire sans attendre le contrôle de flux tronque
les gros fichiers **en silence**.

### 4. Le carnet d'établi n'est pas une table de valeurs à corriger

`materiaux.py` porte huit matériaux réglés **en coupant du papier**, sous
Windows, avant tout ce travail. Aucun calcul ne les reproduit.

Une valeur est douteuse et reste **non corrigée en douce** : le canson 224 g à
force 2, quand l'aquarelle de même épaisseur en demande 14. Probable faute de
recopie pour 20 — à retrouver au nuancier, pas à deviner. Ne jamais « arranger »
un chiffre d'établi : le signaler.

De même, la hauteur de lame est un réglage **physique** sur le porte-lame,
qu'aucune commande ne touche et qu'aucune force ne rattrape.

### 5. Une suite qui passe ne prouve rien

Ce dépôt a produit **cinq détecteurs successifs** qui annonçaient « aucune
erreur » sur des séquences qui en produisaient : l'un comptait un journal vide
comme zéro, l'autre comptait les entrées d'un tampon circulaire dont le total
ne peut pas bouger, un troisième polluait ce qu'il mesurait.

D'où `tests/verifier_les_tests.py`, qui **introduit chaque faute** et exige que
le test la voie. Un test qui passe malgré la faute est signalé comme aveugle.
Tout nouveau test doit y entrer.

## Vérifier une modification

```bash
python3 tests/lancer.py
```

Trois suites, **sans la machine** : les propriétés, leur mise à l'épreuve,
l'interface (hors écran via `QT_QPA_PLATFORM=offscreen`). Le verdict est le code
de sortie.

`tests/test_pupitre.py` existe parce qu'une faute n'avait été vue que par une
capture d'écran : la liste « outil » avait **disparu** de l'interface, une
renumérotation de lignes s'étant appliquée en cascade. Rien n'avait protesté —
le fichier compilait, le champ existait, il répondait aux réglages. Qt empile
deux widgets rangés dans la même case sans un mot.

## Architecture

Trois étages, du quotidien vers l'archéologie :

| | |
|---|---|
| `pupitre.py` | **l'application** — le seul fichier à lancer |
| `svg2hpgl.py`, `envoyer_hpgl.py`, `gabarit_traceur.py`, `nuancier_force.py`, `preparer_planche.py` | les mêmes traitements en ligne de commande |
| `conditions.py`, `materiaux.py`, `mosaique.py`, `etat_machine.py`, `theme.py`, `icones.py` | le moteur, importé par les précédents |
| `sondes/` | les huit programmes qui ont servi à **comprendre** la machine, pas à s'en servir. On n'y touche que pour reprendre l'enquête |

## À l'établi

Le traceur n'est pas toujours branché — la suite tourne sans lui. Mais dès
qu'un essai passe par la machine, une plume ou une lame descend sur du papier
posé par quelqu'un. **Demander avant d'envoyer quoi que ce soit**, et préférer
un tracé au stylo sur une chute à un essai de découpe.

Corollaire du descripteur unique : **ne pas lancer `etat_machine.py` juste
avant un envoi**.

## Ce qui n'est pas fait ici, et ne doit pas l'être

* **La compensation d'offset de lame** : le firmware s'en charge. On lui envoie
  la polyligne nominale, il place la lame. Ne pas la recalculer côté PC.
* **Le calcul de la force de coupe** : elle se trouve sur une chute du vrai
  matériau, en montant jusqu'à ce que le film se détache sans entamer le
  support. Aucun calcul ne donne ce nombre. Plage utile 1 à 38 ; au stylo la
  progression sature vers 10.
