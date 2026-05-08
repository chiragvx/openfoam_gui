import logging
import os

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QProgressBar,
)

import config

log = logging.getLogger(__name__)


class _SolverWorker(QThread):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)
    log_line = pyqtSignal(str)

    def __init__(self, case_dir: str, n_cores: int):
        super().__init__()
        self._case_dir = case_dir
        self._n_cores  = n_cores

    def run(self):
        from core.solver_runner import SolverRunner
        import re

        # Regex for "Time = 123"
        time_regex = re.compile(r"^Time\s*=\s*(\d+)")

        def handle_line(line: str):
            self.log_line.emit(line)
            match = time_regex.search(line)
            if match:
                try:
                    self.progress.emit(int(match.group(1)))
                except ValueError:
                    pass

        runner = SolverRunner(self._case_dir, config.WSL_DISTRO, self._n_cores)
        ok, msg = runner.run(on_line=handle_line)
        self.finished.emit(ok, msg)


class SolverPanel(QWidget):
    """Tab 4 — configure and run simpleFoam."""

    def __init__(self, main_window):
        super().__init__()
        self._mw       = main_window
        self._case_dir: str | None = None
        self._worker: _SolverWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Solver</b> — simpleFoam (steady RANS)"))

        grp  = QGroupBox("Settings")
        form = QFormLayout()

        self._iters = QSpinBox()
        self._iters.setRange(100, 5000)
        self._iters.setValue(500)
        self._iters.setSingleStep(100)
        form.addRow("Iterations:", self._iters)

        self._cores = QSpinBox()
        self._cores.setRange(1, os.cpu_count() or 1)
        self._cores.setValue(config.DEFAULT_CORES)
        self._cores.setToolTip("CPU cores for parallel mesh + solve (uses MPI)")
        form.addRow(f"CPU cores (max {os.cpu_count()}):", self._cores)

        grp.setLayout(form)
        layout.addWidget(grp)

        self._run_btn = QPushButton("Run Solver")
        self._run_btn.setEnabled(False)
        self._run_btn.clicked.connect(self._on_run)
        layout.addWidget(self._run_btn)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("Waiting for mesh…")
        layout.addWidget(self._status)
        layout.addStretch()

    def get_n_cores(self) -> int:
        return self._cores.value()

    def set_case_dir(self, case_dir: str):
        self._case_dir = case_dir
        self._run_btn.setEnabled(True)
        self._status.setText(f"Ready — {case_dir}")

    def _on_run(self):
        if not self._case_dir:
            return
        self._patch_end_time()

        max_iters = self._iters.value()
        n_cores = self._cores.value()
        
        self._run_btn.setEnabled(False)
        self._progress.setRange(0, max_iters)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._status.setText(f"Initialising solver…")
        self._mw.set_status(f"Solver running ({n_cores} core(s))…")
        log.info(f"Solver started in {self._case_dir} using {n_cores} core(s)")

        self._worker = _SolverWorker(self._case_dir, n_cores)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._on_log_line)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_progress(self, val: int):
        self._progress.setValue(val)
        self._status.setText(f"Solving: iteration {val} of {self._iters.value()}")

    def _on_log_line(self, line: str):
        # We could also pipe this to the main window log, but it's already logged by WSLRunner
        pass

    def _patch_end_time(self):
        """Update endTime in controlDict to match the UI spinbox."""
        from pathlib import Path
        import re
        ctrl = Path(self._case_dir) / "system" / "controlDict"
        if not ctrl.exists():
            return
        text = ctrl.read_text(encoding="utf-8")
        text = re.sub(r"(endTime\s+)\d+", rf"\g<1>{self._iters.value()}", text)
        ctrl.write_text(text, encoding="utf-8")
        log.debug(f"controlDict endTime patched to {self._iters.value()}")

    def _on_done(self, ok: bool, msg: str):
        self._run_btn.setEnabled(True)
        self._progress.setVisible(False)
        if ok:
            self._status.setText("Solver complete — load results →")
            self._mw.set_status("Solver done — go to Results tab")
            self._mw.results_panel.set_case_dir(self._case_dir)
            log.info("Solver complete")
            
            # Auto-save study if available
            main_win = self.window()
            if hasattr(main_win, "_save_study"):
                if hasattr(main_win, "_current_study") and main_win._current_study:
                    try:
                        from core.results_reader import ResultsReader
                        coeffs = ResultsReader.read_force_coeffs(self._case_dir)
                        main_win._current_study.results = {**coeffs, "solved": True}
                        main_win._current_study.case_dir = self._case_dir
                    except Exception:
                        pass
                main_win._save_study()
        else:
            self._status.setText(f"FAILED: {msg}")
            self._mw.set_status("Solver FAILED — check log")
            log.error(f"Solver failed: {msg}")

    def set_settings(self, d: dict) -> None:
        if "end_time" in d:
            self._iters.setValue(d["end_time"])
        if "n_cores" in d:
            self._cores.setValue(d["n_cores"])
