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
