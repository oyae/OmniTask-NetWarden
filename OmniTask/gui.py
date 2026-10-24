import os
import time
import subprocess
import sys
import math
import json
import psutil
from collections import deque
from pathlib import Path
from PyQt6.QtWidgets import (
	QApplication, QCheckBox, QHBoxLayout, QLabel, QMainWindow,
	QMessageBox, QPushButton, QVBoxLayout, QWidget, QTabWidget,
	QTableWidget, QTableWidgetItem, QHeaderView, QSlider, QScrollArea,
	QDialog, QLineEdit, QFormLayout, QFileDialog, QComboBox, QSystemTrayIcon, QStyle, QTextEdit
)
from PyQt6.QtCore import QTimer, Qt, QPointF, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QConicalGradient, QPixmap, QPainterPath, QPolygonF, QIcon

import setproctitle

setproctitle.setproctitle("OmniTask")

class DynamicHistoryChart(QWidget):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setMinimumHeight(240)
		self.setMouseTracking(True)
		self.history_cpu = deque(maxlen=3600)
		self.history_ram = deque(maxlen=3600)
		self.hover_pos = None
		self.hover_index = None

	def add_sample(self, cpu: float, ram: float):
		self.history_cpu.append(cpu)
		self.history_ram.append(ram)
		self.update()

	def mouseMoveEvent(self, event):
		self.hover_pos = event.position().x()
		self.update()

	def leaveEvent(self, event):
		self.hover_pos = None
		self.hover_index = None
		self.update()

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		w = float(self.width())
		h = float(self.height())
		painter.fillRect(0, 0, int(w), int(h), QColor("#000810"))
		margin_top, margin_bottom, margin_left, margin_right = 20.0, 35.0, 40.0, 20.0
		chart_w = w - margin_left - margin_right
		chart_h = h - margin_top - margin_bottom

		max_val = 10.0
		if self.history_cpu: max_val = max(max_val, max(self.history_cpu))
		if self.history_ram: max_val = max(max_val, max(self.history_ram))
		max_y_scale = min(100.0, math.ceil(max_val / 10.0) * 10.0)

		pen_grid = QPen(QColor("#002233"), 1, Qt.PenStyle.DashLine)
		painter.setFont(QFont("Helvetica Neue", 8))
		num_lines = 4
		for i in range(num_lines + 1):
			val = (max_y_scale / num_lines) * i
			y = (margin_top + chart_h) - (i * (chart_h / num_lines))
			painter.setPen(pen_grid)
			painter.drawLine(QPointF(margin_left, y), QPointF(w - margin_right, y))
			painter.setPen(QColor("#0088aa"))
			painter.drawText(QRectF(0, y - 8, margin_left - 5, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{int(val)}%")

		painter.setPen(QPen(QColor("#005577"), 1.5))
		painter.drawLine(QPointF(margin_left, margin_top + chart_h), QPointF(w - margin_right, margin_top + chart_h))
		painter.setPen(QColor("#0088aa"))
		painter.drawText(QRectF(margin_left, margin_top + chart_h + 8, 100, 18), Qt.AlignmentFlag.AlignLeft, "-1 Hour")
		painter.drawText(QRectF(w - margin_right - 100, margin_top + chart_h + 8, 100, 18), Qt.AlignmentFlag.AlignRight, "Now")

		legend_x, legend_y = margin_left + 10, margin_top + 5
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(QColor("#ff0055"))
		painter.drawRect(QRectF(legend_x, legend_y + 2, 10, 10))
		painter.setPen(QColor("#ffffff"))
		painter.drawText(QRectF(legend_x + 15, legend_y - 2, 70, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "CPU Usage")
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(QColor("#00ffff"))
		painter.drawRect(QRectF(legend_x + 95, legend_y + 2, 10, 10))
		painter.setPen(QColor("#ffffff"))
		painter.drawText(QRectF(legend_x + 110, legend_y - 2, 70, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "RAM Usage")

		n_samples = len(self.history_cpu)
		if n_samples < 2: return
		step_x = chart_w / float(max(1, n_samples - 1))

		def render_line(data_deque, color_hex):
			path = QPainterPath()
			for idx, val in enumerate(data_deque):
				x = margin_left + (idx * step_x)
				norm_v = min(1.0, max(0.0, val / max_y_scale))
				y = (margin_top + chart_h) - (norm_v * chart_h)
				if idx == 0: path.moveTo(x, y)
				else: path.lineTo(x, y)
			painter.setPen(QPen(QColor(color_hex), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
			painter.setBrush(Qt.BrushStyle.NoBrush)
			painter.drawPath(path)

		render_line(self.history_ram, "#00ffff")
		render_line(self.history_cpu, "#ff0055")

		if self.hover_pos is not None and margin_left <= self.hover_pos <= (w - margin_right):
			idx_rel = int(round((self.hover_pos - margin_left) / step_x))
			idx = max(0, min(n_samples - 1, idx_rel))
			cpu_val, ram_val = self.history_cpu[idx], self.history_ram[idx]
			x_point = margin_left + (idx * step_x)

			painter.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
			painter.drawLine(QPointF(x_point, margin_top), QPointF(x_point, margin_top + chart_h))

			y_cpu = (margin_top + chart_h) - (min(1.0, cpu_val / max_y_scale) * chart_h)
			y_ram = (margin_top + chart_h) - (min(1.0, ram_val / max_y_scale) * chart_h)
			painter.setPen(QPen(QColor("#ffffff"), 1.5))
			painter.setBrush(QColor("#ff0055")); painter.drawEllipse(QPointF(x_point, y_cpu), 4, 4)
			painter.setBrush(QColor("#00ffff")); painter.drawEllipse(QPointF(x_point, y_ram), 4, 4)

			text_info = f" CPU: {cpu_val:.1f}% | RAM: {ram_val:.1f}% "
			box_w, box_h = 160.0, 24.0
			box_x = x_point + 10.0
			if box_x + box_w > w - margin_right: box_x = x_point - box_w - 10.0
			box_y = margin_top + 10.0

			painter.setPen(QPen(QColor("#00e5ff"), 1))
			painter.setBrush(QColor("#001424"))
			painter.drawRoundedRect(QRectF(box_x, box_y, box_w, box_h), 4, 4)
			painter.setFont(QFont("Helvetica Neue", 8, QFont.Weight.Bold))
			painter.setPen(QColor("#ffffff"))
			painter.drawText(QRectF(box_x, box_y, box_w, box_h), Qt.AlignmentFlag.AlignCenter, text_info)

class HelpQuestionWidget(QWidget):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setFixedSize(24, 24)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.mensaje = (
			"Virtual RAM is a technique that takes part of the storage in order "
			"to use it as backup when the physical RAM memory is full. \n"
			"Changing the size of VRAM to much higher values may not speed up "
			"your computer but overheat it. Use carefully."
		)
		self.setToolTip(self.mensaje)
	def mousePressEvent(self, event):
		if event.button() == Qt.MouseButton.LeftButton: QMessageBox.information(self, "VRAM Allocation Warning", self.mensaje)
	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		cx, cy, r = self.width() / 2.0, self.height() / 2.0, (min(self.width(), self.height()) / 2.0) - 1.5
		painter.setPen(QPen(QColor(0, 229, 255, 100), 3)); painter.drawEllipse(QPointF(cx, cy), r, r)
		painter.setPen(QPen(QColor("#00f0ff"), 1.2)); painter.drawEllipse(QPointF(cx, cy), r, r)
		path = QPainterPath(); path.moveTo(cx - 4.5, cy - 3.5)
		path.cubicTo(cx - 4.5, cy - 8.5, cx + 4.5, cy - 8.5, cx + 4.5, cy - 3.5)
		path.cubicTo(cx + 4.5, cy - 0.5, cx, cy + 1.0, cx, cy + 3.5)
		painter.setPen(QPen(QColor(0, 229, 255, 120), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)); painter.drawPath(path)
		painter.setPen(QPen(QColor("#aeffff"), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)); painter.drawPath(path)
		dot_center = QPointF(cx, cy + 6.0)
		painter.setPen(QPen(QColor(0, 229, 255, 140), 2)); painter.drawEllipse(dot_center, 1.2, 1.2)
		painter.setPen(QPen(QColor("#ffffff"), 1)); painter.drawEllipse(dot_center, 1.2, 1.2)

class NeonAddButton(QPushButton):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setFixedSize(24, 24)
		self.setCursor(Qt.CursorShape.PointingHandCursor)
		self.setStyleSheet("background: transparent; border: none;")
	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		cx, cy, r = self.width() / 2.0, self.height() / 2.0, (min(self.width(), self.height()) / 2.0) - 1.5
		glow_alpha = 255 if self.isDown() else (180 if self.underMouse() else 90)
		painter.setPen(QPen(QColor(0, 229, 255, glow_alpha), 3)); painter.drawEllipse(QPointF(cx, cy), r, r)
		painter.setPen(QPen(QColor("#00f0ff"), 1.2)); painter.drawEllipse(QPointF(cx, cy), r, r)
		path_cross = QPainterPath()
		path_cross.addRoundedRect(QRectF(cx - 5.0, cy - 1.0, 10.0, 2.0), 1, 1)
		path_cross.addRoundedRect(QRectF(cx - 1.0, cy - 5.0, 2.0, 10.0), 1, 1)
		painter.setPen(QPen(QColor(0, 229, 255, glow_alpha), 2)); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawPath(path_cross)
		painter.setPen(QPen(QColor("#ffffff"), 1)); painter.drawPath(path_cross)

class GaugeWidget(QWidget):
	def __init__(self, titulo="CPU", parent=None):
		super().__init__(parent)
		self.target_value = 0.0
		self.current_value = 0.0
		self.titulo = titulo
		self.setMinimumSize(200, 200)
		self.alerta_val = None
		self.retorno_val = None
		self.anim_timer = QTimer(self)
		self.anim_timer.setInterval(16)
		self.anim_timer.timeout.connect(self._actualizar_animacion)
		self.anim_timer.start()

	def set_value(self, value):
		self.target_value = max(0.0, min(100.0, float(value)))

	def set_thresholds(self, alerta=None, retorno=None):
		self.alerta_val = alerta
		self.retorno_val = retorno
		self.update()

	def _actualizar_animacion(self):
		diferencia = self.target_value - self.current_value
		if abs(diferencia) > 0.05:
			self.current_value += diferencia * 0.10
			self.update()
		elif self.current_value != self.target_value:
			self.current_value = self.target_value
			self.update()

	def _dibujar_perilla(self, painter, cx, cy, radius, valor, color_hex):
		if valor is None: return
		angle_rad = math.radians(135 + (valor / 100.0) * 270)
		px, py = cx + (radius - 10) * math.cos(angle_rad), cy + (radius - 10) * math.sin(angle_rad)
		painter.save()
		painter.translate(px, py)
		painter.rotate(135 + (valor / 100.0) * 270 + 90)
		tr = QPolygonF([QPointF(0, -7), QPointF(-4, 4), QPointF(4, 4)])
		painter.setPen(QPen(QColor("#ffffff"), 1.2))
		painter.setBrush(QColor(color_hex))
		painter.drawPolygon(tr)
		painter.restore()

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.RenderHint.Antialiasing)
		cx, cy, radius = self.width() / 2.0, self.height() / 2.0, (min(self.width(), self.height()) / 2.0) - 15.0
		painter.setPen(Qt.PenStyle.NoPen)
		painter.setBrush(QColor("#000b14"))
		painter.drawEllipse(QPointF(cx, cy), radius, radius)

		pen_outer = QPen(QColor("#00ffff"), 1.5, Qt.PenStyle.DashLine); pen_outer.setDashPattern([3, 5])
		painter.setPen(pen_outer); painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.drawEllipse(QPointF(cx, cy), radius - 2, radius - 2)
		painter.setPen(QPen(QColor("#004466"), 1, Qt.PenStyle.SolidLine))
		painter.drawEllipse(QPointF(cx, cy), radius - 10, radius - 10)

		rect_arc = QRectF(cx - (radius - 20), cy - (radius - 20), (radius - 20) * 2, (radius - 20) * 2)
		pen_bg_arc = QPen(QColor("#002233"), 8, Qt.PenStyle.SolidLine); pen_bg_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
		painter.setPen(pen_bg_arc); painter.drawArc(rect_arc, 225 * 16, -270 * 16)

		value_span_deg = int((self.current_value / 100.0) * -270 * 16)
		if value_span_deg != 0:
			gradiente = QConicalGradient(cx, cy, -45)
			gradiente.setColorAt(0.0, QColor("#ff0055")); gradiente.setColorAt(0.35, QColor("#ffaa00"))
			gradiente.setColorAt(0.70, QColor("#00ffff")); gradiente.setColorAt(1.0, QColor("#0088ff"))
			pen_active = QPen(gradiente, 8, Qt.PenStyle.SolidLine); pen_active.setCapStyle(Qt.PenCapStyle.RoundCap)
			painter.setPen(pen_active); painter.drawArc(rect_arc, 225 * 16, value_span_deg)

		painter.save()
		painter.translate(cx, cy)
		for i in range(31):
			angle_rad = math.radians(135 + (i * 9))
			r_in, r_out = radius - 33, radius - (27 if i % 5 == 0 else 30)
			x1, y1 = r_in * math.cos(angle_rad), r_in * math.sin(angle_rad)
			x2, y2 = r_out * math.cos(angle_rad), r_out * math.sin(angle_rad)
			painter.setPen(QPen(QColor("#00ffff") if (i * 3.33) <= self.current_value else QColor("#003344"), 1.5 if i % 5 == 0 else 1.0))
			painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
		painter.restore()

		self._dibujar_perilla(painter, cx, cy, radius, self.retorno_val, "#00ff88")
		self._dibujar_perilla(painter, cx, cy, radius, self.alerta_val, "#ff0055")

		font_title = QFont("Helvetica Neue", 10, QFont.Weight.Light); font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
		painter.setFont(font_title); painter.setPen(QColor("#00aacc"))
		painter.drawText(QRectF(cx - 50, cy - 35, 100, 20), Qt.AlignmentFlag.AlignCenter, self.titulo)
		painter.setFont(QFont("Helvetica Neue", 26, QFont.Weight.Thin)); painter.setPen(QColor("#ffffff"))
		painter.drawText(QRectF(cx - 60, cy - 15, 120, 40), Qt.AlignmentFlag.AlignCenter, f"{int(round(self.current_value))}")
		font_unit = QFont("Helvetica Neue", 8, QFont.Weight.Light); font_unit.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
		painter.setFont(font_unit); painter.setPen(QColor("#00ffff"))
		painter.drawText(QRectF(cx - 30, cy + 25, 60, 15), Qt.AlignmentFlag.AlignCenter, "PERCENT")

class DialogoSeleccionApp(QDialog):
	def __init__(self, titulo, parent=None):
		super().__init__(parent)
		self.setWindowTitle(f"Add Process to {titulo}")
		self.setFixedSize(380, 220)
		self.setStyleSheet("background-color: #000c18; color: #00e5ff;")
		self.nombre_seleccionado = ""

		layout = QVBoxLayout(self)
		lbl_info = QLabel("Choose an app from Finder or select a running process:")
		lbl_info.setWordWrap(True)
		lbl_info.setStyleSheet("font-size: 11px; color: #80a0c0;")
		layout.addWidget(lbl_info)

		btn_finder = QPushButton("📁 Select Application (.app) via Finder")
		btn_finder.setStyleSheet("QPushButton { background-color: #002233; border: 1px solid #0088aa; color: #00ffff; border-radius: 4px; padding: 8px; text-align: left; } QPushButton:hover { background-color: #003355; }")
		btn_finder.clicked.connect(self._browse_app)
		layout.addWidget(btn_finder)

		lbl_or = QLabel("— OR SELECT ACTIVE PROCESS —")
		lbl_or.setAlignment(Qt.AlignmentFlag.AlignCenter)
		lbl_or.setStyleSheet("font-size: 10px; color: #005577; font-weight: bold;")
		layout.addWidget(lbl_or)

		self.combo_procesos = QComboBox()
		self.combo_procesos.setStyleSheet("QComboBox { background-color: #001828; border: 1px solid #005577; color: #ffffff; padding: 4px; border-radius: 4px; } QComboBox QAbstractItemView { background-color: #00101c; color: #00ffff; selection-background-color: #003355; }")
		self._cargar_procesos_activos()
		layout.addWidget(self.combo_procesos)

		btn_box = QHBoxLayout()
		btn_confirm = QPushButton("Confirm")
		btn_confirm.setStyleSheet("background: #0055ff; color: white; padding: 6px;")
		btn_confirm.clicked.connect(self._confirmar_combo)
		btn_cancel = QPushButton("Cancel")
		btn_cancel.setStyleSheet("background: #330011; color: #ff5577; border: 1px solid #aa0033; padding: 6px;")
		btn_cancel.clicked.connect(self.reject)
		btn_box.addWidget(btn_cancel)
		btn_box.addWidget(btn_confirm)
		layout.addLayout(btn_box)

	def _cargar_procesos_activos(self):
		procesos = set()
		for proc in psutil.process_iter(['name']):
			try:
				pname = proc.info['name']
				if pname and len(pname.strip()) > 0: procesos.add(pname.strip())
			except (psutil.NoSuchProcess, psutil.AccessDenied): continue
		for p in sorted(procesos, key=lambda x: x.lower()): self.combo_procesos.addItem(p)

	def _browse_app(self):
		file_path, _ = QFileDialog.getOpenFileName(self, "Select Application", "/Applications", "Applications (*.app)")
		if file_path:
			self.nombre_seleccionado = os.path.basename(file_path).replace(".app", "")
			self.accept()

	def _confirmar_combo(self):
		val = self.combo_procesos.currentText().strip()
		if val:
			self.nombre_seleccionado = val
			self.accept()

class LaunchpadListWidget(QWidget):
	def __init__(self, titulo, items_set, callback_eliminar, callback_agregar, parent=None):
		super().__init__(parent)
		self.titulo = titulo
		self.items_set = items_set
		self.callback_eliminar = callback_eliminar
		self.callback_agregar = callback_agregar
		layout_principal = QVBoxLayout(self)
		layout_principal.setContentsMargins(0, 0, 0, 0)
		layout_header = QHBoxLayout()
		lbl_titulo = QLabel(titulo)
		lbl_titulo.setStyleSheet("color: #00e5ff; font-weight: 500; font-size: 12px;")
		btn_add = NeonAddButton(self)
		btn_add.setToolTip(f"Add app/process to {titulo}")
		btn_add.clicked.connect(self._pedir_nuevo_elemento)
		layout_header.addWidget(lbl_titulo)
		layout_header.addStretch()
		layout_header.addWidget(btn_add)
		layout_principal.addLayout(layout_header)

		self.scroll_area = QScrollArea()
		self.scroll_area.setWidgetResizable(True)
		self.scroll_area.setFixedHeight(85)
		self.scroll_area.setStyleSheet("QScrollArea { background-color: rgba(0, 18, 32, 0.7); border: 1px solid #0088aa; border-radius: 6px; } QScrollBar:horizontal { height: 6px; background: #000c18; } QScrollBar::handle:horizontal { background: #0088aa; border-radius: 3px; }")
		self.content_widget = QWidget()
		self.layout_items = QHBoxLayout(self.content_widget)
		self.layout_items.setAlignment(Qt.AlignmentFlag.AlignLeft)
		self.scroll_area.setWidget(self.content_widget)
		layout_principal.addWidget(self.scroll_area)
		self.actualizar_tarjetas()

	def actualizar_tarjetas(self):
		while self.layout_items.count():
			item = self.layout_items.takeAt(0)
			if item.widget(): item.widget().deleteLater()
		if not self.items_set:
			lbl_vacio = QLabel("No items registered")
			lbl_vacio.setStyleSheet("color: #507090; font-style: italic; font-size: 11px;")
			self.layout_items.addWidget(lbl_vacio)
			return
		for item_name in sorted(self.items_set):
			card = QWidget()
			card.setFixedSize(95, 60)
			card.setStyleSheet("QWidget { background-color: #001828; border: 1px solid #005577; border-radius: 4px; } QWidget:hover { border: 1px solid #ff0055; background-color: #200510; }")
			card_layout = QVBoxLayout(card)
			card_layout.setContentsMargins(4, 4, 4, 4)
			lbl_name = QLabel(item_name)
			lbl_name.setStyleSheet("color: #ffffff; font-size: 10px; border: none; background: transparent;")
			lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
			btn_del = QPushButton("× Remove")
			btn_del.setStyleSheet("QPushButton { background-color: #ff0055; color: white; border: none; border-radius: 2px; font-size: 9px; padding: 2px; } QPushButton:hover { background-color: #ff3377; }")
			btn_del.clicked.connect(lambda checked, name=item_name: self.callback_eliminar(name))
			card_layout.addWidget(lbl_name)
			card_layout.addWidget(btn_del)
			self.layout_items.addWidget(card)

	def _pedir_nuevo_elemento(self):
		dlg = DialogoSeleccionApp(self.titulo, self)
		if dlg.exec() == QDialog.DialogCode.Accepted and dlg.nombre_seleccionado:
			self.callback_agregar(dlg.nombre_seleccionado)

class VentanaPrincipal(QMainWindow):
	def __init__(self, hilo_monitor):
		super().__init__()
		self.ram_total_gb = max(1, round(psutil.virtual_memory().total / (1024 ** 3)))
		
		self.init_ui()
		self.hilo = hilo_monitor
		self.hilo.datos_actualizados.connect(self.actualizar_interfaz)
		self.hilo.alerta_seguridad.connect(self._mostrar_aviso_seguridad)
		self.hilo.consola_log.connect(self._append_console_log)
		self.hilo.solicitar_accesibilidad.connect(self._mostrar_aviso_accesibilidad)
		
		self._actualizar_umbrales_cpu()
		self._actualizar_umbrales_ram()
		self._actualizar_vram_slider(self.slider_vram.value())
		self.timer_watchdog = QTimer(self)
		self.timer_watchdog.setInterval(2000)
		self.timer_watchdog.timeout.connect(self._verificar_salud_sistema)
		self.timer_watchdog.start()

	def _verificar_salud_sistema(self):
		if self.hilo.en_modo_estres and len(self.hilo.procesos_congelados) > 0:
			tiempo_transcurrido = time.time() - self.hilo.ultimo_heartbeat
			if tiempo_transcurrido > 3.5: self.hilo.abortar_y_limpiar_lista_negra()

	def _mostrar_aviso_seguridad(self, mensaje):
		QMessageBox.warning(self, "System Protection", mensaje)

	def _mostrar_aviso_accesibilidad(self):
		msg = QMessageBox(self)
		msg.setWindowTitle("Permisos de Accesibilidad Necesarios")
		msg.setIcon(QMessageBox.Icon.Information)
		msg.setText("Para que la aplicación pueda ocultar ventanas y gestionar procesos correctamente, necesita permisos de accesibilidad.\n\nPor favor, otorgue el permiso en:\nPreferencias del Sistema → Seguridad y Privacidad → Privacidad → Accesibilidad")
		btn_abrir = msg.addButton("Abrir Preferencias", QMessageBox.ButtonRole.AcceptRole)
		btn_cerrar = msg.addButton("Cerrar", QMessageBox.ButtonRole.RejectRole)
		msg.exec()
		if msg.clickedButton() == btn_abrir: subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])

	def _crear_style_slider(self, color_thumb="#00ffff"):
		return f"QSlider::groove:horizontal {{ border: 1px solid #005577; height: 4px; background: #001624; border-radius: 2px; }} QSlider::handle:horizontal {{ background: {color_thumb}; border: 1px solid #ffffff; width: 10px; margin: -3px 0; border-radius: 5px; }} QSlider::sub-page:horizontal {{ background: #0088aa; border-radius: 2px; }}"

	def init_ui(self):
		self.setWindowTitle("OmniTask System Monitor - MacOS HUD")
		self.resize(680, 620)
		self.setStyleSheet("QMainWindow, QWidget { background-color: #000c18; font-family: 'Helvetica Neue', 'SF Pro Display', 'Menlo', sans-serif; } QLabel { color: #00e5ff; font-size: 13px; font-weight: 300; } QCheckBox { color: #a0c0d0; font-size: 12px; font-weight: 300; spacing: 8px; } QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #0088aa; background-color: #001624; border-radius: 2px; } QCheckBox::indicator:checked { background-color: #00ffff; border: 1px solid #00ffff; } QTabWidget::pane { border: 1px solid #005577; background-color: #000c18; border-radius: 6px; } QTabBar::tab { background-color: #001624; color: #80a0c0; padding: 8px 20px; min-width: 90px; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; font-size: 12px; } QTabBar::tab:selected { background-color: #003355; color: #00ffff; font-weight: 500; border: 1px solid #0088aa; border-bottom: none; } QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0055ff, stop:1 #00e5ff); color: #ffffff; border: 1px solid #00ffff; border-radius: 4px; padding: 5px 12px; font-weight: 500; font-size: 11px; } QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0066ff, stop:1 #33ffff); border: 1px solid #ffffff; } QTableWidget { background-color: #000e1a; gridline-color: #003344; color: #f0f8ff; border: 1px solid #005577; font-size: 11px; } QHeaderView::section { background-color: #001c2e; color: #00ffff; padding: 4px; border: 1px solid #003344; font-weight: bold; } QComboBox { background-color: #001828; border: 1px solid #005577; color: #00ffff; padding: 3px 8px; border-radius: 4px; font-size: 11px; } QComboBox QAbstractItemView { background-color: #00101c; color: #00ffff; selection-background-color: #003355; } QTextEdit { background-color: #000810; color: #00ff88; border: 1px solid #005577; font-family: 'Menlo', 'Courier New', monospace; font-size: 11px; border-radius: 4px; } QMessageBox { background-color: #000e1a; border: 1px solid #0088aa; } QMessageBox QLabel { color: #f0f8ff; font-size: 13px; }")

		central_widget = QWidget(self)
		self.setCentralWidget(central_widget)
		self.tabs = QTabWidget()
		self.tabs.tabBar().setExpanding(False)

		tab_general = QWidget()
		layout_general = QVBoxLayout(tab_general)
		layout_general.setSpacing(10)

		top_header_layout = QHBoxLayout()
		self.lbl_app = QLabel("ACTIVE APP: Loading...", self)
		self.lbl_app.setStyleSheet("font-size: 13px; font-weight: 400; color: #ffffff;")
		self.lbl_status = QLabel("SYSTEM STATUS: OPERATIONAL", self)
		self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
		self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 500; color: #00e5ff;")
		top_header_layout.addWidget(self.lbl_app)
		top_header_layout.addStretch()
		top_header_layout.addWidget(self.lbl_status)

		self.cpu_gauge = GaugeWidget(titulo="CPU")
		self.ram_gauge = GaugeWidget(titulo="RAM")

		layout_cpu_ctrl = QVBoxLayout()
		row_cpu_alert = QHBoxLayout()
		row_cpu_alert.addWidget(QLabel("CPU Alert:"))
		self.lbl_cpu_alert_v = QLabel("70%")
		self.slider_cpu_alert = QSlider(Qt.Orientation.Horizontal)
		self.slider_cpu_alert.setRange(10, 95)
		self.slider_cpu_alert.setValue(70)
		self.slider_cpu_alert.setStyleSheet(self._crear_style_slider("#ff0055"))
		self.slider_cpu_alert.valueChanged.connect(self._actualizar_umbrales_cpu)
		row_cpu_alert.addWidget(self.slider_cpu_alert)
		row_cpu_alert.addWidget(self.lbl_cpu_alert_v)

		row_cpu_ret = QHBoxLayout()
		row_cpu_ret.addWidget(QLabel("CPU Return:"))
		self.lbl_cpu_ret_v = QLabel("20%")
		self.slider_cpu_ret = QSlider(Qt.Orientation.Horizontal)
		self.slider_cpu_ret.setRange(5, 50)
		self.slider_cpu_ret.setValue(20)
		self.slider_cpu_ret.setStyleSheet(self._crear_style_slider("#00ff88"))
		self.slider_cpu_ret.valueChanged.connect(self._actualizar_umbrales_cpu)
		row_cpu_ret.addWidget(self.slider_cpu_ret)
		row_cpu_ret.addWidget(self.lbl_cpu_ret_v)
		layout_cpu_ctrl.addLayout(row_cpu_alert)
		layout_cpu_ctrl.addLayout(row_cpu_ret)

		layout_ram_ctrl = QVBoxLayout()
		row_ram_alert = QHBoxLayout()
		row_ram_alert.addWidget(QLabel("RAM Alert:"))
		self.lbl_ram_alert_v = QLabel("80%")
		self.slider_ram_alert = QSlider(Qt.Orientation.Horizontal)
		self.slider_ram_alert.setRange(20, 95)
		self.slider_ram_alert.setValue(80)
		self.slider_ram_alert.setStyleSheet(self._crear_style_slider("#ff0055"))
		self.slider_ram_alert.valueChanged.connect(self._actualizar_umbrales_ram)
		row_ram_alert.addWidget(self.slider_ram_alert)
		row_ram_alert.addWidget(self.lbl_ram_alert_v)
		layout_ram_ctrl.addLayout(row_ram_alert)
		layout_ram_ctrl.addStretch()

		col_cpu = QVBoxLayout()
		col_cpu.addWidget(self.cpu_gauge)
		col_cpu.addLayout(layout_cpu_ctrl)
		col_ram = QVBoxLayout()
		col_ram.addWidget(self.ram_gauge)
		col_ram.addLayout(layout_ram_ctrl)
		gauges_layout = QHBoxLayout()
		gauges_layout.addLayout(col_cpu)
		gauges_layout.addLayout(col_ram)

		self.lbl_ram_info = QLabel("Free Memory: 0 MB", self)
		self.lbl_ram_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self.chk_vram = QCheckBox("Activate Aggressive Memory Management / Native Swap", self)
		self.chk_vram.toggled.connect(self._alternar_modo_vram)

		vram_container = QVBoxLayout()
		vram_control_layout = QHBoxLayout()
		val_default_gb = round(self.ram_total_gb * 0.5, 1)
		self.lbl_vram_val = QLabel(f"{val_default_gb:.1f} GB")
		self.slider_vram = QSlider(Qt.Orientation.Horizontal)
		self.slider_vram.setRange(0, self.ram_total_gb * 2)
		self.slider_vram.setValue(int(val_default_gb * 2))
		self.slider_vram.setTickPosition(QSlider.TickPosition.TicksBelow)
		self.slider_vram.setTickInterval(2)
		self.slider_vram.setStyleSheet(self._crear_style_slider("#00ffff"))
		self.slider_vram.valueChanged.connect(self._actualizar_vram_slider)
		self.help_widget = HelpQuestionWidget(self)
		vram_control_layout.addWidget(QLabel("VRAM Allocation Limit:"))
		vram_control_layout.addWidget(self.slider_vram)
		vram_control_layout.addWidget(self.lbl_vram_val)
		vram_control_layout.addWidget(self.help_widget)
		scale_layout = QHBoxLayout(); scale_layout.setContentsMargins(135, 0, 85, 0)
		for mark_gb in [0, round(self.ram_total_gb * 0.25, 1), round(self.ram_total_gb * 0.5, 1), round(self.ram_total_gb * 0.75, 1), self.ram_total_gb]:
			lbl_mark = QLabel(f"{mark_gb} GB"); lbl_mark.setStyleSheet("color: #005577; font-size: 9px; font-weight: bold;"); lbl_mark.setAlignment(Qt.AlignmentFlag.AlignCenter); scale_layout.addWidget(lbl_mark)
		vram_container.addLayout(vram_control_layout)
		vram_container.addLayout(scale_layout)

		self.launchpad_whitelist = LaunchpadListWidget("Whitelist (Protected / High Priority)", None, self._remover_whitelist, self._agregar_whitelist)
		self.launchpad_blacklist = LaunchpadListWidget("Blacklist (Suspended on Stress)", None, self._remover_blacklist, self._agregar_blacklist)
		
		layout_general.addLayout(top_header_layout)
		layout_general.addLayout(gauges_layout)
		layout_general.addWidget(self.lbl_ram_info)
		layout_general.addWidget(self.chk_vram)
		layout_general.addLayout(vram_container)
		layout_general.addWidget(self.launchpad_whitelist)
		layout_general.addWidget(self.launchpad_blacklist)

		tab_slices = QWidget()
		layout_slices = QVBoxLayout(tab_slices)
		layout_orden = QHBoxLayout()
		self.combo_orden = QComboBox()
		self.combo_orden.addItem("RAM Usage (Highest First)", "ram")
		self.combo_orden.addItem("CPU Usage (Highest First)", "cpu")
		layout_orden.addWidget(QLabel("Sort Process List By:"))
		layout_orden.addWidget(self.combo_orden)
		layout_orden.addStretch()
		self.tabla_slices = QTableWidget()
		self.tabla_slices.setColumnCount(4)
		self.tabla_slices.setHorizontalHeaderLabels(["Application / Process", "CPU %", "RAM %", "Work Status"])
		self.tabla_slices.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
		self.tabla_slices.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
		self.tabla_slices.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
		self.tabla_slices.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
		self.tabla_slices.verticalHeader().setVisible(False)
		layout_slices.addLayout(layout_orden)
		layout_slices.addWidget(self.tabla_slices)

		tab_history = QWidget()
		layout_history = QVBoxLayout(tab_history)
		self.chart_widget = DynamicHistoryChart()
		btn_generate_log = QPushButton("📋 Generate Log / Full System Report")
		btn_generate_log.setFixedHeight(35)
		btn_generate_log.clicked.connect(self._generar_reporte_completo)
		layout_history.addWidget(QLabel("System Metrics History (Last Hour)"))
		layout_history.addWidget(self.chart_widget)
		layout_history.addStretch()
		layout_history.addWidget(btn_generate_log)

		tab_console = QWidget()
		layout_console = QVBoxLayout(tab_console)
		self.txt_console = QTextEdit()
		self.txt_console.setReadOnly(True)
		layout_console.addWidget(QLabel("System Events & Background Actions Log:"))
		layout_console.addWidget(self.txt_console)

		self.tabs.addTab(tab_general, "General")
		self.tabs.addTab(tab_slices, "Slices")
		self.tabs.addTab(tab_history, "History")
		self.tabs.addTab(tab_console, "Console")
		main_layout = QVBoxLayout(central_widget)
		main_layout.addWidget(self.tabs)

	def _append_console_log(self, tipo: str, mensaje: str):
		timestamp = time.strftime("%H:%M:%S")
		color = "#ff3366" if tipo == "WARN" else ("#ff0055" if tipo == "ERR" else ("#00e5ff" if tipo == "SYS" else "#00ff88"))
		self.txt_console.append(f'<span style="color:#507090;">[{timestamp}]</span> <b style="color:{color};">[{tipo}]</b> <span style="color:#e0f0ff;">{mensaje}</span>')

	def _generar_reporte_completo(self):
		default_dir = os.path.join(Path.home(), "OmniTask", "Reports")
		os.makedirs(default_dir, exist_ok=True)
		default_file = os.path.join(default_dir, f"SystemReport_{int(time.time())}.txt")
		
		file_path, _ = QFileDialog.getSaveFileName(self, "Save System Report", default_file, "Text Files (*.txt)")
		if not file_path: return
		try:
			hist_cpu, hist_ram = list(self.chart_widget.history_cpu), list(self.chart_widget.history_ram)
			avg_cpu = sum(hist_cpu) / len(hist_cpu) if hist_cpu else 0.0
			avg_ram = sum(hist_ram) / len(hist_ram) if hist_ram else 0.0
			max_cpu = max(hist_cpu) if hist_cpu else 0.0
			max_ram = max(hist_ram) if hist_ram else 0.0

			peak_file = self.hilo.peak_file_path
			peak_data_str = "No peak snapshot available."
			if peak_file.exists():
				with open(peak_file, "r", encoding="utf-8") as f:
					peak_json = json.load(f)
					peak_data_str = f"Peak Time: {peak_json.get('timestamp')}\nPeak Overall Metrics: CPU {peak_json.get('peak_cpu'):.1f}% | RAM {peak_json.get('peak_ram'):.1f}%\n"
					for item in peak_json.get("slices", []): peak_data_str += f"{item['name']:<35} {item['cpu']:<10.1f} {item['ram']:<10.1f} {item['status']:<10}\n"
			
			with open(file_path, "w", encoding="utf-8") as f:
				f.write(f"SYSTEM MONITOR - LOG & REPORT\nGenerated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
				f.write(f"Average CPU: {avg_cpu:.2f}% | Peak CPU: {max_cpu:.2f}%\n")
				f.write(f"Average RAM: {avg_ram:.2f}% | Peak RAM: {max_ram:.2f}%\n\n")
				f.write(f"2. PEAK CONSUMPTION APPS BREAKDOWN\n{peak_data_str}\n\n")
				f.write(f"3. SYSTEM LOG\n{self.txt_console.toPlainText()}\n")
			QMessageBox.information(self, "Report Generated", f"Saved at:\n{file_path}")
		except Exception as e:
			QMessageBox.critical(self, "Error", f"Could not generate log: {str(e)}")

	def _actualizar_umbrales_cpu(self):
		val_alerta, val_retorno = self.slider_cpu_alert.value(), self.slider_cpu_ret.value()
		if val_retorno >= val_alerta: val_retorno = val_alerta - 1; self.slider_cpu_ret.setValue(val_retorno)
		self.lbl_cpu_alert_v.setText(f"{val_alerta}%"); self.lbl_cpu_ret_v.setText(f"{val_retorno}%")
		self.cpu_gauge.set_thresholds(alerta=val_alerta, retorno=val_retorno)
		if hasattr(self, 'hilo'): self.hilo.LIMITE_CPU_GLOBAL, self.hilo.UMBRAL_DESACTIVACION_CPU = float(val_alerta), float(val_retorno)

	def _actualizar_umbrales_ram(self):
		val_alerta = self.slider_ram_alert.value()
		self.lbl_ram_alert_v.setText(f"{val_alerta}%")
		self.ram_gauge.set_thresholds(alerta=val_alerta)
		if hasattr(self, 'hilo'): self.hilo.LIMITE_RAM_PORCENTAJE = float(val_alerta)

	def _actualizar_vram_slider(self, val_pasos):
		gb_seleccionados = val_pasos / 2.0
		self.lbl_vram_val.setText(f"{gb_seleccionados:.1f} GB")
		if hasattr(self, 'hilo'): self.hilo.vram_limit_mb = int(gb_seleccionados * 1024)

	def _agregar_whitelist(self, nombre):
		if nombre: self.hilo.whitelist.add(nombre.lower()); self.launchpad_whitelist.items_set = self.hilo.whitelist; self.launchpad_whitelist.actualizar_tarjetas()
	def _remover_whitelist(self, nombre):
		self.hilo.whitelist.discard(nombre.lower()); self.launchpad_whitelist.items_set = self.hilo.whitelist; self.launchpad_whitelist.actualizar_tarjetas()
	def _agregar_blacklist(self, nombre):
		if nombre: self.hilo.blacklist.add(nombre.lower()); self.launchpad_blacklist.items_set = self.hilo.blacklist; self.launchpad_blacklist.actualizar_tarjetas()
	def _remover_blacklist(self, nombre):
		self.hilo.blacklist.discard(nombre.lower()); self.launchpad_blacklist.items_set = self.hilo.blacklist; self.launchpad_blacklist.actualizar_tarjetas()
	def _alternar_modo_vram(self, checked):
		self.hilo.modo_vram_nativo = checked
		if checked: QMessageBox.information(self, "Memory Management", "Memory delegation to native Swap has been activated.")

	def _update_cell(self, row, col, text, bg_color, txt_color):
		item = self.tabla_slices.item(row, col)
		if item is None:
			item = QTableWidgetItem(text)
			self.tabla_slices.setItem(row, col, item)
		else: item.setText(text)
		item.setBackground(bg_color)
		item.setForeground(txt_color)

	def actualizar_interfaz(self, cpu, ram, ram_libre, app_activa, alerta, lista_slices):
		self.lbl_app.setText(f"<b>ACTIVE APP:</b> {app_activa}")
		self.cpu_gauge.set_value(cpu)
		self.ram_gauge.set_value(ram)
		self.lbl_ram_info.setText(f"Free RAM: {ram_libre:.0f} MB")
		self.chart_widget.add_sample(cpu, ram)

		if self.launchpad_whitelist.items_set is None: self.launchpad_whitelist.items_set = self.hilo.whitelist; self.launchpad_whitelist.actualizar_tarjetas()
		if self.launchpad_blacklist.items_set is None: self.launchpad_blacklist.items_set = self.hilo.blacklist; self.launchpad_blacklist.actualizar_tarjetas()

		if alerta:
			self.lbl_status.setText(f"⚠️ {alerta}")
			self.lbl_status.setStyleSheet("font-size: 11px; font-weight: bold; color: #ff0055;")
		else:
			self.lbl_status.setText("SYSTEM STATUS: STABLE")
			self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 500; color: #00e5ff;")

		if self.tabs.currentIndex() != 1 or self.tabla_slices.verticalScrollBar().isSliderDown(): return

		criterio_orden = self.combo_orden.currentData()
		lista_slices.sort(key=lambda x: x[criterio_orden], reverse=True)
		self.tabla_slices.setUpdatesEnabled(False)
		try:
			if self.tabla_slices.rowCount() != len(lista_slices): self.tabla_slices.setRowCount(len(lista_slices))
			for row, proc in enumerate(lista_slices):
				pname, pcpu, pram, pstatus = proc['name'], proc['cpu'], proc['ram'], proc['status']
				pname_lower = pname.lower()
				es_white, es_black = pname_lower in self.hilo.whitelist, pname_lower in self.hilo.blacklist
				if es_white: bg_color, txt_color = QColor("#002a40"), QColor("#ffffff")
				elif es_black: bg_color, txt_color = QColor("#140008"), QColor("#ff4477")
				else:
					if pname_lower == app_activa.lower(): bg_color, txt_color = QColor("#003344"), QColor("#00ffff")
					else: bg_color, txt_color = QColor("#001422"), QColor("#a0c0d0")
				self._update_cell(row, 0, pname, bg_color, txt_color)
				self._update_cell(row, 1, f"{pcpu:.1f}%", bg_color, txt_color)
				self._update_cell(row, 2, f"{pram:.1f}%", bg_color, txt_color)
				self._update_cell(row, 3, pstatus, bg_color, txt_color)
		finally: self.tabla_slices.setUpdatesEnabled(True)

	def closeEvent(self, event):
		self.hide()
		event.ignore()