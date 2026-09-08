#!/usr/bin/env python3
"""
NetWarden - Guardia de Procesos y Hardening de Red para macOS
Desarrollado por VRTX para proteger la ejecución de navegadores web y supervisar anomalías de red/procesos.
"""

# ==================== METADATOS DEL DESARROLLADOR ====================
__author__ = "VRTX"
__copyright__ = "Copyright 2026 VRTX"
__credits__ = ["VRTX Security Team"]
__license__ = "MIT"
__version__ = "1.0"
__maintainer__ = "VRTX Security"
__status__ = "Production"
__description__ = "Guardia de Procesos y Hardening de Red para Navegadores"

import os
import sys
import time
import signal
import logging
import hashlib
import subprocess
from pathlib import Path
from typing import List, Set, Optional, Dict, Tuple
import psutil

# Cambiamos el nombre del proceso en la memoria del Kernel
try:
	import setproctitle
	setproctitle.setproctitle("NetWarden")
except ImportError:
	pass

# ==================== CONFIGURACIÓN ====================
LOG_FILE = "/var/log/net_warden.log"
CONFIG_FILE = "/etc/net_warden.conf"

# ==================== CONFIGURACIÓN DE NAVEGADORES ====================
# Lista de navegadores soportados con sus rutas y nombres de procesos
BROWSERS_CONFIG = {
	"zen": {
		"paths": [
			"/Applications/Zen Browser.app/Contents/MacOS/Zen Browser",
			"/Applications/Zen.app/Contents/MacOS/Zen"
		],
		"process_names": {"zen", "zen-bin", "zen browser", "zen-browser"},
		"hashes": {}  # Formato: {"version": "sha256_hash"}
	},
	"firefox": {
		"paths": [
			"/Applications/Firefox.app/Contents/MacOS/firefox",
			"/Applications/Firefox Developer Edition.app/Contents/MacOS/firefox",
			"/Applications/Firefox Nightly.app/Contents/MacOS/firefox"
		],
		"process_names": {"firefox", "firefox-bin", "firefox developer edition", "firefox nightly"},
		"hashes": {}
	},
	"chrome": {
		"paths": [
			"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
			"/Applications/Chrome.app/Contents/MacOS/Chrome",
			"/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"
		],
		"process_names": {"google chrome", "chrome", "chrome helper", "chrome canary"},
		"hashes": {}
	},
	"chromium": {
		"paths": [
			"/Applications/Chromium.app/Contents/MacOS/Chromium"
		],
		"process_names": {"chromium", "chromium-browser"},
		"hashes": {}
	},
	"brave": {
		"paths": [
			"/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
		],
		"process_names": {"brave", "brave browser", "brave-browser"},
		"hashes": {}
	},
	"edge": {
		"paths": [
			"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
		],
		"process_names": {"microsoft edge", "edge", "edge browser", "msedge"},
		"hashes": {}
	},
	"opera": {
		"paths": [
			"/Applications/Opera.app/Contents/MacOS/Opera",
			"/Applications/Opera GX.app/Contents/MacOS/Opera"
		],
		"process_names": {"opera", "opera gx", "opera helper"},
		"hashes": {}
	},
	"vivaldi": {
		"paths": [
			"/Applications/Vivaldi.app/Contents/MacOS/Vivaldi"
		],
		"process_names": {"vivaldi", "vivaldi-bin"},
		"hashes": {}
	},
	"arc": {
		"paths": [
			"/Applications/Arc.app/Contents/MacOS/Arc"
		],
		"process_names": {"arc", "arc browser", "arc helper"},
		"hashes": {}
	},
	"safari": {
		"paths": [
			"/Applications/Safari.app/Contents/MacOS/Safari",
			"/System/Applications/Safari.app/Contents/MacOS/Safari"
		],
		"process_names": {"safari", "safari web content", "safari webpage"},
		"hashes": {}
	}
}

# Nombres de procesos de navegadores (para búsqueda rápida)
ALL_BROWSER_PROCESS_NAMES = set()
for browser in BROWSERS_CONFIG.values():
	ALL_BROWSER_PROCESS_NAMES.update(browser["process_names"])

# Nombres de procesos comunes de navegadores (subprocesos)
BROWSER_SUBPROCESS_NAMES = {
	"plugin", "gpu", "renderer", "utility", "sandbox", 
	"extension", "crashpad", "updater", "helper",
	"web content", "webpage", "webworker"
}

# ==================== CONFIGURACIÓN DE SEGURIDAD ====================
# Binarios prohibidos (expandido)
BLACK_BINARY_NAMES = {
	# Shells
	"bash", "zsh", "sh", "dash", "ksh", "csh", "fish", "tcsh",
	# Herramientas de red
	"curl", "wget", "nc", "netcat", "ncat", "socat", "telnet", 
	"ssh", "scp", "rsync", "ftp", "tftp",
	# Lenguajes de scripting
	"python", "python3", "perl", "ruby", "php", "lua", "tcl", "node", "nodejs",
	# Herramientas de depuración/análisis
	"gdb", "lldb", "strace", "dtrace", "nmap", "tshark", "tcpdump",
	"wireshark", "ettercap", "arpspoof", "dsniff",
	# macOS específico
	"osascript", "osacompile", "defaults", "plutil", "PlistBuddy",
	# Compiladores (peligrosos para RCE)
	"gcc", "clang", "make", "cmake", "cc", "c++",
	# Otros
	"java", "groovy", "clojure", "scala", "kotlin", "jruby", "jython",
	"awk", "sed", "grep", "find", "xargs",
	# Herramientas de persistencia
	"launchctl", "cron", "at", "periodic"
}

# Patrones de comandos sospechosos
SUSPICIOUS_CMDLINE_PATTERNS = {
	"curl.*|.*sh",  # curl pipe to shell
	"wget.*|.*sh",  # wget pipe to shell
	"python -c",    # Python one-liners
	"perl -e",      # Perl one-liners
	"ruby -e",      # Ruby one-liners
	"base64 -d",    # Decoding obfuscated payloads
	"openssl enc",  # Encrypted payloads
	"bash -i",      # Interactive shell
	"nc -e",        # Netcat shell
	"ncat -e",      # Ncat shell
	"/dev/tcp/",    # TCP redirection
	"/dev/udp/",    # UDP redirection
	"chmod \+x",    # Making files executable
	"echo.*>/",     # Writing to system directories
	"sudo",         # Privilege escalation
	"su ",          # User switching
	"/bin/",        # System binaries
	"/usr/bin/"     # System binaries
}

# Puertos peligrosos para conexiones salientes
SUSPICIOUS_OUTBOUND_PORTS = {
	21, 22, 23, 25, 53, 80, 110, 143, 443, 587, 993, 995, 
	1080, 1337, 31337, 4444, 5555, 6666, 7777, 8888, 9999,
	1234, 4321, 54321, 12345, 23456, 34567, 45678
}

# ==================== FUNCIONES DE LOGGING ====================
def log_event(message: str, level: str = "INFO", console: bool = True):
	"""Registra eventos con niveles de severidad y opción de salida en consola."""
	if console:
		print(f"[{level}] {message}")
	
	if level == "WARN":
		logging.warning(message)
	elif level == "ERROR":
		logging.error(message)
	elif level == "CRITICAL":
		logging.critical(message)
	else:
		logging.info(message)

# ==================== DETECCIÓN DE NAVEGADORES ====================
def detectar_navegadores_activos() -> Dict[str, Dict]:
	"""
	Detecta todos los navegadores en ejecución.
	Retorna: { "nombre_navegador": {"pid": pid, "process": psutil.Process, "config": config} }
	"""
	browsers_found = {}
	
	for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
		try:
			pid = proc.info['pid']
			pname = (proc.info['name'] or "").lower()
			
			# Buscar coincidencia con nombres de navegadores
			for browser_name, config in BROWSERS_CONFIG.items():
				if pname in config["process_names"]:
					browsers_found[browser_name] = {
						"pid": pid,
						"process": proc,
						"config": config
					}
					log_event(
						f"🌐 Navegador detectado: {browser_name} (PID {pid})",
						level="INFO",
						console=False
					)
					break
					
		except (psutil.NoSuchProcess, psutil.AccessDenied):
			continue
			
	return browsers_found

def es_ancestro_navegador(proc: psutil.Process) -> Tuple[bool, Optional[str]]:
	"""
	Inspecciona el árbol genealógico del proceso para verificar si proviene de algún navegador.
	Retorna: (es_navegador, nombre_navegador)
	"""
	try:
		parent = proc.parent()
		visited_pids = set()
		
		while parent is not None:
			if parent.pid in visited_pids:
				break
			visited_pids.add(parent.pid)
			
			pname = (parent.name() or "").lower()
			
			# Verificar si el padre es un navegador
			for browser_name, config in BROWSERS_CONFIG.items():
				if pname in config["process_names"]:
					return True, browser_name
			
			# Verificar subprocesos comunes de navegadores
			if any(subprocess in pname for subprocess in BROWSER_SUBPROCESS_NAMES):
				# Intentar subir más en el árbol
				grandparent = parent.parent()
				if grandparent:
					gpname = (grandparent.name() or "").lower()
					for browser_name, config in BROWSERS_CONFIG.items():
						if gpname in config["process_names"]:
							return True, browser_name
			
			parent = parent.parent()
			
	except (psutil.NoSuchProcess, psutil.AccessDenied):
		pass
	return False, None

def obtener_navegador_activo(proc: psutil.Process) -> Optional[str]:
	"""Obtiene el nombre del navegador al que pertenece un proceso."""
	# Verificar si el proceso mismo es un navegador
	pname = (proc.name() or "").lower()
	for browser_name, config in BROWSERS_CONFIG.items():
		if pname in config["process_names"]:
			return browser_name
	
	# Verificar ancestros
	es_browser, browser_name = es_ancestro_navegador(proc)
	if es_browser:
		return browser_name
	
	return None

# ==================== VERIFICACIÓN DE INTEGRIDAD ====================
def verificar_integridad_navegador(browser_name: str, config: Dict) -> Tuple[bool, str]:
	"""
	Verifica la integridad del binario del navegador comparando su hash SHA-256.
	Retorna: (es_válido, mensaje)
	"""
	# Intentar todas las rutas posibles para el navegador
	for binary_path in config.get("paths", []):
		try:
			if not os.path.exists(binary_path):
				continue
			
			# Calcular SHA-256 del binario
			sha256_hash = hashlib.sha256()
			with open(binary_path, "rb") as f:
				for byte_block in iter(lambda: f.read(4096), b""):
					sha256_hash.update(byte_block)
			current_hash = sha256_hash.hexdigest()
			
			# Verificar contra hashes conocidos
			known_hashes = config.get("hashes", {})
			if known_hashes:
				for version, known_hash in known_hashes.items():
					if current_hash == known_hash:
						return True, f"Integridad verificada ({browser_name}, versión {version})"
			
			return True, f"Integridad verificada ({browser_name}) - Hash: {current_hash[:16]}..."
			
		except Exception as e:
			continue
	
	return False, f"No se encontró binario para {browser_name}"

# ==================== DETECCIÓN DE PROCESOS ====================
def es_comando_sospechoso(cmdline: List[str]) -> bool:
	"""Detecta comandos con patrones sospechosos mediante regex."""
	if not cmdline:
		return False
	
	cmd_str = " ".join(cmdline).lower()
	import re
	for pattern in SUSPICIOUS_CMDLINE_PATTERNS:
		try:
			if re.search(pattern, cmd_str, re.IGNORECASE):
				return True
		except re.error:
			continue
	return False

def analizar_metadatos_proceso(proc: psutil.Process) -> Dict:
	"""Recopila metadatos adicionales del proceso para análisis."""
	try:
		return {
			"pid": proc.pid,
			"name": proc.name(),
			"cmdline": " ".join(proc.cmdline() or []),
			"username": proc.username(),
			"create_time": proc.create_time(),
			"memory_percent": proc.memory_percent(),
			"cpu_percent": proc.cpu_percent(interval=0.1),
			"num_threads": proc.num_threads(),
			"open_files": [f.path for f in proc.open_files()[:5]],
			"connections": len(proc.connections())
		}
	except (psutil.NoSuchProcess, psutil.AccessDenied):
		return {}

# ==================== AUDITORÍA DE PROCESOS ====================
def auditar_procesos_sospechosos():
	"""Escanea la lista de procesos para detectar y aniquilar subprocesos no autorizados."""
	# Detectar navegadores activos
	browsers = detectar_navegadores_activos()
	
	if not browsers:
		return  # No hay navegadores en ejecución
	
	for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
		try:
			pid = proc.info['pid']
			pname = (proc.info['name'] or "").lower()
			ppid = proc.info['ppid']

			# Omitir NetWarden y procesos del sistema
			if pid == os.getpid() or pid <= 10:
				continue

			# Verificar si el proceso está relacionado con algún navegador
			browser_name = obtener_navegador_activo(proc)
			
			if not browser_name:
				continue  # No está relacionado con ningún navegador

			# === NIVEL 1: Detección por nombre de binario ===
			if pname in BLACK_BINARY_NAMES:
				cmdline = " ".join(proc.info.get('cmdline') or [])
				log_event(
					f"🚨 ¡AMENAZA DETECTADA! Subproceso no autorizado en {browser_name}: "
					f"PID {pid} ({pname}) -> Cmd: '{cmdline[:200]}'",
					level="WARN"
				)
				_terminar_proceso(proc, pid, pname, f"Binario prohibido en {browser_name}")
				continue

			# === NIVEL 2: Detección por patrón de comando ===
			cmdline = proc.info.get('cmdline') or []
			if es_comando_sospechoso(cmdline):
				log_event(
					f"⚠️ COMANDO SOSPECHOSO en {browser_name}: PID {pid} ({pname}) -> "
					f"Cmd: '{' '.join(cmdline)[:200]}'",
					level="WARN"
				)
				_terminar_proceso(proc, pid, pname, f"Patrón sospechoso en {browser_name}")
				continue

			# === NIVEL 3: Detección de comportamiento anómalo ===
			metadata = analizar_metadatos_proceso(proc)
			if metadata:
				# Demasiados hilos (posible malware)
				if metadata.get('num_threads', 0) > 100:
					log_event(
						f"⚠️ COMPORTAMIENTO ANÓMALO en {browser_name}: PID {pid} ({pname}) "
						f"tiene {metadata['num_threads']} hilos",
						level="WARN"
					)
					_terminar_proceso(proc, pid, pname, f"Exceso de hilos en {browser_name}")
					continue
				
				# Uso excesivo de CPU (posible minería)
				if metadata.get('cpu_percent', 0) > 80:
					log_event(
						f"⚠️ ALTO CONSUMO DE CPU en {browser_name}: PID {pid} ({pname}) "
						f"al {metadata['cpu_percent']}%",
						level="INFO"
					)

		except (psutil.NoSuchProcess, psutil.AccessDenied):
			continue
		except Exception as e:
			log_event(f"Error al inspeccionar proceso: {str(e)}", level="ERROR", console=False)

def _terminar_proceso(proc: psutil.Process, pid: int, pname: str, razon: str):
	"""Termina un proceso de manera segura con logging."""
	try:
		# Intentar SIGTERM primero (más limpio)
		proc.terminate()
		time.sleep(0.3)
		
		if proc.is_running():
			proc.kill()
			log_event(
				f"🛡️ Proceso PID {pid} ({pname}) forzado a terminar (SIGKILL) - {razon}",
				level="WARN"
			)
		else:
			log_event(
				f"✅ Proceso PID {pid} ({pname}) terminado (SIGTERM) - {razon}",
				level="INFO"
			)
	except (psutil.NoSuchProcess, psutil.AccessDenied):
		pass

# ==================== AUDITORÍA DE RED ====================
def auditar_conexiones_sospechosas():
	"""Supervisa puertos y sockets de red activos buscando shells reversas o enlaces anómalos."""
	try:
		connections = psutil.net_connections(kind='inet')
		suspicious_connections = []
		
		for conn in connections:
			if conn.status != psutil.CONN_ESTABLISHED or not conn.pid:
				continue
				
			try:
				p = psutil.Process(conn.pid)
				pname = (p.name() or "").lower()
				
				# Verificar si el proceso pertenece a algún navegador
				browser_name = obtener_navegador_activo(p)
				
				if conn.raddr:
					raddr_str = f"{conn.raddr.ip}:{conn.raddr.port}"
					
					# === Detección de conexiones desde shells ===
					if pname in {"bash", "zsh", "sh", "nc", "netcat", "ncat", "socat"}:
						if browser_name:
							log_event(
								f"🔴 ALERTA CRÍTICA: Shell '{pname}' (PID {conn.pid}) "
								f"desde {browser_name} con conexión a {raddr_str}",
								level="CRITICAL"
							)
							_terminar_proceso(p, conn.pid, pname, f"Shell desde {browser_name}")
						else:
							log_event(
								f"⚠️ ALERTA DE RED: Proceso de consola '{pname}' (PID {conn.pid}) "
								f"con conexión activa a {raddr_str}",
								level="WARN"
							)
						suspicious_connections.append((conn.pid, pname, raddr_str))
					
					# === Puertos peligrosos desde navegadores ===
					elif conn.raddr.port in SUSPICIOUS_OUTBOUND_PORTS and browser_name:
						log_event(
							f"⚠️ PUERTO SOSPECHOSO desde {browser_name}: Proceso '{pname}' "
							f"(PID {conn.pid}) conectando a {raddr_str}",
							level="WARN"
						)
						# Si el proceso es sospechoso, terminarlo
						if pname in BLACK_BINARY_NAMES:
							_terminar_proceso(p, conn.pid, pname, f"Puerto sospechoso en {browser_name}")
						suspicious_connections.append((conn.pid, pname, raddr_str))
					
					# === Conexiones a IPs externas sospechosas ===
					elif browser_name and conn.raddr.ip:
						ip = conn.raddr.ip
						# Detectar IPs sospechosas (Tor, VPNs, etc.)
						suspicious_ips = {"127.0.0.1", "0.0.0.0", "::1"}
						if ip not in suspicious_ips:
							# IPs privadas
							is_private = (ip.startswith('10.') or 
										ip.startswith('172.16.') or 
										ip.startswith('192.168.'))
							if not is_private:
								# Solo log para conexiones externas
								log_event(
									f"ℹ️ CONEXIÓN EXTERNA: {browser_name} conectando a {raddr_str}",
									level="INFO",
									console=False
								)
				
			except (psutil.NoSuchProcess, psutil.AccessDenied):
				continue
			except Exception as e:
				log_event(f"Error al analizar conexión: {str(e)}", level="ERROR", console=False)
				
		return suspicious_connections
		
	except psutil.AccessDenied:
		log_event("⚠️ Permisos insuficientes para monitoreo de red. Ejecutar como root.", level="WARN")
		return []
	except Exception as e:
		log_event(f"Error en auditoría de red: {str(e)}", level="ERROR", console=False)
		return []

# ==================== DETECCIÓN DE ARCHIVOS MALICIOSOS ====================
def verificar_archivos_temporales():
	"""Verifica archivos temporales y descargas sospechosas en directorios comunes."""
	temp_dirs = [
		"/tmp",
		"/var/tmp",
		f"/Users/{os.getenv('USER')}/Downloads",
		f"/Users/{os.getenv('USER')}/Desktop",
		f"/Users/{os.getenv('USER')}/.cache"
	]
	
	suspicious_extensions = {'.sh', '.py', '.rb', '.pl', '.php', '.js', '.jar', '.exe', '.com', '.scr', '.vbs', '.ps1'}
	
	for temp_dir in temp_dirs:
		try:
			if not os.path.exists(temp_dir):
				continue
				
			for file in Path(temp_dir).iterdir():
				if file.is_file() and file.suffix.lower() in suspicious_extensions:
					import time
					file_age = time.time() - file.stat().st_ctime
					if file_age < 300:  # 5 minutos
						# Verificar si el archivo está abierto por algún navegador
						is_browser_download = False
						for proc in psutil.process_iter(['pid', 'name']):
							try:
								if any(browser in (proc.name() or "").lower() for browser in ["chrome", "firefox", "safari", "zen", "brave", "edge", "opera"]):
									for open_file in proc.open_files():
										if str(file) == open_file.path:
											is_browser_download = True
											break
							except:
								continue
						
						if is_browser_download:
							log_event(
								f"📁 DESCARGA RECIENTE DEL NAVEGADOR: {file} (creado hace {int(file_age)}s)",
								level="INFO"
							)
						elif file_age < 60:  # Muy reciente y no relacionado con navegador
							log_event(
								f"⚠️ ARCHIVO SOSPECHOSO MUY RECIENTE: {file}",
								level="WARN"
							)
		except (PermissionError, OSError):
			continue

# ==================== MONITOREO DE PROCESOS DE NAVEGADOR ====================
def monitorear_navegadores():
	"""Monitorea el estado de los navegadores y reporta cambios."""
	active_browsers = detectar_navegadores_activos()
	
	for browser_name, browser_info in active_browsers.items():
		proc = browser_info["process"]
		config = browser_info["config"]
		
		try:
			# Verificar si el proceso sigue vivo
			if not proc.is_running():
				log_event(f"❌ {browser_name} se ha cerrado", level="INFO", console=False)
				continue
			
			# Verificar integridad periódicamente
			if int(time.time()) % 60 == 0:  # Cada minuto
				is_valid, msg = verificar_integridad_navegador(browser_name, config)
				if not is_valid:
					log_event(f"⚠️ {msg}", level="WARN")
					
		except (psutil.NoSuchProcess, psutil.AccessDenied):
			continue

# ==================== FUNCIÓN PRINCIPAL ====================
def main():
	# Verificar permisos de root
	is_root = os.geteuid() == 0
	if not is_root:
		log_event("⚠️ ADVERTENCIA: NetWarden no se ejecutó como root. Algunas inspecciones estarán limitadas.", level="WARN")
	
	log_event("🛡️ NetWarden iniciado exitosamente. Monitoreando todos los navegadores...")
	
	# Mostrar navegadores soportados
	log_event(f"📋 Navegadores soportados: {', '.join(BROWSERS_CONFIG.keys())}", level="INFO")
	
	# Bucle principal de monitoreo
	iteration = 0
	while True:
		try:
			iteration += 1
			
			# Monitorear navegadores activos
			monitorear_navegadores()
			
			# Ejecutar auditorías de procesos y red
			auditar_procesos_sospechosos()
			auditar_conexiones_sospechosas()
			
			# Verificar archivos temporales cada 10 iteraciones (~5 segundos)
			if iteration % 10 == 0:
				verificar_archivos_temporales()
			
			# Ajustar frecuencia dinámicamente según carga del sistema
			cpu_percent = psutil.cpu_percent(interval=0.1)
			if cpu_percent > 80:
				time.sleep(1.0)
			else:
				time.sleep(0.5)
				
		except KeyboardInterrupt:
			log_event("🛑 NetWarden detenido por el usuario.", level="INFO")
			sys.exit(0)
		except Exception as e:
			log_event(f"Error en bucle principal: {str(e)}", level="ERROR", console=False)
			time.sleep(1.0)

if __name__ == "__main__":
	main()