# Run log

## v1 run 1 — 2026-09-11 10:32 UTC, original graph
- protocol seed 2026, 30 trials × 7 conditions = 210 trials; body in dry run (held still); frozen params `freeze-v1`
- display: laptop screen, 30 cm wide (~19 cm high, 16:10), 40 cm from the camera, daylight
- derived angles at the screen centre: screen 41° × 26° of the camera's 74° × 50° field;
  grating period 8.6° (≈ 6 cm), drift 12.7°/s of brain time (temporal frequency ≈ 1.5 Hz);
  loom disc 1.3° → 24° over 2 s of brain time; half-field boundary at the midline
- smoke tests before this run (seeds 1 and 2, one trial per condition): loom +22 Hz escape/stop rise, all other conditions ≤ 2 Hz

### Result (analysed 11:24 UTC, `tools/analyze.py logs --seed 2026`, 210 trials)

| condition | n | Δ turn (DNa02 R−L) Hz, mean [95 % CI] | Δ escape/stop Hz | spikes stim / baseline |
|---|---|---|---|---|
| loom | 30 | −0.4 [−1.5, +0.7] | **+13.6** | 29,533 / 28,753 |
| disc (static) | 30 | −0.0 [−1.4, +1.3] | +9.2 | 29,003 / 28,395 |
| grating → R | 30 | +0.7 [−0.6, +2.0] | +0.3 | 28,128 / 28,538 |
| grating → L | 30 | −0.1 [−1.5, +1.2] | +0.2 | 28,054 / 28,573 |
| bright R | 30 | −1.1 [−2.0, −0.2] | +0.5 | 28,268 / 28,720 |
| bright L | 30 | −4.5 [−6.0, −3.0] | +0.2 | 28,260 / 28,827 |
| grey | 30 | +1.5 [+0.2, +2.7] | +4.5 | 29,013 / 28,787 |

Pre-registered criteria:
- **H1 optomotor: not met.** Sign agreement 47 % (≥ 80 % required), grating R vs L permutation p = 0.40. No optomotor
  signal in DNa02 with a 41°-wide stimulus.
- **H2 looming: effect present, criterion narrowly missed.** Escape/stop readouts rose > 5 Hz in 67 % of loom trials
  (≥ 70 % required) and in 22 % of disc/grating controls (< 20 % required); loom vs controls p < 0.0001. The static-disc
  control appears abruptly and itself produced +9.2 Hz — an abrupt-onset dark disc is a looming-like stimulus, so this
  control was badly chosen (v2 amendment: fade the disc in). Grey trials also show +4.5 Hz, which points at carry-over
  from the preceding trial across a 1 s baseline.
- **H3 phototaxis: not met.** 60 % toward the bright side. Bright-left trials turn left (−4.5 Hz, correct sign),
  bright-right trials do not (−1.1 Hz).
- DNa01 (forward) never fired in any condition; MDN never fired. Only DNa02-left and the escape DNs carry signal.

Interpretation is deferred to the control-graph runs (C1 shuffled wiring, C2 scrambled signs) with the identical protocol.

## v1 run 2 — 2026-09-11 11:31 UTC, C1 shuffled wiring
- same protocol, seed 2026, same display geometry; graph `build/graph_shuffled.npz` (degree-preserving permutation, seed 2026),
  sha256 prefix 3bfdad7c298a (original: 050359b2a09f), verified in the service state before the start
- correction: a first start at 11:26 UTC ran for about two minutes on the ORIGINAL graph because the server was still running
  the previous service build, which ignored the graph setting. It was stopped; its rows (ts ≥ 1789125979) are quarantined in
  `logs/original-aborted/` and excluded from every analysis. Logs are now written per variant (`logs/original/`, `logs/shuffled/`).
- first observation: whole-network activity on the shuffled graph is about a third of the original's (≈ 9,700 vs ≈ 28,500 spikes per 20 ms) under the same input

### Result (analysed 12:20 UTC, 210 trials, `tools/analyze.py logs/original --control logs/shuffled --seed 2026`)

| condition | n | Δ escape/stop Hz, shuffled wiring | (original, for comparison) | spikes stim / baseline |
|---|---|---|---|---|
| loom | 30 | +4.6 | +13.6 | 10,315 / 9,744 |
| disc (static) | 30 | +3.0 | +9.2 | 9,769 / 9,607 |
| gratings | 60 | +1.6 | +0.3 | ≈ 9,400 / 9,800 |
| bright halves | 60 | +1.6 | +0.4 | ≈ 9,100 / 9,600 |
| grey | 30 | +4.4 | +4.5 | 10,122 / 9,632 |

Original vs shuffled, pre-registered contrast (criterion p < 0.01):
- **H2 looming — wiring contrast (exploratory; see review below, finding 1).** Loom-evoked escape/stop rise +13.6 Hz on the real wiring vs +4.6 Hz on degree-preserving
  shuffled wiring, permutation p = 0.0001. The whole network also speeds up more on the real wiring during loom
  (+780 vs +571 spikes per 20 ms); normalised per 1,000 extra spikes the escape neurons still gain 17.4 Hz vs 8.1 Hz,
  so the effect is not just more activity everywhere. On the real wiring the rise is carried by DNp04 (+12.8 Hz
  [+8.5, +17.1]) and DNp02 (+5.6 Hz [+3.6, +7.5]) — the two direct LC4 targets — while DNp01 (giant fibre), DNp09 and MDN
  stayed at 0 Hz in every trial. Shuffled wiring shows a small loom-vs-controls difference too (p < 0.0001 within that run),
  i.e. looming is simply the strongest input; what the real wiring adds is where that input lands.
- **H1 optomotor: not met**, and indistinguishable from the control graph (+0.4 vs −0.2 Hz, p = 0.38).
- **H3 phototaxis: not met**; not different from control.

Whole-network activity on the shuffled graph was about one third of the original's under identical input, for all conditions.

### What phase 1 says so far
One innate reflex — looming → escape descending neurons — survives the transfer into the robot body with the wiring
untouched, and it depends on the specific wiring. Wide-field motion (optomotor) and phototaxis do not appear in this
setup; the candidate causes are measured mismatches (41° of a 300° field; a transient-only hand-off; no baseline
activity for disinhibition; a single steering DN as readout) and are the targets of the v2 protocol and of phases 2–3.
Pre-registered v2 amendments: fade-in static disc; ≥ 2 s baseline; hand-off gain calibrated to HS-cell physiology;
a wider pre-registered DN panel for turning; C2 scrambled-sign run.

## v1 run 3 — 2026-09-11 12:39 UTC, C2 scrambled signs
- same protocol, seed 2026, same laptop 30 cm @ 40 cm; graph `build/graph_scrambled.npz` (E/I labels permuted across neurons,
  seed 2026), sha256 prefix e1fd52515539, verified in the service state before the start
- lighting differs from runs 1–2: the room is now dark (evening), the laptop screen is the main light source. This is a
  confound for any cross-run comparison beyond the pre-registered contrasts and is recorded here.
- first observation: with scrambled signs the network is hyperactive — ≈ 158,000 spikes per 20 ms at rest versus ≈ 28,500 on the
  real wiring — i.e. the connectome's excitation/inhibition assignment is what keeps the real network in a stable regime

## Independent review, 2026-09-11 (commit c9b35f3) — accepted findings and corrections
An external review (GPT-6 Astra, run by Can) found six issues. Status of each:

1. **C1 changed the input mapping, not only the wiring (accepted, P1).** Column positions of unlabeled types (T4/T5, Tm3, TmY…)
   are inferred from presynaptic partners of the *loaded* graph, so the shuffled graph received a different FlyVis→neuron map.
   The original-vs-shuffled loom contrast (+13.6 vs +4.6 Hz, p = 0.0001) is therefore confounded and is downgraded to exploratory.
   Fix: derive the column map once from the original anatomy, serialise it with a hash, load it unchanged for every variant.
2. **H2 criteria were not implemented as pre-registered (accepted, P1).** The analysis used a 2 s mean, the max over five
   readouts and a 5 Hz threshold (none frozen), pooled controls, and never tested the 200 ms onset. Per condition, > 5 Hz rises:
   loom 67 %, static disc 67 %, grey 33 %, gratings 0 %. H2 is **not established** in v1; the earlier "met" label was wrong and
   has been removed from the results page. The wiring contrast was never an H2 criterion.
3. **Stimulus labels are not frame-locked; no-frame steps entered trials (accepted, P1).** 435 no-frame steps in 17 trials
   (55 during loom stimuli). Fix: display acknowledges what it showed and when; frames carry capture time; steps are matched to
   exposures; pre-registered trial-invalidation rules (any no-frame step → trial invalid) before v2 runs.
4. **Body agent safety (accepted, P1).** Synchronous HTTP in the ROS callback path can block the 0.5 s watchdog; command
   freshness must be tied to an advancing brain step, not receipt time; LiDAR front sector must use scan angles. All three are
   fixed before motion is enabled.
5. **Degree preservation claim (accepted, P2).** Endpoint permutation preserves the multigraph degrees; merging duplicates changed
   0.19 % of edges. The check printed by the tool was vacuous. Fix: state the null model precisely and verify saved degrees.
6. **Additive forcing and surround fill (accepted, P2).** Injected neurons keep their recurrent input (documented as a decision);
   the off-camera surround was filled with the frame mean, so a dark disc also darkened the whole surround — a synthetic
   full-field dimming. Fix: fixed grey surround; matched-luminance controls in v2.

Also accepted: raw logs of every run are to be published (runs/data/), and the C2 run started at 12:39 UTC carries the same
mapping confound (finding 1) and is exploratory.

### Re-analysis of v1 with the corrected tool (2026-09-11, `tools/analyze.py --mode v1`, valid trials only)
17 original-run trials with no-frame steps excluded (disc 5, grey 3, bright_R 3, loom 3, grating_R 2, bright_L 1).

| condition | n valid | Δ escape/stop Hz [95 % CI] | trials > 5 Hz | loom vs this, p |
|---|---|---|---|---|
| loom | 27 | +13.6 [+9.9, +17.4] | 70 % | — |
| static disc | 25 | +10.1 [+7.0, +13.1] | 72 % | 0.16 |
| grey | 27 | +3.8 [+1.9, +5.7] | 30 % | 0.0001 |
| gratings | 58 | +0.2 | 0 % | < 0.0001 |
| bright halves | 56 | +0.2 | 0 % | < 0.0001 |

The static disc — which appears in a single frame — evokes the same escape-neuron response as the expanding disc.
So v1 shows a response to an abruptly appearing dark object, not looming selectivity. Grey trials show a residual +3.8 Hz,
consistent with carry-over across the 1 s baseline. Loom ΔDNp04 +13.3 Hz [+9.4, +17.2], ΔDNp02 +5.8 Hz [+4.0, +7.6];
DNp01, DNp09, MDN 0 Hz in every trial. Original vs shuffled loom rise +13.6 vs +4.6 Hz (p = 0.0001) remains informative only
(mapping confound). H1 and H3 unchanged: not met.
- **Run 3 stopped at trial 34/210 (12:53 UTC).** With scrambled signs the network is ~5× more active and the simulation ran at
  8× dilation; more importantly the run carried the input-mapping confound (review finding 1), so it could only be exploratory.
  Its 34 trials are kept in `runs/data/scrambled-aborted/` and not analysed. C2 is rerun under protocol v2 with the fixed map.

### The surround artefact (2026-09-11, after review finding 6)
With the off-camera surround fixed at 50 % grey, the synthetic hybrid pilot (`tools/pilot_hybrid.py`) no longer produces
an escape response: the expanding disc drives LC4 to 2 Hz (13 % of cells) and DNp04/DNp02 to 0 Hz, where the frame-mean
surround had given LC4 12 Hz and DNp04 41 Hz. A first frame-locked smoke run on the robot with the fixed surround (seed 8,
one trial per condition) likewise shows DNp04 at 0 Hz in every phase of every trial, including looming.

Interpretation: the v1 "escape response" — to the expanding disc and equally to the static disc — was mostly the model's
response to a whole-eye dimming that the surround fill manufactured whenever a dark object entered the camera frame. It was
not a response to expansion, and with the artefact removed the looming pathway is only weakly driven by a 24° disc that
covers a fraction of one eye. Phase 1 v1 therefore establishes no reflex. This is now the stated status of the project.
What v2 has to settle first: whether the hand-off gain (calibrated to HS-cell physiology, pre-registered) and a larger
stimulus can drive LC4 at all; if not, that is the phase-1 result about this model class in this body.

## Body released — 2026-09-11 13:38 UTC
Dry run switched off (OMMATID_DRY_RUN=0). Free viewing, no protocol. First minute: the brain's steering asymmetry
(DNa02 left 13–24 Hz, right 0 Hz) produced a slow left turn, yaw command 0.03–0.06 rad/s; heading −46° → +21° in ~25 s.
DNa01 silent → no forward motion. Lease stops 0, obstacle blocks 0, link errors 0. LiDAR front sector verified against the
camera before release (nearest object at 90° = the low table on the robot's left; 0° = ahead).

### Rig reliability notes (2026-09-11 evening)
- The stock `stop` action group returns the arm — and the camera on it — to the rest pose (floor). The body agent no longer
  uses it; a halt is `Traveling gait=0` only, and the camera tilt (servo 22 = 275) is re-asserted every 30 s.
- The Aurora 930 dropped off USB and its ROS driver died; frames stopped for several minutes. The body agent now relaunches
  `peripherals depth_camera.launch.py` when no image has arrived for 20 s (at most once per 2 min). Under protocol v2 such a
  gap invalidates the affected trial and inserts 3 s of grey; it cannot silently enter a result.

## v2 runs — 2026-09-11 from 13:45 UTC (unattended chain, `deploy/run_v2.sh`)
Order: original → shuffled 2026 → shuffled 2027 → shuffled 2028 → scrambled → clamped; 240 planned trials each, seed 2026;
frozen parameters `freeze-v2` (docs/frozen-params-v2.md). Body locked (dry run). Display: the laptop screen measured in the
camera frame at ≈ 26° wide (115 of 320 px of the 74° field) → about 63 cm from the camera for a 30 cm screen; centred; room
dark, the screen is the main light. Derived: grating period ≈ 5.3°, drift ≈ 8°/s brain time, loom 0.8° → 15°, half-field
boundary at the midline. Each run's graph and column hashes are written to `run_v2.log` at its start.

### v2 chain, attempt 1 stopped (14:20 UTC)
The original-graph run was stopped by the operator at trial 110/242 to move the screen closer; its logs are kept in
`runs/data/original-v2-63cm-aborted/` as exploratory. Interim (97 valid trials): escape/stop readouts 0 Hz in every
condition; H1 50 %; H3 71 % toward the bright side (bright_R +3.1 Hz, bright_L −0.9 Hz); network ≈ 24,100 spikes/20 ms.

## v2 runs, attempt 2 — 2026-09-11 from 14:28 UTC
Same chain and freeze. Display moved closer: the screen now spans 55 % × 60 % of the camera frame ≈ **41° × 30°**
(≈ 40 cm for a 30 cm screen), centred after tilting the camera to servo pulse 235; room dark, screen the main light.
Derived: grating period ≈ 8.1°, drift ≈ 12°/s brain time (≈ 1.5 Hz); loom 1.5° → 27°; half-field boundary at the midline.

### Exploratory: why the looming detectors stay silent (2026-09-11, `tools/diagnose_lc4.py`; for the v3 design, not a test)
Anatomy: 80 % of LC4's excitatory input (343 mV/cell) comes from types the hand-off drives — TmY3, T2, Tm4, Tm2, Tm3 — so the
boundary covers the pathway; LPLC2 64 %, LC6 42 %. Dynamics on an emulation of the rig (bright 55 % × 60 % screen in a dark
frame, disc 5 → 90 % of the screen): LC4's mean synaptic drive is net NEGATIVE (g ≈ −5.5 mV) with the frozen gain of 100 Hz per
unit; LC4 fires ~5 spikes per 20 ms across its 126 cells and the loom does not raise that; DNp04 0. Whole-frame loom: the same.
Gain sweep (exploratory): at 200 the loom raises LC4 (17 vs 14 spikes/step) and DNp04 fires 3 spikes in 2 s; at 400, DNp04 158 in
the loom vs 12 in the settle window; at 800, 491 vs 67 — the response appears, but so does background DNp04 activity.
Reading: the pathway is there, but under a single global scalar the injected medulla activity leaves LC4 under net inhibition;
a looming response would require either a higher gain (which also raises the background) or a per-type scaling of FlyVis
activity (its units are not comparable across types). Both are v3 design questions, to be pre-registered before any trial.
