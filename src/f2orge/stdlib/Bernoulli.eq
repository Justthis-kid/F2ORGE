eq Bernoulli {
    description = "Bernoulli's equation: steady, incompressible, inviscid flow along a streamline."
    source = "Bernoulli, Hydrodynamica (1738)"

    p1 : Pa "static pressure at point 1"
    v1 : m/s "speed at point 1"
    h1 : m "height at point 1"
    p2 : Pa "static pressure at point 2"
    v2 : m/s "speed at point 2"
    h2 : m "height at point 2"
    rho : kg/m^3 "fluid density"

    p1 + 0.5 * rho * v1^2 + rho * g * h1 = p2 + 0.5 * rho * v2^2 + rho * g * h2
}
