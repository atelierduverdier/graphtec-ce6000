# Le vocabulaire du pilote Graphtec Studio

Relevé le 13/08/2026 par `strings` sur `Graphtec Studio.exe` (47 Mo, Xojo —
d'où des noms de classes et de méthodes en clair). **Interopérabilité** :
matériel et logiciel appartiennent à l'atelier, le but est de faire marcher
la machine sous Linux.

## Ce que la fouille N'A PAS donné

Les commandes ne sont **pas** stockées entières : elles se construisent à
l'exécution. Trois littéraux seulement — `TC2009`, `TC33,`, `TC35` — là où
on espérait une table. Chercher `TC1002` ne rend rien.

Et rien sur la couche USB, ce qui était attendu : il n'y a rien à décoder,
c'est de l'ASCII sur `/dev/usb/lp0`.

## Ce qu'elle a donné : les NOMS

Le pilote nomme ses propriétés, et une table les répartit **par modèle**.
Section `ce6000` :

    ce6000:settings_getters              (réglages MACHINE)
        offset_force  tool_up_move  initial_blade_position
        display_language  display_length_unit  move_step
        push_roller_sensor  media_sensor  fan_power  beep

    ce6000:STD:condition_getters         (par CONDITION)
        cut_line_pattern

    ce6000:STD:condition_array_getters
        speed(%COND)  force(%COND)  tool(%COND)
        cut_line_pattern(%COND)  distance_adjustment(%COND)
        initial_down_force(%COND)

Et dans le vocabulaire général, applicable :

    step_pass  reference_angle  tool_up_speed  nth_pass
    tangential_emulation  tangential_emulation.mode  (mode_1 / mode_2)
    tangential_emulation_overcut.start_point_length
    overcut_start  overcut_end
    data_sorted_x  data_sorted_y
    auto_pre_feed  auto_pre_feed.length
    cutting_area.lower_left_x/y  .upper_right_x/y
    cutter_orientation  plotter_status  step_size
    dash(%COND)  dash_pitch(%COND)  perforation

## Ce que ça explique de nos mesures

**`data_sorted_x` et `data_sorted_y`** : notre `TC1004,6` prend DEUX champs
et rend `[1, 1]` quand on écrit `1,0`. Le tri s'applique **par axe**, ce
qu'on ne pouvait pas deviner.

**`overcut_start` / `overcut_end`** : exactement les deux champs de
`TC1002,9`, confirmés indépendamment.

**`nth_pass(%COND)`** : la machine sait faire **plusieurs passes par
elle-même**, par condition. Nous les faisons en logiciel (`--passages`),
à l'envers depuis la fin, ce qui ne coûte aucun déplacement — l'avantage
reste probablement à notre méthode, mais la sienne existe.

**`dash(%COND)` / `dash_pitch(%COND)`** : la perforation de la machine,
c'est-à-dire les `LTYPE UP` / `LTYPE DWN` du vidage.

## Les pistes concrètes ouvertes

Les réglages du vidage encore sans numéro de paramètre, avec le nom que le
pilote leur donne :

| dans le vidage | nom du pilote | portée |
|---|---|---|
| `INITIAL DOWN FORCE` | `initial_down_force` | condition |
| `CUT LINE PATTERN` | `cut_line_pattern` | condition |
| `LTYPE UP` / `LTYPE DWN` | `dash` / `dash_pitch` | condition |
| `D. ADJ.` + `X` + `Y` | `distance_adjustment` | condition |
| `UP MODE` | — | condition |

Candidats restants côté protocole : `TC1002,6` (quatre champs, `[9,0,0,0]`),
`TC1002,14`, `TC1002,15`, `TC2004,1`, et les familles `TC2005`, `TC2007`,
`TC2010` jamais explorées.

### `TC33` et `TC35` : sondées, muettes

Essayées le 13/08/2026 sous les formes `TC33`, `TC33,1`, `TC35`, `TC2033`,
`TC2035`, `TC1033`, `TC1035`. **Aucune ne répond, aucune ne change quoi que
ce soit au vidage** — état complet identique avant et après.

Le résultat est valide, et il a fallu s'y reprendre à deux fois pour qu'il
le soit : la première série rendait huit réponses vides d'affilée, ce qui
est la signature d'un instrument en panne autant que d'un vrai négatif.
Refaite avec un **témoin** — `TC2002,3,1`, dont on connaît la réponse —
intercalé entre chaque essai : le témoin a répondu `1,70` à chaque fois,
donc la machine était bien vivante et les silences sont réels.

Ce que ça laisse ouvert : ce sont peut-être des commandes d'ÉCRITURE, qui
ne répondent pas par nature — `TC1002` non plus ne répond pas. Le `TC33,`
du binaire porte d'ailleurs une virgule, donc il attend des arguments.

**Ne pas les balayer à l'aveugle.** `TC35` apparaît dans le binaire à côté
de `Cross_cut_throttle` : la coupe transversale du rouleau est un geste
PHYSIQUE, et une valeur devinée au hasard pourrait la déclencher. Il faudra
une capture USB du logiciel en train de s'en servir, pas du tâtonnement.

## L'ARMS

Le pilote porte les états `cd_status_registering` et
`cd_status_registration_failed`, et une propriété `reg_marks_status`. La
détection existe donc bien dans ce dialogue — mais **aucune séquence de
commande n'a été trouvée en clair**. Les noms `ccRegmarks.*` relevés sont
ceux de l'interface, pas du protocole.

## Les états du traceur, enfin nommés

On ne connaissait que `0` et `8`, et on avait vu passer `4` et `12` sans
savoir. Le pilote les nomme :

    cd_plotter_status_ready       cd_plotter_status_busy
    cd_plotter_status_locked      cd_status_paused
    cd_status_cutting             cd_status_uploading
    cd_status_downloading         cd_status_registering
    cd_status_registration_failed cd_status_error
    cd_status_asleep              cd_status_released
    cd_status_auto_released       cd_status_unknown

La correspondance nom → valeur reste à établir : la liste donne le
vocabulaire, pas les nombres.
