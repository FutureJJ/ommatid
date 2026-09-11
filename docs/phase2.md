# Phase 2 — the nerve cord drives and feels the legs (design, 2026-09-11, draft for approval)

Phase 1 read the brain's descending neurons and let the robot's own gait controller walk. Phase 2 removes that
controller: the fly's ventral nerve cord (VNC) commands the 18 servos through its leg motor neurons, and the legs report
back through the fly's own leg sensory neurons. This is the body the fly has to learn (phase 3); phase 2 asks what the
untouched wiring does with it first.

## 1. What the connectome offers

| | male CNS v1.0 | robot |
|---|---|---|
| legs | 6 (T1 front, T2 mid, T3 hind; L/R) | 6 (front, mid, hind; L/R) |
| leg motor neurons | 381 (fl 135, ml 116, hl 130; ≈ 65 per leg), named by muscle | 3 servos per leg |
| leg proprioceptors | chordotonal organs 403, campaniform sensilla 175, hair plates 112 | servo position at 46 Hz; commanded vs reached position; IMU |
| leg touch | leg bristles 688, "leg" sensory 853 | none yet (no foot contact sensor) |
| self-motion | haltere 56, neck 2, IMU has no fly equivalent | IMU 6-axis |

Leg identity of a sensory neuron comes from its entry nerve (ProLN front, MesoLN mid, MetaLN hind; ADMN carries the
campaniform sensilla); side is not annotated for most sensory neurons and is inferred from soma position or from the
side of the motor neurons they synapse onto (to be done and checked).

## 2. Motor mapping — motor-neuron pools → servo targets

Each servo gets an antagonist pair of pools; the target angle moves with the difference of their smoothed rates:

| servo | fly joint | agonist pool (flexion / protraction) | antagonist pool |
|---|---|---|---|
| coxa (yaw) | thorax–coxa | Tergopleural/Pleural promotor MN, Sternal anterior rotator MN | Pleural remotor/abductor MN, Sternal posterior rotator MN |
| femur (pitch) | coxa–trochanter–femur | Tr flexor MN, Acc. tr flexor MN, Fe reductor MN | Tr extensor MN, Sternotrochanter MN, Tergotr. MN |
| tibia (pitch) | femur–tibia | Ti flexor MN, Acc. ti flexor MN | Ti extensor MN |
| (not mapped) | tibia–tarsus | Ta depressor MN, Ta levator MN, ltm | — (robot has no tarsus joint) |

`angle = rest + gain · (rate_agonist − rate_antagonist)`, rates smoothed over 50 ms of brain time; gain per joint is one
scalar, fixed before trials; servo limits from `body/limits.py`. Timing: the LIF step is 20 ms brain time at ~100 ms wall;
servo targets are sent every step with a 100 ms move duration — the robot moves at 1/5 of the fly's speed, consistently.

## 3. Sensory mapping — servo state → the fly's proprioceptors

| fly sensor | encodes in the animal | robot signal | injection |
|---|---|---|---|
| femoral chordotonal organ (per leg) | joint angle, velocity, vibration | femur and tibia servo positions, their derivatives | position-tuned sub-populations (chordotonal neurons are angle-tuned): rate ∝ Gaussian around each neuron's preferred angle, assigned across the pool; velocity-tuned fraction ∝ |dθ/dt| |
| hair plates | joint at an extreme position | angle beyond 80 % of range | on/off |
| campaniform sensilla | cuticle strain = load | commanded − reached position (servo lag under load), and stance/swing from IMU + kinematics | rate ∝ estimated load |
| leg bristles | touch | none (no contact sensor) | silent; stated |
| halteres, neck | body rotation | IMU angular velocity | rate ∝ |ω| per axis, to haltere sensory pools |

All injected as forced Poisson spikes at the paper's activation scale, the same convention as the visual hand-off. Per-leg
identity from the entry nerve; side as inferred in §1 and verified by connectivity before use.

## 4. What is measured (pre-registered before the first trial)

Body held off the ground on a stand for the first trials (legs free to move, nothing at risk), then on the floor.

- **P2-a Motor output exists.** With visual input only (as in phase 1), do leg motor pools fire at all? Rates per pool per
  leg, with and without proprioceptive feedback.
- **P2-b Reflex loops.** Perturb one servo (move the tibia 20° externally) and measure whether the fly's motor output on
  that leg responds within 100 ms of brain time — the resistance reflex the femoral chordotonal organ drives in the animal.
  Criterion: response in ≥ 70 % of perturbations on the perturbed leg, < 20 % on other legs; control graph shows neither.
- **P2-c Rhythm.** Is there any periodic alternation between agonist and antagonist pools (autocorrelation peak in 0.2–2 Hz
  of brain time) when the body is on the ground? Reported as a spectrum, no criterion — nobody knows.
- **P2-d Coordination.** If P2-c is positive: phase relations between legs (tripod vs metachronal vs none).

Failure of P2-b/c/d is expected and is the baseline for phase 3.

## 5. Engineering

- `ommatid/brain/motor.py` — pools by type/leg/side, rate smoothing, angle mapping, limits.
- `ommatid/brain/proprio.py` — servo state → sensory drive (angle-tuned chordotonal model, hair plate, load proxy, IMU).
- body agent: publishes all 18 servo targets per step (`/servo_controller`), streams servo positions at 46 Hz with the
  frame; safety unchanged (lease, battery, LiDAR) plus a joint-rate limit and a stand mode.
- service: one more injection source (proprioception) into `Brain.run`; motor readout replaces the DN→cmd_vel path when
  phase 2 mode is on. Compute: +5,000 injected neurons, negligible; wall time unchanged.
- Time: two weeks for build and bench tests, then trials.

## 6. What must be true before we say "learning"

Phase 2 has no plasticity. The motto changes only when phase 3's dopamine-gated mushroom-body plasticity and the
central-complex heading plasticity are running and a pre-registered integration metric improves over days against the
plasticity-off control.

## 7. Measured on the graph (2026-09-11, `ommatid/brain/motor.py`, `proprio.py`, `tools/build_sensory_sides.py`)
- Motor pools: 266 leg motor neurons mapped to the 18 servos. Per leg and side: coxa agonists 2–6 / antagonists 4–7,
  femur 11–16 / 5–8, tibia 11–17 / 2. Tibia extensor pools are small (2 cells) — the flexion/extension balance of that
  joint will rest on few neurons; noted.
- Proprioceptors with an inferred side: chordotonal 399 (18–100 per leg), hair plates 71, campaniform 37, halteres 56;
  563 neurons injected in total. Side inference from one-hop output partners has median confidence 0.66–0.74 (many leg
  sensory neurons project to both sides), so the per-leg pools are approximate; the perturbation test (P2-b) will show
  whether the mapping is good enough to produce a same-leg reflex.

## 8. First smoke result (2026-09-11, synthetic body, exploratory — not a trial)
With the real graph, the visual pipeline on a grey frame, and a synthetic body reporting the standing pose except the
left-front tibia held 19° flexed, the leg motor pools fire for the first time: mid-left coxa promotors 149 Hz, mid-left
tibia extensors 191 Hz, mid-right coxa 127 Hz, hind-leg pools 20–30 Hz, left-front femur antagonists 32 Hz. A single
perturbed joint produces motor output mostly on OTHER legs (intersegmental), which is exactly what P2-b is designed to
quantify. The 18 servo targets that result would move several joints by 20–30°, so the first real trials are on a stand.

## 9. First live proprioception (2026-09-11 15:33 UTC, robot standing, body in dry run — exploratory)
The real servo positions of the standing robot now feed the leg proprioceptors (18 servos, 563 sensory neurons) and the
nerve cord answers with a tonic motor pattern: mid-leg coxa promotors 141–149 Hz, mid-leg tibia extensors 120–198 Hz,
front-leg femur antagonists 22–41 Hz, hind legs 5–30 Hz. The resulting servo targets would lower the left-front femur by
~32° and raise the right-front by ~18° (clamped by the ±45° range) — the standing pose is not a fixed point of the fly's
reflexes in this body. Nothing moved (dry run). This is why the first real trials need a stand: whether the fly settles into
a posture or oscillates is the first thing P2-a will record, with the legs in the air.

## 10. Pre-registration of P2-a in the dry run (2026-09-11, before the first block; parameters in docs/frozen-params-p2.md)

There is no stand yet and the body stays in dry run, so §4's first question is asked in the only form the body allows:

**P2-a (dry run).** With the camera feeding the eye (free viewing) and the body standing still, do the leg motor-neuron pools
fire, and does the static proprioceptive report of the standing pose change what they do? Two graphs (original, C1 shuffled
seed 2026), for each: feedback ON / OFF / ON / OFF, 150 s of brain time per arm, first 20 s after every switch excluded.
Criterion: at least one of the 18 motor units has a pool with a mean rate > 5 Hz in the original graph's feedback-on blocks.
Reported without a criterion: every unit's rates, the servo angles that would result (the body would clamp them to ± 15°),
agonist − antagonist spectra in 0.2–2 Hz, feedback on vs off (Holm over 18 units), original vs shuffled.

What this can and cannot say. It can say whether the untouched nerve cord produces any leg motor output in this body and
whether that output is specific to the real wiring. It cannot say anything about reflex loops (P2-b) or rhythm on the ground
(P2-c): in the dry run the legs never move, so the proprioceptors report one fixed posture. The §8–9 smoke observations
(mid-leg coxa promotors 130–160 Hz, tibia extensors 120–200 Hz) are the reason to expect P2-a to be met; they were exploratory
and are not evidence.
