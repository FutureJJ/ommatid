# Ommatid — model notes and findings (2026-09-11)

Development record of how the brain model was built, what broke, and what the evidence says. Numbers here come
from tools in `tools/` and are reproducible from `build/graph.npz`.

## 1. The published equations, and a sixfold error in the reference project

Shiu et al. 2024 (Nature) released their Brian2 code (philshiu/Drosophila_brain_model). The model is

    dv/dt = (v_0 − v + g) / t_mbr        dg/dt = −g / τ        spike: v > v_th → v = v_rst, g = 0, refractory t_rfc
    presynaptic spike, after t_dly:  g_post += sign · n_synapses · w_syn

with v_0 = v_rst = −52 mV, v_th = −45 mV, t_mbr = 20 ms, τ = 5 ms, t_rfc = 2.2 ms, t_dly = 1.8 ms, w_syn = 0.275 mV.
A synapse adds 0.275 mV to the synaptic variable g, which decays in 5 ms while the membrane integrates it over
20 ms; the resulting peak depolarisation is 0.043 mV (at ~9 ms). The project this work started from
(fruitflydev/flycoinrh) adds 0.275 mV straight to v. That is about six times too strong.

Consequence, measured on the male CNS graph with a 20 ms drive on the lamina then silence
(`tools/stability.py`), mean rate per neuron in successive 20 ms windows:

| synaptic scale | direct-to-v (reference project) | paper's equations (this work) |
|---|---|---|
| 1.0 | 44 → 56 → 52 → 52 … self-sustained, ~52 Hz/neuron | 2.6 → 0.3 → 0 → 0 … decays |
| 1.5 | — | 3.3 → 0.9 → 2.7 → 5.8 → 9.7 → 10.5 … self-sustained |
| 0.5 | 25 → 24 → 0.4 → 0 … | — |

The reference project's brain is permanently in runaway; its descending-neuron "readouts" (e.g. DNp09 at
167–417 Hz) are refractory-period ceilings, not responses. With the published equations the network is stable at
w_syn and the runaway threshold lies between 1.0× and 1.5×, consistent with the paper's remark that w_syn was
chosen just below runaway.

Other conventions taken from the paper and its code: GABA and glutamate inhibitory, everything else (including
dopamine, octopamine, serotonin, unknown) excitatory; baseline firing 0 Hz; activation = forced Poisson spikes.
Histamine (photoreceptors; absent from the paper's dataset) is set inhibitory. Connections with fewer than 5
synapses are dropped (the FlyWire Codex threshold of the paper's source table). Result: 165,122 neurons,
6,235,682 edges, 3,919,245 excitatory, 2,316,437 inhibitory.

The numba kernel reproduces a plain-numpy implementation of these equations spike for spike (`tests/test_kernel.py`).

## 2. Anatomy behaves in the model

Activating LC4 (the looming-sensitive lobula columnar type, 126 cells) at 150 Hz for 200 ms makes the two
strongest downstream responders DNp04 (370 Hz) and DNp02 (305 Hz) — the known LC4 → escape descending pathway
(Ache 2019; von Reyn 2014). Activating T4a-d at 100 Hz drives CT1, LPi cells, H2, HS cells, the lobula plate
circuit. Nothing was tuned to obtain this. (`tools/propagation.py`)

## 3. Eye geometry from the data

Lamina monopolar cells carry hex column coordinates (assignedOlHex1/2). Against soma positions of the same cells:
hex1+hex2 correlates with soma y at r = −0.98 (left) and −1.00 (right) → dorso-ventral axis; hex1−hex2 moves the
column medially on both sides → antero-posterior axis, frontal = medial. Only 15 columnar types carry a column
label; T4/T5, Tm3 and TmY do not, and receive one as the synapse-weighted mean angle of their column-carrying
presynaptic partners (`Eye.column_angles_all`).

## 4. The spiking model alone is blind

With camera luminance driving L1/L2/L3 (all three depolarise to dimming, as in the animal), `tools/hierarchy.py`:

| stage | grey | drifting grating | looming disc |
|---|---|---|---|
| lamina L1/L2 | 45 Hz | 46 Hz | 31 Hz |
| medulla OFF (Tm1/Tm2) | 5–7 Hz | 6–8 Hz | 4–5 Hz |
| medulla ON (Mi1/Tm3) | 0 | 0 | 0 |
| T4 / T5 | 0 | 0 | 0 |
| LC4 / LPLC2 | 0 | 0 | 0 |
| DNp02 / DNp04 | 0 | 0 | 0 |

Two structural causes. (a) The ON pathway begins with disinhibition: L1 is glutamatergic, inhibits Mi1/Tm3, and
falls silent at brightening; in a model whose baseline is 0 Hz there is nothing to disinhibit, so Mi1/Tm3 never
fire. (b) Optic-lobe columnar neurons are graded, not spiking; excitation and inhibition are balanced and each
spiking stage attenuates roughly tenfold. Multiplying all optic-lobe synapses by 2–5 changes nothing
(`tools/ol_gain_sweep.py`): E and I scale together. Sustained tonic lamina spiking also saturates two descending
neurons (DNb05, DNg33 at ~390 Hz through LPLC4), an artefact of the front-end rather than a response.

Conclusion: the Shiu model class is a model of the spiking central nervous system; it cannot be made to see by
turning knobs, and pretending otherwise would have produced a robot driven by artefacts.

## 5. The optic lobe from FlyVis

Lappalainen et al. 2024 (Nature) trained connectome-constrained networks of the optic lobe (FIB-25 wiring,
45,669 graded units, 64 cell types, 721 columns) on an optic-flow task, with only a few free scalars per cell type,
and showed they predict measured tuning (including T4/T5 direction selectivity) without ever seeing neural data.
Code and pretrained ensembles are MIT (TuragaLab/flyvis). On this machine the pretrained model runs at
16–18 ms per 20 ms control step for two eyes on CPU.

Hand-off: FlyVis output types (T1-T3, T4a-d, T5a-d, Tm, TmY) → activity minus grey-field steady state, rectified,
× 100 Hz per unit → forced spikes in the male CNS neurons of the same type at the nearest column (≤ 6°). The left
eye is the same network fed a mirrored frame. 9,183 male neurons receive input this way; T4/T5 columns are the
anatomically inferred ones of section 3.

Hybrid pilot (`tools/pilot_hybrid.py`, open loop, synthetic stimuli, nothing frozen yet):

| condition | LC4 | DNp04 | DNp02 | T4a right / T4b right | T4a left / T4b left |
|---|---|---|---|---|---|
| grey | 0 | 0 | 0 | 0.3 / 1.4 | 0.2 / 1.2 |
| grating → right | 0 | 0 | 0 | **8.7** / 5.7 | 5.8 / **10.0** |
| grating → left | 0 | 0 | 0 | 6.3 / **9.9** | **9.6** / 5.9 |
| looming disc | **12** | **41** | **17** | — | — |

Looming reaches the escape descending neurons and nothing else does; motion direction is encoded binocularly the
way it is in the animal (front-to-back on one eye, back-to-front on the other). HS cells respond to both directions
at 190–240 Hz with a small correctly-signed asymmetry; DNa02 fires only on the left in this pilot, which will be
examined as a property of the two cells' inputs in this dataset, not tuned away.

Open items before parameters are frozen: the Hz-per-unit scalar (HS cells near ceiling suggests it is high), the
placement of the FlyVis array within each eye (45° lateral), and the max-distance for column matching.
