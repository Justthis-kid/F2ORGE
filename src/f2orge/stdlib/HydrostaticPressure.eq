eq HydrostaticPressure {
    description = "Gauge pressure increase with depth in a static fluid."

    rho : kg/m^3 "fluid density"
    h : m "depth below the surface"
    deltaP : Pa "gauge pressure increase"

    deltaP = rho * g * h
}
