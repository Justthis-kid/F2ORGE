eq KineticEnergy {
    description = "Translational kinetic energy of a moving mass."

    m : kg "mass"
    v : m/s "speed"
    KE : J "kinetic energy"

    KE = 0.5 * m * v^2
}
