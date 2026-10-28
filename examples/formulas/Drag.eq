eq Drag {
    description = "Aerodynamic drag: D = 1/2 rho V^2 S CD."

    rho : kg/m^3 "air density"
    V : m/s "airspeed"
    S : m^2 "reference area"
    CD : dimensionless "drag coefficient"
    D : N "drag force"

    D = 0.5 * rho * V^2 * S * CD
}
