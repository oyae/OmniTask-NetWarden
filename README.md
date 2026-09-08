# 🛡️ VRTX macOS Security & Optimization Suite

Repositorio que alberga dos herramientas independientes orientadas al rendimiento y seguridad avanzada en macOS: **OmniTask** y **NetWarden**.

---

## 📂 Contenido del Repositorio

* **`OmniTask/`**: Interfaz gráfica (GUI) e interactiva para monitorear el rendimiento del sistema y gestionar recursos.
* **`NetWarden/`**: Guardián de seguridad ejecutable como demonio (`LaunchDaemon`) que realiza *hardening* de navegadores web y aislamiento de subprocesos.

---

## 🚀 Instalación y Uso

### 1. OmniTask (GUI)
Aplicación de monitoreo de recursos para el usuario.

```bash
cd OmniTask
pip3 install -r requirements.txt
python3 main.py

*Opcional (Iniciar automáticamente con el sistema como LaunchAgent):*
```bash
mkdir -p ~/Library/LaunchAgents
cp config/com.vrtx.omnitask.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vrtx.omnitask.plist

### 2. NetWarden
Demonio en segundo plano para protección y hardening de navegadores web

Instalar dependencias de Python:
cd NetWarden
pip3 install -r requirements.txt

Desplegar el script ejecutable en el sistema:
sudo mkdir -p /Library/Scripts
sudo cp net_warden.py /Library/Scripts/net_warden.py
sudo chmod 755 /Library/Scripts/net_warden.py
sudo chown root:wheel /Library/Scripts/net_warden.py

Registrar e iniciar el demonio en launchd:
sudo cp config/com.security.netwarden.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.security.netwarden.plist
sudo chmod 644 /Library/LaunchDaemons/com.security.netwarden.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.security.netwarden.plist

Para consultar el logro de NetWarden en tiempo real:
sudo tail -f /var/log/net_warden.log