class UnitConverter:
    # BASE UNIT IS METERS (m)
    FACTORS = {
        "m": 1.0,
        "cm": 0.01,
        "mm": 0.001,
        "in": 0.0254,
        "ft": 0.3048
    }
    
    AREA_FACTORS = {
        "m": 1.0,
        "cm": 0.0001,
        "mm": 0.000001,
        "in": 0.00064516,
        "ft": 0.092903
    }

    @classmethod
    def from_base(cls, value_m: float, to_unit: str) -> float:
        return value_m / cls.FACTORS.get(to_unit, 1.0)

    @classmethod
    def to_base(cls, value: float, from_unit: str) -> float:
        return value * cls.FACTORS.get(from_unit, 1.0)

    @classmethod
    def area_from_base(cls, value_m2: float, to_unit: str) -> float:
        return value_m2 / cls.AREA_FACTORS.get(to_unit, 1.0)

    @classmethod
    def area_to_base(cls, value: float, from_unit: str) -> float:
        return value * cls.AREA_FACTORS.get(from_unit, 1.0)

    @classmethod
    def format_length(cls, value_m: float, unit: str) -> str:
        val = cls.from_base(value_m, unit)
        return f"{val:.3f} {unit}"

