import sys
sys.path.insert(0, "src")
from f2orge import Interpreter
from f2orge.errors import ForgeError

CASES = {
    "doc example": """def accel(t, v) { return -9.81 m/s^2 }
fall = dsolve(accel, 20 m/s, 0 s, 4 s)
n = count(fall[1])
fall[1][n - 1]
fall[0][n - 1]
plot(fall[0], fall[1])""",
    "bare expression": "dsolve(-9.81 m/s^2, 20 m/s, 0 s, 4 s)[0][0]",
    "decay": "def dv(t, v) { return -0.5 1/s * v }\nr = dsolve(dv, 10 m/s, 0 s, 2 s)\nn = count(r[1])\nr[1][n - 1]",
    "wrong derivative unit": "def bad(t, v) { return 1 N }\nr = dsolve(bad, 10 m/s, 0 s, 1 s)",
}
for label, src in CASES.items():
    out = []
    try:
        Interpreter(out=out.append).run(src, "t.forge")
        print(f"  ok   {label}: {out}")
    except ForgeError as err:
        print(f"  {label}: {err.title} | {err.message}")
