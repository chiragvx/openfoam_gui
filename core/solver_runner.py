import logging
from core.wsl_runner import WSLRunner

log = logging.getLogger(__name__)


class SolverRunner:
    """Runs foamRun (incompressibleFluid) inside WSL2, streaming output to the logger."""

    _SCRIPT_SERIAL = """\
set -e
echo "=== foamRun (incompressibleFluid) ==="
foamRun -solver incompressibleFluid > log.foamRun 2>&1
echo "foamRun OK"
"""

    _SCRIPT_PARALLEL = """\
set -e
echo "=== decomposePar ==="
decomposePar > log.decomposePar.solver 2>&1
echo "decomposePar OK"

echo "=== foamRun ({n} cores, parallel) ==="
mpirun --allow-run-as-root -np {n} foamRun -solver incompressibleFluid -parallel > log.foamRun 2>&1
echo "foamRun OK"

echo "=== reconstructPar ==="
reconstructPar > log.reconstructPar 2>&1
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
        log.info(f"Starting foamRun in {self._case_dir} ({self._n_cores} core(s))")
        if self._n_cores > 1:
            script = self._SCRIPT_PARALLEL.format(n=self._n_cores)
        else:
            script = self._SCRIPT_SERIAL
        return self._runner.run_command(
            script,
            cwd_windows=self._case_dir,
            timeout=3600,
            log_prefix="[SOLVER] ",
        )
