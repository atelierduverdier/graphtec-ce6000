#!/usr/bin/env python3
"""Ce qu'une capture d'écran a vu et que la syntaxe ne voit pas.

Le 11/08/2026, la liste « outil » a DISPARU de l'interface : une
renumérotation des lignes s'était appliquée en cascade — 1 devient 3, puis
3 devient 5, puis 5 devient 7 — et le champ a fini par occuper la case d'un
autre. Rien n'a protesté : le fichier compilait, le champ existait, il
répondait aux réglages. Il n'était simplement plus visible.

Qt empile silencieusement deux widgets rangés dans la même case. C'est
exactement le genre de faute qu'un test attrape mieux qu'un relecteur.

    QT_QPA_PLATFORM=offscreen python3 tests/test_pupitre.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from PySide6.QtWidgets import QApplication, QGridLayout, QWidget  # noqa: E402

import pupitre                                                    # noqa: E402


def _grilles(racine):
    """Toutes les QGridLayout de l'arbre, avec le titre qui les porte."""
    trouvees = []
    for w in racine.findChildren(QWidget):
        lay = w.layout()
        if isinstance(lay, QGridLayout):
            titre = w.title() if hasattr(w, "title") else w.objectName()
            trouvees.append((titre or w.__class__.__name__, lay))
    return trouvees


def test_aucune_case_occupee_deux_fois(fenetre):
    """Deux widgets dans la même case : Qt les empile, l'un disparaît."""
    for titre, grille in _grilles(fenetre):
        cases = {}
        for i in range(grille.count()):
            item = grille.itemAt(i)
            if item.widget() is None:
                continue
            r, c, hr, hc = grille.getItemPosition(i)
            for dr in range(hr):
                for dc in range(hc):
                    cle = (r + dr, c + dc)
                    autre = cases.get(cle)
                    assert autre is None, (
                        f"grille « {titre} » : la case {cle} porte à la fois "
                        f"{autre} et {_nom(item.widget())}")
                    cases[cle] = _nom(item.widget())


def _nom(w):
    txt = ""
    for methode in ("text", "currentText"):
        if hasattr(w, methode):
            try:
                txt = getattr(w, methode)()
                break
            except Exception:
                pass
    return f"{w.__class__.__name__}({txt[:24]!r})" if txt else w.__class__.__name__


def test_tous_les_champs_sont_places(fenetre):
    """Un champ créé mais jamais rangé dans une mise en page est invisible."""
    prefixes = ("spn_", "cmb_", "chk_", "lbl_", "b_")
    orphelins = []
    for nom in dir(fenetre):
        if not nom.startswith(prefixes):
            continue
        w = getattr(fenetre, nom)
        if isinstance(w, QWidget) and w.parentWidget() is None:
            orphelins.append(nom)
    assert not orphelins, f"champs jamais placés : {orphelins}"


def test_aucun_titre_ne_perd_son_esperluette(fenetre):
    """Qt lit `&` comme un raccourci clavier et l'EFFACE de l'affichage.

    « Print & cut » s'affichait « Print _cut », le `c` souligné. Aucun
    test ne pouvait le voir : le texte est bien celui qu'on a écrit, c'est
    le rendu qui diffère. Repéré sur une capture d'écran, comme la liste
    « outil » qui avait disparu sous un autre widget.

    La règle : dans un libellé Qt, une esperluette littérale se double.
    """
    from PySide6.QtWidgets import QGroupBox, QCheckBox, QPushButton, QLabel
    for classe in (QGroupBox, QCheckBox, QPushButton, QLabel):
        for w in fenetre.findChildren(classe):
            titre = w.title() if classe is QGroupBox else w.text()
            sans_doubles = titre.replace("&&", "")
            assert "&" not in sans_doubles, (
                f"« {titre} » : esperluette non doublée, Qt l'effacera "
                f"et soulignera la lettre suivante")


def test_les_onglets_sont_nommes(fenetre):
    attendus = ["Dessin", "Outil", "Machine"]
    obtenus = [fenetre.onglets.tabText(i)
               for i in range(fenetre.onglets.count())]
    assert obtenus == attendus, f"onglets : {obtenus}, attendu {attendus}"


def lancer():
    app = QApplication.instance() or QApplication([])
    fenetre = pupitre.Pupitre()
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    echecs = []
    for nom, f in tests:
        try:
            f(fenetre)
            print(f"  ok    {nom}")
        except AssertionError as e:
            echecs.append((nom, str(e)))
            print(f"  RATÉ  {nom}")
    print()
    if echecs:
        for nom, message in echecs:
            print(f"{nom} :\n    {message}")
        print(f"\n{len(echecs)} test(s) sur {len(tests)} ont échoué.")
        return 1
    print(f"{len(tests)} tests passent.")
    return 0


if __name__ == "__main__":
    sys.exit(lancer())
