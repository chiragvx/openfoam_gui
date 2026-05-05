import logging
from pathlib import Path

import trimesh
import config

log = logging.getLogger(__name__)


class GeometryProcessor:
    """Load, optionally repair and scale, then export as ASCII STL for OpenFOAM."""

    def prepare(self, source_path: str, scale_mm_to_m: bool = False) -> str:
        """
        Returns the path to a clean ASCII STL file ready for snappyHexMesh.
        The file is written to cases/geometry/<stem>.stl (created on first use).
        """
        src = Path(source_path)
        geom_dir = config.CASES_DIR / "geometry"
        geom_dir.mkdir(parents=True, exist_ok=True)

        mesh = trimesh.load(str(src), force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError(f"Could not load a single mesh from {src.name}")

        if scale_mm_to_m:
            mesh.apply_scale(0.001)
            log.info("Applied mm→m scale (0.001)")

        if not mesh.is_watertight:
            log.warning("Mesh is not watertight — attempting repair")
            trimesh.repair.fill_holes(mesh)
            trimesh.repair.fix_winding(mesh)
            if not mesh.is_watertight:
                log.warning("Mesh still not watertight after repair; snappyHexMesh may struggle")

        dest = geom_dir / (src.stem + ".stl")
        mesh.export(str(dest), file_type="stl_ascii")
        log.info(f"Geometry prepared: {dest}  ({len(mesh.faces)} triangles)")
        return str(dest)

    def get_info(self, stl_path: str) -> dict:
        mesh = trimesh.load(stl_path, force="mesh")
        b = mesh.bounds  # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
        return {
            "triangles": len(mesh.faces),
            "xmin": float(b[0][0]), "xmax": float(b[1][0]),
            "ymin": float(b[0][1]), "ymax": float(b[1][1]),
            "zmin": float(b[0][2]), "zmax": float(b[1][2]),
        }

    def compute_domain(self, stl_path: str) -> dict:
        """
        Wind-tunnel bounding box for blockMesh.
        Flow travels in the +X direction; AoA rotates the velocity vector.
        """
        info = self.get_info(stl_path)
        span = max(
            info["xmax"] - info["xmin"],
            info["ymax"] - info["ymin"],
            info["zmax"] - info["zmin"],
        )
        import config as cfg
        return {
            "xmin": info["xmin"] - cfg.DOMAIN_UPSTREAM_FACTOR   * span,
            "xmax": info["xmax"] + cfg.DOMAIN_DOWNSTREAM_FACTOR * span,
            "ymin": info["ymin"] - cfg.DOMAIN_LATERAL_FACTOR    * span,
            "ymax": info["ymax"] + cfg.DOMAIN_LATERAL_FACTOR    * span,
            "zmin": info["zmin"] - cfg.DOMAIN_VERTICAL_FACTOR   * span,
            "zmax": info["zmax"] + cfg.DOMAIN_VERTICAL_FACTOR   * span,
        }
