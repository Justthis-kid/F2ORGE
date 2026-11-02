eq SpringForce {
    description = "Linear spring force magnitude from Hooke's law."

    k : N/m "spring stiffness"
    x : m "displacement from equilibrium"
    F : N "spring force magnitude"

    F = k * x
}
