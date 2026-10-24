import os
import signal
import subprocess
import time
import json
import sys
import psutil
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

if sys.platform == 'darwin':
    try:
        from ApplicationServices import AXIsProcessTrusted, AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
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
    datos_actualizados = pyqtSignal(float, float, float, str, str, list)
    alerta_seguridad = pyqtSignal(str)
    consola_log = pyqtSignal(str, str)
    solicitar_accesibilidad = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.LIMITE_CPU_GLOBAL = 70.0
        self.LIMITE_RAM_PORCENTAJE = 80.0
        self.UMBRAL_DESACTIVACION_CPU = 20.0
        self.INTERVALO_MS = 1000
        self.funcionando = True
        self.en_modo_estres = False
        self.modo_vram_nativo = False
        self.vram_limit_mb = 2048

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

        self.process_cache = {}
        psutil.cpu_percent(interval=None)
        self._memory_pressure_pids = set()

    def _get_data_dir(self):
        data_dir = Path.home() / "OmniTask"
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def verificar_accesibilidad(self):
        if not HAS_ACCESSIBILITY or sys.platform != 'darwin': return False
        try:
            if AXIsProcessTrusted(): 
                self._log("SYS", "Permisos de accesibilidad verificados.")
                return True
            options = {kAXTrustedCheckOptionPrompt: True}
            if AXIsProcessTrustedWithOptions(options): 
                self._log("SYS", "Permisos de accesibilidad concedidos exitosamente.")
                return True
            self.solicitar_accesibilidad.emit()
            self._log("WARN", "Permisos de accesibilidad denegados o pendientes.")
            return False
        except Exception as e:
            self._log("ERR", f"Error al verificar accesibilidad: {str(e)}")
            return False

    def _log(self, tipo: str, mensaje: str):
        self.consola_log.emit(tipo, mensaje)

    def _limpiar_memory_pressure(self):
        try:
            result = subprocess.run(['pgrep', '-f', 'memory_pressure'], capture_output=True, text=True)
            for pid_str in result.stdout.strip().split():
                if pid_str:
                    pid = int(pid_str)
                    if pid == os.getpid(): continue
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        if proc.memory_info().rss > 1024**3 and (time.time() - proc.create_time()) > 60:
                            proc.kill()
                            self._log("SYS", f"Proceso memory_pressure (PID {pid}) finalizado por uso excesivo.")
        except Exception: pass

    def _liberar_memoria_inactiva(self):
        if sys.platform != 'darwin': return
        self._limpiar_memory_pressure()
        try:
            result = subprocess.run(['pgrep', '-c', '-f', 'memory_pressure'], capture_output=True, text=True)
            if int(result.stdout.strip() or 0) > 2: return
        except Exception: pass
        
        ahora = time.time()
        if ahora - self.ultimo_purge > 60:
            self.ultimo_purge = ahora
            try: 
                subprocess.Popen(["purge"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._log("SYS", "Purga de memoria inactiva ejecutada.")
            except Exception as e: 
                self._log("ERR", f"Error al ejecutar purge: {str(e)}")

    def run(self):
        self.verificar_accesibilidad()
        self._log("INFO", "Monitor del sistema iniciado correctamente.")
        while self.funcionando:
            self.ultimo_heartbeat = time.time()
            cpu_uso = psutil.cpu_percent(interval=None)
            memoria = psutil.virtual_memory()
            ram_uso = memoria.percent
            ram_libre_mb = memoria.available / (1024 ** 2)
            ram_usada_mb = (memoria.total - memoria.available) / (1024 ** 2)
            app_activa = self._obtener_app_en_foco()
            
            lista_slices = []
            try: current_pids = set(psutil.pids())
            except Exception: current_pids = set()

            dead_pids = set(self.process_cache.keys()) - current_pids
            for pid in dead_pids: del self.process_cache[pid]

            for pid in current_pids:
                try:
                    if pid <= 0: continue
                    if pid not in self.process_cache: self.process_cache[pid] = psutil.Process(pid)
                    proc = self.process_cache[pid]
                    pname = (proc.name() or "").strip()
                    if not pname: continue
                    
                    estado = "Frozen" if pid in self.procesos_congelados else "Hidden" if pid in self.apps_ocultadas else "Full"
                    lista_slices.append({'name': pname, 'cpu': proc.cpu_percent(interval=None) or 0.0, 'ram': proc.memory_percent() or 0.0, 'status': estado, 'pid': pid})
                except Exception:
                    if pid in self.process_cache: del self.process_cache[pid]

            lista_slices.sort(key=lambda x: x['ram'], reverse=True)
            current_sum = cpu_uso + ram_uso
            if current_sum > self.max_peak_sum:
                self.max_peak_sum = current_sum
                self._guardar_snapshot_pico(cpu_uso, ram_uso, lista_slices)

            if app_activa.lower() in ("loginwindow", "screen saver", "lockscreen"):
                if self.en_modo_estres:
                    self.en_modo_estres = False
                    self._restablecer_todos_los_procesos()
                    self._log("INFO", "Sistema bloqueado. Modo estrés desactivado temporalmente.")
                self.datos_actualizados.emit(cpu_uso, ram_uso, ram_libre_mb, "Sistema bloqueado", "💤 Reposo", lista_slices)
                QThread.msleep(self.INTERVALO_MS)
                continue

            supera_vram = (ram_usada_mb > self.vram_limit_mb)
            supera_limite = (cpu_uso > self.LIMITE_CPU_GLOBAL) or (ram_uso > self.LIMITE_RAM_PORCENTAJE)

            if supera_vram or (self.modo_vram_nativo and supera_limite): 
                self._liberar_memoria_inactiva()

            if not self.en_modo_estres and supera_limite:
                self.en_modo_estres = True
                self._log("WARN", f"Modo estrés ACTIVADO: CPU {cpu_uso:.1f}% | RAM {ram_uso:.1f}%")
            elif self.en_modo_estres and cpu_uso <= self.UMBRAL_DESACTIVACION_CPU and ram_uso < self.LIMITE_RAM_PORCENTAJE:
                self.en_modo_estres = False
                self._log("INFO", "Modo estrés DESACTIVADO. Niveles estables.")
                self._restablecer_todos_los_procesos()

            alerta = f"⚠️ Estrés: CPU {cpu_uso:.1f}% | RAM {ram_uso:.1f}%" if self.en_modo_estres else ""
            if self.en_modo_estres:
                if supera_vram: alerta += f" | Límite vRAM Excedido"
                self._clasificar_y_gestionar_apps(app_activa)
            else:
                if self.procesos_congelados or self.procesos_segundo_plano or self.apps_ocultadas:
                    self._restablecer_todos_los_procesos()

            self.datos_actualizados.emit(cpu_uso, ram_uso, ram_libre_mb, app_activa, alerta, lista_slices)
            QThread.msleep(self.INTERVALO_MS)

    def _guardar_snapshot_pico(self, cpu: float, ram: float, lista_slices: list):
        try:
            self.peak_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.peak_file_path, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "peak_cpu": cpu, "peak_ram": ram, "slices": lista_slices}, f, indent=4)
        except Exception: pass

    def abortar_y_limpiar_lista_negra(self):
        self._restablecer_todos_los_procesos()
        self.blacklist.clear()
        self._log("SYS", "Lista negra limpiada y procesos restaurados.")

    def _obtener_app_en_foco(self) -> str:
        if sys.platform == 'darwin' and HAS_APPKIT:
            try: return NSWorkspace.sharedWorkspace().frontmostApplication().localizedName() or "Desconocido"
            except Exception: pass
        return "Desconocido"

    def _ocultar_apps_de_interfaz(self, app_activa: str):
        if not HAS_APPKIT or not AXIsProcessTrusted(): return
        try:
            for app in NSWorkspace.sharedWorkspace().runningApplications():
                if app.activationPolicy() == NSApplicationActivationPolicyRegular:
                    pid = app.processIdentifier()
                    if pid == os.getpid(): continue
                    if app.localizedName().lower() in self.whitelist or app.localizedName().lower() == app_activa.lower():
                        if app.isHidden(): 
                            app.unhide()
                            self.apps_ocultadas.discard(pid)
                            self._log("ACT", f"App visible nuevamente: {app.localizedName()}")
                    elif not app.isHidden():
                        if app.hide(): 
                            self.apps_ocultadas.add(pid)
                            self._log("ACT", f"App ocultada: {app.localizedName()}")
        except Exception: pass

    def _clasificar_y_gestionar_apps(self, app_activa: str):
        self._ocultar_apps_de_interfaz(app_activa)
        for proc in psutil.process_iter(['pid', 'name', 'nice']):
            try:
                pid = proc.info['pid']
                nombre = (proc.info.get('name') or "").lower()
                if pid <= 0 or pid == os.getpid() or nombre in {"kernel_task", "windowserver", "loginwindow"}: continue
                
                if nombre in self.blacklist and nombre != app_activa.lower():
                    if pid not in self.procesos_congelados:
                        proc.send_signal(signal.SIGSTOP)
                        self.procesos_congelados.add(pid)
                        self._log("WARN", f"Proceso congelado (Blacklist): {nombre} (PID: {pid})")
                    continue

                if nombre in self.whitelist or nombre == app_activa.lower():
                    if pid in self.procesos_congelados: 
                        proc.send_signal(signal.SIGCONT)
                        self.procesos_congelados.discard(pid)
                        self._log("INFO", f"Proceso reanudado: {nombre} (PID: {pid})")
                    if pid in self.procesos_segundo_plano: 
                        proc.nice(0)
                        self.procesos_segundo_plano.discard(pid)
                        self._log("INFO", f"Prioridad normalizada: {nombre} (PID: {pid})")
                    continue

                if proc.info.get('nice', 0) < 19: 
                    proc.nice(19)
                    self.procesos_segundo_plano.add(pid)
                    self._log("ACT", f"Prioridad reducida a 2do plano: {nombre} (PID: {pid})")
            except Exception: continue

    def _restablecer_todos_los_procesos(self):
        for pid in list(self.procesos_congelados):
            try: 
                proc = psutil.Process(pid)
                proc.send_signal(signal.SIGCONT)
                self._log("INFO", f"Proceso reanudado (Reset): {proc.name()} (PID: {pid})")
            except Exception: pass
        self.procesos_congelados.clear()
        
        if sys.platform == 'darwin' and HAS_APPKIT:
            try:
                for app in NSWorkspace.sharedWorkspace().runningApplications():
                    if app.activationPolicy() == NSApplicationActivationPolicyRegular and app.isHidden(): 
                        app.unhide()
            except Exception: pass
        self.apps_ocultadas.clear()
        
        for pid in list(self.procesos_segundo_plano):
            try: 
                psutil.Process(pid).nice(0)
            except Exception: pass
        self.procesos_segundo_plano.clear()

    def stop(self):
        self._log("SYS", "Deteniendo monitor...")
        self.funcionando = False
        self._restablecer_todos_los_procesos()
        self.wait()