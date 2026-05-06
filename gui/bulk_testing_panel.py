import logging
import os
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar
)

from core.batch_manager import BatchManager, SweepCondition
from core.case_generator import CaseGenerator
from core.mesh_manager import MeshManager
from core.solver_runner import SolverRunner
from core.results_reader import ResultsReader
import config

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


log = logging.getLogger(__name__)

class _BatchWorker(QThread):
    progress = pyqtSignal(int, int) # current, total
    log_msg = pyqtSignal(str)
    run_complete = pyqtSignal(int, dict) # index, results
    finished = pyqtSignal(bool, str)

    def __init__(self, stl_path, mesh_settings, solver_settings, conditions):
        super().__init__()
        self._stl_path = stl_path
        self._mesh_settings = mesh_settings
        self._solver_settings = solver_settings
        self._conditions = conditions
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        total = len(self._conditions)
        for i, cond in enumerate(self._conditions):
            if not self._is_running:
                self.finished.emit(False, "Cancelled by user")
                return

            self.progress.emit(i + 1, total)
            run_name = BatchManager.get_run_name(i, cond)
            self.log_msg.emit(f"Starting {run_name}: Speed={cond.airspeed}, AoA={cond.aoa_deg}")

            try:
                # 1. Update conditions for this run
                # We need to re-calculate rho, nu, etc. based on airspeed/AoA
                # For now, let's assume we use a helper to get full condition dict
                full_cond = self._build_full_conditions(cond)
                
                # 2. Generate Case
                gen = CaseGenerator(self._stl_path, full_cond, self._mesh_settings)
                case_dir = gen.generate(custom_folder=run_name)
                
                # 3. Generate Mesh
                self.log_msg.emit(f"Generating mesh for {run_name}...")
                mesher = MeshManager(case_dir, config.WSL_DISTRO, self._mesh_settings.get("n_cores", 1))
                m_ok, m_msg = mesher.run()
                if not m_ok:
                    self.log_msg.emit(f"Mesh failed for {run_name}: {m_msg}")
                    continue

                # 4. Patch end time (solver iterations)
                self._patch_end_time(case_dir, self._solver_settings.get("end_time", 500))

                # 5. Run Solver
                self.log_msg.emit(f"Running solver for {run_name}...")
                runner = SolverRunner(case_dir, config.WSL_DISTRO, self._mesh_settings.get("n_cores", 1))
                ok, msg = runner.run()
                
                if ok:
                    # 6. Extract Results

                    coeffs = ResultsReader.read_force_coeffs(case_dir)
                    results = {
                        "case_dir": case_dir,
                        "conditions": full_cond,
                        "results": {**coeffs, "solved": True}
                    }
                    self.run_complete.emit(i, results)
                    self.log_msg.emit(f"Completed {run_name}")
                else:
                    self.log_msg.emit(f"Error in {run_name}: {msg}")
                    # We continue with next run even if one fails
            except Exception as e:
                self.log_msg.emit(f"Exception in {run_name}: {e}")

        self.finished.emit(True, "All runs complete")

    def _build_full_conditions(self, cond: SweepCondition) -> dict:
        # Minimal clone of core logic to get vector components
        from core.atmosphere import ISAAtmosphere
        from core.unit_converter import UnitConverter
        
        # We'll use sea level for sweep for now, or inherit from current panel
        alt = 0.0 
        isa = ISAAtmosphere(alt)
        speed = cond.airspeed
        aoa_rad = math.radians(cond.aoa_deg)
        
        return {
            "airspeed": speed,
            "aoa_deg": cond.aoa_deg,
            "altitude": alt,
            "rho": isa.density,
            "nu": isa.kinematic_viscosity,
            "mu": isa.dynamic_viscosity,
            "speed_of_sound": isa.speed_of_sound,
            "Ux": round(speed * math.cos(aoa_rad), 4),
            "Uy": 0.0,
            "Uz": round(speed * math.sin(aoa_rad), 4),
            "lRef": 0.25, # Default reference values
            "Aref": 0.15
        }

    def _patch_end_time(self, case_dir: str, iters: int):
        import re
        ctrl = Path(case_dir) / "system" / "controlDict"
        if not ctrl.exists(): return
        text = ctrl.read_text(encoding="utf-8")
        text = re.sub(r"(endTime\s+)\d+", rf"\g<1>{iters}", text)
        ctrl.write_text(text, encoding="utf-8")

import math

class BulkTestingPanel(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self._mw = main_window
        self._conditions = []
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Parametric Sweep / Bulk Testing</b>"))
        layout.addWidget(QLabel("Run multiple simulations across ranges of Speed and AoA."))

        # --- Speed Range ---
        spd_grp = QGroupBox("Airspeed Range (m/s)")
        spd_lay = QFormLayout()
        self._spd_min = QDoubleSpinBox(); self._spd_min.setRange(1, 500); self._spd_min.setValue(20)
        self._spd_max = QDoubleSpinBox(); self._spd_max.setRange(1, 500); self._spd_max.setValue(40)
        self._spd_step = QDoubleSpinBox(); self._spd_step.setRange(0, 100); self._spd_step.setValue(10)
        spd_lay.addRow("Min Speed:", self._spd_min)
        spd_lay.addRow("Max Speed:", self._spd_max)
        spd_lay.addRow("Step:", self._spd_step)
        spd_grp.setLayout(spd_lay)
        layout.addWidget(spd_grp)

        # --- AoA Range ---
        aoa_grp = QGroupBox("AoA Range (deg)")
        aoa_lay = QFormLayout()
        self._aoa_min = QDoubleSpinBox(); self._aoa_min.setRange(-90, 90); self._aoa_min.setValue(0)
        self._aoa_max = QDoubleSpinBox(); self._aoa_max.setRange(-90, 90); self._aoa_max.setValue(10)
        self._aoa_step = QDoubleSpinBox(); self._aoa_step.setRange(0, 90); self._aoa_step.setValue(5)
        aoa_lay.addRow("Min AoA:", self._aoa_min)
        aoa_lay.addRow("Max AoA:", self._aoa_max)
        aoa_lay.addRow("Step:", self._aoa_step)
        aoa_grp.setLayout(aoa_lay)
        layout.addWidget(aoa_grp)

        # --- Summary ---
        self._btn_gen = QPushButton("Update Run List")
        self._btn_gen.clicked.connect(self._update_list)
        layout.addWidget(self._btn_gen)

        # Plot area
        self._fig = Figure(figsize=(4, 3), dpi=100)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setFixedHeight(200)
        layout.addWidget(self._canvas)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Run", "Speed", "AoA", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.itemDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self._table)


        self._btn_run = QPushButton("Start Bulk Testing")
        self._btn_run.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
        self._btn_run.clicked.connect(self._on_start)
        layout.addWidget(self._btn_run)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("Ready")
        layout.addWidget(self._status)
        layout.addStretch()

    def _update_list(self):
        s_range = (self._spd_min.value(), self._spd_max.value(), self._spd_step.value())
        a_range = (self._aoa_min.value(), self._aoa_max.value(), self._aoa_step.value())
        self._conditions = BatchManager.generate_grid(s_range, a_range)
        
        self._table.setRowCount(len(self._conditions))
        for i, cond in enumerate(self._conditions):
            self._table.setItem(i, 0, QTableWidgetItem(f"Run {i+1}"))
            self._table.setItem(i, 1, QTableWidgetItem(f"{cond.airspeed} m/s"))
            self._table.setItem(i, 2, QTableWidgetItem(f"{cond.aoa_deg} deg"))
            self._table.setItem(i, 3, QTableWidgetItem("Waiting..."))
        
        self._status.setText(f"Total Runs: {len(self._conditions)}")
        self._update_plot()

    def _update_plot(self):
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        speeds = [c.airspeed for c in self._conditions]
        aoas = [c.aoa_deg for c in self._conditions]
        ax.scatter(speeds, aoas, color="#007acc", s=20)
        ax.set_xlabel("Speed (m/s)")
        ax.set_ylabel("AoA (deg)")
        ax.grid(True, linestyle="--", alpha=0.5)
        self._fig.tight_layout()
        self._canvas.draw()

    def _on_row_double_clicked(self, item):
        row = item.row()
        if hasattr(self._mw, "_current_study") and self._mw._current_study:
            runs = getattr(self._mw._current_study, "runs", [])
            if row < len(runs):
                self._mw.tabs.setCurrentIndex(4) # Switch to Results tab
                self._mw.results_panel._run_combo.setCurrentIndex(row)


    def _on_start(self):
        if not self._conditions:
            self._update_list()
        if not self._conditions:
            return

        # Check if we have geometry
        stl_path = self._mw.import_panel._path
        if not stl_path:
            self._status.setText("Error: No geometry imported!")
            return

        self._btn_run.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(self._conditions))
        self._progress.setValue(0)

        # Gather settings
        mesh_settings = {
            "refinement_min": self._mw.mesh_panel._ref_min.value(),
            "refinement_max": self._mw.mesh_panel._ref_max.value(),
            "surface_layers": self._mw.mesh_panel._layers.value(),
            "n_cores": self._mw.solver_panel.get_n_cores(),
            "end_time": self._mw.solver_panel._iters.value()
        }

        solver_settings = {
            "end_time": self._mw.solver_panel._iters.value()
        }

        self._worker = _BatchWorker(stl_path, mesh_settings, solver_settings, self._conditions)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_msg.connect(lambda msg: log.info(f"[Batch] {msg}"))
        self._worker.run_complete.connect(self._on_run_complete)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, current, total):
        self._progress.setValue(current)
        row = current - 1
        if row >= 0:
            self._table.setItem(row, 3, QTableWidgetItem("Running..."))
            self._table.scrollToItem(self._table.item(row, 0))

    def _on_run_complete(self, index, data):
        self._table.setItem(index, 3, QTableWidgetItem("✅ Complete"))
        # Store results in the main study

        if hasattr(self._mw, "_current_study") and self._mw._current_study:
            study = self._mw._current_study
            if not hasattr(study, "runs") or study.runs is None:
                study.runs = []
            
            # If the study already has this run (e.g., restart), update it
            if index < len(study.runs):
                study.runs[index] = data
            else:
                study.runs.append(data)
            
            # Save progress after each run
            from core.study_manager import StudyManager
            StudyManager.save(study)
            
            # Update results UI if it's visible
            self._mw.results_panel.refresh_runs()


    def _on_finished(self, ok, msg):
        self._btn_run.setEnabled(True)
        self._progress.setVisible(False)
        self._status.setText(msg)
        if ok:
            self._mw.results_panel.refresh_runs()
