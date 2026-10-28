eq Lift {
    description = "Aerodynamic lift of a wing: L = 1/2 rho V^2 S CL."

    rho : kg/m^3 "air density"
    V : m/s "airspeed"
    S : m^2 "wing area"
    CL : dimensionless "lift coefficient"
    L : N "lift force"

    L = 0.5 * rho * V^2 * S * CL
}
