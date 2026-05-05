import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Running as a PyInstaller bundle
    APP_DIR     = Path(sys.executable).parent          # writable: logs, cases
    _BUNDLE_DIR = Path(sys._MEIPASS)                   # read-only bundled data
else:
    APP_DIR     = Path(__file__).parent.resolve()
    _BUNDLE_DIR = APP_DIR

LOGS_DIR      = APP_DIR     / "logs"
TEMPLATES_DIR = _BUNDLE_DIR / "templates"
CASES_DIR     = APP_DIR     / "cases"

# WSL2 integration — confirmed via `wsl -l`
WSL_DISTRO = "Ubuntu-22.04"
# OpenFOAM 11 installed in Ubuntu-22.04
WSL_OPENFOAM_SOURCE = "/opt/openfoam11/etc/bashrc"

# Solver defaults
DEFAULT_END_TIME = 500
DEFAULT_WRITE_INTERVAL = 50

# Domain size multipliers relative to geometry bounding-box longest dimension
DOMAIN_UPSTREAM_FACTOR = 5
DOMAIN_DOWNSTREAM_FACTOR = 10
DOMAIN_LATERAL_FACTOR = 4
DOMAIN_VERTICAL_FACTOR = 4

# snappyHexMesh defaults
DEFAULT_REFINEMENT_MIN = 3
DEFAULT_REFINEMENT_MAX = 5
DEFAULT_SURFACE_LAYERS = 3

# Parallelism — default to all logical CPU cores visible to WSL2
DEFAULT_CORES = os.cpu_count() or 1

# Logging
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 3
LOG_LEVEL = "DEBUG"
