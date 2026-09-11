# Ommatid — experiment design

Status: draft v1, 2026-09-11. This document is written before the closed loop exists. It fixes the hypotheses,
the controls, the measurements and the honesty rules in advance, so that results cannot be shaped after the fact.

## 1. Question

A whole-CNS connectome tells us who is wired to whom and, through neurotransmitter prediction, with what sign.
It does not tell us what the animal does. Shiu et al. (2024) showed that a leaky integrate-and-fire model built
from the female brain connectome alone, with no fitted parameters, reproduces sugar-evoked proboscis extension.

Ommatid asks the next question: **if the same kind of untrained connectome model is given a body and eyes, do the
innate visuomotor reflexes of a walking fly appear in the body's behaviour?** The model is the male CNS v1.0
(brain + ventral nerve cord, 165,122 neurons). The body is a six-legged robot with a camera.

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
Readout: DNp09 rate (stopping/freezing) and MDN rate (backward walking).
Prediction: looming raises DNp09 and/or MDN above their pre-stimulus baseline within 200 ms of brain time; a
same-luminance non-expanding disc does not. Criterion: response in ≥ 70 % of looming trials, < 20 % of control trials.

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
| Excitatory / inhibitory sign | consensus neurotransmitter prediction per neuron | predicted from EM, not recorded |
| Soma coordinates (for display) | male CNS annotations | measured |
| LIF parameters (rest −52 mV, threshold −45 mV, τ 20 ms, refractory 2.2 ms) | Shiu et al. 2024 | assumed, literature |
| 0.275 mV per synapse | Shiu et al. 2024 | assumed, literature |
| Pairs with < 3 synapses dropped | reconstruction-noise threshold | assumed |
| Monoamines (DA, OA, 5-HT) carry zero fast weight | modulatory in reality | simplification |
| Photoreceptor → L1/L2 drive from camera luminance change | ON/OFF split (Joesch 2010; Clark 2011) | modelled, simplified |
| Poisson external drive, rate ∝ contrast | standard | modelled |
| Descending-neuron rate → body velocity gain | one scalar per channel | invented, fixed before trials |
| Robot gait itself | Hiwonder kinematics, not the VNC | engineering, replaced in phase 2 |

No gains, weights or thresholds are tuned against behavioural outcomes. There is no learning and no reward.

## 5. Apparatus

**Brain.** Hetzner CPX32 (4 vCPU, 8 GB), numba LIF kernel over the CSC connectivity matrix. One control step =
20 ms of brain time (100 substeps of 0.2 ms). Measured cost 65 ms wall per step on one core, so the fly experiences
the world at roughly one-third speed; the dilation factor is logged every step and reported with every result.

**Eye.** Camera frame → grey → sampled at the fly's own eye columns (hex coordinates from the annotations,
each column's L1 and L2 cell). L1 receives brightening, L2 receives dimming, each relative to a per-column
adapting mean; both have a tonic baseline. The camera's ~70° field is mapped onto the frontal part of both eyes;
the fly's real ~300° field is not available and this is stated.

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
- The eye model is a caricature of phototransduction; the temporal-contrast split is the minimum needed for
  motion detection to be possible at all.
- The brain runs slower than real time; dynamic behaviours are compared in brain time, not wall time.
- Two DNa02 and two DNa01 neurons exist in the dataset (one per side). Readouts on two cells are noisy; rates are
  averaged over 20 ms windows and many trials, and reported with confidence intervals.

## 9. Milestones

- M0 data + graph + kernel + server — done 2026-09-11
- M1 brain service: eye, readout, persistent state, telemetry, replay mode, tests
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
FlyEM male CNS v1.0 (2026) HHMI Janelia, Cambridge Connectomics Group, Google Research. CC-BY.
