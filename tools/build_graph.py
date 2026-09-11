"""Build the signed sparse connectivity matrix from the FlyEM male CNS connectome v1.0 (CC-BY).

Inputs  (data/): body-annotations.feather, body-neurotransmitters.feather, connectome-weights.feather (traced-only)
Output  (build/graph.npz): W as CSR (rows = postsynaptic, cols = presynaptic, mV per presynaptic spike) + per-neuron metadata.

Sign convention: Shiu et al. 2024 (Nature) — acetylcholine excitatory, GABA and glutamate inhibitory, histamine inhibitory,
monoamines modulatory → zero fast weight. Pairs with fewer than MIN_SYN synapses are dropped as reconstruction noise.
"""
from pathlib import Path
import numpy as np, pandas as pd, scipy.sparse as sp
import pyarrow.feather as pf, pyarrow.compute as pc

MV_PER_SYNAPSE = 0.275
MIN_SYN = 3
SIGN = {"acetylcholine": 1.0, "gaba": -1.0, "glutamate": -1.0, "histamine": -1.0,
        "dopamine": 0.0, "octopamine": 0.0, "serotonin": 0.0, "unclear": 0.0, "unknown": 0.0}
ROOT = Path(__file__).resolve().parent.parent
DATA, BUILD = ROOT / "data", ROOT / "build"

def main():
    BUILD.mkdir(exist_ok=True)
    tbl = pf.read_table(DATA / "connectome-weights.feather")
    print(f"{tbl.num_rows:,} pre->post pairs on disk; columns {tbl.column_names}")
    tbl = tbl.filter(pc.greater_equal(tbl.column("weight"), MIN_SYN))
    pre_a = tbl.column("body_pre").to_numpy(); post_a = tbl.column("body_post").to_numpy()
    wt_a = tbl.column("weight").to_numpy().astype(np.float32); del tbl
    print(f"{len(wt_a):,} pairs with >= {MIN_SYN} synapses")

    ann = pd.read_feather(DATA / "body-annotations.feather")
    ann["t"] = ann["type"].fillna(ann.get("flywireType")).fillna(ann["instance"]).fillna("")
    nt = pd.read_feather(DATA / "body-neurotransmitters.feather")[["body", "consensus_nt"]].dropna(subset=["body"]).drop_duplicates("body")

    neurons = ann.loc[(ann.status == "Traced") & (ann.statusLabel != "Glia"), "bodyId"]
    bodies = np.sort(neurons.unique()); n = len(bodies)
    print(f"{n:,} traced neurons")

    valid = np.zeros(int(max(pre_a.max(), post_a.max())) + 1, dtype=bool); valid[bodies] = True
    ok = valid[pre_a] & valid[post_a]
    pre_a, post_a, wt_a = pre_a[ok], post_a[ok], wt_a[ok]
    print(f"{len(wt_a):,} neuron->neuron edges, {int(wt_a.sum()):,} synapses")

    idx = pd.Series(np.arange(n, dtype=np.int32), index=bodies)
    nt_str = nt.set_index("body")["consensus_nt"].reindex(bodies).fillna("unknown").str.lower().to_numpy().astype("U24")
    sign = np.array([SIGN.get(s, 0.0) for s in nt_str], dtype=np.float32)
    ann_i = ann.drop_duplicates("bodyId").set_index("bodyId")
    col = lambda c: ann_i[c].reindex(bodies).fillna("").to_numpy().astype(str) if c in ann_i else np.full(n, "", dtype=str)

    r = idx.loc[post_a].to_numpy(); c = idx.loc[pre_a].to_numpy()
    v = wt_a * MV_PER_SYNAPSE * sign[c]; keep = v != 0
    W = sp.csr_matrix((v[keep], (r[keep], c[keep])), shape=(n, n), dtype=np.float32); W.sum_duplicates()
    print(f"W {n:,}x{n:,}  nnz {W.nnz:,}  exc {(W.data>0).sum():,}  inh {(W.data<0).sum():,}  dropped(modulatory/unknown) {(~keep).sum():,}")

    np.savez_compressed(BUILD / "graph.npz", data=W.data, indices=W.indices, indptr=W.indptr, shape=W.shape,
        bodies=bodies, sign=sign, nt=nt_str, types=col("t"), superclass=col("superclass"), subclass=col("subclass"),
        soma_side=col("somaSide"), hex1=ann_i["assignedOlHex1"].reindex(bodies).to_numpy(dtype=float),
        hex2=ann_i["assignedOlHex2"].reindex(bodies).to_numpy(dtype=float),
        soma_x=ann_i["somaLocation"].reindex(bodies).apply(lambda p: p[0] if isinstance(p,(list,np.ndarray)) and len(p)==3 else np.nan).to_numpy(dtype=float) if "somaLocation" in ann_i else np.full(n, np.nan),
        soma_y=ann_i["somaLocation"].reindex(bodies).apply(lambda p: p[1] if isinstance(p,(list,np.ndarray)) and len(p)==3 else np.nan).to_numpy(dtype=float) if "somaLocation" in ann_i else np.full(n, np.nan),
        soma_z=ann_i["somaLocation"].reindex(bodies).apply(lambda p: p[2] if isinstance(p,(list,np.ndarray)) and len(p)==3 else np.nan).to_numpy(dtype=float) if "somaLocation" in ann_i else np.full(n, np.nan))
    print(f"wrote {BUILD/'graph.npz'} ({(BUILD/'graph.npz').stat().st_size/1e6:.0f} MB)")

if __name__ == "__main__":
    main()
