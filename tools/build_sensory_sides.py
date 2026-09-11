"""Infer the body side of VNC sensory neurons (not annotated in the male CNS) from their wiring: the side is the majority
somaSide, weighted by synapse count, of the neurons they synapse onto (one hop), restricted to partners that have a
side label. Also reports how confident each assignment is. Output: build/sensory_sides.npz (idx, side, confidence).

Leg identity comes from the entry nerve and is not inferred here.
"""
import sys, numpy as np, pandas as pd, scipy.sparse as sp
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain

b = Brain("build/graph.npz")
a = pd.read_feather("data/body-annotations.feather").drop_duplicates("bodyId").set_index("bodyId").reindex(b.bodies)
sc = a["superclass"].fillna("").to_numpy(dtype=str); nerve = a["entryNerve"].fillna("").to_numpy(dtype=str)
side = b.side.astype(str)
sens = np.flatnonzero((sc == "vnc_sensory") & (side == ""))
W = sp.csc_matrix((b.wdata, b.indices, b.indptr), shape=(b.n, b.n))      # column j = outputs of neuron j
has_side = np.isin(side, ["L", "R"])
out_idx, out_side, out_conf = [], [], []
for j in sens:
    a0, a1 = W.indptr[j], W.indptr[j + 1]
    tgt = W.indices[a0:a1]; w = np.abs(W.data[a0:a1])
    m = has_side[tgt]
    if m.sum() == 0: continue
    wl = w[m & (side[tgt] == "L")].sum(); wr = w[m & (side[tgt] == "R")].sum()
    if wl + wr == 0: continue
    s = "L" if wl > wr else "R"; conf = max(wl, wr) / (wl + wr)
    out_idx.append(j); out_side.append(s); out_conf.append(conf)
out_idx = np.array(out_idx); out_side = np.array(out_side); out_conf = np.array(out_conf)
np.savez_compressed("build/sensory_sides.npz", idx=out_idx, side=out_side, confidence=out_conf, bodies=b.bodies[out_idx])
print(f"{len(sens):,} unsided VNC sensory neurons; {len(out_idx):,} assigned; confidence median {np.median(out_conf):.2f}, "
      f"< 0.7 for {(out_conf < 0.7).sum():,}; L {int((out_side=='L').sum()):,} R {int((out_side=='R').sum()):,}")
for nv in ["ProLN", "MesoLN", "MetaLN"]:
    m = nerve[out_idx] == nv
    print(f"   {nv}: {m.sum():4d} assigned, L {int((out_side[m]=='L').sum()):4d} R {int((out_side[m]=='R').sum()):4d}, median confidence {np.median(out_conf[m]):.2f}")
