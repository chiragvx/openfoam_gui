import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QCheckBox,
)

log = logging.getLogger(__name__)


class ImportPanel(QWidget):
    """Tab 1 — import STL/OBJ, preview geometry, show mesh info."""

    def __init__(self, main_window):
        super().__init__()
        self._mw   = main_window
        self._path: str | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Import Geometry</b>"))
        layout.addWidget(QLabel("Export your model from Fusion 360 as STL or OBJ."))

        self._mm_check = QCheckBox("Scale mm → m (Fusion 360 default unit)")
        layout.addWidget(self._mm_check)

        btn = QPushButton("Open File…")
        btn.clicked.connect(self._on_open)
        layout.addWidget(btn)

        self._info_box = QGroupBox("File Info")
        self._info_box.setVisible(False)
        form = QFormLayout()
        self._lbl_name   = QLabel()
        self._lbl_bounds = QLabel()
        self._lbl_tris   = QLabel()
        form.addRow("File:",     self._lbl_name)
        form.addRow("Extents:",  self._lbl_bounds)
        form.addRow("Triangles:", self._lbl_tris)
        self._info_box.setLayout(form)
        layout.addWidget(self._info_box)

        self._orient_grp = QGroupBox("Reorient Model")
        self._orient_grp.setVisible(False)
        orient_vbox = QVBoxLayout()
        orient_vbox.addWidget(QLabel("Rotate 90° about:"))
        
        row_x = QHBoxLayout()
        btn_xp = QPushButton("X +90°"); btn_xp.clicked.connect(lambda: self._rotate("X", 90))
        btn_xm = QPushButton("X -90°"); btn_xm.clicked.connect(lambda: self._rotate("X", -90))
        row_x.addWidget(btn_xp); row_x.addWidget(btn_xm)
        
        row_y = QHBoxLayout()
        btn_yp = QPushButton("Y +90°"); btn_yp.clicked.connect(lambda: self._rotate("Y", 90))
        btn_ym = QPushButton("Y -90°"); btn_ym.clicked.connect(lambda: self._rotate("Y", -90))
        row_y.addWidget(btn_yp); row_y.addWidget(btn_ym)

        row_z = QHBoxLayout()
        btn_zp = QPushButton("Z +90°"); btn_zp.clicked.connect(lambda: self._rotate("Z", 90))
        btn_zm = QPushButton("Z -90°"); btn_zm.clicked.connect(lambda: self._rotate("Z", -90))
        row_z.addWidget(btn_zp); row_z.addWidget(btn_zm)

        orient_vbox.addLayout(row_x)
        orient_vbox.addLayout(row_y)
        orient_vbox.addLayout(row_z)
        self._orient_grp.setLayout(orient_vbox)
        layout.addWidget(self._orient_grp)

        layout.addStretch()

    def _rotate(self, axis: str, degrees: float):
        if not self._path:
            return
        self._mw.set_status(f"Rotating model {axis} {degrees}°…")
        try:
            from core.geometry import GeometryProcessor
            proc = GeometryProcessor()
            proc.rotate(self._path, axis, degrees)
            
            # Refresh info and viewport
            info = proc.get_info(self._path)
            self._lbl_bounds.setText(
                f"X {info['xmin']:.3f}–{info['xmax']:.3f} m | "
                f"Y {info['ymin']:.3f}–{info['ymax']:.3f} m | "
                f"Z {info['zmin']:.3f}–{info['zmax']:.3f} m"
            )
            self._mw.viewport.show_geometry(self._path)
            self._mw.set_status("Rotation applied")
        except Exception as exc:
            log.error(f"Rotation failed: {exc}")
            self._mw.set_status(f"Rotation error: {exc}")

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Geometry File", "",
            "Geometry Files (*.stl *.obj);;All Files (*)",
        )
        if path:
            self.load_geometry(path)

    def load_geometry(self, path: str):
        """Programmatically load geometry (used by study restore)."""
        if not path:
            return
            
        self._mw.set_status("Processing geometry…")
        try:
            from core.geometry import GeometryProcessor
            proc = GeometryProcessor()
            stl = proc.prepare(path, scale_mm_to_m=self._mm_check.isChecked())
            info = proc.get_info(stl)

            self._path = stl
            self._lbl_name.setText(Path(path).name)
            self._lbl_bounds.setText(
                f"X {info['xmin']:.3f}–{info['xmax']:.3f} m | "
                f"Y {info['ymin']:.3f}–{info['ymax']:.3f} m | "
                f"Z {info['zmin']:.3f}–{info['zmax']:.3f} m"
            )
            self._lbl_tris.setText(f"{info['triangles']:,}")
            self._info_box.setVisible(True)
            self._orient_grp.setVisible(True)

            self._mw.viewport.show_geometry(stl)
            cond = self._mw.get_flight_conditions()
            self._mw.viewport.show_wind_arrow(cond["airspeed"], cond["aoa_deg"])
            self._mw.set_status(f"Loaded: {Path(path).name}")
            log.info(f"Geometry imported: {stl}")
        except Exception as exc:
            log.error(f"Import failed: {exc}")
            self._mw.set_status(f"Import error: {exc}")

    def get_geometry_path(self) -> str | None:
        return self._path
