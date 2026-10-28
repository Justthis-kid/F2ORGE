eq CircularOrbit {
    description = "Speed and period of a circular orbit around a body with gravitational parameter mu."

    mu : m^3/s^2 "gravitational parameter (try muEarth)"
    r : m "orbit radius from the body's centre"
    v : m/s "orbital speed"
    T : s "orbital period"

    v = sqrt(mu / r)
    T = 2 * pi * r / v
}
