import logging
from core.wsl_runner import WSLRunner

log = logging.getLogger(__name__)


class MeshManager:
    """
    Drives blockMesh → surfaceFeatures → snappyHexMesh inside WSL2.
    When n_cores > 1, snappyHexMesh runs in parallel via MPI.
    """

    _SCRIPT_SERIAL = """\
set -e
echo "=== blockMesh ==="
blockMesh > log.blockMesh 2>&1
echo "blockMesh OK"

echo "=== surfaceFeatures ==="
surfaceFeatures > log.surfaceFeatures 2>&1
echo "surfaceFeatures OK"

echo "=== snappyHexMesh ==="
snappyHexMesh -overwrite > log.snappyHexMesh 2>&1
echo "snappyHexMesh OK"
"""

    _SCRIPT_PARALLEL = """\
set -e
echo "=== blockMesh ==="
blockMesh > log.blockMesh 2>&1
echo "blockMesh OK"

echo "=== surfaceFeatures ==="
surfaceFeatures > log.surfaceFeatures 2>&1
echo "surfaceFeatures OK"

echo "=== decomposePar ==="
decomposePar > log.decomposePar 2>&1
echo "decomposePar OK"

echo "=== snappyHexMesh ({n} cores) ==="
mpirun --allow-run-as-root -np {n} snappyHexMesh -overwrite -parallel > log.snappyHexMesh 2>&1
echo "snappyHexMesh OK"

echo "=== reconstructPar (mesh) ==="
reconstructPar -constant > log.reconstructPar 2>&1
echo "reconstructPar OK"

echo "=== removing processor directories ==="
rm -rf processor*
echo "cleanup OK"
"""

    def __init__(self, case_dir: str, wsl_distro: str | None, n_cores: int = 1):
        self._case_dir = case_dir
        self._runner   = WSLRunner(wsl_distro)
        self._n_cores  = max(1, n_cores)

    def run(self) -> tuple[bool, str]:
        log.info(f"Starting meshing pipeline ({self._n_cores} core(s))")
        if self._n_cores > 1:
            script = self._SCRIPT_PARALLEL.format(n=self._n_cores)
        else:
            script = self._SCRIPT_SERIAL
        return self._runner.run_command(
            script,
            cwd_windows=self._case_dir,
            timeout=1800,
            log_prefix="[MESH] ",
        )
