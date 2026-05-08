import logging
from pathlib import Path

import pyvista as pv
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox, QSlider,
    QColorDialog,
)

log = logging.getLogger(__name__)


_FIELDS = [
    ("Airflow Speed (U)",           "U"),
    ("Air Pressure (p)",            "p"),
    ("Surface Friction (Skin Drag)", "wallShearStress"),
    ("Turbulence (Noise Source)",    "k"),
    ("Vortex Energy (Omega)",        "omega"),
]

# Axis styles moved to refresh_theme for theme awareness



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
        self._stream_color: str | None = None
        self._setup_ui()
        self.refresh_theme()


    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Results Visualisation</b>"))

        # --- Run Selection (Bulk Testing) ---
        self._run_grp = QGroupBox("Select Run")
        run_lay = QVBoxLayout()
        self._run_combo = QComboBox()
        self._run_combo.currentIndexChanged.connect(self._on_run_selected)
        run_lay.addWidget(self._run_combo)
        self._run_grp.setLayout(run_lay)
        self._run_grp.setVisible(False)
        layout.addWidget(self._run_grp)

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
        self._stream_n.setRange(5, 120)
        self._stream_n.setValue(20)
        self._stream_n.setFixedWidth(100)
        self._stream_n.setToolTip("Number of seed lines along the chosen axis")
        lines_form.addRow("Lines:", self._stream_n)
        stream_vbox.addLayout(lines_form)

        # Offset controls — shift the seed line left/right (Y-plane) or up/down (Z-plane)
        offset_row = QHBoxLayout()
        self._offset_label = QLabel("Y offset (%):")
        self._offset_label.setFixedWidth(90)
        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(-150.0, 150.0)
        self._offset_spin.setSingleStep(1.0)
        self._offset_spin.setValue(0.0)
        self._offset_spin.setSuffix(" %")
        self._offset_spin.setDecimals(1)
        self._offset_spin.setFixedWidth(110)
        self._offset_spin.setToolTip("Offset as percentage of model size")
        
        self._offset_slider = QSlider(Qt.Orientation.Horizontal)
        self._offset_slider.setRange(-150, 150)
        self._offset_slider.setValue(0)
        self._offset_slider.setToolTip("Drag to offset streamline seed relative to model limits")


        offset_row.addWidget(self._offset_label)
        offset_row.addWidget(self._offset_spin)
        offset_row.addWidget(self._offset_slider)
        stream_vbox.addLayout(offset_row)

        self._offset_spin.valueChanged.connect(self._on_offset_spin_changed)
        self._offset_slider.valueChanged.connect(self._on_offset_slider_changed)

        # Thickness and Color
        prop_row = QHBoxLayout()
        prop_row.addWidget(QLabel("Width:"))
        self._stream_width = QSpinBox()
        self._stream_width.setRange(1, 10)
        self._stream_width.setValue(2)
        self._stream_width.setFixedWidth(80)
        self._stream_width.valueChanged.connect(self._maybe_auto_update)
        prop_row.addWidget(self._stream_width)
        
        prop_row.addSpacing(10)
        self._color_btn = QPushButton("Color")
        self._color_btn.setFixedHeight(24)
        self._color_btn.clicked.connect(self._on_choose_stream_color)
        prop_row.addWidget(self._color_btn)
        
        self._reset_color_btn = QPushButton("\u21ba") # Reset icon
        self._reset_color_btn.setToolTip("Reset to velocity colormap")
        self._reset_color_btn.setFixedHeight(24)
        self._reset_color_btn.setFixedWidth(28)
        self._reset_color_btn.clicked.connect(self._on_reset_stream_color)
        prop_row.addWidget(self._reset_color_btn)
        prop_row.addStretch()
        
        stream_vbox.addLayout(prop_row)

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

        # --- Reporting ---
        report_grp = QGroupBox("Reports")
        report_lay = QHBoxLayout()
        self._btn_report_single = QPushButton("Export Current")
        self._btn_report_bulk   = QPushButton("Export All Runs")
        self._btn_report_single.clicked.connect(self._on_export_single)
        self._btn_report_bulk.clicked.connect(self._on_export_bulk)
        report_lay.addWidget(self._btn_report_single)
        report_lay.addWidget(self._btn_report_bulk)
        report_grp.setLayout(report_lay)
        layout.addWidget(report_grp)

        self._status = QLabel("Waiting for solver…")
        layout.addWidget(self._status)
        layout.addStretch()


        # Initial axis highlight
        self.refresh_theme()

    def refresh_theme(self):
        from core.settings_manager import SettingsManager
        theme = SettingsManager.get("theme")
        
        on_style = "font-weight:bold; background:#007acc; color:white; border-radius:4px;"
        if theme == "dark":
            off_style = "font-weight:normal; background:#333; color:#aaa; border-radius:4px;"
        else:
            off_style = "font-weight:normal; background:#e1e1e1; color:#666; border-radius:4px;"
            
        self._btn_y.setStyleSheet(on_style if self._stream_axis == "Y" else off_style)
        self._btn_z.setStyleSheet(on_style if self._stream_axis == "Z" else off_style)

    def _set_axis(self, axis: str):
        self._stream_axis = axis
        self.refresh_theme()
        label = "Y offset (m):" if axis == "Y" else "Z offset (m):"
    def _on_offset_spin_changed(self, val):
        self._offset_slider.blockSignals(True)
        self._offset_slider.setValue(int(val))
        self._offset_slider.blockSignals(False)
        # We don't trigger update here to avoid too many VTK calls; 
        # the user clicks 'Show Streamlines' or we use a timer.
        if self._streamlines_active:
            self._stream_timer.start(200)

    def _on_offset_slider_changed(self, val):
        self._offset_spin.blockSignals(True)
        self._offset_spin.setValue(float(val))
        self._offset_spin.blockSignals(False)
        if self._streamlines_active:
            self._stream_timer.start(200)

    def _set_axis(self, axis: str):
        self._stream_axis = axis
        self._offset_label.setText(f"{axis} offset (%):")
        self.refresh_theme()
        if self._streamlines_active:
            self._on_show_streamlines()

    def _maybe_auto_update(self):
        if self._streamlines_active:
            # Debounce by 200ms to avoid spamming VTK
            self._stream_timer.start(200)

    # ------------------------------------------------------------------
    def refresh_runs(self):
        """Populate the run selector from current study runs."""
        if not hasattr(self._mw, "_current_study") or not self._mw._current_study:
            self._run_grp.setVisible(False)
            return
            
        runs = getattr(self._mw._current_study, "runs", [])
        if not runs:
            self._run_grp.setVisible(False)
            return
            
        self._run_combo.blockSignals(True)
        self._run_combo.clear()
        for i, run in enumerate(runs):
            cond = run.get("conditions", {})
            label = f"Run {i+1}: {cond.get('airspeed', 0)} m/s, AoA={cond.get('aoa_deg', 0)}°"
            self._run_combo.addItem(label, i)
        self._run_combo.blockSignals(False)
        
        self._run_grp.setVisible(True)

    def _on_run_selected(self, index: int):
        if index < 0: return
        runs = getattr(self._mw._current_study, "runs", [])
        if index >= len(runs): return
        
        run_data = runs[index]
        case_dir = run_data.get("case_dir")
        if case_dir:
            self.set_case_dir(case_dir)
            cond = run_data.get("conditions")
            if cond:
                self._load_aero_summary(cond)
            # Trigger a field reload if a field was already selected
            if self._load_btn.isEnabled():
                self._on_load(reset_camera=False)



    def set_case_dir(self, case_dir: str):

        self._case_dir = case_dir
        self._load_btn.setEnabled(True)
        self._domain_btn.setEnabled(False)
        self._stream_show_btn.setEnabled(True)
        self._stream_clear_btn.setEnabled(True)
        self._status.setText("Results ready — click Load.")
        log.info(f"ResultsPanel ready: {case_dir}")

    # ------------------------------------------------------------------
    def _on_load(self, reset_camera: bool = True):
        if not self._case_dir:
            return
        field = self._combo.currentData()

        # Prefer the saved conditions for the selected bulk run; fall back to
        # the live conditions panel for single-run mode.
        run_idx = self._run_combo.currentIndex()
        runs    = getattr(getattr(self._mw, "_current_study", None), "runs", [])
        if self._run_grp.isVisible() and 0 <= run_idx < len(runs):
            cond = runs[run_idx].get("conditions") or self._mw.conditions_panel.get_conditions()
        else:
            cond = self._mw.conditions_panel.get_conditions()

        log.info(f"Loading field: {field}")

        self._mw.viewport.show_results(self._case_dir, field, reset_camera=reset_camera)
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

        # Calculate absolute offset from percentage
        bounds = self._mw.viewport._aircraft_bounds
        if bounds:
            # Half-extent + some margin
            if self._stream_axis == "Y":
                half_extent = (bounds[3] - bounds[2]) * 0.5
            else:
                half_extent = (bounds[5] - bounds[4]) * 0.5
            
            # 100% means full half-extent
            abs_offset = (self._offset_spin.value() / 100.0) * half_extent
        else:
            abs_offset = 0.0

        self._stream_worker = _StreamlineWorker(
            self._case_dir,
            n,
            self._mw.viewport._aircraft_bounds,
            self._stream_axis,
            abs_offset,
        )
        self._stream_worker.ready.connect(self._on_streamlines_ready)
        self._stream_worker.failed.connect(self._on_streamlines_failed)
        self._stream_worker.start()

    def _on_streamlines_ready(self, stream):
        w = self._stream_width.value()
        self._mw.viewport.add_streamlines_mesh(stream, width=w, color=self._stream_color)
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

    def _on_choose_stream_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self._stream_color = color.name()
            self._color_btn.setStyleSheet(f"background: {self._stream_color}; color: {'white' if color.lightness() < 128 else 'black'};")
            if self._streamlines_active:
                self._on_show_streamlines()

    def _on_reset_stream_color(self):
        self._stream_color = None
        self._color_btn.setStyleSheet("")
        if self._streamlines_active:
            self._on_show_streamlines()

    # ------------------------------------------------------------------
    def _load_aero_summary(self, cond: dict):
        from core.results_reader import ResultsReader
        coeffs = ResultsReader.read_force_coeffs(self._case_dir)
        if coeffs is None:
            self._status.setText("Note: forceCoeffs not found — run solver first.")
            return

        Cl = coeffs["Cl"]
        Cd = coeffs["Cd"]
        Cm = coeffs.get("CmPitch", 0.0)
        ld = Cl / Cd if abs(Cd) > 1e-9 else float("inf")

        # Use the reference values that OpenFOAM actually used when it computed
        # the coefficients (read from the .dat header). This prevents the
        # GUI-panel Aref/rho from silently corrupting the dimensional forces.
        Aref_sim = coeffs.get("Aref_sim") or cond.get("Aref", 0.15)
        # rhoInf is not written by OF to the .dat header (returns None),
        # so fall back to the altitude-correct ISA density from the run conditions.
        rho_sim  = coeffs.get("rho_sim")  or cond.get("rho",  1.225)
        U_sim    = coeffs.get("U_sim")    or cond.get("airspeed", 1.0)

        q_sim  = 0.5 * rho_sim * U_sim ** 2
        lift_N = q_sim * Aref_sim * Cl
        drag_N = q_sim * Aref_sim * Cd

        self._lbl_cl.setText(f"{Cl:.4f}")
        self._lbl_cd.setText(f"{Cd:.4f}")
        self._lbl_ld.setText(f"{ld:.2f}" if ld != float("inf") else "\u221e")
        self._lbl_cm.setText(f"{Cm:.4f}")
        self._lbl_lift.setText(f"{lift_N:.2f} N")
        self._lbl_drag.setText(f"{drag_N:.2f} N")

        log.info(
            f"Aero summary \u2014 CL={Cl:.4f} CD={Cd:.4f} "
            f"L/D={ld:.2f} Lift={lift_N:.2f} N Drag={drag_N:.2f} N "
            f"[sim: Aref={Aref_sim} rho={rho_sim:.4f} U={U_sim}]"
        )
    def _on_export_single(self):
        from PyQt6.QtWidgets import QFileDialog
        from core.results_reader import ResultsReader
        import csv
        
        path, _ = QFileDialog.getSaveFileName(self, "Export Single Report", "aero_summary.csv", "CSV Files (*.csv)")
        if not path: return
        
        try:
            coeffs = ResultsReader.read_force_coeffs(self._case_dir)
            resid  = ResultsReader.read_residuals(self._case_dir)
            yplus  = ResultsReader.read_y_plus(self._case_dir)

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["--- AI-Ready Aerodynamic Report ---"])
                writer.writerow(["Project", self._mw._current_study.name if self._mw._current_study else "Unnamed"])
                writer.writerow(["Timestamp", Path(self._case_dir).name])
                writer.writerow([])

                writer.writerow(["[AERO COEFFICIENTS]"])
                writer.writerow(["Parameter", "Value", "Notes"])
                writer.writerow(["CL", self._lbl_cl.text(), "Lift Coefficient"])
                writer.writerow(["CD", self._lbl_cd.text(), "Drag Coefficient"])
                writer.writerow(["L/D", self._lbl_ld.text(), "Lift-to-Drag Efficiency"])
                writer.writerow(["CmPitch", self._lbl_cm.text(), "Pitching Moment"])
                writer.writerow(["Lift Force", self._lbl_lift.text()])
                writer.writerow(["Drag Force", self._lbl_drag.text()])
                if coeffs:
                    writer.writerow(["CmRoll", f"{(coeffs.get('CmRoll') or 0.0):.6f}"])
                    writer.writerow(["CmYaw", f"{(coeffs.get('CmYaw') or 0.0):.6f}"])
                    writer.writerow(["Cs", f"{(coeffs.get('Cs') or 0.0):.6f}", "Side Force Coeff"])
                writer.writerow([])

                if resid:
                    writer.writerow(["[SOLVER CONVERGENCE (RESIDUALS)]"])
                    writer.writerow(["Field", "Final Residual"])
                    for field, val in resid.items():
                        writer.writerow([field, f"{(val or 0.0):.2e}"])
                    writer.writerow([])

                if yplus:
                    writer.writerow(["[MESH QUALITY (Y+)]"])
                    writer.writerow(["Metric", "Value"])
                    writer.writerow(["Patch", yplus.get("patch")])
                    writer.writerow(["Min Y+", f"{(yplus.get('min') or 0.0):.4f}"])
                    writer.writerow(["Max Y+", f"{(yplus.get('max') or 0.0):.4f}"])
                    writer.writerow(["Average Y+", f"{(yplus.get('average') or 0.0):.4f}"])
                    writer.writerow([])

                writer.writerow(["[SIMULATION PARAMETERS]"])
                if coeffs:
                    writer.writerow(["Reference Area (Aref)", f"{(coeffs.get('Aref_sim') or 0.0):.6f}"])
                    writer.writerow(["Reference Length (lRef)", f"{(coeffs.get('lRef_sim') or 0.0):.6f}"])
                    writer.writerow(["Sim Density (rho)", f"{(coeffs.get('rho_sim') or 0.0):.6f}"])
                    writer.writerow(["Sim Velocity (U)", f"{(coeffs.get('U_sim') or 0.0):.6f}"])

            log.info(f"Enhanced report exported to {path}")
            self._status.setText(f"Exported: {Path(path).name}")
        except Exception as e:
            log.error(f"Enhanced export failed: {e}")
            self._status.setText(f"Export Error: {e}")

    def _on_export_bulk(self):
        from PyQt6.QtWidgets import QFileDialog
        import csv
        
        if not hasattr(self._mw, "_current_study") or not self._mw._current_study:
            return
            
        runs = getattr(self._mw._current_study, "runs", [])
        if not runs:
            self._status.setText("No batch results to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Export Bulk Report", "bulk_results.csv", "CSV Files (*.csv)")
        if not path: return
        
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Run", "Speed (m/s)", "AoA (deg)", "CL", "CD", "L/D", "Cm"])
                for i, run in enumerate(runs):
                    cond = run.get("conditions", {})
                    res  = run.get("results", {})
                    Cl = res.get("Cl", 0)
                    Cd = res.get("Cd", 0)
                    ld = Cl / Cd if abs(Cd) > 1e-9 else 0
                    
                    writer.writerow([
                        i+1,
                        cond.get("airspeed", 0),
                        cond.get("aoa_deg", 0),
                        f"{Cl:.4f}",
                        f"{Cd:.4f}",
                        f"{ld:.2f}",
                        f"{(res.get('CmPitch') or 0.0):.4f}"
                    ])
            log.info(f"Bulk report exported to {path}")
            self._status.setText(f"Bulk Exported: {Path(path).name}")
        except Exception as e:
            log.error(f"Bulk export failed: {e}")
