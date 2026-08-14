# Le gabarit à la croix : mesurer la correction de découpe

Une croix seule, sans rien autour : c'est la mire la plus lisible pour
relever l'écart entre ce qui est imprimé et ce qui est découpé. Deux
traits qui se croisent se comparent au dixième ; un dessin, non.

| fichier | usage |
|---|---|
| `croix_seule.svg` | **à ouvrir dans le pupitre** — le dessin seul |
| `croix_mesure.svg` | la feuille complète, repères compris |
| `croix_mesure.pdf` | la même, prête à imprimer à l'échelle 1 |

## Les cotes

    écart entre repères   180 mm dans l'avance, 120 sous le chariot
    marges du composeur   gauche 40, droite 40, bas 70, haut 70
    dessin depuis le 1er repère   70 ; 40 mm
    centre de la croix            90 ; 60 mm
    branches                      20 mm de part et d'autre

La feuille recomposée par le pupitre à partir de `croix_seule.svg` a été
comparée point par point à `croix_mesure.svg` : **identiques au
centième**. L'impression et la découpe viennent donc du même calcul, ce
qui est toute la valeur de la mire — un écart mesuré sur elle ne peut
venir que de la machine.

## La manœuvre

1. imprimer `croix_mesure.pdf` à l'échelle 1, jamais « ajuster à la page »
2. charger la feuille, détecter les repères au panneau
3. ouvrir `croix_seule.svg` dans le pupitre, quatre marges 40/40/70/70
4. mettre le STYLO, cocher « après une détection de repères », envoyer
5. mesurer l'écart entre les deux centres, et le porter dans les deux
   champs « correction »

Ces champs n'agissent que sur la découpe : les appliquer au dessin
déplacerait aussi les repères, donc recréerait l'écart qu'on corrige.
