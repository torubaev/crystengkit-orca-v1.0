"""Common molecule-rendering primitives used by package-aware PyVista tools."""

from __future__ import annotations

from typing import Any, Dict


def molecule_material_parameters() -> Dict[str, object]:
    """Return the builder preview's standard ball-and-stick material."""
    return {
        "lighting": True,
        "smooth_shading": True,
        "ambient": 0.50,
        "diffuse": 0.62,
        "specular": 0.18,
        "specular_power": 20,
    }


def add_mesh_safe(plotter: Any, mesh: Any, **kwargs: Any) -> Any:
    """Add a mesh, retrying without newer PBR keywords on older PyVista."""
    try:
        return plotter.add_mesh(mesh, **kwargs)
    except TypeError:
        safe_kwargs = dict(kwargs)
        safe_kwargs.pop("pbr", None)
        safe_kwargs.pop("metallic", None)
        safe_kwargs.pop("roughness", None)
        return plotter.add_mesh(mesh, **safe_kwargs)


def cylinder_between(pv_module: Any, p1: Any, p2: Any, radius: float = 0.075, resolution: int = 48) -> Any:
    """Create a capped cylinder between two points, or ``None`` at zero length."""
    import numpy as np

    start = np.asarray(p1, dtype=float)
    end = np.asarray(p2, dtype=float)
    vector = end - start
    length = float(np.linalg.norm(vector))
    if length <= 1.0e-8:
        return None
    return pv_module.Cylinder(
        center=tuple((start + end) / 2.0),
        direction=tuple(vector / length),
        radius=radius,
        height=length,
        resolution=resolution,
        capping=True,
    )
