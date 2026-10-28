eq IdealGas {
    description = "Ideal gas law, P V = n R T."

    P : Pa "pressure"
    V : m^3 "volume"
    n : mol "amount of gas"
    T : K "absolute temperature"

    P = n * R * T / V
}
