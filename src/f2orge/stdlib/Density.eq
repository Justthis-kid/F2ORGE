eq Density {
    description = "Mass density from mass and volume."

    m : kg "mass"
    V : m^3 "volume"
    rho : kg/m^3 "mass density"

    rho = m / V
}
