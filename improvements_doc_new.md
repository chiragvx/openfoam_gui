# Plan: 3D Viewer Usability + Study Management

## Context
The OpenFOAM RC Aircraft CFD GUI needs three areas improved:
1. **3D viewer view presets** — only Front/Side/Top exist; Back/Bottom/Left/Right missing
2. **Camera interaction** — right-click should pan; Ctrl should lock rotation to axis
3. **Reflective ground plane** — when altitude ≈ 0 m show a ground plane
4. **Study management** — no save/load exists; runs are anonymous timestamped folders

---

## Critical Files

| File | Role |
|------|------|
| `gui/viewport_widget.py` (272 lines) | All 3D viewer logic — MAIN EDIT TARGET |
| `gui/main_window.py` (108 lines) | Window layout, cross-panel wiring |
| `gui/conditions_panel.py` (123 lines) | Altitude spinbox → triggers viewport updates |
| `gui/import_panel.py` (82 lines) | Geometry load — needs `load_geometry(path)` added |
| `gui/mesh_panel.py` (123 lines) | `_on_done()` signals solver; add study save hook |
| `gui/solver_panel.py` (124 lines) | `_on_done()` signals results; add study save hook |
| `config.py` (44 lines) | Add `STUDIES_DIR` |
| `main.py` (34 lines) | Entry point — add startup dialog trigger |

**New files to create:**
- `gui/camera_style.py` — custom VTK interactor style
- `gui/study_dialog.py` — New/Load Study dialogs
- `core/study_manager.py` — Study dataclass + JSON persistence

---

## Implementation Steps

### Step 1 — `config.py`: Add STUDIES_DIR
Add after `CASES_DIR`:
```python
STUDIES_DIR = APP_DIR / "studies"
```

---

### Step 2 — `gui/camera_style.py` (new file)

Create `AircraftCameraStyle` subclassing `vtk.vtkInteractorStyleTrackballCamera`:

```python
import vtk

class AircraftCameraStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self):
        super().__init__()
        self._ctrl_locked = False
        self.AddObserver("RightButtonPressEvent",   self._right_press)
        self.AddObserver("RightButtonReleaseEvent", self._right_release)
        self.AddObserver("KeyPressEvent",           self._key_press)
        self.AddObserver("KeyReleaseEvent",         self._key_release)
        self.AddObserver("LeftButtonPressEvent",    self._left_press)

    def _right_press(self, obj, event):
        self.StartPan()          # pan instead of zoom on right-click

    def _right_release(self, obj, event):
        self.EndPan()

    def _key_press(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key in ("Control_L", "Control_R", "ctrl"):
            self._ctrl_locked = True
            # snap camera to nearest axis — call back via stored plotter ref
            if self._snap_callback:
                self._snap_callback()

    def _key_release(self, obj, event):
        key = self.GetInteractor().GetKeySym()
        if key in ("Control_L", "Control_R", "ctrl"):
            self._ctrl_locked = False

    def _left_press(self, obj, event):
        if self._ctrl_locked:
            self.StartPan()      # pan-only while Ctrl held
        else:
            self.OnLeftButtonDown()  # normal rotate

    # Attach a callback so ViewportWidget can snap camera on Ctrl press
    def set_snap_callback(self, cb):
        self._snap_callback = cb
```

Apply in `ViewportWidget._init_plotter()`:
```python
from gui.camera_style import AircraftCameraStyle
style = AircraftCameraStyle()
style.set_snap_callback(self._snap_to_nearest_axis)
# BackgroundPlotter path:
self._plotter.iren.interactor.SetInteractorStyle(style)
# QtInteractor fallback path (same API):
# self._plotter.interactor.SetInteractorStyle(style)
```

**Snap-to-nearest-axis logic** in `ViewportWidget`:
```python
def _snap_to_nearest_axis(self):
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
```

---

### Step 3 — `gui/viewport_widget.py`: View Presets + Ground Plane

**3a. Expand toolbar** (replace `_build_toolbar`, lines 43–56):

Change from 5 buttons to 8 + Ground toggle. Use compact 2-row grid layout:

```
Row 1: [Fit] [Iso] [Frnt] [Back]
Row 2: [Top] [Bot] [Left] [Rght]  [Ground]
```

Button dispatch map extension:
```python
dispatch = {
    "fit":    self._reset_camera_to_aircraft,
    "iso":    self._plotter.view_isometric,
    "front":  self._plotter.view_yz,
    "back":   lambda: self._plotter.view_yz(negative=True),
    "top":    self._plotter.view_xy,
    "bottom": lambda: self._plotter.view_xy(negative=True),
    "left":   lambda: self._plotter.view_xz(negative=True),
    "right":  self._plotter.view_xz,
}
```

**3b. Ground plane** — add two new methods:

```python
def update_ground_plane(self, altitude_m: float):
    """Auto-show ground plane when at ground level."""
    if altitude_m < 1.0:
        self._show_ground_plane()
    else:
        self._hide_ground_plane()

def _show_ground_plane(self):
    if "ground_plane" in self._plotter.actors:
        return
    b = self._aircraft_bounds  # [xmin,xmax,ymin,ymax,zmin,zmax]
    cx = (b[0] + b[1]) / 2
    cy = (b[2] + b[3]) / 2
    span = max(b[1]-b[0], b[3]-b[2]) * 6
    plane = pv.Plane(center=(cx, cy, b[4]),  # z = bottom of model
                     direction=(0, 0, 1),
                     i_size=span, j_size=span,
                     i_resolution=20, j_resolution=20)
    self._plotter.add_mesh(
        plane, color="#7aa8c7", opacity=0.30,
        specular=0.6, specular_power=30,
        name="ground_plane", show_edges=False)
    self._plotter.render()

def _hide_ground_plane(self):
    self._plotter.remove_actor("ground_plane", render=True)

def toggle_ground_plane(self):
    if "ground_plane" in self._plotter.actors:
        self._hide_ground_plane()
    else:
        self._show_ground_plane()
```

Wire "Ground" toolbar button to `self.toggle_ground_plane()`.

**3c. Wire altitude → ground plane** in `conditions_panel.py`:

In `ConditionsPanel._update()` (lines 90–102), after the existing wind arrow call, add:
```python
vp = self._viewport_ref  # need to pass viewport ref at construction
if vp is not None:
    vp.update_ground_plane(self._alt.value())
```

Pass viewport ref from `MainWindow._build_ui()` when constructing ConditionsPanel:
```python
self.conditions_panel = ConditionsPanel(viewport=self.viewport)
```
Add `viewport=None` kwarg to `ConditionsPanel.__init__`, store as `self._viewport_ref`.

---

### Step 4 — `core/study_manager.py` (new file)

```python
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import re
import config

@dataclass
class Study:
    name: str
    study_id: str = ""          # slug_timestamp, used as filename stem
    created: str = ""
    modified: str = ""
    description: str = ""
    geometry_path: Optional[str] = None
    case_dir: Optional[str] = None
    conditions: dict = field(default_factory=dict)
    mesh_settings: dict = field(default_factory=dict)
    solver_settings: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    ui_state: dict = field(default_factory=dict)

    def __post_init__(self):
        now = datetime.now().isoformat(timespec="seconds")
        if not self.created:
            self.created = now
        if not self.modified:
            self.modified = now
        if not self.study_id:
            slug = re.sub(r"[^a-z0-9]+", "_", self.name.lower()).strip("_")[:32]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.study_id = f"{slug}_{ts}"

class StudyManager:
    @staticmethod
    def _dir() -> Path:
        d = config.STUDIES_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def list_studies(cls) -> list[Study]:
        studies = []
        for p in sorted(cls._dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                studies.append(cls._load_file(p))
            except Exception:
                pass
        return studies

    @classmethod
    def save(cls, study: Study) -> Path:
        study.modified = datetime.now().isoformat(timespec="seconds")
        path = cls._dir() / f"{study.study_id}.json"
        path.write_text(json.dumps(asdict(study), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, study_id: str) -> Study:
        return cls._load_file(cls._dir() / f"{study_id}.json")

    @classmethod
    def delete(cls, study_id: str) -> None:
        p = cls._dir() / f"{study_id}.json"
        if p.exists():
            p.unlink()

    @staticmethod
    def _load_file(path: Path) -> Study:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Study(**data)
```

---

### Step 5 — `gui/study_dialog.py` (new file)

Three dialogs:

**`StudyStartupDialog(QDialog)`** — shown at launch:
- Two large buttons: "New Study" and "Load Study"
- "Skip" link (use last state without a named study)
- Returns `.chosen` = `"new"` | `"load"` | `"skip"`

**`NewStudyDialog(QDialog)`**:
- `QLineEdit _name` (required, placeholder "e.g. Wing at 20 m/s")
- `QTextEdit _desc` (optional, 3 lines)
- OK (disabled until name non-empty) / Cancel

**`LoadStudyDialog(QDialog)`**:
- Left: `QListWidget` — one row per study, shows name + date + "✓ solved" badge
- Right: `QGroupBox` preview — Airspeed, AoA, Altitude, Cl, Cd displayed as read-only labels
- Buttons: Load (default), Delete, Cancel
- Populated by `StudyManager.list_studies()` on open

---

### Step 6 — Panel populate methods

**`gui/import_panel.py`** — add:
```python
def load_geometry(self, path: str) -> None:
    """Programmatically load geometry (used by study restore)."""
    # Reuse same logic as _on_open but skip QFileDialog
    try:
        scale = self._scale_cb.isChecked()
        out = GeometryProcessor.prepare(path, scale)
        info = GeometryProcessor.get_info(out)
        self._path = out
        self._update_info(info)
        self._viewport.show_geometry(out)
        # ... same as _on_open lines 60-78
    except Exception as e:
        log.error("load_geometry failed: %s", e)
```

**`gui/conditions_panel.py`** — add:
```python
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
```

**`gui/mesh_panel.py`** — add:
```python
def set_settings(self, d: dict) -> None:
    for widget, key in [
        (self._ref_min, "refinement_min"), (self._ref_max, "refinement_max"),
        (self._layers, "surface_layers"),
    ]:
        if key in d:
            widget.setValue(d[key])
```

**`gui/solver_panel.py`** — add:
```python
def set_settings(self, d: dict) -> None:
    if "end_time" in d:
        self._iters.setValue(d["end_time"])
    if "n_cores" in d:
        self._cores.setValue(d["n_cores"])
```

---

### Step 7 — `gui/main_window.py`: Study integration

Add to `_build_ui()`:
1. Create `QMenuBar` with **File** menu:
   - "New Study…" → `self._new_study()`
   - "Load Study…" → `self._load_study()`
   - "Save Study" → `self._save_study()`  (Ctrl+S shortcut)
   - Separator → "Exit"
2. Add `self._current_study: Study | None = None`
3. Show startup dialog after window is shown:
```python
QTimer.singleShot(200, self._show_startup_dialog)
```

Add methods:

```python
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
        self.setWindowTitle(f"OpenFOAM RC CFD — {self._current_study.name}")

def _load_study(self):
    from gui.study_dialog import LoadStudyDialog
    dlg = LoadStudyDialog(self)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        self._apply_study(dlg.selected_study)

def _apply_study(self, study: Study):
    self._current_study = study
    self.setWindowTitle(f"OpenFOAM RC CFD — {study.name}")
    if study.geometry_path and Path(study.geometry_path).exists():
        self.import_panel.load_geometry(study.geometry_path)
    if study.conditions:
        self.conditions_panel.set_conditions(study.conditions)
    if study.mesh_settings:
        self.mesh_panel.set_settings(study.mesh_settings)
    if study.solver_settings:
        self.solver_panel.set_settings(study.solver_settings)
    if study.case_dir and Path(study.case_dir).exists():
        self.solver_panel.set_case_dir(study.case_dir)
        self.results_panel.set_case_dir(study.case_dir)

def _save_study(self):
    if self._current_study is None:
        self._new_study()
        if self._current_study is None:
            return
    s = self._current_study
    s.conditions = self.conditions_panel.get_conditions()
    s.mesh_settings = self.mesh_panel.get_settings()
    s.solver_settings = {"end_time": self.solver_panel._iters.value(),
                         "n_cores": self.solver_panel.get_n_cores()}
    geom = self.import_panel.get_geometry_path()
    if geom:
        s.geometry_path = geom
    StudyManager.save(s)
    self.set_status(f"Study saved: {s.name}")
```

**Auto-save hooks:** In `MeshPanel._on_done()` and `SolverPanel._on_done()`, after the existing cross-panel wiring, call:
```python
main_win = self.window()  # QWidget.window() returns the QMainWindow
if hasattr(main_win, "_save_study"):
    main_win._save_study()
```
And in `SolverPanel._on_done()`, also snapshot results:
```python
if hasattr(main_win, "_current_study") and main_win._current_study:
    try:
        coeffs = ResultsReader.read_force_coeffs(self._case_dir)
        main_win._current_study.results = {**coeffs, "solved": True}
        main_win._current_study.case_dir = self._case_dir
    except Exception:
        pass
```

---

### Step 8 — `main.py`: Ensure studies dir is created

Add after the existing mkdir calls:
```python
config.STUDIES_DIR.mkdir(parents=True, exist_ok=True)
```

---

## Implementation Order

1. `config.py` — add STUDIES_DIR
2. `core/study_manager.py` — Study + StudyManager (no deps on GUI)
3. `gui/camera_style.py` — VTK interactor style
4. `gui/viewport_widget.py` — view presets, custom interactor, ground plane
5. `gui/conditions_panel.py` — add viewport ref + `set_conditions()`
6. `gui/import_panel.py` — add `load_geometry()`
7. `gui/mesh_panel.py` — add `set_settings()` + auto-save hook
8. `gui/solver_panel.py` — add `set_settings()` + auto-save hook
9. `gui/study_dialog.py` — all three dialogs
10. `gui/main_window.py` — menu bar + study methods + startup trigger
11. `main.py` — studies dir creation

---

## Verification

1. Run `python main.py` — startup dialog appears
2. Click "New Study" → name dialog → main window title updates
3. Import geometry → conditions → mesh → solver → results: window title persists, save/load via File menu
4. Quit and reopen → "Load Study" → select study → all panels restore
5. In viewport: right-click drag pans; Ctrl snaps to nearest axis; scroll zooms
6. Set altitude to 0 m in Conditions → ground plane appears automatically
7. Set altitude to 100 m → ground plane disappears
8. Click "Ground" toolbar button → manual toggle works
9. All 8 view buttons (Front/Back/Top/Bottom/Left/Right/Iso/Fit) work correctly