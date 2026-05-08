import logging
import math

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QFormLayout, QDoubleSpinBox, QPushButton,
)

log = logging.getLogger(__name__)
from core.settings_manager import SettingsManager
from core.unit_converter   import UnitConverter


class _AeroEstimateWorker(QThread):
    """
    Runs GeometryProcessor.estimate_aero_reference() off the main thread
    so the UI stays responsive during the mesh-slicing computation.
    """
    finished = pyqtSignal(dict)   # emits the result dict on success
    failed   = pyqtSignal(str)    # emits an error message on failure

    def __init__(self, stl_path: str):
        super().__init__()
        self._stl_path = stl_path

    def run(self):
        try:
            from core.geometry import GeometryProcessor
            result = GeometryProcessor().estimate_aero_reference(self._stl_path)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class ConditionsPanel(QWidget):
    """Tab 2 — airspeed, angle of attack, altitude with live ISA readouts."""

    def __init__(self, main_window, viewport=None):
        super().__init__()
        self._mw = main_window
        self._viewport_ref = viewport
        self._current_unit = "m"   # tracks the last-applied unit for conversion
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Flight Conditions</b>"))
        layout.addWidget(QLabel("Conditions represent the freestream flow around the aircraft."))


        # --- Inputs ---
        in_grp  = QGroupBox("Inputs")
        in_form = QFormLayout()

        self._speed = QDoubleSpinBox()
        self._speed.setRange(1.0, 1000.0)  # Up to Mach 3
        self._speed.setValue(20.0)
        self._speed.setSuffix(" m/s")
        self._speed.valueChanged.connect(self._update)

        self._aoa = QDoubleSpinBox()
        self._aoa.setRange(-90.0, 90.0)   # Full range AoA
        self._aoa.setValue(3.0)
        self._aoa.setSuffix(" °")
        self._aoa.setSingleStep(0.5)
        self._aoa.valueChanged.connect(self._update)

        self._alt = QDoubleSpinBox()
        self._alt.setRange(0.0, 30000.0)  # Up to Stratosphere
        self._alt.setValue(100.0)
        self._alt.setSuffix(" m")
        self._alt.setSingleStep(50.0)
        self._alt.valueChanged.connect(self._update)

        self._lref = QDoubleSpinBox()
        self._lref.setRange(0.001, 100.0) # Up to Airliner chord
        self._lref.setValue(0.25)
        self._lref.setSuffix(" m")
        self._lref.setSingleStep(0.01)
        self._lref.setDecimals(3)
        self._lref.setToolTip("Mean aerodynamic chord \u2014 reference length for CM")

        self._aref = QDoubleSpinBox()
        self._aref.setRange(0.0001, 2000.0) # Up to Airliner area
        self._aref.setValue(0.15)
        self._aref.setSuffix(" m\u00b2")
        self._aref.setSingleStep(0.01)
        self._aref.setDecimals(4)
        self._aref.setToolTip("Wing planform reference area for CL / CD")

        # Auto-compute button + status label
        self._auto_btn = QPushButton("\U0001F4D0 Auto")
        self._auto_btn.setToolTip(
            "Estimate MAC and Aref automatically from the loaded geometry."
        )
        self._auto_btn.setFixedWidth(70)
        self._auto_btn.clicked.connect(self._on_auto_compute)
        self._auto_lbl = QLabel("")
        self._auto_lbl.setStyleSheet("color: grey; font-size: 10px;")

        # Row: lRef spinbox
        lref_row = QHBoxLayout()
        lref_row.addWidget(self._lref)
        lref_row.setContentsMargins(0, 0, 0, 0)

        # Row: Aref spinbox + Auto button
        aref_row = QHBoxLayout()
        aref_row.addWidget(self._aref)
        aref_row.addWidget(self._auto_btn)
        aref_row.setContentsMargins(0, 0, 0, 0)

        in_form.addRow("Airspeed:", self._speed)
        in_form.addRow("Angle of Attack:", self._aoa)
        in_form.addRow("Altitude:", self._alt)
        in_form.addRow("Mean chord (lRef):", lref_row)
        in_form.addRow("Wing area (Aref):",  aref_row)
        in_form.addRow("", self._auto_lbl)
        in_grp.setLayout(in_form)
        layout.addWidget(in_grp)

        # --- Derived ---
        der_grp  = QGroupBox("Derived (ISA model)")
        der_form = QFormLayout()
        self._lbl_rho   = QLabel()
        self._lbl_nu    = QLabel()
        self._lbl_mach  = QLabel()
        self._lbl_re    = QLabel()
        der_form.addRow("Density ρ:", self._lbl_rho)
        der_form.addRow("Kin. viscosity ν:", self._lbl_nu)
        der_form.addRow("Mach:", self._lbl_mach)
        der_form.addRow("Re / metre:", self._lbl_re)
        der_grp.setLayout(der_form)
        layout.addWidget(der_grp)
        layout.addStretch()
        self.refresh_units()
        self.refresh_theme()


    def refresh_units(self):
        new_u = SettingsManager.get("units")
        old_u = self._current_unit

        if old_u != new_u:
            # Convert the currently-displayed values so the underlying physical
            # quantity is preserved (e.g. 0.25 m → 25.0 cm, not 0.25 cm).
            old_alt_m   = UnitConverter.to_base(self._alt.value(),  old_u)
            old_lref_m  = UnitConverter.to_base(self._lref.value(), old_u)
            old_aref_m2 = UnitConverter.area_to_base(self._aref.value(), old_u)

            self._alt.blockSignals(True)
            self._lref.blockSignals(True)
            self._aref.blockSignals(True)
            self._alt.setValue(UnitConverter.from_base(old_alt_m,   new_u))
            self._lref.setValue(UnitConverter.from_base(old_lref_m,  new_u))
            self._aref.setValue(UnitConverter.area_from_base(old_aref_m2, new_u))
            self._alt.blockSignals(False)
            self._lref.blockSignals(False)
            self._aref.blockSignals(False)

            self._current_unit = new_u

        self._alt.setSuffix(f" {new_u}")
        self._lref.setSuffix(f" {new_u}")
        self._aref.setSuffix(f" {new_u}\u00b2")
        self._update()

    def refresh_theme(self):
        self._update()


    def _update(self):
        from core.atmosphere import ISAAtmosphere
        u = SettingsManager.get("units")
        alt_m = UnitConverter.to_base(self._alt.value(), u)
        isa   = ISAAtmosphere(alt_m)
        speed = self._speed.value()
        mach  = speed / isa.speed_of_sound
        self._lbl_rho.setText(f"{isa.density:.4f} kg/m³")
        self._lbl_nu.setText(f"{isa.kinematic_viscosity:.2e} m²/s")
        
        mach_str = f"{mach:.4f}"
        if mach > 0.3:
            theme = SettingsManager.get("theme")
            color = "#ffaa00" if theme == "dark" else "#d48806"
            self._lbl_mach.setStyleSheet(f"color: {color}; font-weight: bold;")
            mach_str += " (Incompressible limit)"
        else:
            self._lbl_mach.setStyleSheet("")
        self._lbl_mach.setText(mach_str)

        
        self._lbl_re.setText(f"{speed / isa.kinematic_viscosity:,.0f} m⁻¹")

        # Live-update the wind arrow whenever geometry is already loaded
        vp = self._viewport_ref or getattr(self._mw, "viewport", None)
        if vp and vp.has_geometry():
            vp.show_wind_arrow(speed, self._aoa.value())
            if hasattr(vp, "update_ground_plane"):
                vp.update_ground_plane(alt_m)

    def get_conditions(self) -> dict:
        from core.atmosphere import ISAAtmosphere
        u = SettingsManager.get("units")
        alt_m = UnitConverter.to_base(self._alt.value(), u)
        lref_m = UnitConverter.to_base(self._lref.value(), u)
        aref_m2 = UnitConverter.area_to_base(self._aref.value(), u)
        
        isa   = ISAAtmosphere(alt_m)
        speed = self._speed.value()
        aoa   = self._aoa.value()
        return {
            "airspeed":       speed,
            "aoa_deg":        aoa,
            "altitude":       alt_m,
            "rho":            isa.density,
            "nu":             isa.kinematic_viscosity,
            "mu":             isa.dynamic_viscosity,
            "speed_of_sound": isa.speed_of_sound,
            "Ux": speed * math.cos(math.radians(aoa)),
            "Uy": 0.0,
            "Uz": speed * math.sin(math.radians(aoa)),
            "lRef": lref_m,
            "Aref": aref_m2,
        }

    def set_conditions(self, d: dict) -> None:
        for widget, key in [
            (self._speed, "airspeed"), (self._aoa, "aoa_deg"),
            (self._alt, "altitude"), (self._lref, "lRef"), (self._aref, "Aref"),
        ]:
            if key in d:
                widget.blockSignals(True)
                widget.setValue(d[key])
                widget.blockSignals(False)
        self._update()

    # ------------------------------------------------------------------
    # Auto-compute MAC / Aref from geometry
    # ------------------------------------------------------------------
    def _on_auto_compute(self):
        stl_path = self._mw.get_geometry_path()
        if not stl_path:
            self._auto_lbl.setText("No geometry loaded \u2014 import STL first.")
            return

        self._auto_btn.setEnabled(False)
        self._auto_lbl.setText("Computing\u2026 (slicing mesh along span)")

        self._estimate_worker = _AeroEstimateWorker(stl_path)
        self._estimate_worker.finished.connect(self._on_estimate_done)
        self._estimate_worker.failed.connect(self._on_estimate_failed)
        self._estimate_worker.start()

    def _on_estimate_done(self, result: dict):
        self._auto_btn.setEnabled(True)
        u = SettingsManager.get("units")

        mac_m   = result["mac"]
        aref_m2 = result["aref"]
        span_m  = result["span"]
        method  = result.get("method", "integrated")

        # Convert to display units before setting spinboxes
        mac_disp  = UnitConverter.from_base(mac_m,   u)
        aref_disp = UnitConverter.area_from_base(aref_m2, u)

        self._lref.blockSignals(True)
        self._aref.blockSignals(True)
        self._lref.setValue(mac_disp)
        self._aref.setValue(aref_disp)
        self._lref.blockSignals(False)
        self._aref.blockSignals(False)
        self._update()

        tag = "integrated" if method == "integrated" else "bbox approx"
        cr  = UnitConverter.from_base(result.get("chord_root", mac_m), u)
        ct  = UnitConverter.from_base(result.get("chord_tip",  mac_m), u)
        self._auto_lbl.setText(
            f"\u2713 span={UnitConverter.format_length(span_m, u)}  "
            f"root={cr:.3f}  tip={ct:.3f}  [{tag}]"
        )
        log.info(
            f"Auto aero ref: MAC={mac_m:.4f} m  Aref={aref_m2:.4f} m\u00b2  "
            f"span={span_m:.4f} m  method={method}"
        )

    def _on_estimate_failed(self, msg: str):
        self._auto_btn.setEnabled(True)
        self._auto_lbl.setText(f"Error: {msg}")
        log.error(f"Aero estimate failed: {msg}")

