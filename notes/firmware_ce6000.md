# Le firmware CE6000 V2.70, décortiqué

Fichier fourni par Christophe le 14/08/2026 :
`GRAPHTEC-CD/CE6000_FU(v270)/CE6000_V270.x` (4,33 Mo). C'est l'image de
mise à jour, pas un vidage de la machine en marche.

**Le binaire n'est PAS dans ce dépôt** : il appartient à Graphtec. Ce
fichier ne consigne que ce qu'on en a appris. L'image reconstruite et les
extractions restent dans le bac à sable.

## Le format `.x` — enregistrements de 24 octets

Un en-tête `0b 00`, trois octets d'adresse, un marqueur `0c`, un octet de
drapeau, seize octets de données, une somme de contrôle :

    0b 00 AA AA AA 0c FF  DD DD DD DD DD DD DD DD DD DD DD DD DD DD DD DD  CK

La somme est `CK = somme(octets[2..22]) & 0xff` — **vérifiée sur les
180 607 enregistrements, 100 %**. Les données utiles sont les octets
`[7..23]`.

L'adresse est un mot de 16 bits dans une fenêtre à `0x10xxxx` ; le firmware
est **paginé par banques de 64 Ko**, écrites à la file. Remis bout à bout
dans l'ordre du fichier, on obtient une image linéaire de **2,89 Mo**.

Le script de reconstruction est dans le bac à sable (`fw/`). Il refuse tout
enregistrement dont la somme ne tombe pas juste, et se resynchronise aux
9 sauts de banque.

## Ce que la machine est, au fond

| | |
|---|---|
| processeur | **SH-3** (« Graphtec Simple Debugger for SH-3 Release.1.00.2007 ») |
| système | **ITRON** (`cre_tsk`, `exit_tsk`, `Kernel Trace Monitor`, `ITRON_TraceCount`) |
| repères, en interne | **« Tonbo »** — 蜻蛉, le mot japonais pour un repère de calage |

Décortiquer du code SH-3 sous ITRON sur 2,89 Mo pour trouver POURQUOI le
scan lancé du PC échoue là où celui du panneau réussit serait un chantier
de plusieurs semaines, à l'issue incertaine. **Ce n'est pas fait, et je ne
promets pas de le faire.** Ce qui suit vient des chaînes de caractères, pas
du désassemblage — et ça suffit à faire avancer le vrai problème.

## Le message que Christophe a vu, enfin nommé

Le firmware porte DEUX messages d'erreur de scan distincts, de deux chemins
de code différents :

| affiché | anglais d'origine | sens réel (par le portugais, sans ambiguïté) |
|---|---|---|
| `ERREUR SCAN REPER!` | `MARK SCAN ERROR!` | `ERRO MED. MARCAS` — erreur de **mesure** |
| `MARQUE SCAN ERREUR` | (2ᵉ variante) | `ERRO LEITURA DAS MARCAS` — erreur de **LECTURE** |

Christophe a eu la seconde, sur la feuille aux repères rallongés : **« la
tête a trouvé où lire et n'a pas réussi à LIRE »**. Ce n'est ni une affaire
de position ni de géométrie — c'est le signal du capteur qui n'a pas suffi.
Elle est d'ailleurs suivie de `RETRY` (« 1 RECOMMENCEZ »).

Cela **confirme** la piste de `SENSING SPEED` : le manuel dit qu'une
détection qui rate à la lecture s'améliore en LENTE, et c'est exactement le
défaut nommé ici. Voir [protocole_arms.md].

## Comment la machine décide qu'un repère est là

Le débogueur intègre tout un jeu de commandes « Tonbo » qui met la logique
à nu :

    cmd adc     Tonbo AD get         — lit la valeur brute du capteur
    cmd trate   Set threshold rate   — le SEUIL est un POURCENTAGE d'un pic
    cmd tbave   move average number  — le signal est moyenné sur N mesures
    cmd tsttb   PEAK_GET / AVE_PEAK_GET
    cmd tg      gain auto set         — depuis « Manufactur » ou « User »
    cmd sct     Tonbo search test

Le seuil de détection n'est donc pas un niveau absolu : c'est un
**pourcentage d'un pic mesuré**, calculé « Search & calculation Threshold »
soit depuis les données d'usine, soit depuis les données utilisateur. Le
vidage de la machine dit `RM SENSOR LEVEL ADJ SELECT=USER`.

**Hypothèse, à marquer comme telle :** la détection MANUELLE au panneau
recalcule ce seuil sur la matière présente (c'est ce que fait « recalibrer
le capteur »), tandis que le chemin déclenché du PC réutilise le seuil
stocké. Cela collerait avec le seul fait solide qu'on tient depuis le
début — le scan manuel réussit, le scan PC échoue, sur la même feuille et
la même calibration. Non prouvé : il faudrait le voir dans le code, ou le
mesurer via `cmd adc`.

## Un mode service existe — hors de portée par l'USB d'impression

Le firmware contient un menu de maintenance complet : `MAINTENANCE MODE`,
`SELF TEST`, un `ARMS menu` avec `TEST ARMS SENSOR`, `Monitor XY`,
**`Output last scan`** (qui donnerait ce que le capteur a vu au dernier
essai), et un débogueur série `gsd>` avec lecture/écriture mémoire.

**On n'a PAS la combinaison de touches qui y entre**, et le `gsd>` répond
sur une liaison série/réseau, pas sur `/dev/usb/lp0`. Surtout : y écrire en
mémoire sur la vraie machine, à l'aveugle, est exactement le genre de sonde
risquée que la prudence d'atelier interdit. **Ne pas tenter d'entrer dans
ce mode sans la procédure officielle.** C'est noté comme une piste, pas
comme une manœuvre.

Ce que ça vaut quand même : si un jour on trouve l'entrée documentée,
`Output last scan` et `cmd adc` diraient d'un coup si le capteur voit le
repère — la question qu'on se pose depuis le début.
