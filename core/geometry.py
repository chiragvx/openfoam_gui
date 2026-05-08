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
        # Export as binary STL for performance and robustness
        mesh.export(str(dest), file_type="stl")
        log.info(f"Geometry prepared: {dest}  ({len(mesh.faces)} triangles, binary)")
        return str(dest)
    def rotate(self, stl_path: str, axis: str, degrees: float):
        """Rotates the STL mesh around a given axis through its centroid and overwrites the file."""
        import numpy as np
        mesh = trimesh.load(stl_path, force="mesh")
        angle = np.radians(degrees)
        
        # Identity matrix for axis vector
        axis_vec = [0.0, 0.0, 0.0]
        if axis == "X": axis_vec[0] = 1.0
        elif axis == "Y": axis_vec[1] = 1.0
        else: axis_vec[2] = 1.0
        
        # Rotate about the centroid
        rot = trimesh.transformations.rotation_matrix(angle, axis_vec, point=mesh.centroid)
        mesh.apply_transform(rot)
        mesh.export(stl_path, file_type="stl")
        log.info(f"Rotated {axis} by {degrees} deg about centroid: {stl_path}")

    def scale(self, stl_path: str, factor: float):
        """Scales the STL mesh by a factor and overwrites the file."""
        mesh = trimesh.load(stl_path, force="mesh")
        mesh.apply_scale(factor)
        mesh.export(stl_path, file_type="stl")
        log.info(f"Scaled by {factor}: {stl_path}")

    def estimate_aero_reference(self, stl_path: str, n_slices: int = 60) -> dict:
        """
        Estimate aerodynamic reference quantities from STL geometry.

        Convention (must match your OpenFOAM setup):
            nose → +X   span → Y   up → +Z

        Algorithm
        ---------
        1. Slice the mesh at ``n_slices`` evenly-spaced Y planes.
        2. At each slice, measure chord = (Xmax − Xmin) of the cross-section.
        3. Integrate numerically:
               Aref = ∫ c(y) dy          (planform area)
               MAC  = ∫ c(y)² dy / Aref  (mean aerodynamic chord)
        4. If fewer than 3 valid slices are obtained (non-watertight mesh),
           fall back to bounding-box approximations.

        Returns
        -------
        dict with keys: span, mac, aref, chord_root, chord_tip, method
        """
        import numpy as np

        mesh = trimesh.load(stl_path, force="mesh")
        b = mesh.bounds          # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
        xmin, ymin, zmin = b[0]
        xmax, ymax, zmax = b[1]

        span      = ymax - ymin
        bbox_chord = xmax - xmin

        # Guard: degenerate geometry
        if span < 1e-6 or bbox_chord < 1e-6:
            log.warning("estimate_aero_reference: degenerate bounding box")
            return dict(span=span, mac=bbox_chord, aref=span * bbox_chord,
                        chord_root=bbox_chord, chord_tip=bbox_chord, method="bbox")

        # Slice positions — avoid the very tips (often closed caps give false results)
        margin   = span * 0.02
        y_pos    = np.linspace(ymin + margin, ymax - margin, n_slices)
        chords   = []
        y_valid  = []

        for y in y_pos:
            try:
                sec = mesh.section(
                    plane_origin=[0.0, float(y), 0.0],
                    plane_normal=[0.0, 1.0, 0.0],
                )
                if sec is None or len(sec.vertices) == 0:
                    continue
                xs = sec.vertices[:, 0]
                c  = float(xs.max() - xs.min())
                if c > 1e-6:
                    chords.append(c)
                    y_valid.append(float(y))
            except Exception:
                continue  # skip bad slices silently

        if len(chords) < 3:
            # Fall back: use bounding-box projected area
            log.warning(
                f"estimate_aero_reference: only {len(chords)} valid slices — "
                "using bounding-box fallback"
            )
            aref = span * bbox_chord
            mac  = bbox_chord
            return dict(span=span, mac=mac, aref=aref,
                        chord_root=bbox_chord, chord_tip=bbox_chord, method="bbox")

        chords  = np.array(chords)
        y_valid = np.array(y_valid)

        # np.trapz was renamed to np.trapezoid in NumPy 2.0
        _trapz = getattr(np, "trapezoid", None) or np.trapz

        aref = float(_trapz(chords,    y_valid))
        mac  = float(_trapz(chords**2, y_valid) / aref) if aref > 1e-9 else bbox_chord

        log.info(
            f"estimate_aero_reference: span={span:.4f} m  "
            f"Aref={aref:.4f} m²  MAC={mac:.4f} m  "
            f"(from {len(chords)} slices)"
        )
        return dict(
            span       = span,
            mac        = mac,
            aref       = aref,
            chord_root = float(chords[0]),
            chord_tip  = float(chords[-1]),
            method     = "integrated",
        )

    def get_info(self, stl_path: str) -> dict:
        mesh = trimesh.load(stl_path, force="mesh")
        b = mesh.bounds  # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
        return {
            "triangles": len(mesh.faces),
            "xmin": float(b[0][0]), "xmax": float(b[1][0]),
            "ymin": float(b[0][1]), "ymax": float(b[1][1]),
            "zmin": float(b[0][2]), "zmax": float(b[1][2]),
        }

    def compute_domain(self, stl_path: str, altitude: float = 100.0) -> dict:
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
        
        # Ground effect: If altitude is 0, floor is exactly at the bottom of the model
        zmin = info["zmin"] if altitude <= 0.01 else info["zmin"] - cfg.DOMAIN_VERTICAL_FACTOR * span
        
        return {
            "xmin": info["xmin"] - cfg.DOMAIN_UPSTREAM_FACTOR   * span,
            "xmax": info["xmax"] + cfg.DOMAIN_DOWNSTREAM_FACTOR * span,
            "ymin": info["ymin"] - cfg.DOMAIN_LATERAL_FACTOR    * span,
            "ymax": info["ymax"] + cfg.DOMAIN_LATERAL_FACTOR    * span,
            "zmin": zmin,
            "zmax": info["zmax"] + cfg.DOMAIN_VERTICAL_FACTOR   * span,
        }
