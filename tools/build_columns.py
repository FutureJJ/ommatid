"""Derive the FlyVis → male-CNS column map ONCE from the original anatomy and serialise it.

Review finding 1 (2026-09-11): the map used to be rebuilt from whichever graph was loaded, so a shuffled control graph also
received a different input mapping. Every graph variant must load this same file; the service refuses to run a variant
without it and records its hash.

usage: python tools/build_columns.py            → build/columns.npz
"""
import sys, hashlib, numpy as np
from pathlib import Path
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.eye import Eye
from ommatid.brain.optic_lobe import OpticLobe, ColumnMap

ROOT = Path(__file__).resolve().parent.parent
graph = ROOT / "build/graph.npz"
b = Brain(graph); eye = Eye(b); ol = OpticLobe()
cm = ColumnMap(ol, b, eye.column_angles_all)
keys = sorted(cm.pairs)
pos = np.concatenate([cm.pairs[k][0] for k in keys]); male = np.concatenate([cm.pairs[k][1] for k in keys])
types = np.concatenate([[k[0]] * len(cm.pairs[k][1]) for k in keys]).astype("U16")
sides = np.concatenate([[k[1]] * len(cm.pairs[k][1]) for k in keys]).astype("U1")
gsha = hashlib.sha256(graph.read_bytes()).hexdigest()[:12]
out = ROOT / "build/columns.npz"
np.savez_compressed(out, pos=pos, male=male, types=types, sides=sides, n_neurons=b.n, source_graph_sha=gsha,
                    bodies=b.bodies[male], n_inferred=cm.n_inferred)
csha = hashlib.sha256(out.read_bytes()).hexdigest()[:12]
print(f"{len(male):,} male neurons mapped ({cm.n_inferred:,} with inferred columns) from graph {gsha} → {out} sha {csha}")
