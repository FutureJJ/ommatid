# Ommatid

A real fruit-fly nervous system, simulated neuron by neuron, given a six-legged metal body.

165,122 neurons and 10,228,000 signed synaptic connections, every one measured by electron microscopy from a single
male *Drosophila melanogaster* (FlyEM male CNS v1.0, CC-BY). The simulation is a leaky integrate-and-fire model with
the parameters of Shiu et al. 2024 (Nature). Nothing is trained; the wiring is the behaviour.

The fly sees through the hexapod's camera, sampled onto its own 892 retinotopic eye columns. It moves through the
descending neurons a fly actually walks with: DNa02 (steering), DNa01 (forward), MDN (backward), DNp09 (stop).
The body is a Hiwonder RoSpider hexapod. The brain runs on a server; the body streams what it sees and receives what
to do. Everything is watchable live.

## Purpose

Ommatid is a body-transfer experiment. A nervous system that evolved for one body — six legs a few millimetres long,
wings, compound eyes spanning almost the whole sphere — is placed in a body it never had: a six-legged robot with one
camera, no wings, joints driven by servos. Phase 1 measures what survives the transfer untouched: which reflexes still
work, which fail, and where exactly the mismatch is (field of view, timing, proprioception). Phase 2 lets the nerve cord
drive the legs and feel them through the robot's own sensors. Phase 3 asks what an adapting nervous system needs to
live in a new body at all: which plasticity, grounded in the fly's own circuits, closes the gap. The point is to leave a
carefully measured reference for a question that will be asked of other nervous systems one day: what happens to a
mind when its body changes.

## Status (11 September 2026)

Phase 1 is closed: protocol v1 (210 trials) established none of the three pre-registered reflexes, and its apparent looming
response was traced to an input artefact after an independent review; protocol v2 (frame-locked, calibrated gain) ran 108
valid trials before being stopped — every stimulus shifted the steering readout the same way, the looming detectors stayed
silent under the frozen gain. Both are recorded in `docs/runs.md` and on the results page, with the corrections.

Phase 2 is wired and live in dry run: the nerve cord's 266 leg motor neurons compute targets for the 18 servos every step
(shown on the site, Plate VII), and the robot's joint positions feed 563 of the fly's own proprioceptors. Its first
measurement, P2-a, is pre-registered (`docs/phase2.md` §10, tag `freeze-p2a`) and waits for a still body. Nothing has been
learned or tuned; the motto changes only in phase 3.

## Layout
- `ommatid/brain/` — connectome graph, LIF kernel (numba), eye, FlyVis optic lobe, descending-neuron readout, leg motor pools (`motor.py`), proprioceptors (`proprio.py`), the service
- `ommatid/body/` — Raspberry Pi side: camera, gait commands, reflexes
- `ommatid/stream/` — telemetry websocket and the public site
- `tools/build_graph.py` — builds `build/graph.npz` from the CC-BY connectome files in `data/`

## Attribution
Connectome: FlyEM male CNS v1.0, HHMI Janelia FlyEM, Cambridge Connectomics Group and Google Research, CC-BY.
Model: Shiu et al. 2024, *Nature*. Readout design after fruitflydev/flycoinrh (MIT).
