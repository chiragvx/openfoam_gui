import logging

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QProgressBar,
    QComboBox, QDoubleSpinBox,
)

import config

log = logging.getLogger(__name__)


class _MeshWorker(QThread):
    finished = pyqtSignal(bool, str, str)  # success, message, case_dir

    def __init__(self, case_dir: str, n_cores: int, mesher: str):
        super().__init__()
        self._case_dir = case_dir
        self._n_cores  = n_cores
        self._mesher   = mesher

    def run(self):
        from core.mesh_manager import MeshManager
        mgr = MeshManager(self._case_dir, config.WSL_DISTRO, self._n_cores)
        ok, msg = mgr.run(mesher=self._mesher)
        self.finished.emit(ok, msg, self._case_dir)


class MeshPanel(QWidget):
    """Tab 3 — configure snappyHexMesh or cfMesh and run the meshing pipeline."""

    def __init__(self, main_window):
        super().__init__()
        self._mw     = main_window
        self._worker: QThread | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Mesh Generation</b>"))

        # Mesher Selection
        mesher_grp = QGroupBox("Meshing Engine")
        mesher_lay = QFormLayout()
        self._mesher_combo = QComboBox()
        self._mesher_combo.addItems(["snappyHexMesh", "cfMesh (cartesianMesh)"])
        self._mesher_combo.currentIndexChanged.connect(self._on_mesher_changed)
        mesher_lay.addRow("Engine:", self._mesher_combo)
        mesher_grp.setLayout(mesher_lay)
        layout.addWidget(mesher_grp)

        # snappyHexMesh Settings
        self._snappy_grp = QGroupBox("snappyHexMesh Settings")
        form = QFormLayout()

        self._ref_min = QSpinBox()
        self._ref_min.setRange(1, 8)
        self._ref_min.setValue(config.DEFAULT_REFINEMENT_MIN)

        self._ref_max = QSpinBox()
        self._ref_max.setRange(1, 8)
        self._ref_max.setValue(config.DEFAULT_REFINEMENT_MAX)

        self._layers = QSpinBox()
        self._layers.setRange(1, 10)
        self._layers.setValue(config.DEFAULT_SURFACE_LAYERS)

        form.addRow("Refinement min:", self._ref_min)
        form.addRow("Refinement max:", self._ref_max)
        form.addRow("Surface layers:", self._layers)
        self._snappy_grp.setLayout(form)
        layout.addWidget(self._snappy_grp)

        # cfMesh Settings
        self._cfmesh_grp = QGroupBox("cfMesh Settings")
        cf_form = QFormLayout()
        
        self._cf_cell_size = QDoubleSpinBox()
        self._cf_cell_size.setRange(0.01, 10.0)
        self._cf_cell_size.setSingleStep(0.1)
        self._cf_cell_size.setValue(config.DEFAULT_CFMESH_CELL_SIZE)
        self._cf_cell_size.setSuffix(" m")
        
        cf_form.addRow("Max Cell Size:", self._cf_cell_size)
        self._cfmesh_grp.setLayout(cf_form)
        self._cfmesh_grp.setVisible(False)
        layout.addWidget(self._cfmesh_grp)

        self._run_btn = QPushButton("Run Mesh")
        self._run_btn.clicked.connect(self._on_run)
        layout.addWidget(self._run_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        layout.addWidget(self._status)
        layout.addStretch()

    def _on_mesher_changed(self, index: int):
        is_cfmesh = (index == 1)
        self._snappy_grp.setVisible(not is_cfmesh)
        self._cfmesh_grp.setVisible(is_cfmesh)

    def _on_run(self):
        geom = self._mw.get_geometry_path()
        if not geom:
            self._status.setText("No geometry loaded. Go to tab 1 first.")
            return

        settings = self.get_settings()
        mesher = settings["mesher"]

        self._mw.set_status("Generating case files…")
        try:
            from core.case_generator import CaseGenerator
            gen = CaseGenerator(geom, self._mw.get_flight_conditions(), settings)
            case_dir = gen.generate()
        except Exception as exc:
            log.error(f"Case generation failed: {exc}")
            self._status.setText(f"Case generation error: {exc}")
            return

        n_cores = self._mw.solver_panel.get_n_cores()
        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText(f"Running {mesher} pipeline…")
        self._mw.set_status(f"Meshing ({mesher})…")
        log.info(f"Mesh job started: {case_dir} using {mesher}")

        self._worker = _MeshWorker(case_dir, n_cores, mesher)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool, msg: str, case_dir: str):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        if ok:
            self._status.setText("Mesh complete.")
            self._mw.set_status("Mesh done — proceed to Solver tab")
            self._mw.solver_panel.set_case_dir(case_dir)
            log.info("Mesh generation complete")
            
            # Auto-save study if available
            main_win = self.window()
            if hasattr(main_win, "_save_study"):
                main_win._save_study()
        else:
            self._status.setText(f"FAILED: {msg}")
            self._mw.set_status("Mesh FAILED — check log")
            log.error(f"Mesh failed: {msg}")

    def get_settings(self) -> dict:
        mesher = "cfmesh" if self._mesher_combo.currentIndex() == 1 else "snappy"
        return {
            "mesher":           mesher,
            "refinement_min":   self._ref_min.value(),
            "refinement_max":   self._ref_max.value(),
            "surface_layers":   self._layers.value(),
            "cfmesh_cell_size": self._cf_cell_size.value(),
            "n_cores":          self._mw.solver_panel.get_n_cores(),
        }

    def set_settings(self, d: dict) -> None:
        if "mesher" in d:
            idx = 1 if d["mesher"] == "cfmesh" else 0
            self._mesher_combo.setCurrentIndex(idx)
            self._on_mesher_changed(idx)

        for widget, key in [
            (self._ref_min, "refinement_min"), (self._ref_max, "refinement_max"),
            (self._layers, "surface_layers"), (self._cf_cell_size, "cfmesh_cell_size"),
        ]:
            if key in d:
                widget.setValue(d[key])
