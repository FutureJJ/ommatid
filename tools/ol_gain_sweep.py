"""Sweep a single synaptic gain on optic-lobe-intrinsic presynaptic neurons; report visual hierarchy rates and stability."""
import sys, numpy as np, scipy.sparse as sp
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.eye import Eye
from tools.pilot_optomotor import grating, loom, H, W, STEPS

b = Brain("build/graph.npz"); eye = Eye(b)
sc = b.superclass
print("superclasses:", dict(zip(*np.unique(sc, return_counts=True))))
ol = np.char.startswith(sc.astype(str), "ol_")
print(f"optic-lobe presynaptic neurons: {ol.sum():,}")

# who drives DNb05 / DNg33 (weight-weighted presynaptic types)
Wc = sp.csc_matrix((b.wdata, b.indices, b.indptr), shape=(b.n, b.n)).tocsr()   # row = post
for t in ["DNb05", "DNg33", "DCH", "LPi12"]:
    sel = b.where(type=t); row = Wc[sel].tocoo(); agg = {}
    for c, v in zip(row.col, row.data): agg[b.types[c]] = agg.get(b.types[c], 0) + v
    top = sorted(agg.items(), key=lambda kv: -abs(kv[1]))[:6]
    print(f"inputs of {t}: {[(k, round(float(v),1)) for k, v in top]}")

TYPES = ["L2", "Tm1", "Tm2", "Mi1", "Tm3", "T4a", "T5a", "T5b", "LC4", "LPLC2", "HSE", "DNp04", "DNp02", "DNa02", "DNb05"]
def block(frames):
    counts = np.zeros(b.n); secs = 0; tot = []
    for f in frames:
        r = b.run(eye.look(f, dt_ms=STEPS * b.p.dt), STEPS); counts += r["counts"]; secs += r["secs"]; tot.append(r["total"])
    return {t: counts[b.where(type=t)].sum() / max(len(b.where(type=t)), 1) / secs for t in TYPES}, np.mean(tot)

w0 = b.wdata.copy()
blank = np.full((H, W), 0.5, np.float32)
for k in [1.0, 2.0, 3.0, 5.0]:
    b.gain[:] = 1.0; b.gain[ol] = k
    b.reset(seed=0); eye.mean = None
    _, t_settle = block([blank] * 20)
    g, t_g = block([grating(i * 3.0) for i in range(30)])
    l, t_l = block([loom(min(0.05 + 0.03 * i, 1.0)) for i in range(30)])
    _, t_b = block([blank] * 20)
    fmt = lambda d: " ".join(f"{t}:{d[t]:.0f}" for t in TYPES)
    print(f"\nOL gain x{k}: spikes/step grey {t_settle:.0f} grating {t_g:.0f} loom {t_l:.0f} grey-after {t_b:.0f}")
    print("  grating:", fmt(g)); print("  loom   :", fmt(l))
