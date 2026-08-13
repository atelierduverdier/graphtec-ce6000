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

## Ce que ça ouvre

`TB124` **dit exactement où Studio attend les repères**. Le gabarit peut
donc être engendré à partir de la capture plutôt que deviné : on lit ce que
Studio demande, on le trace, et la détection a une chance d'aboutir.

Reste à obtenir une capture d'un scan RÉUSSI pour connaître la réponse qui
porte les coordonnées trouvées — la moitié du protocole qui manque encore.
