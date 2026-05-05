import logging

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QProgressBar,
)

import config

log = logging.getLogger(__name__)


class _MeshWorker(QThread):
    finished = pyqtSignal(bool, str, str)  # success, message, case_dir

    def __init__(self, case_dir: str, n_cores: int):
        super().__init__()
        self._case_dir = case_dir
        self._n_cores  = n_cores

    def run(self):
        from core.mesh_manager import MeshManager
        mgr = MeshManager(self._case_dir, config.WSL_DISTRO, self._n_cores)
        ok, msg = mgr.run()
        self.finished.emit(ok, msg, self._case_dir)


class MeshPanel(QWidget):
    """Tab 3 — configure snappyHexMesh and run the meshing pipeline."""

    def __init__(self, main_window):
        super().__init__()
        self._mw     = main_window
        self._worker: QThread | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Mesh Generation</b>"))

        grp  = QGroupBox("snappyHexMesh Settings")
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
        grp.setLayout(form)
        layout.addWidget(grp)

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

    def _on_run(self):
        geom = self._mw.get_geometry_path()
        if not geom:
            self._status.setText("No geometry loaded. Go to tab 1 first.")
            return

        self._mw.set_status("Generating case files…")
        try:
            from core.case_generator import CaseGenerator
            gen = CaseGenerator(geom, self._mw.get_flight_conditions(), self.get_settings())
            case_dir = gen.generate()
        except Exception as exc:
            log.error(f"Case generation failed: {exc}")
            self._status.setText(f"Case generation error: {exc}")
            return

        n_cores = self._mw.solver_panel.get_n_cores()
        self._run_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._status.setText(f"Running meshing pipeline ({n_cores} core(s))…")
        self._mw.set_status(f"Meshing ({n_cores} core(s))…")
        log.info(f"Mesh job started: {case_dir} ({n_cores} core(s))")

        self._worker = _MeshWorker(case_dir, n_cores)
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
        else:
            self._status.setText(f"FAILED: {msg}")
            self._mw.set_status("Mesh FAILED — check log")
            log.error(f"Mesh failed: {msg}")

    def get_settings(self) -> dict:
        return {
            "refinement_min": self._ref_min.value(),
            "refinement_max": self._ref_max.value(),
            "surface_layers": self._layers.value(),
            "n_cores":        self._mw.solver_panel.get_n_cores(),
        }
