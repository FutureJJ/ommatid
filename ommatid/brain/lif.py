"""Leaky integrate-and-fire simulation of the male Drosophila CNS connectome (165,122 neurons).

Model: Shiu et al. 2024 (Nature), reproduced from their released Brian2 code (philshiu/Drosophila_brain_model):

    dv/dt = (v_0 - v + g) / t_mbr      (unless refractory)
    dg/dt = -g / tau                   (unless refractory)
    on presynaptic spike, after a delay t_dly:   g_post += w      with  w = sign * n_synapses * w_syn
    spike when v > v_th;  then v = v_rst, g = 0, refractory for t_rfc

    v_0 = v_rst = -52 mV, v_th = -45 mV, t_mbr = 20 ms, tau = 5 ms, t_rfc = 2.2 ms, t_dly = 1.8 ms, w_syn = 0.275 mV

Note the synaptic variable g: a single synapse does not step the membrane by 0.275 mV. It adds 0.275 mV to g,
which decays with tau = 5 ms while the membrane integrates it with t_mbr = 20 ms, so the peak depolarisation from
one synapse is about 0.043 mV (peak at ~9 ms). Implementations that inject w_syn directly into v overdrive the
network roughly sixfold and run away; this one does not.

Integration is exact for the linear subsystem over each substep dt (default 0.2 ms); delays are a ring buffer of
pending g increments. The kernel is numba-compiled and operates on the CSC form of W so cost scales with spikes.
External drive follows the paper's convention for activation: a driven neuron is forced to spike at a Poisson rate.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import scipy.sparse as sp
import numba as nb


@dataclass(frozen=True)
class Params:
    v_0: float = -52.0      # mV resting potential
    v_rst: float = -52.0    # mV reset
    v_th: float = -45.0     # mV threshold
    t_mbr: float = 20.0     # ms membrane time constant
    tau: float = 5.0        # ms synaptic time constant
    t_rfc: float = 2.2      # ms refractory period
    t_dly: float = 1.8      # ms synaptic delay
    dt: float = 0.2         # ms integration step


@nb.njit(cache=True, fastmath=True)
def _step_kernel(v, g, refr, pend, ring_pos, indptr, indices, wdata, gain, ext_idx, ext_p, rand, steps,
                 v_0, v_th, v_rst, e_m, e_s, k_vg, refr_steps, dly_steps, fired_mask, spike_count_out):
    """Advance `steps` substeps in place.
    v, g          : membrane potential and synaptic variable per neuron
    refr          : remaining refractory substeps per neuron
    pend          : (dly_steps+1, n) ring buffer of pending g increments; ring_pos[0] = current slot
    e_m, e_s      : exp(-dt/t_mbr), exp(-dt/tau)
    k_vg          : tau/(t_mbr - tau) * (e_m - e_s)   -- exact contribution of g to v over one substep
    rand          : (steps, len(ext_idx)) uniform draws for the external Poisson drive
    Returns total spikes; fills fired_mask and per-neuron spike counts."""
    n = v.shape[0]
    total = 0
    pos = ring_pos[0]
    for s in range(steps):
        # 1. deliver synaptic increments whose delay has elapsed
        slot = pend[pos]
        for i in range(n):
            if slot[i] != 0.0:
                g[i] += slot[i]
                slot[i] = 0.0
        # 2. exact integration of (v, g) over dt for non-refractory neurons
        for i in range(n):
            if refr[i] > 0:
                refr[i] -= 1
            else:
                gi = g[i]
                v[i] = v_0 + (v[i] - v_0) * e_m + gi * k_vg
                g[i] = gi * e_s
        # 3. external drive: forced spikes (activation, as in the paper's Poisson input)
        for k in range(ext_idx.shape[0]):
            if rand[s, k] < ext_p[k]:
                j = ext_idx[k]
                if refr[j] <= 0:
                    v[j] = v_th + 1.0
        # 4. threshold, reset, schedule delayed synaptic output
        out_pos = pos + dly_steps
        if out_pos > dly_steps:
            out_pos -= dly_steps + 1
        out = pend[out_pos]
        for i in range(n):
            if refr[i] <= 0 and v[i] > v_th:
                total += 1
                fired_mask[i] = True
                spike_count_out[i] += 1
                v[i] = v_rst
                g[i] = 0.0
                refr[i] = refr_steps
                gi = gain[i]
                for e in range(indptr[i], indptr[i + 1]):
                    out[indices[e]] += wdata[e] * gi
        pos += 1
        if pos > dly_steps:
            pos = 0
    ring_pos[0] = pos
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
        self.e_m = np.float32(np.exp(-p.dt / p.t_mbr))
        self.e_s = np.float32(np.exp(-p.dt / p.tau))
        self.k_vg = np.float32(p.tau / (p.t_mbr - p.tau) * (self.e_m - self.e_s))
        self.refr_steps = int(round(p.t_rfc / p.dt))
        self.dly_steps = int(round(p.t_dly / p.dt))
        self.gain = np.ones(self.n, dtype=np.float32)
        self.rng = np.random.default_rng(0)
        self.reset()

    def reset(self, seed: int | None = None):
        self.v = np.full(self.n, self.p.v_0, dtype=np.float32)
        self.g = np.zeros(self.n, dtype=np.float32)
        self.refr = np.zeros(self.n, dtype=np.int32)
        self.pend = np.zeros((self.dly_steps + 1, self.n), dtype=np.float32)
        self.ring_pos = np.zeros(1, dtype=np.int64)
        self.t_ms = 0.0
        if seed is not None:
            self.rng = np.random.default_rng(seed)

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
        """drive: {neuron_index_tuple: rate_hz | per-neuron rates}. Advances the persistent state by `steps` substeps.
        Returns per-neuron spike counts, the set of neurons that fired, and summary stats."""
        p = self.p
        if drive:
            idx = np.concatenate([np.asarray(k, dtype=np.int64) for k in drive])
            rates = np.concatenate([np.broadcast_to(np.asarray(r, np.float32), (len(k),)) for k, r in drive.items()])
            ext_p = np.clip(rates * p.dt / 1000.0, 0, 1).astype(np.float32)
        else:
            idx = np.zeros(0, np.int64); ext_p = np.zeros(0, np.float32)
        rand = self.rng.random((steps, len(idx)), dtype=np.float32)
        fired_mask = np.zeros(self.n, dtype=np.bool_)
        counts = np.zeros(self.n, dtype=np.int32)
        total = _step_kernel(self.v, self.g, self.refr, self.pend, self.ring_pos, self.indptr, self.indices, self.wdata,
                             self.gain, idx, ext_p, rand, steps, np.float32(p.v_0), np.float32(p.v_th),
                             np.float32(p.v_rst), self.e_m, self.e_s, self.k_vg, self.refr_steps, self.dly_steps,
                             fired_mask, counts)
        secs = steps * p.dt / 1000.0
        self.t_ms += steps * p.dt
        return {"counts": counts, "fired": np.flatnonzero(fired_mask), "total": int(total),
                "spikes_per_sec": total / secs, "mean_mv": float(self.v.mean()), "secs": secs}

    def rate_hz(self, counts: np.ndarray, sel: np.ndarray, secs: float) -> float:
        return float(counts[sel].sum() / max(len(sel), 1) / secs) if len(sel) else 0.0
