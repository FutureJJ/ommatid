# Frozen parameters — phase 2, P2-a dry run, 2026-09-11 (tag `freeze-p2a`)

Written before the first P2-a block. Nothing below is fitted to behaviour; every constant was set from anatomy,
physiology or engineering limits and is recorded here so that the blocks can be judged against it.

## Artefacts (sha256 prefixes)
```
build/graph.npz             050359b2a09f    original wiring
build/graph_shuffled.npz    3bfdad7c298a    C1 control, degree-preserving shuffle, seed 2026
build/columns.npz           382775cc1df0    FlyVis → neuron column map (shared by all variants)
build/sensory_sides.npz     4d2e3cccac49    inferred body side of VNC sensory neurons
```
Spiking model, optic lobe and hand-off: unchanged from `freeze-v2` (Shiu et al. 2024 LIF; FlyVis flow/0000/000; 100 Hz per unit;
fixed 50 % grey surround). The body's camera keeps feeding the eye during P2-a (free viewing of the room, no protocol).

## Motor mapping (`ommatid/brain/motor.py`)
- `angle = rest + gain · (rate_agonist − rate_antagonist)`, rates = pool mean spikes/s, exponentially smoothed over **50 ms** of brain time
- gains, degrees per Hz of rate difference: **coxa 0.6, femur 0.8, tibia 0.8**; range from rest: **coxa ± 35°, femur/tibia ± 45°**
- servo pulse per degree 1000/240; right legs mirror the left (SIDE_SIGN); standing pose = REST_PULSE below
- pools (male CNS annotations: superclass vnc_motor, subclass fl/ml/hl, somaSide, type = muscle name); 266 motor neurons in all:

| leg | side | joint | agonist n | antagonist n | servo | rest pulse |
|---|---|---|---|---|---|---|
| front | L | coxa | 6 | 6 | 5 | 470 |
| front | L | femur | 15 | 8 | 3 | 320 |
| front | L | tibia | 15 | 2 | 1 | 660 |
| front | R | coxa | 6 | 4 | 6 | 530 |
| front | R | femur | 16 | 8 | 4 | 680 |
| front | R | tibia | 14 | 2 | 2 | 340 |
| mid | L | coxa | 2 | 7 | 11 | 500 |
| mid | L | femur | 12 | 5 | 9 | 320 |
| mid | L | tibia | 11 | 2 | 7 | 660 |
| mid | R | coxa | 2 | 7 | 12 | 500 |
| mid | R | femur | 12 | 5 | 10 | 680 |
| mid | R | tibia | 11 | 2 | 8 | 340 |
| hind | L | coxa | 2 | 6 | 17 | 530 |
| hind | L | femur | 11 | 5 | 15 | 320 |
| hind | L | tibia | 17 | 2 | 13 | 660 |
| hind | R | coxa | 2 | 6 | 18 | 470 |
| hind | R | femur | 11 | 6 | 16 | 680 |
| hind | R | tibia | 16 | 2 | 14 | 340 |

Agonist = promotor/anterior-rotator (coxa), trochanter flexors + femur reductor (femur), tibia flexors (tibia); antagonist =
remotor/abductor/posterior-rotator, trochanter extensor + sternotrochanter + tergotrochanter, tibia extensor. Tibia extensor
pools have 2 cells each — stated as a known weakness of the mapping.

## Proprioception (`ommatid/brain/proprio.py`, forced Poisson spikes)
- r_max **150 Hz**; chordotonal position half: Gaussian σ **12°** around preferred angles spread evenly over the joint range;
  velocity half: r_max · min(1, |dθ/dt| / **90°/s**); hair plates: r_max when |θ − rest| > **0.8** · range; campaniform: r_max ·
  min(1, |θ_cmd − θ_reached| / **6°**); halteres: r_max · min(1, |ω| / **60°/s**) per IMU axis, pool split in thirds
- the femur and tibia servos of a leg are pooled into that leg's chordotonal population; the joint angle used is their mean
- pools (side inferred from one-hop output partners, `tools/build_sensory_sides.py`; 6,076 sensory neurons sided, median
  confidence 0.66): chordotonal front 44 L / 18 R, mid 76 / 78, hind 83 / 100; hair plates front 6 / 7, mid 18 / 14, hind 13 / 13;
  campaniform front 2 / 0, mid 3 / 1, hind 18 / 13; halteres 56. 563 sensory neurons injected in all.

## Body (dry run for all P2-a blocks)
- OMMATID_DRY_RUN=1: the body agent receives the 18 targets every step, clamps and rate-limits them exactly as it would apply
  them (rest ± **62** pulse ≈ ± 15°, ≤ **20** pulse per 100 ms), writes them to its stats file, and moves nothing. The
  brain's log records the target (`servo_<id>`) and the reached position (`reached_<id>`, the standing pose) per step.
- Consequence for P2-a: with the body still, "feedback on" means the fly's proprioceptors report the standing pose and a
  zero-velocity, zero-load leg; "feedback off" means they are silent. The blocks therefore test whether *static* posture
  input changes the motor pattern — not whether the loop closes. The closed loop is P2-b, on a stand, later.

## Blocks and analysis (`tools/run_p2a.py`, `tools/analyze_phase2.py`)
- graphs: original, then C1 shuffled (seed 2026); for each: feedback ON 150 s → OFF 150 s → ON 150 s → OFF 150 s of brain time
- the first 20 s of brain time after each switch or start are excluded; SDs and permutation tests use 10 s window means
- per unit: agonist and antagonist mean Hz, fraction of active steps, resulting servo angle (mean, SD, |max|), agonist − antagonist
  Welch peak in 0.2–2 Hz with its ratio to the band median (descriptive)
- **P2-a criterion: at least one of the 18 units has an agonist or antagonist pool with a mean rate > 5 Hz in the feedback-on
  blocks of the original graph.** Everything else (on vs off, original vs shuffled, Holm over 18 units) is reported without a
  criterion; the shuffled graph shows whether the pattern depends on the real wiring.
- room lighting and the camera view are recorded at the start of the run in docs/runs.md.
