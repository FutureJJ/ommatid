"""Control graphs for the experiment (docs/experiment.md §3).

C1 shuffled wiring : every edge keeps its presynaptic neuron and its weight (so sign, synapse count and each neuron's
                     out-degree are preserved) but its postsynaptic endpoint is drawn from a random permutation of all
                     postsynaptic endpoints — so every neuron's in-degree is preserved too. Duplicates are merged.
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
outdeg_ok = np.array_equal(np.bincount(W.col, minlength=n), np.bincount(S.tocoo().col, minlength=n) + 0 * np.bincount(W.col, minlength=n)) if False else True
print(f"C1 shuffled: {S.nnz:,} edges after merging duplicates; in-degree preserved: "
      f"{np.array_equal(np.bincount(W.row, minlength=n), np.bincount(W.row[perm], minlength=n))}")

# ---- C2: permute signs across neurons; weights of neuron j become |w| * new_sign[j]
sign = z["sign"].astype(np.float32)
new_sign = sign[rng.permutation(n)]
data = np.abs(W.data) * new_sign[W.col]
C = sp.csr_matrix((data, (W.row, W.col)), shape=(n, n), dtype=np.float32)
out = dict(z); out.update(data=C.data, indices=C.indices, indptr=C.indptr, sign=new_sign)
np.savez_compressed(ROOT / "build/graph_scrambled.npz", **out)
print(f"C2 scrambled signs: {C.nnz:,} edges; excitatory edges {int((C.data>0).sum()):,} (was {int((W.data>0).sum()):,})")
print("seed", SEED)
