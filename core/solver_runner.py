import logging
from core.wsl_runner import WSLRunner

log = logging.getLogger(__name__)


class SolverRunner:
    """Runs foamRun (incompressibleFluid) inside WSL2, streaming output to the logger."""

    _SCRIPT_SERIAL = """\
set -e
echo "=== foamRun (incompressibleFluid) ==="
foamRun -solver incompressibleFluid 2>&1 | tee log.foamRun
echo "foamRun OK"

echo "=== Post-Processing ==="
foamPostProcess -func wallShearStress -latestTime 2>&1 | tee log.wallShearStress || echo "wallShearStress failed"
foamPostProcess -func yPlus -latestTime 2>&1 | tee log.yPlus || echo "yPlus failed"
echo "Post-processing OK"
"""

    _SCRIPT_PARALLEL = """\
set -e
echo "=== decomposePar ==="
decomposePar -force 2>&1 | tee log.decomposePar.solver
echo "decomposePar OK"

echo "=== foamRun ({n} cores, parallel) ==="
mpirun --allow-run-as-root -np {n} foamRun -solver incompressibleFluid -parallel 2>&1 | tee log.foamRun
echo "foamRun OK"

echo "=== reconstructPar ==="
reconstructPar -latestTime 2>&1 | tee log.reconstructPar
echo "reconstructPar OK"

echo "=== Post-Processing ==="
foamPostProcess -func wallShearStress -latestTime 2>&1 | tee log.wallShearStress || echo "wallShearStress failed"
foamPostProcess -func yPlus -latestTime 2>&1 | tee log.yPlus || echo "yPlus failed"
echo "Post-processing OK"

echo "=== removing processor directories ==="
rm -rf processor*
echo "cleanup OK"
"""

    def __init__(self, case_dir: str, wsl_distro: str | None, n_cores: int = 1):
        self._case_dir = case_dir
        self._runner   = WSLRunner(wsl_distro)
        self._n_cores  = max(1, n_cores)

    def run(self, on_line: callable = None) -> tuple[bool, str]:
        log.info(f"Starting foamRun in {self._case_dir} ({self._n_cores} core(s))")
        if self._n_cores > 1:
            script = self._SCRIPT_PARALLEL.format(n=self._n_cores)
        else:
            script = self._SCRIPT_SERIAL
        return self._runner.run_command(
            script,
            cwd_windows=self._case_dir,
            timeout=7200,
            log_prefix="[SOLVER] ",
            on_line=on_line,
        )
