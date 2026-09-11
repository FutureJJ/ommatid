"""Why do the looming detectors stay silent? Exploratory diagnosis for the v3 design (not part of any frozen protocol).

1. Anatomy: where does LC4 (and LPLC2) get its input in the male CNS graph, and how much of that input comes from types
   the FlyVis hand-off drives (build/columns.npz)?
2. Dynamics: run the real pipeline on a synthetic emulation of the actual rig (a bright screen covering 55 % × 60 % of the
   frame in a dark room, a disc growing to 90 % of the screen height) and record, per step, LC4's mean membrane potential
   relative to threshold, its synaptic drive, the injected rate into its FlyVis-driven partners, and LC4/DNp04 spikes.
3. Exploratory gain sweep: at which hand-off scalar would LC4 respond at all?
"""
import sys, numpy as np, scipy.sparse as sp
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.optic_lobe import OpticLobe, OpticLobeParams, ColumnMap

H, W, STEPS = 200, 320, 100
SCREEN_W, SCREEN_H = 0.55, 0.60           # fraction of the camera frame the laptop screen covers (attempt 2 geometry)

def rig_frame(disc_frac, bg=0.03):
    """Dark room, bright screen centred, black disc of `disc_frac` × screen height in its centre."""
    f = np.full((H, W), bg, np.float32)
    x0, x1 = int(W * (0.5 - SCREEN_W / 2)), int(W * (0.5 + SCREEN_W / 2)); y0, y1 = int(H * (0.5 - SCREEN_H / 2)), int(H * (0.5 + SCREEN_H / 2))
    f[y0:y1, x0:x1] = 1.0
    if disc_frac > 0:
        r = disc_frac * (y1 - y0) / 2; yy, xx = np.mgrid[0:H, 0:W]
        f[((xx - W / 2) ** 2 + (yy - H / 2) ** 2) < r * r] = 0.0
    return f

b = Brain("build/graph.npz"); cm = ColumnMap.load("build/columns.npz", b)
driven = np.zeros(b.n, bool)
for _, male in cm.pairs.values(): driven[male] = True
W_post = sp.csc_matrix((b.wdata, b.indices, b.indptr), shape=(b.n, b.n)).tocsr()   # row = post

print("== 1. anatomy of the looming detectors' input")
for t in ["LC4", "LPLC2", "LC6"]:
    sel = b.where(type=t); rows = W_post[sel].tocoo()
    exc = rows.data > 0
    w_driven = np.abs(rows.data[exc & driven[rows.col]]).sum(); w_exc = np.abs(rows.data[exc]).sum(); w_inh = np.abs(rows.data[~exc]).sum()
    agg = {}
    for c, v in zip(rows.col[exc], rows.data[exc]): agg[b.types[c]] = agg.get(b.types[c], 0) + v
    top = sorted(agg.items(), key=lambda kv: -kv[1])[:8]
    print(f"{t}: {len(sel)} cells; excitatory input {w_exc/len(sel):.0f} mV/cell of which from FlyVis-driven types {w_driven/w_exc*100:.0f} %; inhibitory {w_inh/len(sel):.0f} mV/cell")
    print("   top excitatory input types:", [(k, round(v / len(sel), 1), "driven" if k in {b.types[i] for i in np.flatnonzero(driven)} else "NOT driven") for k, v in top])

print("\n== 2. dynamics on the emulated rig (hz_per_unit 100, frozen v2)")
lc4 = b.where(type="LC4"); dnp04 = b.where(type="DNp04"); th = b.p.v_th
ol = OpticLobe(OpticLobeParams(hz_per_unit=100.0))
def run_block(frames, label):
    peak_v = []; g_mean = []; spikes_lc4 = []; spikes_dn = []; inj = []
    for f in frames:
        act = ol.see(f); rates = ol.rates(act); d = cm.drive(rates)
        r = b.run(d, STEPS)
        peak_v.append(float(b.v[lc4].max())); g_mean.append(float(b.g[lc4].mean()))
        spikes_lc4.append(int(r["counts"][lc4].sum())); spikes_dn.append(int(r["counts"][dnp04].sum()))
        inj.append(float(sum(v.sum() for v in d.values())))
    print(f"{label:28s} LC4 peak v {max(peak_v):+6.1f} mV (threshold {th:+.0f}), mean g {np.mean(g_mean):5.2f} mV, LC4 spikes {sum(spikes_lc4)}, DNp04 spikes {sum(spikes_dn)}, injected Hz sum {np.mean(inj):8.0f}")
b.reset(seed=0); ol.state = ol.net.steady_state(t_pre=1.0, dt=ol.p.dt, batch_size=2)
run_block([rig_frame(0.0)] * 30, "screen only, settle")
run_block([rig_frame(0.05 + 0.85 * i / 99) for i in range(100)], "loom 5→90 % (2 s brain)")
run_block([rig_frame(0.90)] * 20, "disc held")
run_block([rig_frame(0.0)] * 20, "screen only")
# full-frame loom for comparison: what if the fly's whole camera field were the stimulus?
run_block([np.where(rig_frame(0.0) > 0.5, 1.0, 1.0).astype(np.float32)] * 20, "whole field white, settle")
yy, xx = np.mgrid[0:H, 0:W]
run_block([np.where(((xx - W/2)**2 + (yy - H/2)**2) < ((0.05 + 0.9 * i / 99) * H / 2) ** 2, 0.0, 1.0).astype(np.float32) for i in range(100)], "loom over the WHOLE frame")

print("\n== 3. exploratory gain sweep on the rig loom (v3 design only)")
for hz in [100, 200, 400, 800]:
    ol = OpticLobe(OpticLobeParams(hz_per_unit=float(hz))); b.reset(seed=0)
    run_block([rig_frame(0.0)] * 20, f"hz {hz}: settle")
    run_block([rig_frame(0.05 + 0.85 * i / 99) for i in range(100)], f"hz {hz}: loom")
