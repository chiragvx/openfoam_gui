import logging
import subprocess
from pathlib import Path

import config

log = logging.getLogger(__name__)


class WSLRunner:
    """
    Execute bash scripts inside WSL2.

    Path translation:
        Windows  C:\\Users\\Chirag\\...\\cases\\run_xyz
        WSL2     /mnt/c/Users/Chirag/.../cases/run_xyz
    """

    def __init__(self, wsl_distro: str | None = None):
        self._distro = wsl_distro

    # ------------------------------------------------------------------
    def windows_to_wsl_path(self, windows_path: str) -> str:
        p = Path(windows_path)
        drive = p.drive.lower().rstrip(":")          # "C:" → "c"
        rest  = "/".join(p.parts[1:])                # strip drive, join with /
        return f"/mnt/{drive}/{rest}"

    def _prefix(self) -> list[str]:
        cmd = ["wsl"]
        if self._distro:
            cmd += ["-d", self._distro]
        return cmd

    # ------------------------------------------------------------------
    def validate_wsl(self) -> tuple[bool, str]:
        """Check that WSL2 + OpenFOAM are reachable. Call at app startup."""
        try:
            result = subprocess.run(
                self._prefix() + ["bash", "-c",
                    f"source {config.WSL_OPENFOAM_SOURCE} 2>&1 && "
                    "simpleFoam -help 2>&1 | head -1"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, "WSL2 + OpenFOAM OK"
            return False, f"OpenFOAM not found: {result.stderr.strip()}"
        except FileNotFoundError:
            return False, "wsl.exe not found — is WSL2 installed?"
        except subprocess.TimeoutExpired:
            return False, "WSL2 validation timed out"

    # ------------------------------------------------------------------
    def run_command(
        self,
        bash_script: str,
        cwd_windows: str | None = None,
        timeout: int = 7200,
        log_prefix: str = "",
    ) -> tuple[bool, str]:
        """
        Run a bash script inside WSL2, streaming output to the logger.
        Returns (success, last_error_line).
        """
        preamble = [f"source {config.WSL_OPENFOAM_SOURCE}"]
        if cwd_windows:
            wsl_cwd = self.windows_to_wsl_path(cwd_windows)
            preamble.append(f"cd '{wsl_cwd}'")
        full_script = "\n".join(preamble + [bash_script])

        cmd = self._prefix() + ["bash", "-c", full_script]
        log.debug(f"WSL cmd: {bash_script[:120]!r}")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            last_error = ""
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                log.info(f"{log_prefix}{line}")
                upper = line.upper()
                if "ERROR" in upper or "FATAL" in upper:
                    last_error = line
            proc.wait(timeout=timeout)
            if proc.returncode != 0:
                log.error(f"Process exited with code {proc.returncode}")
                return False, last_error or f"exit code {proc.returncode}"
            return True, ""
        except subprocess.TimeoutExpired:
            proc.kill()
            msg = f"Timed out after {timeout}s"
            log.error(msg)
            return False, msg
        except FileNotFoundError:
            msg = "wsl.exe not found — is WSL2 installed?"
            log.error(msg)
            return False, msg
        except Exception as exc:
            log.error(f"WSL runner error: {exc}")
            return False, str(exc)
