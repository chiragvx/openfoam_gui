import logging
from pathlib import Path

import pyvista as pv

log = logging.getLogger(__name__)


class ResultsReader:
    """
    Wraps pyvista.OpenFOAMReader and provides parsers for postProcessing data.
    The case directory must contain a case.foam touchfile.
    """

    def __init__(self, case_dir: str):
        foam_file = str(Path(case_dir) / "case.foam")
        self._reader = pv.OpenFOAMReader(foam_file)
        self._reader.enable_all_cell_arrays()
        self._reader.enable_all_point_arrays()
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
        Returns the last row as a dict, including reference values from header.
        """
        dat_file = ResultsReader._find_latest_dat(case_dir, "forceCoeffs")
        if not dat_file:
            return None

        header_ref, col_map, rows = ResultsReader._parse_dat_file(dat_file)
        if not rows:
            return None

        last = rows[-1]
        result = {}
        
        # Standard columns
        mapping = {
            "Time": "time", "Cd": "Cd", "Cs": "Cs", "Cl": "Cl",
            "CmRoll": "CmRoll", "CmPitch": "CmPitch", "CmYaw": "CmYaw"
        }
        # Some versions use "Cm" for pitch
        if "Cm" in col_map and "CmPitch" not in col_map:
            mapping["Cm"] = "CmPitch"

        for of_name, target in mapping.items():
            if of_name in col_map:
                result[target] = last[col_map[of_name]]
            else:
                result[target] = 0.0

        # Positional fallbacks for headers-less files
        if not col_map:
            if len(last) == 6:
                result.update({"time": last[0], "CmPitch": last[1], "Cd": last[2], "Cl": last[3]})
            elif len(last) >= 7:
                result.update({"time": last[0], "Cd": last[1], "Cs": last[2], "Cl": last[3], "CmRoll": last[4], "CmPitch": last[5]})

        # Reference values
        result["Aref_sim"] = header_ref.get("Aref")
        result["lRef_sim"] = header_ref.get("lRef")
        result["U_sim"]    = header_ref.get("magUInf")
        result["rho_sim"]  = header_ref.get("rhoInf")
        return result

    @staticmethod
    def read_residuals(case_dir: str) -> dict | None:
        """Parse postProcessing/residuals/<t>/residuals.dat. Returns last row."""
        dat_file = ResultsReader._find_latest_dat(case_dir, "residuals")
        if not dat_file: return None
        _, col_map, rows = ResultsReader._parse_dat_file(dat_file)
        if not rows: return None
        
        last = rows[-1]
        # Clean up column names (remove tabs/spaces)
        return {name.strip(): last[idx] for name, idx in col_map.items()}

    @staticmethod
    def read_y_plus(case_dir: str) -> dict | None:
        """Parse postProcessing/yPlus/<t>/yPlus.dat. Returns last row stats."""
        dat_file = ResultsReader._find_latest_dat(case_dir, "yPlus")
        if not dat_file: return None
        rows = []
        with open(dat_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                parts = line.split()
                if len(parts) >= 5: # Time, Patch, Min, Max, Average
                    try:
                        rows.append({
                            "time": float(parts[0]),
                            "patch": parts[1],
                            "min": float(parts[2]),
                            "max": float(parts[3]),
                            "average": float(parts[4])
                        })
                    except ValueError: continue
        return rows[-1] if rows else None

    @staticmethod
    def _find_latest_dat(case_dir: str, func_name: str) -> Path | None:
        pp = Path(case_dir) / "postProcessing" / func_name
        if not pp.exists(): return None
        subdirs = sorted(
            (d for d in pp.iterdir() if d.is_dir()),
            key=lambda d: float(d.name) if d.name.replace(".", "", 1).lstrip("-").isdigit() else 0,
        )
        if not subdirs: return None
        dat_file = subdirs[0] / f"{func_name}.dat"
        return dat_file if dat_file.exists() else None

    @staticmethod
    def _parse_dat_file(path: Path):
        ref = {}
        col_map = {}
        rows = []
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line: continue
                if line.startswith("#"):
                    # Header metadata
                    for key in ("Aref", "lRef", "magUInf", "rhoInf"):
                        if f"# {key}" in line:
                            try: ref[key] = float(line.split()[-1])
                            except: pass
                    # Columns
                    stripped = line.lstrip("# ").strip()
                    if stripped.lower().startswith("time"):
                        names = stripped.split()
                        col_map = {n.strip(): i for i, n in enumerate(names)}
                    continue
                try:
                    rows.append([float(v) for v in line.split()])
                except: continue
        return ref, col_map, rows
