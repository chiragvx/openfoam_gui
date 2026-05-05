import logging
from pathlib import Path

import pyvista as pv

log = logging.getLogger(__name__)


class ResultsReader:
    """
    Wraps pyvista.OpenFOAMReader.
    The case directory must contain a case.foam touchfile.
    """

    def __init__(self, case_dir: str):
        foam_file = str(Path(case_dir) / "case.foam")
        self._reader = pv.OpenFOAMReader(foam_file)
        log.info(f"OpenFOAMReader ready — time steps: {self._reader.time_values}")

    @property
    def time_values(self) -> list:
        return list(self._reader.time_values)

    def get_boundary_surface(self, time_value: float | None = None) -> pv.DataSet:
        tv = time_value if time_value is not None else self._reader.time_values[-1]
        self._reader.set_active_time_value(tv)
        data = self._reader.read()
        return data["boundary"]

    def available_fields(self, time_value: float | None = None) -> list[str]:
        return list(self.get_boundary_surface(time_value).array_names)

    @staticmethod
    def read_force_coeffs(case_dir: str) -> dict | None:
        """
        Parse postProcessing/forceCoeffs/<t>/forceCoeffs.dat.

        Returns dict: {time, Cd, Cs, Cl, CmRoll, CmPitch, CmYaw}
        using the last (most converged) data row, or None on failure.
        """
        pp = Path(case_dir) / "postProcessing" / "forceCoeffs"
        if not pp.exists():
            log.warning(f"postProcessing/forceCoeffs not found in {case_dir}")
            return None

        # subdirs are named after the start time (usually "0")
        subdirs = sorted(
            (d for d in pp.iterdir() if d.is_dir()),
            key=lambda d: float(d.name) if d.name.replace(".", "", 1).lstrip("-").isdigit() else 0,
        )
        if not subdirs:
            log.warning("forceCoeffs: no time subdirectory found")
            return None

        dat_file = subdirs[0] / "forceCoeffs.dat"
        if not dat_file.exists():
            log.warning(f"forceCoeffs.dat missing in {subdirs[0]}")
            return None

        rows: list[list[float]] = []
        with open(dat_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    rows.append([float(v) for v in line.split()])
                except ValueError:
                    continue

        if not rows:
            log.warning("forceCoeffs.dat contained no numeric data")
            return None

        last = rows[-1]
        # OF11 columns: Time  Cm  Cd  Cl  Cl(f)  Cl(r)
        # Older OF columns: Time Cd Cs Cl CmRoll CmPitch CmYaw ...
        # Detect layout by column count.
        try:
            if len(last) == 6:
                # OF11 compact format
                return {
                    "time":    last[0],
                    "CmPitch": last[1],
                    "Cd":      last[2],
                    "Cl":      last[3],
                }
            else:
                # Legacy 7+ column format
                return {
                    "time":    last[0],
                    "Cd":      last[1],
                    "Cs":      last[2],
                    "Cl":      last[3],
                    "CmRoll":  last[4],
                    "CmPitch": last[5],
                    "CmYaw":   last[6],
                }
        except IndexError:
            log.warning(f"Unexpected column count ({len(last)}) in forceCoeffs.dat")
            return None
