# OpenFOAM RC Aircraft CFD GUI — Project Plan

## Purpose

A self-contained Windows 11 desktop application that lets you:
1. Import an RC aircraft geometry from Fusion 360 (STL or OBJ)
2. Set flight conditions (airspeed, angle of attack, altitude)
3. Run the full OpenFOAM meshing and solving pipeline via WSL2
4. Visualise results (pressure, velocity, wall shear) inline — no external tools

---

## Architecture Overview

```
Windows 11 (Python GUI)          WSL2 (Ubuntu + OpenFOAM)
─────────────────────────        ──────────────────────────
PyQt6 GUI                ──────▶ blockMesh
  ├─ Import Panel                snappyHexMesh
  ├─ Conditions Panel            simpleFoam (RANS, steady)
  ├─ Mesh Panel         wsl.exe  
  ├─ Solver Panel        calls   case written to
  └─ Results Panel               cases/run_TIMESTAMP/
                                 (accessible via /mnt/c/...)
PyVista viewport ◀─────────────  reads case.foam
Log panel (QTextEdit)
```

---

## Tech Stack

| Component | Choice | Why |
|---|---|---|
| GUI | PyQt6 | Free, Python-native, modern Qt6 |
| 3D Visualisation | PyVista + pyvistaqt | Reads OpenFOAM results natively; RTX GPU via OpenGL |
| Geometry | trimesh | STL/OBJ load, repair, scale, re-export |
| Templates | Jinja2 | Clean rendering of OpenFOAM dict files |
| Atmosphere | Custom ISA model | ρ, μ, Mach from altitude (troposphere) |
| Solver | simpleFoam | Incompressible steady RANS — correct for RC aircraft ≤50 m/s |
| Turbulence | k-omega SST | Industry standard for low-Re external aero |
| Mesher | blockMesh + snappyHexMesh | Standard OpenFOAM surface-fitting pipeline |
| OpenFOAM on Windows | WSL2 subprocess | OpenFOAM is Linux-only |

---

## File Structure

```
openfoam_gui/
├── main.py                        Entry point
├── requirements.txt
├── config.py                      All paths, WSL settings, defaults
├── PLAN.md                        This file
│
├── gui/
│   ├── main_window.py             Top-level layout
│   ├── viewport_widget.py         PyVista BackgroundPlotter wrapper
│   ├── log_widget.py              Thread-safe colour-coded log panel
│   ├── import_panel.py            Tab 1: open STL/OBJ
│   ├── conditions_panel.py        Tab 2: airspeed / AoA / altitude
│   ├── mesh_panel.py              Tab 3: snappyHexMesh settings + run
│   ├── solver_panel.py            Tab 4: simpleFoam run
│   └── results_panel.py           Tab 5: field selector + visualise
│
├── core/
│   ├── logger_setup.py            Rotating file log + Qt handler hook
│   ├── atmosphere.py              ISA atmosphere model
│   ├── geometry.py                Geometry load / repair / scale / export
│   ├── case_generator.py          Jinja2 → OpenFOAM case directory
│   ├── wsl_runner.py              WSL2 subprocess + path translation
│   ├── mesh_manager.py            blockMesh → surfaceFeatureExtract → snappyHexMesh
│   ├── solver_runner.py           simpleFoam
│   └── results_reader.py          pv.OpenFOAMReader wrapper
│
├── templates/
│   ├── system/
│   │   ├── blockMeshDict.j2
│   │   ├── snappyHexMeshDict.j2
│   │   ├── surfaceFeatureExtractDict.j2
│   │   ├── controlDict.j2         includes forceCoeffs (CL, CD)
│   │   ├── fvSchemes.j2
│   │   ├── fvSolution.j2          GAMG for p, symGaussSeidel for U/k/ω
│   │   └── decomposeParDict.j2
│   ├── constant/
│   │   ├── transportProperties.j2
│   │   └── turbulenceProperties.j2  kOmegaSST
│   └── 0/
│       ├── U.j2    ├── p.j2    ├── k.j2    ├── omega.j2    └── nut.j2
│
├── cases/                         Auto-created; run_YYYYMMDD_HHMMSS/ per run
└── logs/                          Rotating log files (5 MB × 3)
```

---

## Workflow (0 → 1)

```
1. Import STL/OBJ ──▶ trimesh repair ──▶ preview in viewport
        │
        ▼
2. Set flight conditions (airspeed, AoA, altitude)
   ISA model computes: ρ, ν, Mach, Re
        │
        ▼
3. Run Mesh
   CaseGenerator writes OpenFOAM case from Jinja2 templates
   ──▶ WSL2: blockMesh → surfaceFeatureExtract → snappyHexMesh
   Logs stream into GUI log panel in real time
        │
        ▼
4. Run Solver
   ──▶ WSL2: simpleFoam (k-omega SST, RANS, steady)
   Residuals stream into log panel
        │
        ▼
5. Load Results
   PyVista reads case.foam → renders pressure / velocity / WSS
   on aircraft surface in the embedded viewport
```

---

## Flight Conditions

| Input | Range | Notes |
|---|---|---|
| Airspeed | 1–100 m/s | RC aircraft typically 10–50 m/s |
| Angle of Attack | −20° to +30° | Velocity decomposes into Ux = V·cos(α), Uz = V·sin(α) |
| Altitude | 0–4000 m | ISA troposphere model; ρ and μ updated live |

**Derived (shown live):**
- Air density ρ (kg/m³)
- Kinematic viscosity ν (m²/s)
- Mach number
- Reynolds number per metre

---

## OpenFOAM Case Details

- **Solver:** `simpleFoam` (incompressible, steady RANS)
- **Turbulence:** k-omega SST — best for RC aircraft Reynolds numbers (10⁴–10⁶) with potential separation
- **Domain:** Auto-sized wind tunnel (5× upstream, 10× downstream, 4× lateral/vertical relative to geometry span)
- **Boundary patches:** `inlet` (fixedValue U), `outlet` (zeroGradient U, fixedValue p=0), `top/bottom/sides` (symmetryPlane), `aircraft` (noSlip wall)
- **Post-processing:** `forceCoeffs` function writes CL and CD to `postProcessing/forceCoeffs/`

---

## Setup Instructions

### 1. Install WSL2 + OpenFOAM (one-time)
```powershell
# In PowerShell (admin)
wsl --install -d Ubuntu
# Then in WSL2 Ubuntu terminal:
curl https://dl.openfoam.com/add-apt-repository.sh | sudo bash
sudo apt install openfoam2312
```

### 2. Update config.py
```python
WSL_DISTRO = "Ubuntu"                              # match `wsl -l` output
WSL_OPENFOAM_SOURCE = "/opt/openfoam2312/etc/bashrc"  # match installed version
```

### 3. Install Python dependencies
```powershell
cd C:\Users\Chirag\Documents\openfoam_gui
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Run
```powershell
python main.py
```

---

## Logging

All activity is logged to two destinations simultaneously:
- **File:** `logs/openfoam_gui.log` — rotating, 5 MB × 3 files
- **GUI:** colour-coded `QTextEdit` panel at the bottom of the window
  - DEBUG = grey, INFO = white, WARNING = yellow, ERROR = red

OpenFOAM command output (blockMesh, snappyHexMesh, simpleFoam) is piped line-by-line through Python's logger tagged `[MESH]` or `[SOLVER]`, so every line appears in both the file log and the GUI log panel in real time.

---

## Known Limitations & Workarounds

| Issue | Workaround |
|---|---|
| Fusion 360 exports in mm | Check "Scale mm → m" checkbox in Import tab |
| Non-watertight geometry | trimesh auto-repair; warning shown in log |
| `locationInMesh` inside aircraft | Point auto-computed at 95% of domain xmax — expose override if needed |
| simpleFoam diverges | Reduce relaxation factors in fvSolution.j2 (p: 0.3, U: 0.7) |
| WSL2 distro name wrong | Run `wsl -l` in PowerShell; update WSL_DISTRO in config.py |
| OpenFOAM version path | Run `ls /opt/openfoam*` in WSL2; update WSL_OPENFOAM_SOURCE |

---

## Verification Checklist

- [ ] `python -c "from core.atmosphere import ISAAtmosphere; a=ISAAtmosphere(0); print(a.density, a.speed_of_sound)"` → ≈1.225 kg/m³, ≈340 m/s
- [ ] `python main.py` — window opens, log panel shows startup, PyVista viewport initialises
- [ ] Open any STL file — geometry renders in viewport, bounding box appears in Import tab
- [ ] Change altitude in Conditions tab — ρ and ν update live
- [ ] Click "Run Mesh" on a test STL — `cases/run_*/` directory created with correct structure
- [ ] Meshing completes — log shows "snappyHexMesh OK"
- [ ] Solver runs — residuals appear in log panel
- [ ] Click "Load Results" — pressure contour renders on aircraft surface
- [ ] Check `cases/run_*/postProcessing/forceCoeffs/0/coefficient.dat` for CL/CD values
