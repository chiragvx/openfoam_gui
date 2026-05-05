# OpenFOAM RC Aircraft CFD GUI

A Windows 11 desktop app for running steady RANS CFD on RC aircraft geometry. Import an STL or OBJ from Fusion 360, set flight conditions, run the full OpenFOAM meshing and solving pipeline through WSL2, and view pressure/velocity results in an embedded 3D viewport — no external tools required.

## Requirements

- Windows 11 with WSL2 enabled
- Ubuntu in WSL2 with OpenFOAM installed
- Python 3.11+

## One-time setup

### 1. Install WSL2 and OpenFOAM

In an elevated PowerShell:

```powershell
wsl --install -d Ubuntu
```

Then inside the WSL2 Ubuntu terminal:

```bash
curl https://dl.openfoam.com/add-apt-repository.sh | sudo bash
sudo apt install openfoam2312
```

### 2. Configure WSL paths

Open `config.py` and update these two values to match your installation:

```python
WSL_DISTRO = "Ubuntu"                                 # verify with: wsl -l
WSL_OPENFOAM_SOURCE = "/opt/openfoam2312/etc/bashrc"  # verify with: ls /opt/openfoam* in WSL
```

### 3. Install Python dependencies

```powershell
cd C:\path\to\openfoam_gui
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Running

```powershell
.venv\Scripts\Activate.ps1
python main.py
```

## Usage

1. **Import** — Load an STL or OBJ file. Check "Scale mm → m" if exported from Fusion 360 in millimetres.
2. **Conditions** — Set airspeed (m/s), angle of attack (°), and altitude (m). Air density, viscosity, Mach, and Reynolds number update live.
3. **Mesh** — Click "Run Mesh" to generate the wind tunnel domain and run blockMesh → snappyHexMesh via WSL2.
4. **Solver** — Click "Run Solver" to run simpleFoam (k-omega SST, steady RANS). Residuals stream into the log panel.
5. **Results** — Click "Load Results" to render pressure, velocity, or wall shear stress on the aircraft surface. CL/CD coefficients are written to `cases/run_*/postProcessing/forceCoeffs/`.

## Pre-run verification

```powershell
python -c "from core.atmosphere import ISAAtmosphere; a=ISAAtmosphere(0); print(a.density, a.speed_of_sound)"
# Expected: ~1.225  ~340
```

## Troubleshooting

| Problem | Fix |
|---|---|
| WSL2 distro not found | Run `wsl -l` in PowerShell; update `WSL_DISTRO` in `config.py` |
| OpenFOAM not found in WSL | Run `ls /opt/openfoam*` in WSL; update `WSL_OPENFOAM_SOURCE` in `config.py` |
| Geometry appears hollow / errors | Enable "Auto-repair" in the Import tab — trimesh will attempt to close the mesh |
| Solver diverges | Reduce relaxation factors in `templates/system/fvSolution.j2` (p: 0.3, U: 0.7) |
| Fusion 360 geometry scaled wrong | Check "Scale mm → m" in the Import tab |

## Logs

- **File:** `logs/openfoam_gui.log` — rotating, 5 MB × 3 files
- **GUI:** colour-coded panel at the bottom of the window (DEBUG = grey, INFO = white, WARNING = yellow, ERROR = red)

All OpenFOAM output (blockMesh, snappyHexMesh, simpleFoam) is piped line-by-line and tagged `[MESH]` or `[SOLVER]` in both destinations.

## Pre-built binaries

Windows executables are attached to each [GitHub release](../../releases). Download `OpenFOAM-GUI.exe` and run it directly — no Python installation needed. WSL2 and OpenFOAM must still be installed separately (steps 1–2 above).
