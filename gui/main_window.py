import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout,
    QTabWidget, QSplitter, QStatusBar,
)

from gui.import_panel     import ImportPanel
from gui.conditions_panel import ConditionsPanel
from gui.mesh_panel       import MeshPanel
from gui.solver_panel     import SolverPanel
from gui.results_panel    import ResultsPanel
from gui.log_widget       import LogWidget
from gui.viewport_widget  import ViewportWidget

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main window layout:

        ┌──────────────────────────────────────────┐
        │  Tabs (380px)   │  ViewportWidget        │
        │  1. Import       ├──────────────────────  │
        │  2. Conditions   │  LogWidget (200px)     │
        │  3. Mesh         │                        │
        │  4. Solver       │                        │
        │  5. Results      │                        │
        └──────────────────────────────────────────┘
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenFOAM RC CFD")
        self.resize(1400, 900)
        self._build_ui()
        self._validate_wsl()
        log.info("OpenFOAM RC CFD GUI ready")

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Left: workflow tabs
        self.tabs = QTabWidget()
        self.tabs.setFixedWidth(390)

        self.import_panel     = ImportPanel(self)
        self.conditions_panel = ConditionsPanel(self)
        self.mesh_panel       = MeshPanel(self)
        self.solver_panel     = SolverPanel(self)
        self.results_panel    = ResultsPanel(self)

        self.tabs.addTab(self.import_panel,      "1. Import")
        self.tabs.addTab(self.conditions_panel,  "2. Conditions")
        self.tabs.addTab(self.mesh_panel,        "3. Mesh")
        self.tabs.addTab(self.solver_panel,      "4. Solver")
        self.tabs.addTab(self.results_panel,     "5. Results")
        root.addWidget(self.tabs)

        # Right: viewport + log splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.viewport   = ViewportWidget(self)
        self.log_widget = LogWidget(self)

        splitter.addWidget(self.viewport)
        splitter.addWidget(self.log_widget)
        splitter.setSizes([650, 200])
        root.addWidget(splitter, stretch=1)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    # ------------------------------------------------------------------
    def _validate_wsl(self):
        from core.wsl_runner import WSLRunner
        runner = WSLRunner()
        ok, msg = runner.validate_wsl()
        if ok:
            log.info(msg)
            self.set_status(msg)
        else:
            log.warning(f"WSL check: {msg}")
            self.set_status(f"WARNING: {msg}")

    # ------------------------------------------------------------------
    # Cross-panel accessors
    def get_geometry_path(self) -> str | None:
        return self.import_panel.get_geometry_path()

    def get_flight_conditions(self) -> dict:
        return self.conditions_panel.get_conditions()

    def get_mesh_settings(self) -> dict:
        return self.mesh_panel.get_settings()

    def set_status(self, message: str):
        self._status_bar.showMessage(message)
