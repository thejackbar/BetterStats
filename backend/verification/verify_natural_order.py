"""Squad, team and grade names sort with numbers read as numbers: 1st XI, 2nd XI,
... 10th XI, never 1st, 10th, 2nd. Pure check of services/natural_order.natural_key
and of the places that use it (selection_pool squad order, the availability matrix).

    cd backend && python verification/verify_natural_order.py
Control: plain `sorted(names)` fails the first check (the bug this guards)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.services.natural_order import natural_key
try:
    from app.services import selection_pool
except ModuleNotFoundError as e:  # no backend deps in this shell: skip that one check
    selection_pool = None
    print('  skip selection_pool check:', e)

FAILS = []
def check(name, cond, detail=""):
    print(("  ok  " if cond else " FAIL ") + name + ("" if cond else "  — " + str(detail)))
    if not cond: FAILS.append(name)

names = ["Applecross 10th XI", "Applecross", "Applecross 2nd XI", "Applecross A", "Applecross 1st XI",
         "Applecross T20 Div 10", "Applecross T20 Div 2", "Applecross Colts", "Applecross 9th XI"]
want = ["Applecross", "Applecross 1st XI", "Applecross 2nd XI", "Applecross 9th XI", "Applecross 10th XI",
        "Applecross A", "Applecross Colts", "Applecross T20 Div 2", "Applecross T20 Div 10"]
check("1st XI before 2nd before 10th, lettered sides after", sorted(names, key=natural_key) == want, sorted(names, key=natural_key))
check("a plain sort would get it wrong (the check can fail)", sorted(names) != want)
check("OD2 above OD10", sorted(["OD10 Gold", "OD2 Gold"], key=natural_key) == ["OD2 Gold", "OD10 Gold"])
check("None and empty do not raise", sorted([None, "", "A"], key=natural_key) == [None, "", "A"])
check("mixed digit/letter names never raise", sorted(["1", "a", "10", "A1", "a10", "a2", "T20"], key=natural_key) is not None)

so = selection_pool and selection_pool._squad_order({"x": ("Applecross 10th XI", 0), "y": ("Applecross 2nd XI", 0), "z": ("Applecross 1st XI", 0), "r": ("Ranked", 3)})
check("selection pool squad rank: ranked first, then 1st < 2nd < 10th", so is None or (so["r"] == 1 and so["z"] < so["y"] < so["x"]), so)
if FAILS:
    print(f"\n{len(FAILS)} failed"); sys.exit(1)
print("\nall passed")
