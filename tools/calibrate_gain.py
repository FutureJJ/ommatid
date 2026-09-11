"""Pre-registered calibration of the optic-lobe → central-brain hand-off scalar (docs/experiment.md §10).

Rule: choose, from a fixed grid, the LARGEST Hz-per-FlyVis-unit for which the lobula-plate HS cells (HSN, HSE, HSS) of
the eye seeing front-to-back motion fire at ≤ 150 Hz for a full-contrast CALIBRATION grating. The calibration grating is
not a test stimulus: period 0.40 screen widths (test: 0.20), speed 0.60 screen widths per second of brain time (test: 0.30),
sinusoidal (test: square wave). Nothing about the hypotheses' readouts (DNa02, DNp02/04, …) enters the choice.

Runs offline on synthetic frames through the real pipeline (OpticLobe → ColumnMap → LIF). Deterministic (seed 0).
usage: python tools/calibrate_gain.py            → prints the table and the chosen value
"""
import sys, numpy as np
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.optic_lobe import OpticLobe, OpticLobeParams, ColumnMap

GRID = [25, 50, 75, 100, 150]
H, W, STEPS = 200, 320, 100
PERIOD, SPEED = 0.40, 0.60        # screen widths, and screen widths per second of brain time
LIMIT_HZ = 150.0

def frame(t_ms, direction):
    x = np.arange(W) / W
    ph = direction * SPEED * t_ms / 1000.0
    g = 0.5 + 0.5 * np.sin(2 * np.pi * (x - ph) / PERIOD)
    return np.tile(g, (H, 1)).astype(np.float32)

b = Brain("build/graph.npz")
cm = ColumnMap.load("build/columns.npz", b)
hs = {s: np.concatenate([b.where(type=t, side=s) for t in ("HSN", "HSE", "HSS")]) for s in ("R", "L")}
print(f"HS cells: R {len(hs['R'])}, L {len(hs['L'])}")
rows = []
for hz in GRID:
    ol = OpticLobe(OpticLobeParams(hz_per_unit=float(hz)))
    b.reset(seed=0)
    out = {}
    for direction, label in ((+1, "rightward"), (-1, "leftward")):
        # settle on grey, then 40 steps of motion; the preferred (front-to-back) eye is R for rightward, L for leftward
        for _ in range(10): b.run(cm.drive(ol.rates(ol.see(np.full((H, W), 0.5, np.float32)))), STEPS)
        counts = np.zeros(b.n); secs = 0.0
        for i in range(40):
            r = b.run(cm.drive(ol.rates(ol.see(frame(i * STEPS * b.p.dt, direction)))), STEPS)
            if i >= 10: counts += r["counts"]; secs += r["secs"]
        pref = "R" if direction > 0 else "L"
        out[label] = {s: counts[hs[s]].sum() / len(hs[s]) / secs for s in ("R", "L")}
        out[label]["preferred"] = out[label][pref]
    worst = max(out["rightward"]["preferred"], out["leftward"]["preferred"])
    rows.append((hz, out, worst))
    print(f"hz_per_unit {hz:4d}: HS preferred-eye rate rightward {out['rightward']['preferred']:6.1f} Hz (other eye {out['rightward']['L']:5.1f}), "
          f"leftward {out['leftward']['preferred']:6.1f} Hz (other eye {out['leftward']['R']:5.1f})  → max {worst:6.1f}")
ok = [hz for hz, _, worst in rows if worst <= LIMIT_HZ]
chosen = max(ok) if ok else min(GRID)
print(f"\nchosen hz_per_unit = {chosen}  (largest grid value with preferred-eye HS rate ≤ {LIMIT_HZ:.0f} Hz)")
