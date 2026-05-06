import logging
from pathlib import Path

import pyvista as pv
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox, QSlider,
)

log = logging.getLogger(__name__)


_FIELDS = [
    ("Airflow Speed (U)",           "U"),
    ("Air Pressure (p)",            "p"),
    ("Surface Friction (Skin Drag)", "wallShearStress"),
    ("Turbulence (Noise Source)",    "k"),
    ("Vortex Energy (Omega)",        "omega"),
]

_AXIS_STYLE_ON  = "font-weight:bold; background:#4a90d9; color:white; border-radius:4px;"
_AXIS_STYLE_OFF = "font-weight:normal; background:#e0e0e0; color:#333; border-radius:4px;"


class _StreamlineWorker(QThread):
    """
    Computes planar streamlines in a background thread.

    axis='Y'  →  seed line at Y=centre, seeds spaced in Z  (side / XZ view)
    axis='Z'  →  seed line at Z=centre, seeds spaced in Y  (top  / XY view)
    """
    ready  = pyqtSignal(object)  # PolyData (raw stream lines, no tube)
    failed = pyqtSignal(str)

    def __init__(self, case_dir: str, n_lines: int,
                 aircraft_bounds: list | None, axis: str = "Y", offset: float = 0.0):
        super().__init__()
        self._case_dir        = case_dir
        self._n_lines         = n_lines
        self._aircraft_bounds = aircraft_bounds
        self._axis            = axis    # 'Y' or 'Z'
        self._offset          = offset  # metres from model centre

    def run(self):
        try:
            foam_file = str(Path(self._case_dir) / "case.foam")
            reader = pv.OpenFOAMReader(foam_file)
            if not reader.time_values:
                self.failed.emit("No time steps in results")
                return

            reader.set_active_time_value(reader.time_values[-1])
            dataset = reader.read()

            internal = dataset["internalMesh"]
            if internal is None:
                self.failed.emit("internalMesh not found")
                return
            if hasattr(internal, "n_blocks"):
                internal = internal.combine(merge_points=True)

            internal = internal.cell_data_to_point_data()
            if "U" not in internal.point_data.keys():
                self.failed.emit(
                    f"U not found in point data — have: {list(internal.point_data.keys())}"
                )
                return

            b = self._aircraft_bounds or list(internal.bounds)
            ac_len    = b[1] - b[0]
            ac_width  = b[3] - b[2]   # Y span
            ac_height = b[5] - b[4]   # Z span
            cy = (b[2] + b[3]) / 2
            cz = (b[4] + b[5]) / 2

            margin   = max(ac_width, ac_height) * 0.4
            x_seed   = b[0] - ac_len * 0.4
            max_len  = ac_len * 14.0

            if self._axis == "Y":
                # Seed line at Y = cy + offset, varying in Z  → XZ plane flow
                seed_y = cy + self._offset
                seed = pv.Line(
                    pointa=(x_seed, seed_y, b[4] - margin),
                    pointb=(x_seed, seed_y, b[5] + margin),
                    resolution=self._n_lines,
                )
            else:
                # Seed line at Z = cz + offset, varying in Y  → XY plane flow
                seed_z = cz + self._offset
                seed = pv.Line(
                    pointa=(x_seed, b[2] - margin, seed_z),
                    pointb=(x_seed, b[3] + margin, seed_z),
                    resolution=self._n_lines,
                )

            stream = internal.streamlines_from_source(
                seed,
                vectors="U",
                integration_direction="forward",
                max_length=max_len,
            )

            if stream is None or stream.n_points == 0:
                self.failed.emit("No streamlines generated — check mesh / U field")
                return

            self.ready.emit(stream)
            log.info(f"Streamlines ({self._axis}-axis): {stream.n_points} pts")

        except Exception as exc:
            self.failed.emit(str(exc))


class ResultsPanel(QWidget):
    """Tab 5 — field visualisation + aerodynamic coefficient summary."""

    def __init__(self, main_window):
        super().__init__()
        self._mw           = main_window
        self._case_dir: str | None = None
        self._domain_shown = False
        self._stream_axis   = "Y"
        self._stream_offset = 0.0
        self._streamlines_active = False
        self._stream_worker: QThread | None = None
        self._stream_timer = QTimer()
        self._stream_timer.setSingleShot(True)
        self._stream_timer.timeout.connect(self._on_show_streamlines)
        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Results Visualisation</b>"))

        # --- Field selector ---
        disp_grp  = QGroupBox("Display Options")
        disp_form = QFormLayout()
        self._combo = QComboBox()
        for label, field in _FIELDS:
            self._combo.addItem(label, field)
        disp_form.addRow("Field:", self._combo)
        disp_grp.setLayout(disp_form)
        layout.addWidget(disp_grp)

        self._load_btn = QPushButton("Load Results")
        self._load_btn.setEnabled(False)
        self._load_btn.clicked.connect(self._on_load)
        layout.addWidget(self._load_btn)

        self._domain_btn = QPushButton("Hide Domain Box")
        self._domain_btn.setEnabled(False)
        self._domain_btn.clicked.connect(self._toggle_domain)
        layout.addWidget(self._domain_btn)

        # --- Streamlines ---
        stream_grp  = QGroupBox("Streamlines")
        stream_vbox = QVBoxLayout()

        # Axis toggle: Y | Z
        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Plane:"))
        self._btn_y = QPushButton("Y")
        self._btn_z = QPushButton("Z")
        for btn in (self._btn_y, self._btn_z):
            btn.setFixedHeight(24)
            btn.setFixedWidth(36)
        self._btn_y.clicked.connect(lambda: self._set_axis("Y"))
        self._btn_z.clicked.connect(lambda: self._set_axis("Z"))
        axis_row.addWidget(self._btn_y)
        axis_row.addWidget(self._btn_z)
        axis_row.addStretch()
        stream_vbox.addLayout(axis_row)

        lines_form = QFormLayout()
        self._stream_n = QSpinBox()
        self._stream_n.setRange(5, 60)
        self._stream_n.setValue(20)
        self._stream_n.setFixedWidth(100)
        self._stream_n.setToolTip("Number of seed lines along the chosen axis")
        lines_form.addRow("Lines:", self._stream_n)
        stream_vbox.addLayout(lines_form)

        # Offset controls — shift the seed line left/right (Y-plane) or up/down (Z-plane)
        offset_row = QHBoxLayout()
        self._offset_label = QLabel("Y offset (m):")
        self._offset_label.setFixedWidth(90)
        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(-5.0, 5.0)
        self._offset_spin.setSingleStep(0.001)
        self._offset_spin.setValue(0.0)
        self._offset_spin.setDecimals(3)
        self._offset_spin.setFixedWidth(100)
        self._offset_spin.setToolTip("Offset seed line from model centre (metres) — 1mm precision")
        self._offset_slider = QSlider(Qt.Orientation.Horizontal)
        self._offset_slider.setRange(-5000, 5000)   # maps to ±5.0 m (0.001 m/step)
        self._offset_slider.setValue(0)
        self._offset_slider.setToolTip("Drag to offset streamline seed (1mm increments)")

        offset_row.addWidget(self._offset_label)
        offset_row.addWidget(self._offset_spin)
        offset_row.addWidget(self._offset_slider)
        stream_vbox.addLayout(offset_row)

        self._offset_spin.valueChanged.connect(self._on_offset_spin_changed)
        self._offset_slider.valueChanged.connect(self._on_offset_slider_changed)

        stream_grp.setLayout(stream_vbox)
        layout.addWidget(stream_grp)

        self._stream_show_btn = QPushButton("Show Streamlines")
        self._stream_show_btn.setEnabled(False)
        self._stream_show_btn.clicked.connect(self._on_show_streamlines)
        layout.addWidget(self._stream_show_btn)

        self._stream_clear_btn = QPushButton("Clear Streamlines")
        self._stream_clear_btn.setEnabled(False)
        self._stream_clear_btn.clicked.connect(self._on_clear_streamlines)
        layout.addWidget(self._stream_clear_btn)

        # --- Aerodynamic summary ---
        aero_grp  = QGroupBox("Aerodynamic Summary")
        aero_form = QFormLayout()
        self._lbl_cl   = QLabel("—")
        self._lbl_cd   = QLabel("—")
        self._lbl_ld   = QLabel("—")
        self._lbl_cm   = QLabel("—")
        self._lbl_lift = QLabel("—")
        self._lbl_drag = QLabel("—")
        aero_form.addRow("CL (lift coeff):",   self._lbl_cl)
        aero_form.addRow("CD (drag coeff):",   self._lbl_cd)
        aero_form.addRow("L/D ratio:",         self._lbl_ld)
        aero_form.addRow("CM (pitch moment):", self._lbl_cm)
        aero_form.addRow("Lift force:",        self._lbl_lift)
        aero_form.addRow("Drag force:",        self._lbl_drag)
        aero_grp.setLayout(aero_form)
        layout.addWidget(aero_grp)

        self._status = QLabel("Waiting for solver…")
        layout.addWidget(self._status)
        layout.addStretch()

        # Initial axis highlight
        self._set_axis("Y")

    # ------------------------------------------------------------------
    def _set_axis(self, axis: str):
        self._stream_axis = axis
        self._btn_y.setStyleSheet(_AXIS_STYLE_ON  if axis == "Y" else _AXIS_STYLE_OFF)
        self._btn_z.setStyleSheet(_AXIS_STYLE_ON  if axis == "Z" else _AXIS_STYLE_OFF)
        label = "Y offset (m):" if axis == "Y" else "Z offset (m):"
        self._offset_label.setText(label)

    def _on_offset_spin_changed(self, value: float):
        self._stream_offset = value
        # Update slider without triggering its own signal back
        self._offset_slider.blockSignals(True)
        self._offset_slider.setValue(round(value / 0.001))
        self._offset_slider.blockSignals(False)
        self._maybe_auto_update()

    def _on_offset_slider_changed(self, slider_val: int):
        value = round(slider_val * 0.001, 3)
        self._stream_offset = value
        self._offset_spin.blockSignals(True)
        self._offset_spin.setValue(value)
        self._offset_spin.blockSignals(False)
        self._maybe_auto_update()

    def _maybe_auto_update(self):
        if self._streamlines_active:
            # Debounce by 200ms to avoid spamming VTK
            self._stream_timer.start(200)

    # ------------------------------------------------------------------
    def set_case_dir(self, case_dir: str):
        self._case_dir = case_dir
        self._load_btn.setEnabled(True)
        self._domain_btn.setEnabled(False)
        self._stream_show_btn.setEnabled(True)
        self._stream_clear_btn.setEnabled(True)
        self._status.setText("Results ready — click Load.")
        log.info(f"ResultsPanel ready: {case_dir}")

    # ------------------------------------------------------------------
    def _on_load(self):
        if not self._case_dir:
            return
        field = self._combo.currentData()
        cond  = self._mw.get_flight_conditions()
        log.info(f"Loading field: {field}")

        self._mw.viewport.show_results(self._case_dir, field)
        self._mw.viewport.show_wind_arrow(cond["airspeed"], cond["aoa_deg"])

        self._domain_shown = False
        self._domain_btn.setText("Show Domain Box")
        self._domain_btn.setEnabled(True)

        self._load_aero_summary(cond)
        self._status.setText(f"Displaying: {self._combo.currentText()}")
        self._mw.set_status(f"Results shown: {self._combo.currentText()}")

    # ------------------------------------------------------------------
    def _toggle_domain(self):
        self._domain_shown = not self._domain_shown
        self._mw.viewport.set_domain_box_visible(self._domain_shown)
        self._domain_btn.setText(
            "Hide Domain Box" if self._domain_shown else "Show Domain Box"
        )

    # ------------------------------------------------------------------
    def _on_show_streamlines(self):
        if not self._case_dir:
            return
        
        # If worker is already running, wait/ignore to avoid VTK collisions
        if self._stream_worker and self._stream_worker.isRunning():
            self._stream_timer.start(100) # retry soon
            return

        n = self._stream_n.value()
        self._streamlines_active = True
        self._stream_show_btn.setEnabled(False)
        self._stream_clear_btn.setEnabled(False)
        self._status.setText(f"Computing {n} streamlines ({self._stream_axis}-plane)…")

        self._stream_worker = _StreamlineWorker(
            self._case_dir,
            n,
            self._mw.viewport._aircraft_bounds,
            self._stream_axis,
            self._stream_offset,
        )
        self._stream_worker.ready.connect(self._on_streamlines_ready)
        self._stream_worker.failed.connect(self._on_streamlines_failed)
        self._stream_worker.start()

    def _on_streamlines_ready(self, stream):
        self._mw.viewport.add_streamlines_mesh(stream)
        self._stream_show_btn.setEnabled(True)
        self._stream_clear_btn.setEnabled(True)
        self._status.setText(f"Streamlines shown ({self._stream_axis}-plane)")
        self._mw.set_status("Streamlines done")

    def _on_streamlines_failed(self, msg: str):
        log.error(f"Streamlines failed: {msg}")
        self._stream_show_btn.setEnabled(True)
        self._stream_clear_btn.setEnabled(True)
        self._status.setText(f"Streamlines failed: {msg}")
        self._mw.set_status("Streamlines failed")

    def _on_clear_streamlines(self):
        self._streamlines_active = False
        self._stream_timer.stop()
        self._mw.viewport.clear_streamlines()
        self._status.setText("Streamlines cleared")

    # ------------------------------------------------------------------
    def _load_aero_summary(self, cond: dict):
        from core.results_reader import ResultsReader
        coeffs = ResultsReader.read_force_coeffs(self._case_dir)
        if coeffs is None:
            self._status.setText("Note: forceCoeffs not found — run solver first.")
            return

        Cl = coeffs["Cl"]
        Cd = coeffs["Cd"]
        Cm = coeffs["CmPitch"]
        ld = Cl / Cd if abs(Cd) > 1e-9 else float("inf")

        q      = 0.5 * cond["rho"] * cond["airspeed"] ** 2
        Aref   = cond.get("Aref", 0.15)
        lift_N = q * Aref * Cl
        drag_N = q * Aref * Cd

        self._lbl_cl.setText(f"{Cl:.4f}")
        self._lbl_cd.setText(f"{Cd:.4f}")
        self._lbl_ld.setText(f"{ld:.2f}" if ld != float("inf") else "∞")
        self._lbl_cm.setText(f"{Cm:.4f}")
        self._lbl_lift.setText(f"{lift_N:.2f} N")
        self._lbl_drag.setText(f"{drag_N:.2f} N")

        log.info(
            f"Aero summary — CL={Cl:.4f} CD={Cd:.4f} "
            f"L/D={ld:.2f} Lift={lift_N:.2f} N Drag={drag_N:.2f} N"
        )
