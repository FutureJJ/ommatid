# Frozen parameters — v1, 2026-09-11

Written before the first recorded trial, as required by docs/experiment.md §6. Every value below is what the code
used for the v1 protocol run; none was chosen by looking at behavioural outcomes. Development pilots that preceded
this freeze are disclosed in docs/model.md §5 (open-loop synthetic stimuli; they informed nothing but the
hand-off scalar's order of magnitude, which was set to the paper's activation rate scale).

## Graph
- FlyEM male CNS v1.0, traced neurons, connections with ≥ 5 synapses; signs per Shiu 2024 (GABA/Glu −, else +; histamine −)
- 165,122 neurons, 6,235,682 edges; `build/graph.npz` sha256 prefix recorded in every telemetry snapshot (`graph_sha`)
- Controls: `graph_shuffled.npz` (C1, seed 2026), `graph_scrambled.npz` (C2, seed 2026) from `tools/make_controls.py`

## Spiking model (Shiu et al. 2024)
v_0 = v_rst = −52 mV · v_th = −45 mV · t_mbr = 20 ms · τ_syn = 5 ms · t_rfc = 2.2 ms · t_dly = 1.8 ms · w_syn = 0.275 mV · dt = 0.2 ms
Control step = 100 substeps = 20 ms brain time. Baseline firing 0 Hz. Forced-spike activation.

## Optic lobe (FlyVis, Lappalainen et al. 2024)
- ensemble `flow/0000/000`, dt = 10 ms, 2 frames per control step, canvas 391 px, 5.8° per 13 px
- eye centre placed 45° lateral of the midline; camera 74° HFOV centred on the midline; left eye = mirrored frame
- hand-off: output types T1–T3, T4a–d, T5a–d, Tm*, TmY*; rate = 100 Hz × max(0, activity − grey steady state)
- column matching: nearest by visual angle within 6°; columns of unlabeled types = synapse-weighted mean of column-carrying inputs

## Readout (ommatid/brain/readout.py)
- populations: DNa02 L/R, DNa01 L/R, MDN, DNp09, DNp01, DNp02, DNp04 (by type name and soma side)
- rates smoothed with an exponential average, time constant 200 ms of brain time
- turn = (DNa02_R − DNa02_L) / 200 Hz · forward = mean DNa01 / 200 Hz · backward = MDN / 200 Hz · stop if DNp09 ≥ 150 Hz
- body limits: 0.08 m/s, 0.5 rad/s. During the v1 protocol the body is in dry run (held still): readouts are neural.

## Stimuli (ommatid/brain/protocol.py, site/stimulus.html)
- trial = 1000 ms grey baseline + 2000 ms stimulus, brain time; conditions interleaved at random (seed recorded)
- grating: square wave, period 0.20 screen widths, drift 0.30 screen widths per second of brain time, right or left
- loom: dark disc on white, 5 % → 90 % of screen height over the 2000 ms; control disc held at 50 %
- half-field: right or left half white, other half black; grey: uniform 50 %
- viewing geometry recorded per run (screen width, distance, room light) in the run note

## Pass criteria
As pre-registered in docs/experiment.md §2, evaluated by `tools/analyze.py` on the Parquet logs; no other analysis
is reported as a test of H1–H3.
