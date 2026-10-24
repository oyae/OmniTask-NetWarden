#!/bin/bash

APP_DIR="$HOME/OmniTask"
REPORTS_DIR="$APP_DIR/Reports"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="com.vrtx.omnitask.plist"

if ! command -v python3 &> /dev/null; then
    echo "Python3 is not installed. Installing Command Line Tools..."
    xcode-select --install
    echo "Please run this script again when the Apple installation is complete."
    exit 1
fi

mkdir -p "$APP_DIR"
mkdir -p "$REPORTS_DIR"
mkdir -p "$PLIST_DIR"

# Se elimina la copia de setup.py
cp main.py gui.py requirements.txt Stress.png speedometer.png "$APP_DIR/"
cp -r config "$APP_DIR/" 2>/dev/null

echo "Installing dependencies..."
python3.14 -m pip install --user -r "./requirements.txt" --break-system-packages

echo "Cleaning previous services of OmniTask..."
# Forzamos la salida por identificador y limpiamos el registro de la caché de launchd
launchctl bootout gui/$(id -u)/com.vrtx.omnitask 2>/dev/null
launchctl remove com.vrtx.omnitask 2>/dev/null

echo "Copying configuration and starting service..."
cp "config/$PLIST_FILE" "$PLIST_DIR/"
chmod 644 "$PLIST_DIR/$PLIST_FILE"
launchctl enable gui/$(id -u)/com.vrtx.omnitask
launchctl bootstrap gui/$(id -u) "$PLIST_DIR/$PLIST_FILE"

echo "Installation completed and service is running in background."