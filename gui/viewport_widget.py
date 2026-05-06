import logging
import math
from pathlib import Path

import numpy as np
import pyvista as pv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QGridLayout,
)
from gui.camera_style import AircraftCameraStyle

log = logging.getLogger(__name__)


class ViewportWidget(QWidget):
    """
    Embeds a PyVista plotter in a Qt widget.
    Uses pyvistaqt.BackgroundPlotter; falls back to QtInteractor on failure.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._plotter = None
        self._scene_bounds: list | None = None
        self._aircraft_bounds: list | None = None
        self._domain_actor_names: set[str] = set()
        self._domain_visible = True

        layout.addWidget(self._build_toolbar())
        self._embed(layout)

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setMaximumHeight(60)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        layout.addLayout(row1)
        layout.addLayout(row2)

        views1 = [
            ("Fit",   "fit"),
            ("Iso",   "iso"),
            ("Front", "front"),
            ("Back",  "back"),
        ]
        views2 = [
            ("Top",   "top"),
            ("Bot",   "bottom"),
            ("Left",  "left"),
            ("Rght",  "right"),
        ]

        for label, view in views1:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setFixedWidth(46)
            btn.clicked.connect(lambda _=False, v=view: self._set_view(v))
            row1.addWidget(btn)
        row1.addStretch()

        for label, view in views2:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setFixedWidth(46)
            btn.clicked.connect(lambda _=False, v=view: self._set_view(v))
            row2.addWidget(btn)

        self._ground_btn = QPushButton("Ground")
        self._ground_btn.setFixedHeight(24)
        self._ground_btn.setFixedWidth(54)
        self._ground_btn.setCheckable(True)
        self._ground_btn.clicked.connect(self.toggle_ground_plane)
        row2.addWidget(self._ground_btn)

        row2.addStretch()
        return frame

    def _set_view(self, view: str):
        if self._plotter is None:
            return
        if view == "fit":
            self._reset_camera_to_aircraft()
            return
            
        dispatch = {
            "iso":    self._plotter.view_isometric,
            "front":  self._plotter.view_yz,
            "back":   lambda: self._plotter.view_yz(negative=True),
            "top":    self._plotter.view_xy,
            "bottom": lambda: self._plotter.view_xy(negative=True),
            "left":   lambda: self._plotter.view_xz(negative=True),
            "right":  self._plotter.view_xz,
        }
        if view in dispatch:
            dispatch[view]()

    def _reset_camera_to_aircraft(self):
        """Centre orbit and pan on the aircraft, not the domain box."""
        if self._plotter is None:
            return
        b = self._aircraft_bounds
        if b is None:
            self._plotter.reset_camera()
            return
        pad = max(b[1]-b[0], b[3]-b[2], b[5]-b[4]) * 1.5
        # Ensure we don't have near-zero padding which can cause clipping
        pad = max(pad, 0.1)
        self._plotter.reset_camera(bounds=[
            b[0]-pad, b[1]+pad,
            b[2]-pad, b[3]+pad,
            b[4]-pad, b[5]+pad,
        ])
        # Set clipping range explicitly to avoid issues with large-scale models
        self._plotter.camera.clipping_range = (pad * 0.01, pad * 100)

    def _snap_to_nearest_axis(self):
        if self._plotter is None:
            return
        cam = self._plotter.camera
        pos = cam.position
        focal = cam.focal_point
        vec = [pos[i] - focal[i] for i in range(3)]
        # find dominant axis
        abs_vec = [abs(v) for v in vec]
        dominant = abs_vec.index(max(abs_vec))
        views = [
            self._plotter.view_yz,    # dominant X → front
            self._plotter.view_xz,    # dominant Y → side
            self._plotter.view_xy,    # dominant Z → top
        ]
        # negate if looking from negative side
        if vec[dominant] < 0:
            views[dominant](negative=True)
        else:
            views[dominant]()

    # ------------------------------------------------------------------
    def _embed(self, layout):
        try:
            from pyvistaqt import BackgroundPlotter
            # Hide default toolbar and menu to avoid duplication with our custom ones
            self._plotter = BackgroundPlotter(show=False, toolbar=False, menu_bar=False)
            layout.addWidget(self._plotter.app_window)
            self._init_plotter_style()
            log.info("ViewportWidget: using BackgroundPlotter")
        except Exception as e:
            log.warning(f"BackgroundPlotter failed ({e}); falling back to QtInteractor")
            try:
                from pyvistaqt import QtInteractor
                self._plotter = QtInteractor(self)
                layout.addWidget(self._plotter)
                self._init_plotter_style()
                log.info("ViewportWidget: using QtInteractor")
            except Exception as e2:
                log.error(f"QtInteractor also failed: {e2}")

    def _init_plotter_style(self):
        if self._plotter is None:
            return
        style = AircraftCameraStyle()
        style.set_snap_callback(self._snap_to_nearest_axis)
        
        # Determine if we have a BackgroundPlotter (app_window) or QtInteractor
        if hasattr(self._plotter, "iren"):
            self._plotter.iren.interactor.SetInteractorStyle(style)
        elif hasattr(self._plotter, "interactor"):
            self._plotter.interactor.SetInteractorStyle(style)

    # ------------------------------------------------------------------
    def has_geometry(self) -> bool:
        return self._scene_bounds is not None

    # ------------------------------------------------------------------
    def show_geometry(self, stl_path: str):
        if self._plotter is None:
            return
        try:
            mesh = pv.read(stl_path)
            self._plotter.clear()
            self._domain_actor_names.clear()
            
            # Show model with wireframe
            self._plotter.add_mesh(
                mesh, color="lightblue", opacity=0.85, 
                show_edges=True, edge_color="gray", line_width=1,
                name="model"
            )
            
            self._scene_bounds    = list(mesh.bounds)
            self._aircraft_bounds = list(mesh.bounds)
            self._plotter.reset_camera()
            
            # Add XYZ Axes marker
            self._plotter.add_axes()
            
            # Add Dimension Labels (mm)
            b = mesh.bounds
            pts = [
                [(b[0]+b[1])/2, b[2], b[4]], # X midpoint (bottom-front)
                [b[0], (b[2]+b[3])/2, b[4]], # Y midpoint
                [b[0], b[2], (b[4]+b[5])/2], # Z midpoint
            ]
            lbls = [
                f"L: {(b[1]-b[0])*1000:.1f} mm",
                f"W: {(b[3]-b[2])*1000:.1f} mm",
                f"H: {(b[5]-b[4])*1000:.1f} mm",
            ]
            self._plotter.add_point_labels(
                pts, lbls, name="dims", 
                font_size=12, text_color="white", 
                shape_color="black", shape_opacity=0.4,
                always_visible=True, show_points=False
            )
            
            log.info(f"Geometry loaded into viewport: {Path(stl_path).name}")
        except Exception as exc:
            log.error(f"Viewport geometry load error: {exc}")

    # ------------------------------------------------------------------
    def show_results(self, case_dir: str, field: str = "p"):
        if self._plotter is None:
            return
        try:
            foam_file = str(Path(case_dir) / "case.foam")
            reader = pv.OpenFOAMReader(foam_file)
            if not reader.time_values:
                log.warning("No time steps found in results")
                return
            reader.set_active_time_value(reader.time_values[-1])
            dataset = reader.read()
            boundary = dataset["boundary"]

            self._plotter.clear()
            self._domain_actor_names.clear()
            self._domain_visible = False
            aircraft_bounds = None

            for name in (boundary.keys() or []):
                if name is None:
                    continue
                block = boundary[name]
                if block is None or block.n_cells == 0:
                    continue

                if name == "aircraft":
                    aircraft_bounds = list(block.bounds)
                    self._plotter.add_mesh(
                        block,
                        scalars=field,
                        cmap="coolwarm",
                        show_scalar_bar=True,
                        name="ac_surface",
                    )
                else:
                    actor_name = f"domain_{name}"
                    actor = self._plotter.add_mesh(
                        block,
                        color="#888888",
                        opacity=0.08,
                        show_edges=False,
                        name=actor_name,
                    )
                    if hasattr(actor, "SetVisibility"):
                        actor.SetVisibility(False)
                    self._domain_actor_names.add(actor_name)

            # Centre camera on aircraft so orbit/pan feel natural
            if aircraft_bounds:
                self._aircraft_bounds = aircraft_bounds
                self._scene_bounds    = aircraft_bounds
                self._reset_camera_to_aircraft()
            else:
                self._scene_bounds = list(boundary.bounds)
                self._plotter.reset_camera()

            log.info(f"Results displayed: field={field}, time={reader.time_values[-1]}")
        except Exception as exc:
            log.error(f"Viewport results load error: {exc}")

    # ------------------------------------------------------------------
    def add_streamlines_mesh(self, stream):
        """Called on the main thread once the worker has computed the streamlines."""
        if self._plotter is None:
            return
        try:
            self._plotter.add_mesh(
                stream,
                scalars="U",
                cmap="coolwarm",
                line_width=2,
                render_lines_as_tubes=True,
                name="streamlines",
            )
            self._plotter.render()
            log.info("Streamlines added to viewport")
        except Exception as exc:
            log.error(f"add_streamlines_mesh: {exc}")

    def clear_streamlines(self):
        if self._plotter is None:
            return
        try:
            self._plotter.remove_actor("streamlines")
            self._plotter.render()
        except Exception:
            pass
        log.info("Streamlines cleared")

    # ------------------------------------------------------------------
    def set_domain_box_visible(self, visible: bool):
        if self._plotter is None:
            return
        self._domain_visible = visible
        for name in self._domain_actor_names:
            actor = self._plotter.actors.get(name)
            if actor is not None:
                actor.SetVisibility(visible)
        try:
            self._plotter.render()
        except Exception:
            pass
        log.info(f"Domain box visibility → {visible}")

    # ------------------------------------------------------------------
    def show_wind_arrow(self, speed: float, aoa_deg: float):
        if self._plotter is None:
            return
        try:
            aoa_rad  = math.radians(aoa_deg)
            flow_dir = np.array([math.cos(aoa_rad), 0.0, math.sin(aoa_rad)])

            if self._scene_bounds:
                b    = self._scene_bounds
                cx   = (b[0] + b[1]) / 2
                cy   = (b[2] + b[3]) / 2
                cz   = (b[4] + b[5]) / 2
                span = max(b[1]-b[0], b[5]-b[4], b[3]-b[2])
            else:
                cx, cy, cz, span = 0.0, 0.0, 0.0, 1.0

            arrow_len = span * 0.35
            tail = np.array([cx, cy + span * 0.6, cz]) - flow_dir * span * 0.55

            arrow_mesh = pv.Arrow(
                start=tuple(tail),
                direction=tuple(flow_dir),
                scale=arrow_len,
                tip_length=0.28,
                tip_radius=0.10,
                shaft_radius=0.04,
            )
            self._plotter.add_mesh(arrow_mesh, color="cyan", name="wind_arrow")

            label_pt = tail - flow_dir * arrow_len * 0.15
            self._plotter.add_point_labels(
                [label_pt],
                [f"Wind  {speed:.1f} m/s\nAoA  {aoa_deg:+.1f}°"],
                font_size=12,
                text_color="cyan",
                shape_color="black",
                shape_opacity=0.5,
                name="wind_label",
                always_visible=True,
                show_points=False,
            )
            log.info(f"Wind arrow updated — {speed:.1f} m/s  AoA={aoa_deg:+.1f}°")
        except Exception as exc:
            log.error(f"Wind arrow error: {exc}")

    # ------------------------------------------------------------------
    def update_ground_plane(self, altitude_m: float):
        """Auto-show ground plane when at ground level."""
        if altitude_m < 1.0:
            self._show_ground_plane()
        else:
            self._hide_ground_plane()

    def _show_ground_plane(self):
        if self._plotter is None:
            return
        if "ground_plane" in self._plotter.actors:
            return
        b = self._aircraft_bounds or [-1, 1, -1, 1, -1, 1]
        cx = (b[0] + b[1]) / 2
        cy = (b[2] + b[3]) / 2
        span = max(b[1]-b[0], b[3]-b[2]) * 6
        if span < 1: span = 10
        
        plane = pv.Plane(center=(cx, cy, b[4]),  # z = bottom of model
                         direction=(0, 0, 1),
                         i_size=span, j_size=span,
                         i_resolution=20, j_resolution=20)
        self._plotter.add_mesh(
            plane, color="#7aa8c7", opacity=0.30,
            specular=0.6, specular_power=30,
            name="ground_plane", show_edges=False)
        
        if hasattr(self, "_ground_btn"):
            self._ground_btn.blockSignals(True)
            self._ground_btn.setChecked(True)
            self._ground_btn.blockSignals(False)
            
        self._plotter.render()

    def _hide_ground_plane(self):
        if self._plotter is None:
            return
        self._plotter.remove_actor("ground_plane", render=True)
        if hasattr(self, "_ground_btn"):
            self._ground_btn.blockSignals(True)
            self._ground_btn.setChecked(False)
            self._ground_btn.blockSignals(False)

    def toggle_ground_plane(self):
        if self._plotter is None:
            return
        if "ground_plane" in self._plotter.actors:
            self._hide_ground_plane()
        else:
            self._show_ground_plane()
