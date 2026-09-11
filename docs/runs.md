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
- **H2 looming: met.** Loom-evoked escape/stop rise +13.6 Hz on the real wiring vs +4.6 Hz on degree-preserving
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
