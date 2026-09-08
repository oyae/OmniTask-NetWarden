"""
OmniTask - Optimizador de CPU/RAM para macOS
Desarrollado por VRTX
"""

# ==================== METADATOS DEL DESARROLLADOR ====================
__author__ = "VRTX"
__copyright__ = "Copyright 2026 VRTX"
__credits__ = ["VRTX Security Team"]
__license__ = "MIT"
__version__ = "1.0"
__maintainer__ = "VRTX Security"
__status__ = "Production"
__description__ = "Optimizador de CPU/RAM"

import os
import signal
import subprocess
import time
import json
import sys
import psutil
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

# Solo importar APIs de macOS si estamos en esa plataforma
if sys.platform == 'darwin':
	try:
		from ApplicationServices import (
			AXIsProcessTrusted,
			AXIsProcessTrustedWithOptions,
			kAXTrustedCheckOptionPrompt
		)
		HAS_ACCESSIBILITY = True
	except ImportError:
		HAS_ACCESSIBILITY = False

	try:
		from AppKit import NSWorkspace, NSApplicationActivationPolicyRegular
		HAS_APPKIT = True
	except ImportError:
		HAS_APPKIT = False
else:
	HAS_ACCESSIBILITY = False
	HAS_APPKIT = False


class HiloMonitor(QThread):
	"""
	Hilo de monitoreo del sistema. Recoge métricas de CPU/RAM, gestiona
	listas blanca/negra y activa el 'Modo Estrés' cuando se superan los umbrales.
	"""
	datos_actualizados = pyqtSignal(float, float, float, str, str, list)
	alerta_seguridad = pyqtSignal(str)
	consola_log = pyqtSignal(str, str)
	solicitar_accesibilidad = pyqtSignal()   # Para pedir permisos desde la GUI

	def __init__(self, parent=None):
		super().__init__(parent)
		self.LIMITE_CPU_GLOBAL = 70.0
		self.LIMITE_RAM_PORCENTAJE = 80.0
		self.UMBRAL_DESACTIVACION_CPU = 20.0
		self.INTERVALO_MS = 1000
		self.funcionando = True

		self.en_modo_estres = False
		self.modo_vram_nativo = False
		self.vram_limit_mb = 2048  # Reducido de 4096 a 2048

		# Listas con nombres exactos (en minúsculas) para coincidencia exacta
		self.whitelist = {
			"finder", "terminal", "python", "python3", "macs fan control",
			"garageband", "obs", "coreaudiod", "windowserver", "sublime_text",
			"systemmonitor", "loginwindow", "powerd", "corebrightnessd",
			"displaypolicyd", "airplaydaemon", "launchd", "mediaserverd", "kernel_task"
		}

		self.blacklist = set()
		self.procesos_congelados = set()
		self.procesos_segundo_plano = set()
		self.apps_ocultadas = set()

		self.ultimo_purge = 0
		self.ultimo_heartbeat = 0
		self.max_peak_sum = 0.0
		self.peak_file_path = self._get_data_dir() / "peak_slice.json"

		# Cache ligero de procesos
		self.process_cache = {}
		psutil.cpu_percent(interval=None)
		
		# Control de procesos memory_pressure
		self._memory_pressure_pids = set()

	def _get_data_dir(self):
		home = Path.home()
		data_dir = home / "Library" / "Application Support" / "OmniTask"
		if not data_dir.exists():
			data_dir.mkdir(parents=True, exist_ok=True)
			try:
				data_dir.chmod(0o755)
			except Exception:
				pass
		return data_dir

	def verificar_accesibilidad(self):
		"""Verifica y solicita permisos de accesibilidad en macOS."""
		if not HAS_ACCESSIBILITY:
			self._log("WARN", "API de Accesibilidad no disponible (falta ApplicationServices).")
			return False
		if sys.platform != 'darwin':
			self._log("WARN", "Accesibilidad solo aplica en macOS.")
			return False
		try:
			if AXIsProcessTrusted():
				self._log("SYS", "Permisos de accesibilidad ya concedidos.")
				return True

			options = {kAXTrustedCheckOptionPrompt: True}
			is_trusted = AXIsProcessTrustedWithOptions(options)
			if is_trusted:
				self._log("SYS", "Permisos de accesibilidad concedidos exitosamente.")
				return True
			else:
				self._log("WARN", "Permisos de accesibilidad denegados o pendientes.")
				self.solicitar_accesibilidad.emit()
				return False
		except Exception as e:
			self._log("ERR", f"Error al verificar accesibilidad: {str(e)}")
			return False

	def _log(self, tipo: str, mensaje: str):
		self.consola_log.emit(tipo, mensaje)

	def _limpiar_memory_pressure(self):
		"""Limpia procesos memory_pressure zombies que consumen memoria excesiva."""
		try:
			# Buscar procesos memory_pressure
			result = subprocess.run(['pgrep', '-f', 'memory_pressure'], capture_output=True, text=True)
			pids = result.stdout.strip().split()
			
			for pid_str in pids:
				if not pid_str:
					continue
				try:
					pid = int(pid_str)
					# No matar el proceso actual
					if pid == os.getpid():
						continue
					# Verificar si el proceso sigue existiendo
					if psutil.pid_exists(pid):
						proc = psutil.Process(pid)
						# Si el proceso ha estado ejecutándose por más de 60 segundos y tiene > 1GB de memoria
						mem_info = proc.memory_info()
						if mem_info.rss > 1024 * 1024 * 1024:  # > 1GB
							elapsed = time.time() - proc.create_time()
							if elapsed > 60:  # > 60 segundos
								self._log("WARN", f"Matando memory_pressure (PID: {pid}) con {mem_info.rss/(1024**2):.0f}MB después de {elapsed:.0f}s")
								proc.kill()
				except (psutil.NoSuchProcess, psutil.AccessDenied):
					pass
		except Exception as e:
			self._log("ERR", f"Error limpiando memory_pressure: {str(e)}")

	def _liberar_memoria_inactiva(self):
		"""Ejecuta comandos nativos para liberar memoria inactiva (macOS)."""
		if sys.platform != 'darwin':
			return
		
		# Primero limpiar procesos memory_pressure problemáticos
		self._limpiar_memory_pressure()
		
		# Contar instancias de memory_pressure
		try:
			result = subprocess.run(['pgrep', '-c', '-f', 'memory_pressure'], capture_output=True, text=True)
			count = int(result.stdout.strip() or 0)
			
			if count > 2:  # Si ya hay más de 2 instancias, no crear más
				self._log("WARN", f"Demasiadas instancias de memory_pressure ({count}). Saltando ejecución.")
				return
		except Exception:
			pass
			
		ahora = time.time()
		if ahora - self.ultimo_purge > 60:  # Aumentar intervalo a 60 segundos
			self.ultimo_purge = ahora
			try:
				# Ejecutar purge con timeout
				subprocess.Popen(["purge"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
				self._log("SYS", "Comando 'purge' ejecutado.")
			except Exception as e:
				self._log("ERR", f"Error al ejecutar purge: {str(e)}")

	def run(self):
		self.verificar_accesibilidad()

		self._log("SYS", "Demonio de monitoreo e inspección iniciado correctamente.")
		while self.funcionando:
			self.ultimo_heartbeat = time.time()

			cpu_uso = psutil.cpu_percent(interval=None)
			memoria = psutil.virtual_memory()
			ram_uso = memoria.percent
			ram_libre_mb = memoria.available / (1024 ** 2)
			ram_usada_mb = (memoria.total - memoria.available) / (1024 ** 2)

			app_activa = self._obtener_app_en_foco()
			alerta = ""
			lista_slices = []

			try:
				current_pids = set(psutil.pids())
			except Exception:
				current_pids = set()

			dead_pids = set(self.process_cache.keys()) - current_pids
			for pid in dead_pids:
				del self.process_cache[pid]

			for pid in current_pids:
				try:
					if pid <= 0:
						continue
					if pid not in self.process_cache:
						self.process_cache[pid] = psutil.Process(pid)
					proc = self.process_cache[pid]
					pname = (proc.name() or "").strip()
					if not pname:
						continue
					pram = proc.memory_percent() or 0.0
					pcpu = proc.cpu_percent(interval=None) or 0.0

					if pid in self.procesos_congelados:
						estado = "Frozen"
					elif pid in self.apps_ocultadas:
						estado = "Hidden"
					else:
						estado = "Full"

					lista_slices.append({
						'name': pname,
						'cpu': pcpu,
						'ram': pram,
						'status': estado,
						'pid': pid
					})
				except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
					if pid in self.process_cache:
						del self.process_cache[pid]
					continue

			lista_slices.sort(key=lambda x: x['ram'], reverse=True)

			current_sum = cpu_uso + ram_uso
			if current_sum > self.max_peak_sum:
				self.max_peak_sum = current_sum
				self._guardar_snapshot_pico(cpu_uso, ram_uso, lista_slices)

			# Si la pantalla está bloqueada o en reposo, desactivamos estrés
			app_lower = app_activa.lower()
			if app_lower in ("loginwindow", "screen saver", "lockscreen"):
				if self.en_modo_estres:
					self.en_modo_estres = False
					self._log("SYS", "Sistema en reposo/bloqueo. Desactivando Modo Estrés.")
					self._restablecer_todos_los_procesos()
				self.datos_actualizados.emit(
					cpu_uso, ram_uso, ram_libre_mb,
					"Sistema bloqueado / Reposo",
					"💤 Sistema en Reposo", lista_slices
				)
				QThread.msleep(self.INTERVALO_MS)
				continue

			supera_vram = (ram_usada_mb > self.vram_limit_mb)
			supera_limite = (cpu_uso > self.LIMITE_CPU_GLOBAL) or (ram_uso > self.LIMITE_RAM_PORCENTAJE)

			if supera_vram or (self.modo_vram_nativo and supera_limite):
				self._liberar_memoria_inactiva()

			if not self.en_modo_estres and supera_limite:
				self.en_modo_estres = True
				self._log("WARN", f"¡EXCESO DE CONSUMO! CPU: {cpu_uso:.1f}% | RAM: {ram_uso:.1f}%. Entrando en Modo Estrés.")
			elif self.en_modo_estres and cpu_uso <= self.UMBRAL_DESACTIVACION_CPU and ram_uso < self.LIMITE_RAM_PORCENTAJE:
				self.en_modo_estres = False
				self._log("INFO", f"Métricas normalizadas (CPU: {cpu_uso:.1f}%, RAM: {ram_uso:.1f}%). Saliendo de Modo Estrés.")
				self._restablecer_todos_los_procesos()

			if self.en_modo_estres:
				alerta = f"⚠️ Modo Estrés Activo: CPU {cpu_uso:.1f}% | RAM {ram_uso:.1f}%"
				if supera_vram:
					alerta += f" | Límite vRAM Excedido ({int(ram_usada_mb)}MB/{self.vram_limit_mb}MB)"
				self._clasificar_y_gestionar_apps(app_activa)
			else:
				if self.procesos_congelados or self.procesos_segundo_plano or self.apps_ocultadas:
					self._restablecer_todos_los_procesos()

			self.datos_actualizados.emit(cpu_uso, ram_uso, ram_libre_mb, app_activa, alerta, lista_slices)
			QThread.msleep(self.INTERVALO_MS)

	def _guardar_snapshot_pico(self, cpu: float, ram: float, lista_slices: list):
		data = {
			"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
			"peak_cpu": cpu,
			"peak_ram": ram,
			"slices": lista_slices
		}
		try:
			self.peak_file_path.parent.mkdir(parents=True, exist_ok=True)
			with open(self.peak_file_path, "w", encoding="utf-8") as f:
				json.dump(data, f, indent=4)
			self._log("SYS", f"Nuevo pico registrado ({cpu:.1f}% CPU, {ram:.1f}% RAM). Reporte guardado.")
		except Exception as e:
			self._log("ERR", f"Error al guardar snapshot: {str(e)}")

	def abortar_y_limpiar_lista_negra(self):
		self._log("ERR", "¡INTERVENCIÓN DEL WATCHDOG! Se detectó bloqueo prolongado.")
		self._restablecer_todos_los_procesos()
		apps_removidas = list(self.blacklist)
		self.blacklist.clear()
		if apps_removidas:
			nombres = ", ".join(apps_removidas)
			self._log("ERR", f"Watchdog eliminó de Lista Negra: [{nombres}].")
			self.alerta_seguridad.emit(
				f"🚨 ¡Intervención de Seguridad!\n\n"
				f"Se detectó un congelamiento del sistema.\n"
				f"Aplicaciones removidas de la lista negra: [{nombres}]"
			)

	def _obtener_app_en_foco(self) -> str:
		if sys.platform != 'darwin' or not HAS_APPKIT:
			return "Desconocido"
		try:
			app = NSWorkspace.sharedWorkspace().frontmostApplication()
			if app and app.localizedName():
				return app.localizedName()
		except Exception:
			pass
		return "Desconocido"

	def _enforzar_limite_vram(self):
		self._liberar_memoria_inactiva()

	def _ocultar_apps_de_interfaz(self, app_activa: str):
		if sys.platform != 'darwin' or not HAS_APPKIT:
			return
		
		# Verificar que tenemos permisos de accesibilidad antes de intentar ocultar
		if not AXIsProcessTrusted():
			self._log("WARN", "No hay permisos de accesibilidad para ocultar apps.")
			return
			
		app_activa_lower = app_activa.lower().strip()
		try:
			apps_corriendo = NSWorkspace.sharedWorkspace().runningApplications()
			for app in apps_corriendo:
				if app.activationPolicy() == NSApplicationActivationPolicyRegular:
					nombre_app = (app.localizedName() or "").lower()
					pid = app.processIdentifier()
					if pid == os.getpid():
						continue
					es_whitelist = nombre_app in self.whitelist
					es_activa = (app_activa_lower == nombre_app)
					if es_activa or es_whitelist:
						if app.isHidden():
							app.unhide()
							self._log("INFO", f"Ventana restaurada: '{app.localizedName()}'")
						self.apps_ocultadas.discard(pid)
					else:
						if not app.isHidden():
							res = app.hide()
							if res:
								self.apps_ocultadas.add(pid)
								self._log("INFO", f"Ventana ocultada: '{app.localizedName()}'")
							else:
								self._log("WARN", f"No se pudo ocultar '{app.localizedName()}'. Verifique permisos de accesibilidad.")
		except Exception as e:
			self._log("ERR", f"Error al ocultar aplicaciones: {str(e)}")

	def _clasificar_y_gestionar_apps(self, app_activa: str):
		app_activa_lower = app_activa.lower().strip()
		mi_pid = os.getpid()

		self._ocultar_apps_de_interfaz(app_activa)

		for proc in psutil.process_iter(['pid', 'name', 'nice']):
			try:
				pid = proc.info['pid']
				if pid <= 0 or pid == mi_pid:
					continue

				nombre_proc = (proc.info.get('name') or "").lower()
				if not nombre_proc:
					continue

				criticos = {"kernel_task", "windowserver", "loginwindow",
							"powerd", "coreaudiod", "mediaserverd", "airplayagent"}
				if nombre_proc in criticos:
					continue

				if nombre_proc in self.blacklist and nombre_proc != app_activa_lower:
					if pid not in self.procesos_congelados:
						try:
							proc.send_signal(signal.SIGSTOP)
							self.procesos_congelados.add(pid)
							self._log("WARN", f"PROCESO DETENIDO (SIGSTOP): '{proc.info.get('name', '')}' (PID: {pid}).")
						except Exception:
							pass
					continue

				nice_val = proc.info.get('nice')
				if nombre_proc in self.whitelist or nombre_proc == app_activa_lower:
					if pid in self.procesos_congelados:
						try:
							proc.send_signal(signal.SIGCONT)
							self._log("INFO", f"PROCESO REANUDADO (SIGCONT): '{proc.info.get('name', '')}' (PID: {pid}).")
						except Exception:
							pass
						self.procesos_congelados.discard(pid)
					if pid in self.procesos_segundo_plano:
						try:
							if nice_val is not None:
								proc.nice(0)
						except Exception:
							pass
						self.procesos_segundo_plano.discard(pid)
					continue

				try:
					if nice_val is not None and nice_val < 19:
						proc.nice(19)
					self.procesos_segundo_plano.add(pid)
				except Exception:
					pass

			except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
				continue

	def _restablecer_todos_los_procesos(self):
		if self.procesos_congelados or self.apps_ocultadas or self.procesos_segundo_plano:
			self._log("SYS", "Restaurando estado normal para todos los procesos modificados.")

		for pid in list(self.procesos_congelados):
			if pid > 0:
				try:
					if psutil.pid_exists(pid):
						psutil.Process(pid).send_signal(signal.SIGCONT)
				except Exception:
					pass
		self.procesos_congelados.clear()

		if sys.platform == 'darwin' and HAS_APPKIT:
			try:
				apps_corriendo = NSWorkspace.sharedWorkspace().runningApplications()
				for app in apps_corriendo:
					if app.activationPolicy() == NSApplicationActivationPolicyRegular and app.isHidden():
						app.unhide()
			except Exception:
				pass
		self.apps_ocultadas.clear()

		for pid in list(self.procesos_segundo_plano):
			if pid > 0:
				try:
					if psutil.pid_exists(pid):
						p = psutil.Process(pid)
						if p.nice() != 0:
							p.nice(0)
				except Exception:
					pass
		self.procesos_segundo_plano.clear()

	def stop(self):
		self.funcionando = False
		self._restablecer_todos_los_procesos()
		self.wait()
