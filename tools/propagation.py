"""Propagation probe: activate one population the way the paper does (forced Poisson spikes at a fixed rate) and
list which cell types fire downstream. Used to verify the kernel and to see how deep visual input travels.

usage: python tools/propagation.py L1 150        (type name, Hz; several types may be given comma-separated)
"""
import sys, numpy as np
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain

types = sys.argv[1].split(",") if len(sys.argv) > 1 else ["L1"]
hz = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
ms = float(sys.argv[3]) if len(sys.argv) > 3 else 200.0

b = Brain("build/graph.npz")
sel = np.concatenate([b.where(type=t) for t in types])
print(f"driving {len(sel)} neurons of type {types} at {hz:.0f} Hz for {ms:.0f} ms of brain time")
b.reset(seed=0)
steps = int(ms / b.p.dt)
r = b.run({tuple(sel): np.float32(hz)}, steps)
counts = r["counts"].astype(np.float64)
secs = r["secs"]
driven = np.zeros(b.n, bool); driven[sel] = True
print(f"total spikes {r['total']:,}  driven-population spikes {int(counts[driven].sum()):,}  downstream spikes {int(counts[~driven].sum()):,}")
print(f"downstream neurons that fired: {int((counts[~driven] > 0).sum()):,}")
# per-type mean rate over the block, downstream only
tp = b.types.copy(); tp[driven] = "__driven__"
rows = {}
for t in np.unique(tp[counts > 0]):
    if t == "__driven__": continue
    m = tp == t
    rows[t] = (counts[m].sum() / m.sum() / secs, int((counts[m] > 0).sum()), int(m.sum()))
top = sorted(rows.items(), key=lambda kv: -kv[1][0])[:25]
print(f"{'type':16s} {'mean Hz':>8s} {'firing/total':>13s}")
for t, (rate, nf, nt) in top:
    print(f"{t:16s} {rate:8.1f} {nf:6d}/{nt:<6d}")
