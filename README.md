# 🛡️ VRTX macOS Security & Optimization Suite

Repository that hosts two independent tools aimed at performance and advanced security in macOS: **OmniTask** and **NetWarden**.

Any dev that wants to help in developing ports to windows/linux is welcomed!

---

## 📂 Repository Content

* **`OmniTask/`**: Graphical and interactive interface (GUI) to monitor system performance and manage resources.
* **`NetWarden/`**: A security guard runnable as a daemon (`LaunchDaemon`) that performs *hardening* of web browsers and thread isolation.

---

## 🚀 Installation and Use

### 1. OmniTask (GUI)
Resource monitoring application for the user.

```bash
cd OmniTask
# In case of not having a recent version of Python installed:
brew install python@3.14 

chmod +x install.sh
./install.sh
```

*In case you need to stop and uninstall the program*
```bash
launchctl bootout gui/$(id -u)/com.vrtx.omnitask
rm ~/Library/LaunchAgents/com.vrtx.omnitask.plist
```

### 2. NetWarden
Background daemon for web browser protection and hardening

Install Python dependencies:
```
cd NetWarden
pip3 install -r requirements.txt
```

Deploy the executable script on the system:
```
sudo mkdir -p /Library/Scripts
sudo cp net_warden.py /Library/Scripts/net_warden.py
sudo chmod 755 /Library/Scripts/net_warden.py
sudo chown root:wheel /Library/Scripts/net_warden.py
```

Register and start the daemon in launchd:
```
sudo cp config/com.security.netwarden.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.security.netwarden.plist
sudo chmod 644 /Library/LaunchDaemons/com.security.netwarden.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.security.netwarden.plist
```

To check NetWarden's achievement in real time:
```
sudo tail -f /var/log/net_warden.log
```
*In case you need to stop and uninstall the program*
```bash
sudo launchctl bootout system /Library/LaunchDaemons/com.security.netwarden.plist
sudo rm /Library/LaunchDaemons/com.security.netwarden.plist
```