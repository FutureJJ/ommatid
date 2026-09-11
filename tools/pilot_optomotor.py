"""Open-loop pilot (control C3 style): does a wide-field drifting grating produce a DNa02 asymmetry at all?

This is a development smoke test, run before parameters are frozen, and is disclosed as such. It renders synthetic
frames (grating drifting left or right, a looming disc, a blank) into the eye and reports readout rates.
"""
import sys, time, numpy as np
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.eye import Eye
from ommatid.brain.readout import Readout

H, W = 200, 320          # synthetic camera (same aspect as the Aurora stream)
STEPS = 100              # 20 ms brain time per control step

def grating(phase_deg, period_deg=30.0, hfov=74.0):
    az = (np.arange(W) / W - 0.5) * hfov
    g = 0.5 + 0.5 * np.sin(2 * np.pi * (az + phase_deg) / period_deg)
    return np.tile(g, (H, 1)).astype(np.float32)

def loom(size_frac):
    yy, xx = np.mgrid[0:H, 0:W]
    r = size_frac * H / 2
    img = np.ones((H, W), np.float32)
    img[(xx - W / 2) ** 2 + (yy - H / 2) ** 2 < r * r] = 0.05
    return img

def run_block(name, frames, brain, eye, ro, seed):
    brain.rng = np.random.default_rng(seed)
    acc = {k: [] for k in ro.pop}; totals = []
    for f in frames:
        drive = eye.look(f, dt_ms=STEPS * brain.p.dt)
        r = brain.run(drive, STEPS)
        hz = ro.rates(r["counts"], r["secs"])
        for k in acc: acc[k].append(hz[k])
        totals.append(r["total"])
    m = {k: np.mean(v[len(v)//2:]) for k, v in acc.items()}   # second half of the block (after transients)
    print(f"{name:14s} DNa02 L {m['DNa02_L']:5.1f} R {m['DNa02_R']:5.1f} R-L {m['DNa02_R']-m['DNa02_L']:+6.1f} | "
          f"DNa01 {np.mean([m['DNa01_L'], m['DNa01_R']]):5.1f} | MDN {m['MDN']:5.1f} DNp09 {m['DNp09']:5.1f} | "
          f"escape DNp01 {m['DNp01']:5.1f} DNp02 {m['DNp02']:5.1f} DNp04 {m['DNp04']:5.1f} | spikes/step {np.mean(totals):7.0f}")
    return m

if __name__ == "__main__":
    brain = Brain("build/graph.npz"); eye = Eye(brain); ro = Readout(brain)
    print("columns", eye.n_columns, "in view", int(eye.in_view.sum()), "| readout", ro.describe()["populations"])
    blank = np.full((H, W), 0.5, np.float32)
    t = time.time()
    # settle on a static blank so adaptation and network state are at baseline
    run_block("uniform grey", [blank] * 30, brain, eye, ro, seed=1)
    speed = 3.0  # degrees of phase per 20 ms step
    run_block("grating → R", [grating(i * speed) for i in range(40)], brain, eye, ro, seed=2)
    run_block("blank", [blank] * 20, brain, eye, ro, seed=3)
    run_block("grating → L", [grating(-i * speed) for i in range(40)], brain, eye, ro, seed=4)
    run_block("blank", [blank] * 20, brain, eye, ro, seed=5)
    run_block("loom", [loom(min(0.05 + 0.03 * i, 1.0)) for i in range(30)], brain, eye, ro, seed=6)
    run_block("blank", [blank] * 20, brain, eye, ro, seed=7)
    run_block("static disc", [loom(0.5)] * 30, brain, eye, ro, seed=8)
    print(f"wall {time.time()-t:.0f}s")
