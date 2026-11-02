eq ElectricalPower {
    description = "Electrical power from voltage and current."

    V : V "voltage"
    I : A "current"
    P : W "electrical power"

    P = V * I
}
