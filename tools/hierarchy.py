"""Where does a visual stimulus die? Run a stimulus through the eye and report the mean rate of each stage of the
fly's visual hierarchy: lamina → medulla → T4/T5 → lobula columnar / lobula plate → descending neurons.
"""
import sys, numpy as np
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.eye import Eye
from tools.pilot_optomotor import grating, loom, H, W, STEPS

STAGES = [
    ("lamina",   ["L1", "L2", "L3"]),
    ("medulla ON", ["Mi1", "Tm3", "Mi4", "Mi9"]),
    ("medulla OFF", ["Tm1", "Tm2", "Tm4", "Tm9"]),
    ("T4 (ON motion)", ["T4a", "T4b", "T4c", "T4d"]),
    ("T5 (OFF motion)", ["T5a", "T5b", "T5c", "T5d"]),
    ("lobula plate", ["HSN", "HSE", "HSS", "VS", "H2", "CH", "DCH", "VCH", "LPi12", "LPi21"]),
    ("loom detectors", ["LC4", "LC6", "LPLC2", "LPLC1", "LC11", "LC16"]),
    ("escape DNs", ["DNp01", "DNp02", "DNp04", "DNp11", "DNp09"]),
    ("walking DNs", ["DNa02", "DNa01", "MDN", "DNb05", "DNg33"]),
]

def report(name, frames, brain, eye):
    counts = np.zeros(brain.n, np.float64); secs = 0.0; totals = []
    for f in frames:
        d = eye.look(f, dt_ms=STEPS * brain.p.dt)
        r = brain.run(d, STEPS)
        counts += r["counts"]; secs += r["secs"]; totals.append(r["total"])
    print(f"\n== {name}: {len(frames)} steps, {np.mean(totals):.0f} spikes/step")
    for stage, types in STAGES:
        parts = []
        for t in types:
            sel = brain.where(type=t)
            if len(sel) == 0: continue
            hz = counts[sel].sum() / len(sel) / secs
            frac = (counts[sel] > 0).mean()
            parts.append(f"{t} {hz:.0f}Hz/{frac*100:.0f}%")
        print(f"  {stage:16s} " + "  ".join(parts))

if __name__ == "__main__":
    brain = Brain("build/graph.npz"); eye = Eye(brain)
    blank = np.full((H, W), 0.5, np.float32)
    report("uniform grey (settle)", [blank] * 25, brain, eye)
    report("grating → R", [grating(i * 3.0) for i in range(40)], brain, eye)
    report("uniform grey", [blank] * 25, brain, eye)
    report("loom (dark disc expanding)", [loom(min(0.05 + 0.03 * i, 1.0)) for i in range(30)], brain, eye)
    report("uniform grey", [blank] * 25, brain, eye)
    report("full-field dimming step", [np.full((H, W), 0.1, np.float32)] * 10, brain, eye)
