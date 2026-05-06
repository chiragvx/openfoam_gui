import logging
import math
from dataclasses import dataclass
from typing import List, Dict, Any

log = logging.getLogger(__name__)

@dataclass
class SweepCondition:
    airspeed: float
    aoa_deg: float
    # We could add altitude here too if needed

class BatchManager:
    """
    Handles the generation of parametric sweep conditions and provides
    utilities for managing a list of CFD runs.
    """

    @staticmethod
    def generate_grid(speed_range: tuple, aoa_range: tuple) -> List[SweepCondition]:
        """
        Generate a Cartesian product of speed and AoA ranges.
        Ranges are (min, max, step). If step is 0 or min==max, it's a single value.
        """
        speeds = BatchManager._linspace(speed_range)
        aoas   = BatchManager._linspace(aoa_range)
        
        grid = []
        for s in speeds:
            for a in aoas:
                grid.append(SweepCondition(airspeed=round(s, 2), aoa_deg=round(a, 2)))
        
        return grid

    @staticmethod
    def _linspace(r: tuple) -> List[float]:
        mi, ma, step = r
        if step <= 0 or mi >= ma:
            return [mi]
        
        vals = []
        curr = mi
        while curr <= ma + (step * 0.01): # Small epsilon for float precision
            vals.append(curr)
            curr += step
        return vals

    @staticmethod
    def get_run_name(index: int, condition: SweepCondition) -> str:
        """Generate a folder-safe name for a specific run."""
        s_str = str(int(condition.airspeed))
        a_str = str(int(condition.aoa_deg)).replace("-", "m")
        return f"run_{index:02d}_S{s_str}_A{a_str}"
