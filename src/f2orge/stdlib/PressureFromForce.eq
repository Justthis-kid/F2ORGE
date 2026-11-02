eq PressureFromForce {
    description = "Uniform pressure from a normal force distributed over an area."

    F : N "normal force"
    A : m^2 "area"
    p : Pa "pressure"

    p = F / A
}
