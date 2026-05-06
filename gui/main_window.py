import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout,
    QTabWidget, QSplitter, QStatusBar,
    QDialog, QFileDialog,
)
from PyQt6.QtGui import QAction, QKeySequence

from core.study_manager import StudyManager, Study
from pathlib import Path

from gui.import_panel     import ImportPanel
from gui.conditions_panel import ConditionsPanel
from gui.mesh_panel       import MeshPanel
from gui.solver_panel     import SolverPanel
from gui.results_panel    import ResultsPanel
from gui.log_widget       import LogWidget
from gui.viewport_widget  import ViewportWidget
from gui.theme_manager    import ThemeManager
from core.settings_manager import SettingsManager
from gui.settings_dialog  import SettingsDialog

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
        self.setWindowTitle("Rekon labs CFD")
        self.resize(1400, 900)
        self._current_study: Study | None = None
        self._apply_initial_theme()
        self._build_ui()
        self._validate_wsl()
        log.info("Rekon labs CFD ready")
        QTimer.singleShot(200, self._show_startup_dialog)

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(central)
        central.setHandleWidth(6)
        central.setChildrenCollapsible(False)

        # Left: workflow tabs
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(300)

        # Right: viewport + log splitter
        vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.viewport   = ViewportWidget(self)
        self.log_widget = LogWidget(self)
        vertical_splitter.addWidget(self.viewport)
        vertical_splitter.addWidget(self.log_widget)
        vertical_splitter.setSizes([650, 200])
        vertical_splitter.setHandleWidth(6)
        vertical_splitter.setChildrenCollapsible(False)

        self.import_panel     = ImportPanel(self)
        self.conditions_panel = ConditionsPanel(self, viewport=self.viewport)
        self.mesh_panel       = MeshPanel(self)
        self.solver_panel     = SolverPanel(self)
        self.results_panel    = ResultsPanel(self)

        self.tabs.addTab(self.import_panel,      "1. Import")
        self.tabs.addTab(self.conditions_panel,  "2. Conditions")
        self.tabs.addTab(self.mesh_panel,        "3. Mesh")
        self.tabs.addTab(self.solver_panel,      "4. Solver")
        self.tabs.addTab(self.results_panel,     "5. Results")
        
        central.addWidget(self.tabs)
        central.addWidget(vertical_splitter)
        central.setSizes([390, 1010])

        self._build_menu()

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

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        new_act = QAction("&New Study…", self)
        new_act.setShortcut(QKeySequence.StandardKey.New)
        new_act.triggered.connect(self._new_study)
        file_menu.addAction(new_act)

        load_act = QAction("&Load Study…", self)
        load_act.setShortcut(QKeySequence.StandardKey.Open)
        load_act.triggered.connect(self._load_study)
        file_menu.addAction(load_act)

        save_act = QAction("&Save Study", self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._save_study)
        file_menu.addAction(save_act)
        file_menu.addSeparator()
        exit_act = QAction("E&xit", self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        options_menu = menubar.addMenu("&Options")
        settings_act = QAction("&Settings…", self)
        settings_act.triggered.connect(self._open_settings)
        options_menu.addAction(settings_act)


    def _show_startup_dialog(self):
        from gui.study_dialog import StudyStartupDialog
        dlg = StudyStartupDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.chosen == "new":
                self._new_study()
            elif dlg.chosen == "load":
                self._load_study()

    def _new_study(self):
        from gui.study_dialog import NewStudyDialog
        dlg = NewStudyDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._current_study = Study(name=dlg.name, description=dlg.description)
            StudyManager.save(self._current_study)
            self.setWindowTitle(f"Rekon labs CFD — {self._current_study.name}")
            self.set_status(f"New study created: {self._current_study.name}")

    def _load_study(self):
        from gui.study_dialog import LoadStudyDialog
        dlg = LoadStudyDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.selected_study:
                self._apply_study(dlg.selected_study)

    def _apply_study(self, study: Study):
        self._current_study = study
        self.setWindowTitle(f"Rekon labs CFD — {study.name}")
        
        # Restore panel states
        if study.conditions:
            self.conditions_panel.set_conditions(study.conditions)
        if study.mesh_settings:
            self.mesh_panel.set_settings(study.mesh_settings)
        if study.solver_settings:
            self.solver_panel.set_settings(study.solver_settings)
            
        # Restore geometry if path exists
        if study.geometry_path and Path(study.geometry_path).exists():
            self.import_panel.load_geometry(study.geometry_path)
            
        # Restore case dir for solver/results
        if study.case_dir and Path(study.case_dir).exists():
            self.solver_panel.set_case_dir(study.case_dir)
            self.results_panel.set_case_dir(study.case_dir)
            
        self.set_status(f"Loaded study: {study.name}")

    def _save_study(self):
        if self._current_study is None:
            # If no study active, offer to create one or just skip (if we want auto-anonymous)
            # For now, let's trigger "New Study"
            self._new_study()
            if self._current_study is None:
                return

        s = self._current_study
        s.conditions = self.conditions_panel.get_conditions()
        s.mesh_settings = self.mesh_panel.get_settings()
        s.solver_settings = {
            "end_time": self.solver_panel._iters.value(),
            "n_cores": self.solver_panel.get_n_cores()
        }
        
        geom = self.import_panel.get_geometry_path()
        if geom:
            s.geometry_path = geom
            
        StudyManager.save(s)
        self.set_status(f"Study saved: {s.name}")

    def _apply_initial_theme(self):
        theme = SettingsManager.get("theme")
        ThemeManager.apply_theme(theme)

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.set_status("Settings updated")
            # Refresh panels that display units
            if hasattr(self, "conditions_panel"):
                self.conditions_panel.refresh_units()
                self.conditions_panel.refresh_theme()

            if hasattr(self, "import_panel"):
                self.import_panel.refresh_units()
            if hasattr(self, "viewport"):
                self.viewport.refresh_theme()
                self.viewport.refresh_units()
            if hasattr(self, "log_widget"):
                self.log_widget.refresh_theme()
            if hasattr(self, "results_panel"):
                self.results_panel.refresh_theme()






