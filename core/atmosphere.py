import math


class ISAAtmosphere:
    """
    ICAO International Standard Atmosphere, troposphere (0-11 000 m).

    All properties at the specified altitude:
        temperature           K
        pressure              Pa
        density               kg/m³
        dynamic_viscosity     Pa·s
        kinematic_viscosity   m²/s
        speed_of_sound        m/s
    """

    T0 = 288.15      # K  sea-level temperature
    P0 = 101_325.0   # Pa sea-level pressure
    L  = 0.0065      # K/m lapse rate
    R  = 287.05      # J/(kg·K)
    g  = 9.80665     # m/s²
    gamma = 1.4

    def __init__(self, altitude_m: float):
        self.altitude = altitude_m
        h = min(altitude_m, 11_000.0)
        T = self.T0 - self.L * h
        P = self.P0 * (T / self.T0) ** (self.g / (self.L * self.R))

        self.temperature = T
        self.pressure    = P
        self.density     = P / (self.R * T)

        # Sutherland's law
        T_ref, mu_ref, S = 273.15, 1.716e-5, 110.4
        self.dynamic_viscosity   = mu_ref * (T / T_ref) ** 1.5 * (T_ref + S) / (T + S)
        self.kinematic_viscosity = self.dynamic_viscosity / self.density
        self.speed_of_sound      = math.sqrt(self.gamma * self.R * T)
