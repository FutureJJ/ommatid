# Frozen parameters — v2, 2026-09-11 (tag `freeze-v2`)

Written before the first v2 trial. Changes from v1 are exactly the amendments pre-registered in docs/experiment.md §10.

## Artefacts (sha256 prefixes)
```
build/graph.npz                  050359b2a09f
build/graph_shuffled.npz         3bfdad7c298a
build/graph_shuffled_2027.npz    e73220356b22
build/graph_shuffled_2028.npz    299e5fb35fbc
build/graph_scrambled.npz        54cf9af0b3d0
build/graph_clamped.npz          a2f54e8d2a80
build/columns.npz                382775cc1df0
```
- `columns.npz` is built from `graph.npz` (tools/build_columns.py) and loaded unchanged by every variant; the service refuses
  a variant whose neuron identities do not match it and records both hashes in every snapshot.
- C1 shuffled: three seeds (2026, 2027, 2028); multigraph-degree-preserving endpoint permutation, coincident edges merged
  (0.19 % of edges; unique in-degree changes for ~5,700 neurons).
- C2 scrambled signs: seed 2026. C5 clamped: 762,788 synapses onto the 38,011 FlyVis-driven neurons removed.

## Spiking model
As v1 (Shiu et al. 2024): v_0 = v_rst = −52 mV, v_th = −45 mV, t_mbr = 20 ms, τ_syn = 5 ms, t_rfc = 2.2 ms, t_dly = 1.8 ms,
w_syn = 0.275 mV, dt = 0.2 ms, 100 substeps per control step. Baseline 0 Hz. Forced-spike activation.

## Optic lobe and hand-off
- FlyVis ensemble `flow/0000/000`, dt 10 ms, 2 frames per step; canvas 391 px, 5.8° per 13 px; eye centre 45° lateral;
  camera 74° HFOV on the midline; left eye = mirrored frame; **off-camera surround fixed at 50 % grey** (v1: frame mean).
- Injected types: T1–T3, T4a–d, T5a–d, Tm*, TmY*; rate = hz_per_unit × max(0, activity − grey steady state).
- **hz_per_unit = 100**, chosen by the pre-registered rule (tools/calibrate_gain.py): largest of {25, 50, 75, 100, 150} for which
  the preferred-eye HS cells fire ≤ 150 Hz to a full-contrast calibration grating (period 0.40 sw, 0.60 sw/s, sinusoidal —
  not a test stimulus). Table: 25 → 48 Hz, 50 → 88, 75 → 118, **100 → 141**, 150 → 176.
  Observation recorded, not acted on: in the model the HS cells of the OTHER eye fire more than the preferred eye's
  (200 vs 131 Hz at 100), i.e. HS direction preference is not reproduced as expected. To be examined after the runs.
- Additive forcing (injected neurons keep recurrent input) is the main condition; C5 removes it.

## Protocol v2 (ommatid/brain/protocol.py, PROTOCOL_VERSION 2)
- trial = 2000 ms grey baseline + 2000 ms stimulus (brain time); 8 conditions × 30 = 240 planned trials, seed 2026
- loom: disc 5 % → 90 % of screen height; disc: 90 % disc, contrast 0 → 1 over the stimulus (fade-in); recede: loom reversed;
  gratings: period 0.20 sw, 0.30 sw/s, square wave; bright halves; grey
- interruption (any step without a fresh frame): current trial invalid, 3000 ms grey recovery, replacement trial appended
- display acknowledges each change; steps record frame receipt time and age; analysis assigns a step the display state
  acknowledged ≥ 0.30 s before its frame was received

## Analysis (tools/analyze.py --mode v2)
- primary table on valid trials only; each control condition reported separately, never pooled
- H2: onset = first of 2 consecutive stimulus steps with any of DNp01/DNp02/DNp04/DNp09/MDN > baseline mean + 2 SD;
  criterion onset ≤ 200 ms brain time in ≥ 70 % of valid loom trials and < 20 % of valid trials of each control
- H1/H3 as v1 (DNa02 asymmetry sign agreement ≥ 80 %); wider DN panel reported descriptively
- graph contrasts (original vs each control) reported with permutation p; the C1 contrast is informative for wiring
  specificity only now that the input map is fixed

## Viewing geometry (to be re-recorded at run start)
laptop screen 30 cm wide at 40 cm, camera-height centre; lighting recorded per run.
