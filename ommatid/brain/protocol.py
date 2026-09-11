"""Trial protocol (docs/experiment.md §6). Runs inside the brain service, in brain time.

A block is a randomised interleaving of conditions; each trial is BASELINE_MS of grey followed by STIM_MS of stimulus.
The stimulus page (site/stimulus.html) polls /stimulus/state.json and draws whatever is current. Durations are
defined in the fly's time and converted to wall time with the live dilation factor, so the stimulus the fly
experiences has the intended speed regardless of how slowly the simulation runs.

Conditions
  grating_R / grating_L : vertical square-wave grating drifting right / left (optomotor, H1)
  loom / disc           : dark disc expanding from 5 % to 90 % of screen height / same disc held at 50 % (H2 + control)
  bright_R / bright_L   : right / left half of the screen white, other half black (phototaxis, H3)
  grey                  : uniform grey (baseline, C4-like)
"""
from __future__ import annotations
import time, random
from dataclasses import dataclass, field, asdict

BASELINE_MS = 1000.0      # brain time
STIM_MS = 2000.0          # brain time
CONDITIONS = ["grating_R", "grating_L", "loom", "disc", "bright_R", "bright_L", "grey"]

# Stimulus geometry in screen units (the page does not know the viewing distance; it is recorded with the run)
GRATING_PERIOD = 0.20          # fraction of screen width per cycle
GRATING_SPEED = 0.30           # screen widths per second of BRAIN time
LOOM_FROM, LOOM_TO = 0.05, 0.90   # fraction of screen height
DISC_SIZE = 0.50


@dataclass
class Trial:
    id: int
    condition: str
    start_brain_ms: float
    seed: int


class Protocol:
    def __init__(self, trials_per_condition: int = 30, seed: int = 2026, note: str = ""):
        rng = random.Random(seed)
        order = [c for c in CONDITIONS for _ in range(trials_per_condition)]
        rng.shuffle(order)
        self.seed = seed; self.note = note
        self.trials = [Trial(i, c, 0.0, seed * 1000 + i) for i, c in enumerate(order)]
        self.i = -1
        self.active = False
        self.started_wall = None
        self.dilation = 6.0
        self.trial_brain_start = None
        self.finished = False

    # ---- control ------------------------------------------------------------
    def start(self, brain_ms: float):
        self.active = True; self.finished = False; self.i = -1; self.started_wall = time.time()
        self._next(brain_ms)

    def stop(self):
        self.active = False

    def _next(self, brain_ms: float):
        self.i += 1
        if self.i >= len(self.trials):
            self.active = False; self.finished = True; return
        self.trials[self.i].start_brain_ms = brain_ms
        self.trial_brain_start = brain_ms

    # ---- called every control step by the brain loop -------------------------
    def tick(self, brain_ms: float, dilation: float) -> dict:
        """Returns the stimulus that should be on screen now, plus trial bookkeeping for the log."""
        self.dilation = dilation
        if not self.active:
            return {"kind": "grey", "trial": None, "phase": "idle", "condition": None}
        t = brain_ms - self.trial_brain_start
        if t >= BASELINE_MS + STIM_MS:
            self._next(brain_ms)
            if not self.active:
                return {"kind": "grey", "trial": None, "phase": "done", "condition": None}
            t = 0.0
        tr = self.trials[self.i]
        phase = "baseline" if t < BASELINE_MS else "stim"
        spec = {"kind": "grey", "trial": tr.id, "condition": tr.condition, "phase": phase,
                "t_brain_ms": round(t, 1), "n_trials": len(self.trials)}
        if phase == "stim":
            s = t - BASELINE_MS
            if tr.condition.startswith("grating"):
                spec.update(kind="grating", period=GRATING_PERIOD, direction=+1 if tr.condition.endswith("R") else -1,
                            # phase of the grating in screen widths, advanced in brain time
                            phase_sw=GRATING_SPEED * s / 1000.0)
            elif tr.condition == "loom":
                spec.update(kind="disc", size=LOOM_FROM + (LOOM_TO - LOOM_FROM) * min(1.0, s / STIM_MS))
            elif tr.condition == "disc":
                spec.update(kind="disc", size=DISC_SIZE)
            elif tr.condition.startswith("bright"):
                spec.update(kind="half", bright="R" if tr.condition.endswith("R") else "L")
        return spec

    def status(self) -> dict:
        return {"active": self.active, "finished": self.finished, "trial_index": self.i, "n_trials": len(self.trials),
                "seed": self.seed, "note": self.note, "started_wall": self.started_wall, "dilation": self.dilation}
