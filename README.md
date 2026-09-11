# Ommatid

A real fruit-fly nervous system, simulated neuron by neuron, given a six-legged metal body.

165,122 neurons and 10,228,000 signed synaptic connections, every one measured by electron microscopy from a single
male *Drosophila melanogaster* (FlyEM male CNS v1.0, CC-BY). The simulation is a leaky integrate-and-fire model with
the parameters of Shiu et al. 2024 (Nature). Nothing is trained; the wiring is the behaviour.

The fly sees through the hexapod's camera, sampled onto its own 892 retinotopic eye columns. It moves through the
descending neurons a fly actually walks with: DNa02 (steering), DNa01 (forward), MDN (backward), DNp09 (stop).
The body is a Hiwonder RoSpider hexapod. The brain runs on a server; the body streams what it sees and receives what
to do. Everything is watchable live.

## Layout
- `ommatid/brain/` — connectome graph, LIF kernel (numba), eye, descending-neuron readout
- `ommatid/body/` — Raspberry Pi side: camera, gait commands, reflexes
- `ommatid/stream/` — telemetry websocket and the public site
- `tools/build_graph.py` — builds `build/graph.npz` from the CC-BY connectome files in `data/`

## Attribution
Connectome: FlyEM male CNS v1.0, HHMI Janelia FlyEM, Cambridge Connectomics Group and Google Research, CC-BY.
Model: Shiu et al. 2024, *Nature*. Readout design after fruitflydev/flycoinrh (MIT).
