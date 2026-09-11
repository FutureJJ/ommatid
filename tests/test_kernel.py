"""The numba kernel must reproduce a plain-numpy implementation of the same equations spike for spike."""
import sys, numpy as np
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain


def numpy_reference(b: Brain, drive_idx, drive_p, rand, steps):
    p = b.p
    n = b.n
    v = np.full(n, p.v_0, np.float32); g = np.zeros(n, np.float32); refr = np.zeros(n, np.int32)
    pend = np.zeros((b.dly_steps + 1, n), np.float32); pos = 0
    counts = np.zeros(n, np.int32)
    W = None
    for s in range(steps):
        g += pend[pos]; pend[pos] = 0
        active = refr <= 0
        refr[~active] -= 1
        v[active] = p.v_0 + (v[active] - p.v_0) * b.e_m + g[active] * b.k_vg
        g[active] *= b.e_s
        hit = drive_idx[rand[s] < drive_p]
        hit = hit[refr[hit] <= 0]
        v[hit] = p.v_th + 1.0
        fired = np.flatnonzero((refr <= 0) & (v > p.v_th))
        counts[fired] += 1
        v[fired] = p.v_rst; g[fired] = 0; refr[fired] = b.refr_steps
        out = (pos + b.dly_steps) % (b.dly_steps + 1)
        for i in fired:
            a, z = b.indptr[i], b.indptr[i + 1]
            np.add.at(pend[out], b.indices[a:z], b.wdata[a:z] * b.gain[i])
        pos = (pos + 1) % (b.dly_steps + 1)
    return counts


def test_kernel_matches_reference():
    b = Brain("build/graph.npz")
    sel = b.where(type="L2")[:300]   # L2 is cholinergic (excitatory); L1 is glutamatergic and would inhibit only
    steps = 60
    rng = np.random.default_rng(3)
    rand = rng.random((steps, len(sel)), dtype=np.float32)
    drive_p = np.full(len(sel), 150 * b.p.dt / 1000, np.float32)
    ref = numpy_reference(b, sel, drive_p, rand, steps)
    b.reset()
    from ommatid.brain.lif import _step_kernel
    fired_mask = np.zeros(b.n, np.bool_); counts = np.zeros(b.n, np.int32)
    _step_kernel(b.v, b.g, b.refr, b.pend, b.ring_pos, b.indptr, b.indices, b.wdata, b.gain, sel.astype(np.int64),
                 drive_p, rand, steps, np.float32(b.p.v_0), np.float32(b.p.v_th), np.float32(b.p.v_rst), b.e_m, b.e_s,
                 b.k_vg, b.refr_steps, b.dly_steps, fired_mask, counts)
    assert counts.sum() > len(sel) * 2, "input should propagate beyond the driven cells"
    assert np.array_equal(counts, ref), f"mismatch on {int((counts != ref).sum())} neurons"


if __name__ == "__main__":
    test_kernel_matches_reference(); print("kernel == numpy reference: OK")
