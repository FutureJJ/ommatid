"""Trial protocol (docs/experiment.md §6). Runs inside the brain service, in brain time.

A block is a randomised interleaving of conditions; each trial is BASELINE_MS of grey followed by STIM_MS of stimulus.
The stimulus page (site/stimulus.html) polls /stimulus/state.json and draws whatever is current. Durations are
defined in the fly's time and converted to wall time with the live dilation factor, so the stimulus the fly
experiences has the intended speed regardless of how slowly the simulation runs.

Conditions (v2)
  grating_R / grating_L : vertical square-wave grating drifting right / left (optomotor, H1)
  loom                  : dark disc expanding from 5 % to 90 % of screen height over the stimulus (H2)
  disc                  : fade-in control — a 90 % disc whose contrast ramps 0 → 1 over the stimulus, no abrupt onset
  recede                : the loom played backwards — same luminance history, opposite motion
  bright_R / bright_L   : right / left half of the screen white, other half black (phototaxis, H3)
  grey                  : uniform grey
Interruptions: a step without a fresh frame invalidates the current trial, RECOVERY_MS of grey follow once frames return,
and a replacement trial of the same condition is appended so every condition keeps its planned number of attempts.
"""
from __future__ import annotations
import time, random
from dataclasses import dataclass, field, asdict

BASELINE_MS = 2000.0      # brain time (v2: was 1000 in v1; carry-over across a 1 s baseline was visible in grey trials)
STIM_MS = 2000.0          # brain time
RECOVERY_MS = 3000.0      # v2: grey inserted after an interruption (no frame) before the next trial
# v2 conditions. 'disc' is now a FADE-IN static disc (contrast ramps over the whole stimulus to the loom's end size);
# 'recede' is the loom played backwards (same luminance history reversed). Both are looming controls, reported separately.
CONDITIONS = ["grating_R", "grating_L", "loom", "disc", "recede", "bright_R", "bright_L", "grey"]
PROTOCOL_VERSION = 2

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
        self.planned = len(self.trials)
        self.i = -1
        self.active = False
        self.started_wall = None
        self.dilation = 6.0
        self.trial_brain_start = None
        self.finished = False
        self.interrupted_until = None      # brain_ms until which grey is shown after an interruption
        self.invalid_trials = set()

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
    def interrupt(self, brain_ms: float):
        """Called by the brain loop on a step without a fresh frame: the current trial is invalid and, once frames
        return, RECOVERY_MS of grey precede the next trial (pre-registered v2 rule)."""
        if self.active and 0 <= self.i < len(self.trials):
            tr = self.trials[self.i]
            if tr.id not in self.invalid_trials and len(self.trials) < 2 * self.planned:
                self.invalid_trials.add(tr.id)
                self.trials.append(Trial(len(self.trials), tr.condition, 0.0, self.seed * 1000 + len(self.trials)))
        self.interrupted_until = brain_ms + RECOVERY_MS

    def tick(self, brain_ms: float, dilation: float, frame_ok: bool = True) -> dict:
        """Returns the stimulus that should be on screen now, plus trial bookkeeping for the log."""
        self.dilation = dilation
        if not self.active:
            return {"kind": "grey", "trial": None, "phase": "idle", "condition": None, "version": PROTOCOL_VERSION}
        if not frame_ok:
            self.interrupt(brain_ms)
        if self.interrupted_until is not None:
            if brain_ms < self.interrupted_until or not frame_ok:
                return {"kind": "grey", "trial": None, "phase": "recovery", "condition": None, "version": PROTOCOL_VERSION,
                        "invalid": sorted(self.invalid_trials)[-3:]}
            # recovery over: restart the interrupted trial's slot as a fresh trial
            self.interrupted_until = None
            self._next(brain_ms)
            if not self.active:
                return {"kind": "grey", "trial": None, "phase": "done", "condition": None, "version": PROTOCOL_VERSION}
        t = brain_ms - self.trial_brain_start
        if t >= BASELINE_MS + STIM_MS:
            self._next(brain_ms)
            if not self.active:
                return {"kind": "grey", "trial": None, "phase": "done", "condition": None}
            t = 0.0
        tr = self.trials[self.i]
        phase = "baseline" if t < BASELINE_MS else "stim"
        spec = {"kind": "grey", "trial": tr.id, "condition": tr.condition, "phase": phase,
                "t_brain_ms": round(t, 1), "n_trials": len(self.trials), "version": PROTOCOL_VERSION}
        if phase == "stim":
            s = t - BASELINE_MS
            f = min(1.0, s / STIM_MS)
            if tr.condition.startswith("grating"):
                spec.update(kind="grating", period=GRATING_PERIOD, direction=+1 if tr.condition.endswith("R") else -1,
                            # phase of the grating in screen widths, advanced in brain time
                            phase_sw=GRATING_SPEED * s / 1000.0)
            elif tr.condition == "loom":
                spec.update(kind="disc", size=LOOM_FROM + (LOOM_TO - LOOM_FROM) * f, contrast=1.0)
            elif tr.condition == "recede":
                spec.update(kind="disc", size=LOOM_TO - (LOOM_TO - LOOM_FROM) * f, contrast=1.0)
            elif tr.condition == "disc":
                # fade-in: full size from the start, contrast ramps 0 → 1 over the stimulus (no abrupt onset)
                spec.update(kind="disc", size=LOOM_TO, contrast=f)
            elif tr.condition.startswith("bright"):
                spec.update(kind="half", bright="R" if tr.condition.endswith("R") else "L")
        return spec

    def status(self) -> dict:
        return {"active": self.active, "finished": self.finished, "trial_index": self.i, "n_trials": len(self.trials),
                "seed": self.seed, "note": self.note, "started_wall": self.started_wall, "dilation": self.dilation,
                "version": PROTOCOL_VERSION, "invalid_trials": sorted(self.invalid_trials)}
