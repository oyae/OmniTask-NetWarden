# 🛡️ VRTX macOS Security & Optimization Suite

Repository that hosts two independent tools aimed at performance and advanced security in macOS: **OmniTask** and **NetWarden**.

---

## 📂 Repository Content

* **`OmniTask/`**: Graphical and interactive interface (GUI) to monitor system performance and manage resources.
* **`NetWarden/`**: A security guard runnable as a daemon (`LaunchDaemon`) that performs *hardening* of web browsers and thread isolation.

---

## 🚀 Installation and Use

### 1. OmniTask (GUI)
Resource monitoring application for the user.

```bash
OmniTask cd
pip3 install -r requirements.txt
python3 main.py
```

*Optional (Auto-start with system as LaunchAgent):*
```bash
mkdir -p ~/Library/LaunchAgents
cp config/com.vrtx.omnitask.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.vrtx.omnitask.plist
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