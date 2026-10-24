#!/bin/bash

APP_DIR="$HOME/OmniTask"
REPORTS_DIR="$APP_DIR/Reports"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="com.vrtx.omnitask.plist"

if ! command -v python3 &> /dev/null; then
    echo "Python3 no está instalado. Instalando Command Line Tools..."
    xcode-select --install
    echo "Vuelve a ejecutar este script cuando la instalación de Apple termine."
    exit 1
fi

mkdir -p "$APP_DIR"
mkdir -p "$REPORTS_DIR"
mkdir -p "$PLIST_DIR"

cp main.py gui.py setup.py requirements.txt "$APP_DIR/"
cp -r config "$APP_DIR/" 2>/dev/null

echo "Instalando dependencias..."
python3.10 -m pip install --user -r "$APP_DIR/requirements.txt" --break-system-packages

echo "Reiniciando el servicio OmniTask..."
if launchctl print gui/$(id -u)/com.vrtx.omnitask &> /dev/null; then
    launchctl bootout gui/$(id -u) "$PLIST_DIR/$PLIST_FILE" 2>/dev/null
fi

cp "config/$PLIST_FILE" "$PLIST_DIR/"
launchctl bootstrap gui/$(id -u) "$PLIST_DIR/$PLIST_FILE"

echo "Instalación completada y servicio en marcha."
