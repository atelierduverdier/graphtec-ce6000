# Ce que dit le binaire de Cutting Master 3

Relevé le 14/08/2026 sur `Cutting Master 3.exe` (46 Mo) et
`Registration Marks.exe` (10 Mo), copiés depuis
`Windows11/Program Files (x86)/Graphtec Corporation/Cutting Master 3/`.

**Pas de désassemblage.** Cutting Master 3 est une application **Xojo**
— d'où `RBGUIFramework.dll` et les greffons `MBS_*`. Xojo laisse dans le
binaire la table des noms de méthodes et de propriétés, en clair. Le
vocabulaire du programme se lit donc directement, sans décompiler quoi
que ce soit. C'est le même terrain que Graphtec Studio, et il a rendu
davantage.

L'installeur `CM3_V2.2.1070.003_STD.exe` du CD, lui, est une impasse :
entropie 8,00 bit/octet d'un bout à l'autre, tout est compressé derrière
son propre `Decoder.dll`. **Prendre les fichiers d'une installation faite**
coûte infiniment moins cher que d'ouvrir l'installeur.

## CM3 parle GP-GL, pas HP-GL

La méthode s'appelle `SendToCutter_spec_gpgl_generate`, et le préambule
sort en clair, dans cet ordre :

    FC18   FC0   TB99   FM1   TB50,…   &100,100,100   &1,1,1
    TB50,0   FO0   FY0   FY1   …   !10,0
    TB51,…   TB52,2   TB53,…   TB54,0,0   TB55,1   TB123   TB23

C'est **beaucoup plus complet** que ce qu'on avait capturé de Studio, qui
se limitait à `TB99 / TB57 / TB59 / TB52 / TB51 / TB53 / TB55 / TB54 /
TB124 / TB99`.

### Ce qui est neuf

| | |
|---|---|
| `TB123`, `TB23`, `TB50` | jamais vues en capture |
| `TB52,2` | on n'avait observé que `TB52,1` |
| `FC18` / `FC0` | GP-GL, encadrent la séquence |
| `FM1`, `FO0`, `FY0`, `FY1` | réglages GP-GL du travail |
| `&100,100,100` puis `&1,1,1` | facteurs d'échelle, remis à l'unité |
| `!10,0` | vitesse GP-GL |

## `TB55` n'est PAS le numéro du type — c'est un code

Le binaire porte une méthode nommée :

    RegMarkType_Studio_to_PCode

**Une table de conversion** entre le type affiché à l'utilisateur et le
code envoyé à la machine. Elle explique enfin pourquoi Studio dessine des
repères de TYPE 2 dans son propre PDF tout en envoyant `TB55,1`, ce qu'on
tenait pour une incohérence.

Les deux valeurs d'entrée sont dans le binaire, en toutes lettres :
`type_1` et `type_2`.

### Mais `PCode` ne veut pas dire « petit entier »

Le même vocabulaire porte `GetPCode`, `PCodeA`, `AccumPCode_NORMAL`,
`AccumPCode_TB57_MODE` : un **PCode est le programme de commandes
accumulé**. `RegMarkType_Studio_to_PCode` ne convertit donc pas un numéro
en numéro — elle traduit un type de repère en **séquence de commandes**.

Et `type_1` / `type_2` sont rangés à côté de `registration_mark_type=` :
ce sont les valeurs de la DESCRIPTION DU TRAVAIL, pas du protocole.

### `TB55,1` est une CONSTANTE

Relevé en distinguant, dans le binaire, les chaînes complètes des simples
préfixes complétés à l'exécution :

| constantes | préfixes |
|---|---|
| `TB5` `TB23` `TB50,0` `TB52,2` `TB54,0,0` `TB55,1` `TB99` `TB123` | `TB50,` `TB51,` `TB53,` |

`TB55,1` ne varie donc **jamais** dans Cutting Master 3, quel que soit le
type de repère du travail. Studio envoie la même chose. Ce champ ne porte
pas le type, et l'essai de `TB55,2` du 13/08/2026 n'avait aucune raison
d'aboutir — il n'a effectivement rien changé.

## Le paramètre qui reste : `TB57`

`AccumPCode_TB57_MODE`. C'est le **seul** paramètre de notre séquence
dont un binaire officiel dise qu'il porte un mode, et il **ne figure pas**
parmi les chaînes constantes de CM3 : il est donc construit à l'exécution,
ses valeurs changent selon ce qu'on demande.

Or on envoie `TB57,1,1` depuis le premier jour, recopié de la capture,
sans savoir ce que ça réclame. C'est là qu'il faut essayer.

Rendu réglable dans `arms.sequence_scan(tb57=…)` et dans le pupitre, sous
« essais de protocole ».

## Les modes de repérage, nommés par le programme

    use_registration_marks_mode
      reg_marks_4_point_auto           (bâti par « reg_marks_ » + N + « _point_auto »)
      reg_marks_segment_auto
      reg_marks_segment_divisional

    should_use_divisional_reg_marks
    should_use_v_segment_reg_marks

Et les paramètres du travail, tels que CM3 les écrit :

    registration_mark_type=            type_1 | type_2
    registration_mark_size=
    registration_mark_thickness=
    registration_mark_arrays 1,1
    registration_mark_array_block_spacing 0,0
    registration_mark_distance_adjustment=off | on
    ,x_axis,   ,y_axis,

`registration_mark_distance_adjustment` est le `MARK DISTANCE` du panneau,
vu du côté du travail. Il a donc bien un rôle dans la détection, et CM3 le
pose explicitement à chaque envoi plutôt que de s'en remettre au réglage
de la machine.

## La boucle de détection, confirmée

    :status_clear reg_marks_status
    :start_polling reg_marks_status
    :registration_loop
    :stop_polling reg_marks_status
    :registration_loop_2
    AccumPCode_NORMAL
    AccumPCode_TB57_MODE

C'est exactement la structure qu'on avait reconstituée à l'analyseur USB :
on efface l'état, on lance, **on interroge en boucle**, on s'arrête. Notre
`ESC.C11:` est ce `reg_marks_status`.

`AccumPCode_TB57_MODE` dit au passage que **`TB57` a un mode**, là où on
envoie `TB57,1,1` sans savoir ce qu'on demande.

Deux boucles distinctes — `registration_loop` et `registration_loop_2` —
recoupent les **deux phases de recherche** observées le 13/08/2026 dans
un scan de 24 secondes.

## La description d'un jeu de repères

`rm.RegMarksSpec` porte :

    s_type   s_regsize   s_thickness   s_count
    s_step_size   s_step_direction   s_inversion
    marks_rect   limit_rect   geometry_mm   geometry_border
    pdefn_absolute | pdefn_job | pdefn_media

Ces trois derniers sont le piège « Par rapport à : Tâche / Support »
rencontré dans Studio, ici nommé sans ambiguïté : les repères se placent
en absolu, par rapport au TRAVAIL, ou par rapport au MÉDIA.

Et le résumé que CM3 affiche :

    Reg Marks : Type= / Size= / Thickness= / Step Size=
    Reg Marks=OFF

## Ce que ça ne donne pas

**La forme d'une réponse réussie.** Le binaire dit ce que le programme
envoie et comment il interroge, pas ce que la machine répond. Cette
moitié-là ne s'obtient que d'une détection qui aboutit, et elle reste à
capturer — voir `protocole_arms.md`.
