import logging
import os
import config

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTabWidget, QSplitter, QStatusBar,
    QDialog, QFileDialog, QLabel,
)
from PyQt6.QtGui import QAction, QKeySequence, QIcon, QPixmap

from core.study_manager import StudyManager, Study
from pathlib import Path

from gui.import_panel     import ImportPanel
from gui.conditions_panel import ConditionsPanel
from gui.mesh_panel       import MeshPanel
from gui.solver_panel     import SolverPanel
from gui.results_panel    import ResultsPanel
from gui.bulk_testing_panel import BulkTestingPanel

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
        self.setWindowIcon(QIcon("logo.png"))
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

        # Left: workflow tabs container
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(15)

        # Logo/Brand header
        brand_container = QWidget()
        brand_layout = QHBoxLayout(brand_container)
        brand_layout.setContentsMargins(5, 5, 5, 5)
        
        logo_label = QLabel()
        logo_pixmap = QPixmap("logo.png").scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        brand_layout.addWidget(logo_label)

        brand_text = QLabel("REKON LABS")
        brand_text.setStyleSheet("font-weight: 900; font-size: 14pt; letter-spacing: 2px; color: #409eff;")
        brand_layout.addWidget(brand_text)
        brand_layout.addStretch()
        
        left_layout.addWidget(brand_container)

        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(300)
        left_layout.addWidget(self.tabs)

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
        self.bulk_panel       = BulkTestingPanel(self)


        self.tabs.addTab(self.import_panel,      "1. Import")
        self.tabs.addTab(self.conditions_panel,  "2. Conditions")
        self.tabs.addTab(self.mesh_panel,        "3. Mesh")
        self.tabs.addTab(self.solver_panel,      "4. Solver")
        self.tabs.addTab(self.results_panel,     "5. Results")
        self.tabs.addTab(self.bulk_panel,        "6. Bulk Testing")

        
        central.addWidget(left_panel)
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

        import_act = QAction("&Import Study… (.zip)", self)
        import_act.triggered.connect(self._import_study)
        file_menu.addAction(import_act)


        save_act = QAction("&Save Study", self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._save_study)
        file_menu.addAction(save_act)

        save_as_act = QAction("Save Study &As…", self)
        save_as_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_act.triggered.connect(self._save_study_as)
        file_menu.addAction(save_as_act)

        export_act = QAction("&Export Study… (.zip)", self)
        export_act.triggered.connect(self._export_study)
        file_menu.addAction(export_act)

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
            
        self.results_panel.refresh_runs()
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

    def _save_study_as(self):
        if self._current_study is None:
            self._new_study()
            return

        from gui.study_dialog import NewStudyDialog
        dlg = NewStudyDialog(self)
        dlg.setWindowTitle("Save Study As")
        dlg._name.setText(f"{self._current_study.name} (Copy)")
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            import copy
            # Create a shallow copy and reset identity
            s = self._current_study
            new_study = Study(
                name=dlg.name,
                description=dlg.description,
                geometry_path=s.geometry_path,
                conditions=copy.deepcopy(s.conditions),
                mesh_settings=copy.deepcopy(s.mesh_settings),
                solver_settings=copy.deepcopy(s.solver_settings),
                ui_state=copy.deepcopy(s.ui_state)
            )
            # We explicitly DON'T copy case_dir, results, or runs 
            # to keep the duplicate clean for a new simulation branch.
            
            StudyManager.save(new_study)
            self._apply_study(new_study)
            self.set_status(f"Project duplicated as: {new_study.name}")

    def _export_study(self):
        if self._current_study is None:
            self.set_status("Error: No active study to export.")
            return

        from PyQt6.QtWidgets import QFileDialog, QProgressDialog
        import zipfile
        import shutil

        s = self._current_study
        default_name = f"{s.study_id}_export.zip"
        path, _ = QFileDialog.getSaveFileName(self, "Export Whole Study", default_name, "ZIP Archives (*.zip)")
        if not path: return

        self.set_status("Exporting study... this may take a while")
        
        # Collect files to include
        files_to_add = []
        
        # 1. Study JSON
        json_path = StudyManager.get_path(s.study_id)
        if json_path.exists():
            files_to_add.append((json_path, "study.json"))
            
        # 2. Geometry
        if s.geometry_path and Path(s.geometry_path).exists():
            geom_path = Path(s.geometry_path)
            files_to_add.append((geom_path, f"geometry/{geom_path.name}"))
            
        # 3. Case directories
        dirs_to_add = []
        if s.case_dir and Path(s.case_dir).exists():
            dirs_to_add.append((Path(s.case_dir), f"results/main_run"))
            
        for i, run in enumerate(getattr(s, "runs", [])):
            rd = run.get("case_dir")
            if rd and Path(rd).exists():
                dirs_to_add.append((Path(rd), f"results/run_{i+1}"))

        # Create ZIP
        try:
            progress = QProgressDialog("Archiving study files...", "Cancel", 0, len(files_to_add) + len(dirs_to_add), self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()
            
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                idx = 0
                # Add single files
                for src, arcname in files_to_add:
                    if progress.wasCanceled(): break
                    zipf.write(src, arcname)
                    idx += 1
                    progress.setValue(idx)
                    
                # Add directories
                for src_dir, arcbase in dirs_to_add:
                    if progress.wasCanceled(): break
                    for root, dirs, files in os.walk(src_dir):
                        if progress.wasCanceled(): break
                        for file in files:
                            file_path = Path(root) / file
                            # Skip large processor directories or huge logs if needed? 
                            # User said "whole study", so we include everything.
                            rel_path = file_path.relative_to(src_dir)
                            zipf.write(file_path, Path(arcbase) / rel_path)
                    idx += 1
                    progress.setValue(idx)
            
            if not progress.wasCanceled():
                self.set_status(f"Study exported successfully to {Path(path).name}")
                log.info(f"Study {s.study_id} exported to {path}")
            else:
                self.set_status("Export cancelled.")
        except Exception as e:
            self.set_status(f"Export failed: {e}")
            log.error(f"Export failed: {e}")

    def _import_study(self):
        from PyQt6.QtWidgets import QFileDialog, QProgressDialog
        import zipfile
        import shutil
        import json
        import time

        path, _ = QFileDialog.getOpenFileName(self, "Import Study ZIP", "", "ZIP Archives (*.zip)")
        if not path: return

        temp_dir = config.APP_DIR / "temp_import"
        if temp_dir.exists(): shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)

        try:
            self.set_status("Extracting study...")
            with zipfile.ZipFile(path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            json_file = temp_dir / "study.json"
            if not json_file.exists():
                self.set_status("Error: Invalid study ZIP (missing study.json)")
                return
                
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update study ID to avoid collision if importing same study twice
            # Actually, let's keep it but ensure we don't overwrite if name exists
            ts = int(time.time())
            data["study_id"] = f"{data.get('study_id', 'imported')}_{ts}"
            data["name"] = f"{data.get('name', 'Imported')} (Copy)"
            
            # --- Remap Geometry ---
            geom_dir = temp_dir / "geometry"
            if geom_dir.exists():
                stl_files = list(geom_dir.glob("*.*"))
                if stl_files:
                    dest_geom = config.CASES_DIR / "geometry" / stl_files[0].name
                    dest_geom.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(stl_files[0], dest_geom)
                    data["geometry_path"] = str(dest_geom)
            
            # --- Remap Results ---
            results_dir = temp_dir / "results"
            if results_dir.exists():
                # Main run
                main_run_src = results_dir / "main_run"
                if main_run_src.exists():
                    dest_main = config.CASES_DIR / f"run_{ts}_main"
                    shutil.move(str(main_run_src), str(dest_main))
                    data["case_dir"] = str(dest_main)
                    
                # Batch runs
                runs = data.get("runs", [])
                for i, run in enumerate(runs):
                    run_src = results_dir / f"run_{i+1}"
                    if run_src.exists():
                        dest_run = config.CASES_DIR / f"run_{ts}_batch_{i+1}"
                        shutil.move(str(run_src), str(dest_run))
                        run["case_dir"] = str(dest_run)
            
            # Save new study JSON
            new_study = Study(**data)
            StudyManager.save(new_study)
            
            self._apply_study(new_study)
            self.set_status(f"Study imported and loaded: {new_study.name}")
            
        except Exception as e:
            self.set_status(f"Import failed: {e}")
            log.error(f"Import failed: {e}")
        finally:
            if temp_dir.exists(): shutil.rmtree(temp_dir)



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






