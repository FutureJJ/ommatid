"""Stability sweep: does the network self-sustain activity with no image?

For each global synaptic scale s (multiplying the 0.275 mV/synapse weights), start from rest, apply either
(a) a single 20 ms kick to L1/L2 at 100 Hz then nothing, or (b) the tonic 5 Hz blind drive, and report the
population spike rate over successive 20 ms windows. A physiological baseline is a few Hz per neuron; a flat
ceiling near the refractory limit (~450 Hz) is runaway.
"""
import sys, numpy as np
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.eye import Eye

STEPS = 100
scales = [float(x) for x in (sys.argv[1:] or ["1.0", "0.5", "0.25", "0.1"])]
b = Brain("build/graph.npz"); eye = Eye(b)
w0 = b.wdata.copy()
cols = tuple(eye.idx)

def reset():
    b.reset(seed=0)

def window_rates(drives):
    out = []
    for d in drives:
        r = b.run(d, STEPS)
        out.append(r["total"] / b.n / r["secs"])     # mean Hz per neuron in this window
    return out

for s in scales:
    b.wdata[:] = w0 * np.float32(s)
    reset()
    kick = window_rates([{cols: np.float32(100.0)}] + [{}] * 9)
    reset()
    tonic = window_rates([eye.blind()] * 10)
    fmt = lambda xs: " ".join(f"{x:6.1f}" for x in xs)
    print(f"scale {s:4.2f} | kick then silence (Hz/neuron per 20 ms): {fmt(kick)}")
    print(f"           | tonic 5 Hz on L1/L2                         : {fmt(tonic)}")
