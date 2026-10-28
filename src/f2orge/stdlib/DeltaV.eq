eq DeltaV {
    description = "Tsiolkovsky rocket equation: velocity change from propellant burned."
    source = "Tsiolkovsky (1903)"

    Isp : s "specific impulse"
    m0 : kg "initial mass (with propellant)"
    mf : kg "final mass (propellant burned)"
    dv : m/s "velocity change"

    dv = Isp * g * ln(m0 / mf)
}
