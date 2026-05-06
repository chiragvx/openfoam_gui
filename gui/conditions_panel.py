import logging
import math

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QGroupBox,
    QFormLayout, QDoubleSpinBox,
)

log = logging.getLogger(__name__)


class ConditionsPanel(QWidget):
    """Tab 2 — airspeed, angle of attack, altitude with live ISA readouts."""

    def __init__(self, main_window, viewport=None):
        super().__init__()
        self._mw = main_window
        self._viewport_ref = viewport
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
        self._lref.setToolTip("Mean aerodynamic chord — reference length for CM")

        self._aref = QDoubleSpinBox()
        self._aref.setRange(0.0001, 2000.0) # Up to Airliner area
        self._aref.setValue(0.15)
        self._aref.setSuffix(" m²")
        self._aref.setSingleStep(0.01)
        self._aref.setDecimals(4)
        self._aref.setToolTip("Wing planform reference area for CL / CD")

        in_form.addRow("Airspeed:", self._speed)
        in_form.addRow("Angle of Attack:", self._aoa)
        in_form.addRow("Altitude:", self._alt)
        in_form.addRow("Mean chord (lRef):", self._lref)
        in_form.addRow("Wing area (Aref):", self._aref)
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

        self._update()

    def _update(self):
        from core.atmosphere import ISAAtmosphere
        isa   = ISAAtmosphere(self._alt.value())
        speed = self._speed.value()
        mach  = speed / isa.speed_of_sound
        self._lbl_rho.setText(f"{isa.density:.4f} kg/m³")
        self._lbl_nu.setText(f"{isa.kinematic_viscosity:.2e} m²/s")
        
        mach_str = f"{mach:.4f}"
        if mach > 0.3:
            self._lbl_mach.setStyleSheet("color: #ffaa00; font-weight: bold;")
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
                vp.update_ground_plane(self._alt.value())

    def get_conditions(self) -> dict:
        from core.atmosphere import ISAAtmosphere
        isa   = ISAAtmosphere(self._alt.value())
        speed = self._speed.value()
        aoa   = self._aoa.value()
        return {
            "airspeed":       speed,
            "aoa_deg":        aoa,
            "altitude":       self._alt.value(),
            "rho":            isa.density,
            "nu":             isa.kinematic_viscosity,
            "mu":             isa.dynamic_viscosity,
            "speed_of_sound": isa.speed_of_sound,
            "Ux": speed * math.cos(math.radians(aoa)),
            "Uy": 0.0,
            "Uz": speed * math.sin(math.radians(aoa)),
            "lRef": self._lref.value(),
            "Aref": self._aref.value(),
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
