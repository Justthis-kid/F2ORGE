"""User-defined domain objects written in F²ORGE source."""
import pytest

from f2orge import Interpreter
from f2orge.errors import ForgeError, ForgeNameError, UnitError
from helpers import error_of, run, run_it

CAR = """object Car {
    description = "A simple electric car"
    mass : kg = 1500 kg "kerb mass"
    v : m/s = 20 m/s
    energy() : J = 0.5 * mass * v^2 "kinetic energy"
    distance(seconds : s) : m = v * seconds "how far it travels"
}
"""
# A typed line is a property; a typed line with parentheses is a formula that states its unit.


def test_a_custom_object_builds_from_its_defaults():
    # Defaults print in their declared unit, as a declaration's values always do.
    assert run(CAR + "c = Car()\nc.mass\nc.v") == ["1500 kg", "20 m/s"]


def test_a_custom_object_evaluates_its_formulas():
    assert run(CAR + "c = Car()\nc.energy") == ["300000 J"]


def test_a_formula_with_parameters_is_called():
    assert run(CAR + "c = Car()\nc.distance(3 s)") == ["60 m"]


def test_arguments_override_defaults():
    assert run(CAR + "Car(mass = 900 kg).energy") == ["180000 J"]


def test_units_are_checked_at_construction_and_in_formulas():
    with pytest.raises(ForgeError, match="mass"):
        run(CAR + "Car(mass = 5 m)")
    # `distance(seconds : s) : m` says the parameter is a time and the result a length, so
    # kilograms are refused: v * 3 kg measures momentum, not distance.
    with pytest.raises(ForgeError, match="should give length"):
        run(CAR + "c = Car()\nc.distance(3 kg)")


def test_a_declared_result_unit_is_checked():
    src = """object Car {
    v : m/s = 10 m/s
    wrong(t : s) : J = v * t
}
Car().wrong(2 s)
"""
    with pytest.raises(ForgeError, match="should give energy"):
        run(src)


def test_a_required_property_is_reported_when_missing():
    src = """object Tank {
    volume : L
    mass = volume * 1 kg/L
}
Tank()
"""
    with pytest.raises(ForgeError, match="needs a value for 'volume'"):
        run(src)


def test_an_unknown_property_is_reported():
    with pytest.raises(ForgeNameError, match="no property named 'weight'"):
        run(CAR + "Car(weight = 5 kg)")


def test_a_formula_may_use_another_formula():
    src = """object Car {
    mass : kg = 1000 kg
    v : m/s = 10 m/s
    energy() : J = 0.5 * mass * v^2
    distance(consumption : J/m) : m = energy / consumption
}
Car().distance(540 J/m)
"""
    assert run(src) == ["92.59259259 m"]


def test_a_formula_using_an_undeclared_name_is_refused_at_definition():
    with pytest.raises(ForgeError, match="neither a property"):
        run("""object Bad {
    mass : kg = 1 kg
    energy = mass * velocity
}""")


def test_object_defaults_are_unit_checked():
    with pytest.raises(UnitError, match="expects kg"):
        run("""object Bad {
    mass : kg = 5 m
}""")


def test_object_and_property_documentation_is_kept():
    it, _ = run_it(CAR)
    kind = it.object_types["Car"]
    assert kind.doc == "A simple electric car"
    assert kind.properties["mass"].doc == "kerb mass"
    assert "energy" in kind.formulas and kind.formulas["energy"].doc == "kinetic energy"


def test_describe_lists_properties_and_formulas():
    it, _ = run_it(CAR)
    text = "\n".join(it.object_types["Car"].describe())
    assert "object Car" in text and "mass : kg = 1500 kg" in text and "distance(seconds)" in text


def test_objects_appear_in_the_browser_workspace():
    from f2orge.web_ide import _workspace
    from f2orge.desktop import DesktopSession

    session = DesktopSession()
    session.execute(CAR)
    objects = _workspace(session)["objects"]
    assert objects[0]["name"] == "Car"
    assert objects[0]["description"] == "A simple electric car"
    assert {p["name"] for p in objects[0]["properties"]} == {"mass", "v"}
    assert objects[0]["properties"][0]["required"] is False
    assert objects[0]["properties"][0]["default"] == "1500 kg"


def test_objects_appear_in_the_desktop_workspace_text():
    import inspect

    from f2orge import desktop

    source = inspect.getsource(desktop.launch_desktop_ide)
    assert 'values=("Object", name' in source
