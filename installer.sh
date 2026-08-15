#!/usr/bin/env bash
# Installe le lanceur du pupitre dans le menu des applications.
#
# Rien de système : tout va dans ~/.local, donc pas de sudo et une
# désinstallation qui tient en une ligne (voir --retirer).
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="$HOME/.local/share/applications"
ICONES="$HOME/.local/share/icons/hicolor/scalable/apps"
NOM=graphtec-traceur

if [[ "${1:-}" == "--retirer" ]]; then
    rm -f "$APPS/$NOM.desktop" "$ICONES/$NOM.svg"
    update-desktop-database "$APPS" 2>/dev/null || true
    echo "lanceur retiré."
    exit 0
fi

command -v python3 >/dev/null || { echo "python3 introuvable" >&2; exit 1; }
python3 -c "import PySide6" 2>/dev/null || {
    echo "PySide6 manque : sudo pacman -S pyside6" >&2; exit 1; }

mkdir -p "$APPS" "$ICONES"
install -m 644 "$ICI/resources/icons/traceur.svg" "$ICONES/$NOM.svg"
# Guillemets DOUBLES : la spec Desktop Entry réserve l'apostrophe, et
# desktop-file-validate refuse le fichier si on l'emploie pour citer.
# Guillemets DOUBLES : la spec Desktop Entry réserve l'apostrophe,
# et desktop-file-validate refuse le fichier si on l'emploie.
EXEC="python3 \"$ICI/pupitre.py\""
sed -e "s|@EXEC@|$EXEC|" \
    -e "s|@ICON@|$NOM|" \
    "$ICI/$NOM.desktop" > "$APPS/$NOM.desktop"
chmod 644 "$APPS/$NOM.desktop"
update-desktop-database "$APPS" 2>/dev/null || true

echo "Lanceur « Pupitre de tracé » installé."
echo "   menu      : $APPS/$NOM.desktop"
echo "   icône     : $ICONES/$NOM.svg"
echo "   retirer   : $ICI/installer.sh --retirer"
