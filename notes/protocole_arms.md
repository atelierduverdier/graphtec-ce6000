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

## Ce que ça ouvre

`TB124` **dit exactement où Studio attend les repères**. Le gabarit peut
donc être engendré à partir de la capture plutôt que deviné : on lit ce que
Studio demande, on le trace, et la détection a une chance d'aboutir.

Reste à obtenir une capture d'un scan RÉUSSI pour connaître la réponse qui
porte les coordonnées trouvées — la moitié du protocole qui manque encore.
