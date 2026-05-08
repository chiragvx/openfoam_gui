import logging
import math
import shutil
from datetime import datetime
from pathlib import Path

import jinja2

import config
from core.geometry import GeometryProcessor

log = logging.getLogger(__name__)


class CaseGenerator:
    """
    Build a complete OpenFOAM case directory from Jinja2 templates.

    Output layout:
        cases/run_YYYYMMDD_HHMMSS/
            0/               initial conditions
            constant/
                triSurface/  aircraft.stl
                transportProperties
                turbulenceProperties
            system/          all mesh and solver dicts
            case.foam        touchfile for PyVista OpenFOAMReader
    """

    TEMPLATE_MAP = [
        ("system/blockMeshDict.j2",             "system/blockMeshDict"),
        ("system/snappyHexMeshDict.j2",         "system/snappyHexMeshDict"),
        ("system/surfaceFeatureExtractDict.j2", "system/surfaceFeatureExtractDict"),
        ("system/surfaceFeaturesDict.j2",       "system/surfaceFeaturesDict"),
        ("system/controlDict.j2",               "system/controlDict"),
        ("system/fvSchemes.j2",                 "system/fvSchemes"),
        ("system/fvSolution.j2",                "system/fvSolution"),
        ("system/decomposeParDict.j2",          "system/decomposeParDict"),
        ("constant/transportProperties.j2",     "constant/transportProperties"),
        ("constant/turbulenceProperties.j2",    "constant/turbulenceProperties"),
        ("0/U.j2",                              "0/U"),
        ("0/p.j2",                              "0/p"),
        ("0/k.j2",                              "0/k"),
        ("0/omega.j2",                          "0/omega"),
        ("0/nut.j2",                            "0/nut"),
    ]

    def __init__(self, stl_path: str, conditions: dict, mesh_settings: dict):
        self._stl_path      = stl_path
        self._conditions    = conditions
        self._mesh_settings = mesh_settings
        self._jinja = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(config.TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=jinja2.StrictUndefined,
        )

    def generate(self, custom_folder: str | None = None) -> str:
        """Create case directory, render all templates, return its path."""
        if custom_folder:
            case_dir = config.CASES_DIR / custom_folder
        else:
            stamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
            case_dir = config.CASES_DIR / f"run_{stamp}"


        (case_dir / "0").mkdir(parents=True)
        (case_dir / "constant" / "triSurface").mkdir(parents=True)
        (case_dir / "system").mkdir(parents=True)

        # Copy STL into triSurface
        shutil.copy2(self._stl_path, case_dir / "constant" / "triSurface" / "aircraft.stl")

        # Build template context
        geom = GeometryProcessor()
        domain = geom.compute_domain(
            self._stl_path, 
            altitude=self._conditions.get("altitude", 100.0)
        )
        ctx = self._build_context(domain)

        # Determine templates to render
        mesher = self._mesh_settings.get("mesher", config.DEFAULT_MESHER)
        templates_to_render = []
        
        # Base templates (always needed)
        base_templates = [
            ("system/controlDict.j2",               "system/controlDict"),
            ("system/fvSchemes.j2",                 "system/fvSchemes"),
            ("system/fvSolution.j2",                "system/fvSolution"),
            ("system/decomposeParDict.j2",          "system/decomposeParDict"),
            ("constant/transportProperties.j2",     "constant/transportProperties"),
            ("constant/turbulenceProperties.j2",    "constant/turbulenceProperties"),
            ("0/U.j2",                              "0/U"),
            ("0/p.j2",                              "0/p"),
            ("0/k.j2",                              "0/k"),
            ("0/omega.j2",                          "0/omega"),
            ("0/nut.j2",                            "0/nut"),
        ]
        templates_to_render.extend(base_templates)

        if mesher == "cfmesh":
            templates_to_render.append(("system/meshDict.j2", "system/meshDict"))
            # cfMesh still often needs blockMesh for the background domain, 
            # though cartesianMesh can generate its own background if configured.
            # In our case, we'll keep blockMesh for consistency.
            templates_to_render.append(("system/blockMeshDict.j2", "system/blockMeshDict"))
        else:
            # snappyHexMesh pipeline
            templates_to_render.append(("system/blockMeshDict.j2", "system/blockMeshDict"))
            templates_to_render.append(("system/snappyHexMeshDict.j2", "system/snappyHexMeshDict"))
            templates_to_render.append(("system/surfaceFeatureExtractDict.j2", "system/surfaceFeatureExtractDict"))
            templates_to_render.append(("system/surfaceFeaturesDict.j2", "system/surfaceFeaturesDict"))

        # Render every template
        for tmpl_name, rel_dest in templates_to_render:
            tmpl = self._jinja.get_template(tmpl_name)
            dest = case_dir / rel_dest
            dest.write_text(tmpl.render(**ctx), encoding="utf-8")
            log.debug(f"  rendered {rel_dest}")

        # Touchfile required by pv.OpenFOAMReader
        (case_dir / "case.foam").touch()

        log.info(f"Case generated: {case_dir} using {mesher}")
        return str(case_dir)

    # ------------------------------------------------------------------
    def _build_context(self, domain: dict) -> dict:
        c = self._conditions
        m = self._mesh_settings
        U = c["airspeed"]

        k_init     = self._k(U)
        omega_init = self._omega(U, c["nu"])

        # AoA-corrected lift/drag unit vectors in the XZ-plane.
        # dragDir  = freestream direction  = ( cos α,  0,  sin α )
        # liftDir  = perpendicular upward  = (-sin α,  0,  cos α )
        aoa_rad = math.radians(c.get("aoa_deg", 0.0))
        drag_x =  round(math.cos(aoa_rad), 6)
        drag_z =  round(math.sin(aoa_rad), 6)
        lift_x =  round(-math.sin(aoa_rad), 6)
        lift_z =  round(math.cos(aoa_rad), 6)

        return {
            **domain,
            # Background mesh cell counts
            "bg_cells_x": 20,
            "bg_cells_y": 8,
            "bg_cells_z": 8,
            # Geometry refinement
            "ref_min":  m["refinement_min"],
            "ref_max":  m["refinement_max"],
            "n_layers": m["surface_layers"],
            # cfMesh specific
            "cfmesh_cell_size": m.get("cfmesh_cell_size", config.DEFAULT_CFMESH_CELL_SIZE),
            # Velocity components (AoA rotation in XZ-plane)
            "Ux": c["Ux"],
            "Uy": c["Uy"],
            "Uz": c["Uz"],
            # Transport
            "nu":  c["nu"],
            "rho": c["rho"],
            # Turbulence
            "k_init":     k_init,
            "omega_init": omega_init,
            # Parallelism
            "n_cores": m.get("n_cores", 1),
            # Solver control
            "end_time":       m.get("end_time", config.DEFAULT_END_TIME),
            "write_interval": config.DEFAULT_WRITE_INTERVAL,

            # forceCoeffs reference values
            "U_mag":  U,
            "drag_x": drag_x,
            "drag_z": drag_z,
            "lift_x": lift_x,
            "lift_z": lift_z,
            "lRef":   c.get("lRef", 0.25),
            "Aref":   c.get("Aref", 0.15),
        }

    @staticmethod
    def update_case_conditions(case_dir: str, conditions: dict):
        """Update 0/U and system/controlDict in an existing case without re-meshing."""
        from core.geometry import GeometryProcessor
        log.info(f"Updating flow conditions in {case_dir}...")
        
        # We need the domain bounds to calculate the context again
        # For simplicity, we assume the geometry is aircraft.stl
        case_path = Path(case_dir)
        stl_path = case_path / "constant" / "triSurface" / "aircraft.stl"
        if not stl_path.exists():
            log.warning("Original STL not found in case, cannot update conditions precisely.")
            return

        geom = GeometryProcessor()
        domain = geom.compute_domain(str(stl_path), altitude=conditions.get("altitude", 100.0))
        
        # Instantiate a temporary generator to use its context logic
        # mesh_settings aren't needed for U/controlDict update
        gen = CaseGenerator(str(stl_path), conditions, {"refinement_min":1, "refinement_max":1, "surface_layers":1})
        ctx = gen._build_context(domain)

        # Update 0/U
        u_tmpl = gen._jinja.get_template("0/U.j2")
        (case_path / "0" / "U").write_text(u_tmpl.render(**ctx), encoding="utf-8")
        
        # Update system/controlDict (for forceCoeffs)
        cd_tmpl = gen._jinja.get_template("system/controlDict.j2")
        (case_path / "system" / "controlDict").write_text(cd_tmpl.render(**ctx), encoding="utf-8")
        
        log.info(f"Case updated with new AoA: {conditions.get('aoa_deg')} deg")

    @staticmethod
    def _k(U: float, I: float = 0.001) -> float:
        return max(1.5 * (U * I) ** 2, 1e-10)

    @staticmethod
    def _omega(U: float, nu: float, I: float = 0.001) -> float:
        k = max(1.5 * (U * I) ** 2, 1e-10)
        L, Cmu = 0.01, 0.09
        return math.sqrt(k) / (Cmu ** 0.25 * L)
