# Ommatid — experiment design

Status: draft v2, 2026-09-11 (v1 → v2: optic lobe replaced by FlyVis after the pilot in docs/model.md showed a zero-baseline spiking model cannot see). This document is written before the closed loop exists. It fixes the hypotheses,
the controls, the measurements and the honesty rules in advance, so that results cannot be shaped after the fact.

## 1. Question

A whole-CNS connectome tells us who is wired to whom and, through neurotransmitter prediction, with what sign.
It does not tell us what the animal does. Shiu et al. (2024) showed that a leaky integrate-and-fire model built
from the female brain connectome alone, with no fitted parameters, reproduces sugar-evoked proboscis extension.

Ommatid asks the next question: **if a connectome model is given a body and eyes, do the innate visuomotor
reflexes of a walking fly appear in the body's behaviour?** The model has two connectome-constrained parts joined
at the boundary where the fly's own physiology changes from graded to spiking: the optic lobe (FlyVis, Lappalainen
et al. 2024: 45,669 graded neurons, 64 types, 721 columns, a few trained scalars per type) and the rest of the male
CNS v1.0 (brain + ventral nerve cord, untrained spiking model after Shiu et al. 2024, 165,122 neurons). The body is
a six-legged robot with a camera. The hypotheses test the untrained part: whether the wiring downstream of the
motion and feature detectors turns their activity into the right descending commands.

## 2. Hypotheses (pre-registered)

Each hypothesis names the fly behaviour, the known circuit, the model readout and the pass criterion.

**H1 — Optomotor response.** A fly turns with wide-field visual rotation (Götz 1968). Pathway: photoreceptors →
L1/L2 → T4/T5 motion detectors → lobula plate tangential cells → descending neurons including DNa02
(Namiki 2018; Rayshubskiy 2020).
Readout: DNa02 right-minus-left firing-rate difference.
Prediction: a grating drifting rightward across the camera produces a positive right-minus-left DNa02 difference
and a rightward yaw command; leftward drift the reverse. Criterion: sign agreement in ≥ 80 % of trials, effect
distinguishable from the shuffled-connectome control at p < 0.01 (permutation test), across ≥ 30 trials per direction.

**H2 — Looming response.** An expanding dark disc drives lobula columnar cells (LC4, LC6, LPLC2) onto escape and
freezing descending neurons (von Reyn 2014; Ache 2019; Zacarias 2018).
Readout: the escape descending neurons DNp02 and DNp04 (direct LC4 targets), the giant fibre DNp01, DNp09
(stopping/freezing) and MDN (backward walking).
Prediction: looming raises these above their pre-stimulus baseline within 200 ms of brain time; a same-luminance
non-expanding disc and drifting gratings do not. Criterion: response in ≥ 70 % of looming trials, < 20 % of control
trials. Body response: stop, then back away (MDN) if it fires.
Disclosure: in the development pilot of 2026-09-11 (open loop, synthetic disc, before any parameter was frozen)
looming drove LC4 to 12 Hz and DNp04/DNp02 to 41/17 Hz while gratings and grey left them at 0 Hz.

**H3 — Phototaxis.** Walking flies orient toward light. Prediction: with one half of the camera field brighter, the
DNa02 asymmetry points toward the bright side and DNa01 (forward) rate is higher than in uniform darkness.
Criterion: as H1.

Hypotheses that fail are reported as failures. A failed hypothesis is a result about the model, not a bug to be
tuned away. Parameters are frozen before the first recorded trial (section 6).

## 3. Controls

- **C1 Shuffled wiring.** Same neurons, same in- and out-degree per neuron, edges rewired at random
  (degree-preserving). Signs and weights travel with the presynaptic neuron. If behaviours survive this, they were
  not coming from the wiring.
- **C2 Scrambled signs.** Original wiring, excitatory/inhibitory labels permuted across neurons.
- **C3 Open loop.** Recorded camera frames replayed to the brain with the body held still. Separates what the
  wiring does from what the closed loop adds.
- **C4 Blind.** No visual drive. Measures the spontaneous rate of every readout neuron, so responses are reported
  relative to a measured baseline, not to zero.

Every reported effect is a contrast against C1 and C4 at minimum.

## 4. What is measured, what is assumed, what is invented

| Component | Source | Status |
|---|---|---|
| Neurons, synapses, synapse counts | FlyEM male CNS v1.0, EM reconstruction | measured |
| Neuron types, soma side, eye column assignment | male CNS annotations | measured (curated) |
| Excitatory / inhibitory sign | consensus neurotransmitter prediction per neuron (GABA/Glu inhibitory, all else excitatory, as in Shiu 2024) | predicted from EM, not recorded |
| Optic lobe (R1-R8 → T4/T5, Tm, TmY) | FlyVis: FIB-25 connectome wiring; per-type time constants, resting potentials and one synaptic scale trained on an optic-flow task | connectome-constrained, task-trained, never fit to neural data |
| Optic lobe → central brain hand-off | FlyVis output activity, minus its grey-field baseline, rectified, × one scalar (Hz per unit) → forced spikes in the male CNS neurons of the same type and column | invented scalar, fixed before trials |
| Columns of T4/T5, Tm3, TmY (no column label in the male CNS) | synapse-weighted mean of column-carrying presynaptic partners | anatomical inference |
| Soma coordinates (for display) | male CNS annotations | measured |
| LIF dynamics (rest −52 mV, threshold −45 mV, τ_m 20 ms, τ_syn 5 ms, delay 1.8 ms, refractory 2.2 ms, 0.275 mV per synapse into the synaptic variable) | Shiu et al. 2024, reproduced from their released code | assumed, literature |
| Pairs with < 5 synapses dropped | FlyWire Codex threshold used by the paper's source table | assumed |
| Monoamines treated as excitatory, baseline firing 0 Hz | Shiu et al. 2024 | paper's convention |
| Descending-neuron rate → body velocity gain | one scalar per channel | invented, fixed before trials |
| Robot gait itself | Hiwonder kinematics, not the VNC | engineering, replaced in phase 2 |

No gains, weights or thresholds are tuned against behavioural outcomes. There is no learning and no reward.

## 5. Apparatus

**Brain.** Hetzner CPX32 (4 vCPU, 8 GB). One control step = 20 ms of brain time: two 10 ms FlyVis frames, then 100
LIF substeps of 0.2 ms (numba kernel over the CSC connectivity matrix, verified spike-for-spike against a numpy
reference). Measured cost about 70 ms wall per step on the development machine, so the fly experiences the world at
roughly one-third speed; the dilation factor is logged every step and reported with every result.

**Eye and optic lobe.** Camera frame → grey → placed on FlyVis's 721-column retina for each eye (the left eye is
the same network fed a mirrored frame) → FlyVis integrates at 10 ms steps → the activity of its output types
(T4a-d, T5a-d, Tm, TmY, T1-T3) is injected as forced spikes into the male CNS neurons of the same type and column.
The camera's 74° × 50° field covers the frontal part of each eye; the rest of the fly's ~300° field sees a
uniform grey and this is stated. A pilot (docs/model.md) showed the spiking model alone is blind: its ON pathway
needs disinhibition from a baseline it does not have.

**Body.** Hiwonder RoSpider hexapod, Raspberry Pi 5, ROS 2 Humble. The Pi runs a body agent: grabs frames,
publishes `/controller/cmd_vel`, enforces reflexes the brain cannot override (LiDAR obstacle stop, servo/battery
limits, 500 ms command watchdog → stop). Power from a fixed 12 V supply for continuous operation.

**Stimulus display.** A screen in front of the robot shows controlled stimuli (drifting gratings, looming discs,
luminance steps) for H1–H3 trials. Outside trial blocks the robot lives in the room under natural conditions and
the public stream shows that.

**Readout → body.**
yaw ∝ DNa02(right) − DNa02(left); forward ∝ mean DNa01; backward ∝ MDN; stop when DNp09 exceeds a threshold
set from the C4 baseline. Gains fixed before trials and published.

## 6. Protocol

1. Freeze: graph build (hash), kernel version, eye parameters, gains → `docs/frozen-params.md`, tagged in git.
2. Baseline block (C4): 10 minutes blind, record all readout rates.
3. Trials: randomised interleaving of H1 (left/right), H2 (loom/control), H3 (left/right bright), each trial 2 s
   of brain time stimulus after 1 s baseline; ≥ 30 trials per condition.
4. Repeat 2–3 with C1 and C2 graphs.
5. Analysis scripts run on the logged data and produce the results page. No hand-edited numbers.

## 7. Logging and openness

Every control step logs: wall time, brain time, frame hash, per-column drive summary, spike count per readout
neuron, total spikes, dilation factor, command sent, IMU yaw, LiDAR minimum, reflex state. Parquet on the server,
daily public dumps. Code MIT, connectome CC-BY with attribution, results and raw logs CC-BY.

## 8. Known limitations

- The VNC is simulated but its motor neurons do not yet drive the legs; the robot gait is engineered. Phase 2
  reads leg motor neurons directly and this document will be revised before that.
- No neuromodulation, no plasticity, no internal state (hunger, sleep).
- FlyVis models a female (FIB-25) optic lobe; the central model is male. Types are matched by name, columns by
  visual angle. FlyVis was trained for optic flow, so feature pathways it was not trained on may be under-expressed.
- The Shiu-class spiking model has no baseline firing, so disinhibition cannot act on silent neurons anywhere in the
  central brain either; this is a property of the model class, reported, not corrected.
- The brain runs slower than real time; dynamic behaviours are compared in brain time, not wall time.
- Two DNa02 and two DNa01 neurons exist in the dataset (one per side). Readouts on two cells are noisy; rates are
  averaged over 20 ms windows and many trials, and reported with confidence intervals.

## 9. Milestones

- M0 data + graph + kernel + server — done 2026-09-11
- M1 brain service: FlyVis eye + LIF central model + readout, persistent state, telemetry, replay mode, tests
  (2026-09-11: model corrected and validated, hybrid pilot passes looming; service and telemetry pending)
- M2 body agent on the Pi: frames up, commands down, reflexes, tunnel, bench test
- M3 closed loop + stimulus rig + protocol run + analysis
- M4 public site and continuous stream
- M5 write-up and data release

## References

Shiu PK et al. (2024) A Drosophila computational brain model reveals sensorimotor processing. Nature.
Götz KG (1968) Flight control in Drosophila by visual perception of motion. Kybernetik.
Namiki S et al. (2018) The functional organization of descending sensory-motor pathways in Drosophila. eLife.
Rayshubskiy A et al. (2020) Neural circuit mechanisms for steering control in walking Drosophila. bioRxiv.
Bidaye SS et al. (2014) Neuronal control of Drosophila walking direction. Science.
von Reyn CR et al. (2014) A spike-timing mechanism for action selection. Nature Neuroscience.
Ache JM et al. (2019) Neural basis for looming size and velocity encoding in the Drosophila giant fiber escape pathway. Current Biology.
Zacarias R et al. (2018) Speed dependent descending control of freezing behavior in Drosophila. Nature Communications.
Joesch M et al. (2010) ON and OFF pathways in Drosophila motion vision. Nature.
Clark DA et al. (2011) Defining the computational structure of the motion detector in Drosophila. Neuron.
Lappalainen JK et al. (2024) Connectome-constrained networks predict neural activity across the fly visual system. Nature.
FlyEM male CNS v1.0 (2026) HHMI Janelia, Cambridge Connectomics Group, Google Research. CC-BY.
