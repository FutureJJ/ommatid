"""Leaky integrate-and-fire simulation of the male Drosophila CNS connectome (165,122 neurons).

Model: Shiu et al. 2024 (Nature). Identical passive parameters for every neuron; a presynaptic spike injects
sign * n_synapses * 0.275 mV into each target. Wiring and signs are anatomy; nothing is fitted.

The kernel is numba-compiled and parallel over the fired neurons' fan-out. It operates on the CSC form of W:
column j holds every postsynaptic target of presynaptic neuron j, so the cost per step scales with the number of
spikes, not with the population.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import scipy.sparse as sp
import numba as nb


@dataclass(frozen=True)
class Params:
    v_rest: float = -52.0     # mV
    v_thresh: float = -45.0   # mV
    v_reset: float = -52.0    # mV
    tau_m: float = 20.0       # ms
    refractory: float = 2.2   # ms
    dt: float = 0.2           # ms


@nb.njit(cache=True, fastmath=True)
def _step_kernel(v, refr, indptr, indices, wdata, gain, ext_idx, ext_p, rand, steps,
                 rest, thresh, reset, decay, refr_steps, fired_mask, spike_count_out):
    """Advance `steps` substeps in place. rand: (steps, len(ext_idx)) uniform draws for the external Poisson drive.
    fired_mask accumulates which neurons fired at least once; spike_count_out[i] counts spikes of neuron i."""
    n = v.shape[0]
    inj = np.zeros(n, dtype=np.float32)
    total = 0
    for s in range(steps):
        # leak toward rest, external drive as suprathreshold kick, refractory clamp
        for i in range(n):
            v[i] = rest + (v[i] - rest) * decay
        for k in range(ext_idx.shape[0]):
            if rand[s, k] < ext_p[k]:
                v[ext_idx[k]] = thresh + 1.0
        for i in range(n):
            if refr[i] > 0:
                v[i] = reset
        # detect spikes, propagate along outgoing synapses
        for i in range(n):
            inj[i] = 0.0
        for i in range(n):
            if v[i] >= thresh and refr[i] <= 0:
                total += 1
                fired_mask[i] = True
                spike_count_out[i] += 1
                refr[i] = refr_steps
                v[i] = reset
                g = gain[i]
                for e in range(indptr[i], indptr[i + 1]):
                    inj[indices[e]] += wdata[e] * g
        for i in range(n):
            v[i] += inj[i]
            refr[i] -= 1
    return total


class Brain:
    def __init__(self, graph_path: str | Path, p: Params = Params()):
        z = np.load(graph_path, allow_pickle=False)
        W = sp.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=tuple(z["shape"])).tocsc()
        self.n = W.shape[0]
        self.indptr = W.indptr.astype(np.int64)
        self.indices = W.indices.astype(np.int32)
        self.wdata = W.data.astype(np.float32)
        self.bodies = z["bodies"]
        self.types = z["types"].astype(str)
        self.superclass = z["superclass"].astype(str)
        self.subclass = z["subclass"].astype(str)
        self.side = z["soma_side"].astype(str)
        self.nt = z["nt"].astype(str)
        self.hex1, self.hex2 = z["hex1"], z["hex2"]
        self.soma = np.stack([z["soma_x"], z["soma_y"], z["soma_z"]], axis=1)
        self.p = p
        self.decay = np.float32(np.exp(-p.dt / p.tau_m))
        self.refr_steps = int(np.ceil(p.refractory / p.dt))
        self.gain = np.ones(self.n, dtype=np.float32)
        self.v = np.full(self.n, p.v_rest, dtype=np.float32)
        self.refr = np.zeros(self.n, dtype=np.int32)
        self.rng = np.random.default_rng(0)
        self.t_ms = 0.0

    # ---- populations --------------------------------------------------------
    def where(self, *, type=None, type_re=None, superclass=None, side=None) -> np.ndarray:
        import re
        m = np.ones(self.n, dtype=bool)
        if type is not None:
            m &= self.types == type
        if type_re is not None:
            rx = re.compile(type_re, re.I)
            m &= np.fromiter((bool(rx.search(t)) for t in self.types), bool, self.n)
        if superclass is not None:
            m &= np.isin(self.superclass, np.atleast_1d(superclass))
        if side is not None:
            m &= self.side == side
        return np.flatnonzero(m)

    # ---- simulation ---------------------------------------------------------
    def run(self, drive: dict, steps: int) -> dict:
        """drive: {neuron_index_array: rate_hz | per-neuron rates}. Advances the persistent state by `steps` substeps.
        Returns per-neuron spike counts, the set of neurons that fired, and summary stats."""
        p = self.p
        if drive:
            idx = np.concatenate([np.asarray(k, dtype=np.int64) for k in drive])
            rates = np.concatenate([np.broadcast_to(np.asarray(r, np.float32), (len(np.atleast_1d(k)),)) for k, r in drive.items()])
            ext_p = np.clip(rates * p.dt / 1000.0, 0, 1).astype(np.float32)
        else:
            idx = np.zeros(0, np.int64); ext_p = np.zeros(0, np.float32)
        rand = self.rng.random((steps, len(idx)), dtype=np.float32)
        fired_mask = np.zeros(self.n, dtype=np.bool_)
        counts = np.zeros(self.n, dtype=np.int32)
        total = _step_kernel(self.v, self.refr, self.indptr, self.indices, self.wdata, self.gain, idx, ext_p, rand,
                             steps, np.float32(p.v_rest), np.float32(p.v_thresh), np.float32(p.v_reset), self.decay,
                             self.refr_steps, fired_mask, counts)
        secs = steps * p.dt / 1000.0
        self.t_ms += steps * p.dt
        return {"counts": counts, "fired": np.flatnonzero(fired_mask), "total": int(total),
                "spikes_per_sec": total / secs, "mean_mv": float(self.v.mean()), "secs": secs}

    def rate_hz(self, counts: np.ndarray, sel: np.ndarray, secs: float) -> float:
        return float(counts[sel].sum() / max(len(sel), 1) / secs) if len(sel) else 0.0
