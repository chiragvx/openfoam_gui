import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QGroupBox, QFormLayout, QCheckBox, QDoubleSpinBox,
    QColorDialog,
)

log = logging.getLogger(__name__)

from core.settings_manager import SettingsManager
from core.unit_converter   import UnitConverter


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

        self._mm_check = QCheckBox("Scale mm \u2192 m (Fusion 360 default unit)")
        layout.addWidget(self._mm_check)

        btn = QPushButton("Open File\u2026")
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

        self._orient_grp = QGroupBox("Adjust Geometry")
        self._orient_grp.setVisible(False)
        adjust_lay = QFormLayout()

        self._rot_x = QDoubleSpinBox(); self._rot_x.setRange(-360, 360); self._rot_x.setSuffix("\u00b0")
        self._rot_y = QDoubleSpinBox(); self._rot_y.setRange(-360, 360); self._rot_y.setSuffix("\u00b0")
        self._rot_z = QDoubleSpinBox(); self._rot_z.setRange(-360, 360); self._rot_z.setSuffix("\u00b0")
        
        rot_btn = QPushButton("Apply Rotations")
        rot_btn.clicked.connect(self._on_apply_rotations)
        
        adjust_lay.addRow("Rotate X:", self._rot_x)
        adjust_lay.addRow("Rotate Y:", self._rot_y)
        adjust_lay.addRow("Rotate Z:", self._rot_z)
        adjust_lay.addRow("", rot_btn)
        
        # Simple spacer
        adjust_lay.addRow(QLabel(""))
        
        self._scale_val = QDoubleSpinBox()
        self._scale_val.setRange(0.0001, 10000.0)
        self._scale_val.setValue(1.0)
        self._scale_val.setSingleStep(0.1)
        self._scale_val.setDecimals(4)
        
        scale_btn = QPushButton("Apply Scale")
        scale_btn.clicked.connect(self._on_apply_scale)
        
        adjust_lay.addRow("Scale Factor:", self._scale_val)
        adjust_lay.addRow("", scale_btn)

        self._orient_grp.setLayout(adjust_lay)
        layout.addWidget(self._orient_grp)

        # Model Appearance
        app_grp = QGroupBox("Model Appearance")
        app_lay = QHBoxLayout()
        app_lay.addWidget(QLabel("Surface Color:"))
        self._color_btn = QPushButton("Select Color")
        self._color_btn.clicked.connect(self._on_choose_model_color)
        app_lay.addWidget(self._color_btn)
        app_lay.addStretch()
        app_grp.setLayout(app_lay)
        layout.addWidget(app_grp)

        layout.addStretch()
        self.refresh_units()

    def refresh_units(self):
        if not self._path:
            return
        # Refresh the bounds label
        try:
            from core.geometry import GeometryProcessor
            proc = GeometryProcessor()
            info = proc.get_info(self._path)
            u = SettingsManager.get("units")
            self._lbl_bounds.setText(
                f"X {UnitConverter.format_length(info['xmin'], u)} \u2013 {UnitConverter.format_length(info['xmax'], u)} | "
                f"Y {UnitConverter.format_length(info['ymin'], u)} \u2013 {UnitConverter.format_length(info['ymax'], u)} | "
                f"Z {UnitConverter.format_length(info['zmin'], u)} \u2013 {UnitConverter.format_length(info['zmax'], u)}"
            )
        except Exception:
            pass


    def _on_apply_rotations(self):
        if not self._path:
            return
        
        rx = self._rot_x.value()
        ry = self._rot_y.value()
        rz = self._rot_z.value()
        
        if rx == 0 and ry == 0 and rz == 0:
            return

        self._mw.set_status("Applying rotations\u2026")
        try:
            from core.geometry import GeometryProcessor
            proc = GeometryProcessor()
            
            if rx != 0: proc.rotate(self._path, "X", rx)
            if ry != 0: proc.rotate(self._path, "Y", ry)
            if rz != 0: proc.rotate(self._path, "Z", rz)
            
            # Reset values to 0 after applying
            self._rot_x.setValue(0)
            self._rot_y.setValue(0)
            self._rot_z.setValue(0)
            
            self._refresh_after_edit()
            self._mw.set_status("Rotations applied")
        except Exception as exc:
            log.error(f"Rotation failed: {exc}")
            self._mw.set_status(f"Rotation error: {exc}")

    def _on_apply_scale(self):
        if not self._path:
            return
        
        factor = self._scale_val.value()
        if factor == 1.0:
            return

        self._mw.set_status(f"Scaling by {factor}\u2026")
        try:
            from core.geometry import GeometryProcessor
            proc = GeometryProcessor()
            proc.scale(self._path, factor)
            
            # Reset to 1.0
            self._scale_val.setValue(1.0)
            
            self._refresh_after_edit()
            self._mw.set_status("Scale applied")
        except Exception as exc:
            log.error(f"Scaling failed: {exc}")
            self._mw.set_status(f"Scaling error: {exc}")

    def _refresh_after_edit(self):
        """Update info labels and viewport after geometry modification."""
        from core.geometry import GeometryProcessor
        proc = GeometryProcessor()
        info = proc.get_info(self._path)
        u = SettingsManager.get("units")
        self._lbl_bounds.setText(
            f"X {UnitConverter.format_length(info['xmin'], u)} \u2013 {UnitConverter.format_length(info['xmax'], u)} | "
            f"Y {UnitConverter.format_length(info['ymin'], u)} \u2013 {UnitConverter.format_length(info['ymax'], u)} | "
            f"Z {UnitConverter.format_length(info['zmin'], u)} \u2013 {UnitConverter.format_length(info['zmax'], u)}"
        )
        self._mw.viewport.show_geometry(self._path)
        # Re-add wind arrow
        cond = self._mw.get_flight_conditions()
        self._mw.viewport.show_wind_arrow(cond["airspeed"], cond["aoa_deg"])

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
            
        self._mw.set_status("Processing geometry\u2026")
        try:
            from core.geometry import GeometryProcessor
            proc = GeometryProcessor()
            stl = proc.prepare(path, scale_mm_to_m=self._mm_check.isChecked())
            info = proc.get_info(stl)

            self._path = stl
            self._lbl_name.setText(Path(path).name)
            u = SettingsManager.get("units")
            self._lbl_bounds.setText(
                f"X {UnitConverter.format_length(info['xmin'], u)} \u2013 {UnitConverter.format_length(info['xmax'], u)} | "
                f"Y {UnitConverter.format_length(info['ymin'], u)} \u2013 {UnitConverter.format_length(info['ymax'], u)} | "
                f"Z {UnitConverter.format_length(info['zmin'], u)} \u2013 {UnitConverter.format_length(info['zmax'], u)}"
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

    def _on_choose_model_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            cname = color.name()
            self._color_btn.setStyleSheet(f"background: {cname}; color: {'white' if color.lightness() < 128 else 'black'};")
            self._mw.viewport.set_model_color(cname)
