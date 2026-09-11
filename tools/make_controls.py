"""Control graphs for the experiment (docs/experiment.md §3).

C1 shuffled wiring : every edge keeps its presynaptic neuron and its weight; its postsynaptic endpoint is drawn from a
                     random permutation of all postsynaptic endpoints. This preserves every neuron's in- and out-degree in
                     the MULTIGRAPH sense (counting parallel edges). Coincident edges are then merged (summed), which lowers
                     the unique-neighbour degree of a small fraction of neurons; the exact fraction is measured and printed.
C2 scrambled signs : original wiring; the excitatory/inhibitory label is permuted across neurons (the multiset of
                     signs is preserved, their assignment to neurons is not).

The optic lobe types that receive FlyVis input keep their identity, so the controls test what the wiring downstream of
the hand-off does with the same input.
"""
import sys, numpy as np, scipy.sparse as sp
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 2026

z = dict(np.load(ROOT / "build/graph.npz", allow_pickle=False))
W = sp.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=tuple(z["shape"])).tocoo()
n = W.shape[0]; rng = np.random.default_rng(SEED)
print(f"original: {W.nnz:,} edges")

# ---- C1: permute postsynaptic endpoints (rows) across edges
perm = rng.permutation(W.nnz)
S = sp.csr_matrix((W.data, (W.row[perm], W.col)), shape=(n, n), dtype=np.float32); S.sum_duplicates()
out = dict(z); out.update(data=S.data, indices=S.indices, indptr=S.indptr)
np.savez_compressed(ROOT / "build/graph_shuffled.npz", **out)
Sc = S.tocoo()
in0, out0 = np.bincount(W.row, minlength=n), np.bincount(W.col, minlength=n)            # unique-neighbour degrees, original
in1, out1 = np.bincount(Sc.row, minlength=n), np.bincount(Sc.col, minlength=n)          # saved shuffled graph
print(f"C1 shuffled: {S.nnz:,} edges after merging {W.nnz - S.nnz:,} coincident edges ({(W.nnz - S.nnz) / W.nnz * 100:.2f} %)")
print(f"   unique in-degree changed for {(in0 != in1).sum():,} neurons (max change {np.abs(in0 - in1).max()}), "
      f"unique out-degree changed for {(out0 != out1).sum():,} (max {np.abs(out0 - out1).max()}); "
      f"total |weight| preserved: {np.isclose(np.abs(W.data).sum(), np.abs(S.data).sum())}")

# ---- C2: permute signs across neurons; weights of neuron j become |w| * new_sign[j]
sign = z["sign"].astype(np.float32)
new_sign = sign[rng.permutation(n)]
data = np.abs(W.data) * new_sign[W.col]
C = sp.csr_matrix((data, (W.row, W.col)), shape=(n, n), dtype=np.float32)
out = dict(z); out.update(data=C.data, indices=C.indices, indptr=C.indptr, sign=new_sign)
np.savez_compressed(ROOT / "build/graph_scrambled.npz", **out)
print(f"C2 scrambled signs: {C.nnz:,} edges; excitatory edges {int((C.data>0).sum()):,} (was {int((W.data>0).sum()):,})")
print("seed", SEED)
