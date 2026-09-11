"""The fly's eye: camera frame → the animal's own retinotopic columns → L1/L2 drive.

Geometry (derived from the data, see docs/eye.md):
  Every lamina monopolar cell in the male CNS carries the hex coordinates (assignedOlHex1, assignedOlHex2) of the
  eye column it belongs to. Correlating those with soma positions shows that hex1+hex2 runs dorso-ventral
  (r = −0.98 left, −1.00 right against soma y, y increasing ventrally) and hex1−hex2 runs antero-posterior: columns
  with larger hex1−hex2 sit medially, i.e. at the front of the eye, on both sides. So
      elevation  ∝ +(hex1 + hex2)     (up)
      azimuth    ∝ −(hex1 − hex2)     (front → side)
  Each eye is given a 160° azimuth span and a ±60° elevation span, frontal columns sitting ~5° past the midline
  (binocular overlap). The camera's field is placed frontally; columns outside it see the frame's mean luminance
  and therefore produce no contrast signal. This is a caricature of a ~300° compound eye and is stated as such.

Transduction (lamina monopolar cells, after Joesch 2010 / Clark 2011 and the connectome's own signs):
  Photoreceptors R1-R6 are histaminergic and hyperpolarise L1, L2 and L3 when light increases; all three lamina
  monopolar cells therefore depolarise to DIMMING. The ON and OFF pathways are not split here by hand: L1 is
  glutamatergic (inhibitory in the model) onto Mi1/Tm3, so brightening — a drop in L1 firing — releases Mi1/Tm3
  from inhibition (the ON pathway); L2 and L3 are cholinergic and excite Tm1/Tm2 and Tm9/Tm20 when they fire
  (the OFF pathway). The split is computed by the wiring, exactly as in the animal.
  Each column keeps an adapting mean luminance M and drives its L1, L2, L3 with the same Poisson rate:
      rate = clip(tonic + gain · (M − I) / (M + ε), 0, r_max)
  so the rate rises on dimming and falls on brightening. Real lamina cells are graded, not spiking; the LIF model
  needs spikes, so this is the paper's activation convention applied one layer downstream of the photoreceptors.
  R7/R8 (colour) exist in the dataset but carry no column coordinates and are not driven.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class EyeParams:
    cam_hfov_deg: float = 74.0     # Aurora 930: 74° HFOV (Hiwonder spec)
    cam_vfov_deg: float = 50.0     # from 74° HFOV at the 640x400 (1.6:1) stream
    eye_azimuth_span_deg: float = 160.0
    eye_elevation_span_deg: float = 120.0
    binocular_overlap_deg: float = 10.0   # frontal columns reach this far past the midline
    acceptance_deg: float = 5.0    # per-column acceptance half-angle (sampling window)
    tonic_hz: float = 50.0     # lamina cells' steady-state drive; must be > 0 so that brightening can be signalled
    gain_hz: float = 100.0     # Hz per unit Weber contrast of dimming
    r_max_hz: float = 150.0
    tau_adapt_ms: float = 300.0    # adaptation time constant, in brain time
    eps: float = 0.05              # luminance floor for the Weber fraction


class Eye:
    def __init__(self, brain, p: EyeParams = EyeParams()):
        self.p = p
        self.brain = brain
        idx, az, el = [], [], []
        self.cells = {"L1": [], "L2": [], "L3": []}
        for side, sign in (("L", -1.0), ("R", +1.0)):
            for t in ("L1", "L2", "L3"):
                sel = brain.where(type=t, side=side)
                sel = sel[np.isfinite(brain.hex1[sel]) & np.isfinite(brain.hex2[sel])]
                h1, h2 = brain.hex1[sel], brain.hex2[sel]
                a = h1 - h2                     # larger = more frontal
                e = h1 + h2                     # larger = more dorsal
                # normalise using this side's L1+L2 column range so both cell types share one map
                both = np.concatenate([brain.where(type=tt, side=side) for tt in ("L1", "L2", "L3")])
                both = both[np.isfinite(brain.hex1[both])]
                A = brain.hex1[both] - brain.hex2[both]; E = brain.hex1[both] + brain.hex2[both]
                fr = (A.max() - a) / max(A.max() - A.min(), 1)          # 0 at the front, 1 at the back
                azimuth = sign * (-p.binocular_overlap_deg / 2 + fr * p.eye_azimuth_span_deg)
                elevation = ((e - E.min()) / max(E.max() - E.min(), 1) - 0.5) * p.eye_elevation_span_deg
                idx.append(sel); az.append(azimuth); el.append(elevation)
                self.cells[t].append(sel)
        self.idx = np.concatenate(idx)
        self.azimuth = np.concatenate(az).astype(np.float32)
        self.elevation = np.concatenate(el).astype(np.float32)
        self.cell_type = np.empty(len(self.idx), dtype="U2")
        for t, parts in self.cells.items():
            self.cell_type[np.isin(self.idx, np.concatenate(parts))] = t
        self.n_columns = len(self.idx)
        # which columns can see the camera at all
        self.in_view = (np.abs(self.azimuth) <= p.cam_hfov_deg / 2) & (np.abs(self.elevation) <= p.cam_vfov_deg / 2)
        self.mean = None            # adapting mean luminance per column
        self.last_I = None

    # ---- sampling ---------------------------------------------------------
    def _sample(self, gray: np.ndarray) -> np.ndarray:
        """Mean luminance in each column's acceptance window. gray: float32 HxW in [0,1]."""
        H, W = gray.shape
        p = self.p
        u = (self.azimuth / p.cam_hfov_deg + 0.5) * W      # pixel column
        v = (0.5 - self.elevation / p.cam_vfov_deg) * H    # pixel row (up = smaller row)
        r = max(1, int(round(p.acceptance_deg / p.cam_hfov_deg * W)))
        # integral image for O(1) box means
        S = np.zeros((H + 1, W + 1), dtype=np.float64)
        S[1:, 1:] = gray.cumsum(0).cumsum(1)
        x0 = np.clip((u - r).astype(int), 0, W - 1); x1 = np.clip((u + r).astype(int) + 1, 1, W)
        y0 = np.clip((v - r).astype(int), 0, H - 1); y1 = np.clip((v + r).astype(int) + 1, 1, H)
        area = (x1 - x0) * (y1 - y0)
        box = S[y1, x1] - S[y0, x1] - S[y1, x0] + S[y0, x0]
        I = (box / np.maximum(area, 1)).astype(np.float32)
        I[~self.in_view] = float(gray.mean())
        return I

    # ---- transduction -----------------------------------------------------
    def look(self, gray: np.ndarray, dt_ms: float) -> dict:
        """One control step of vision. Returns {neuron_indices: rates_hz} for Brain.run plus a summary."""
        p = self.p
        I = self._sample(gray)
        if self.mean is None:
            self.mean = I.copy()
        dimming = (self.mean - I) / (self.mean + p.eps)          # positive when the column gets darker
        rates = np.clip(p.tonic_hz + p.gain_hz * dimming, 0.0, p.r_max_hz)
        # adapt after computing the response
        a = 1.0 - np.exp(-dt_ms / p.tau_adapt_ms)
        self.mean += a * (I - self.mean)
        self.last_I = I
        return {tuple(self.idx): rates.astype(np.float32)}

    def blind(self) -> dict:
        """Control C4: no image at all — the paper's zero-input baseline."""
        return {}

    def uniform(self) -> dict:
        """Static uniform field: every lamina cell at its tonic rate, no contrast anywhere."""
        return {tuple(self.idx): np.full(self.n_columns, self.p.tonic_hz, dtype=np.float32)}

    def summary(self, drive: dict) -> dict:
        r = next(iter(drive.values())) if drive else np.zeros(self.n_columns, np.float32)
        return {"columns": int(self.n_columns), "in_view": int(self.in_view.sum()),
                "mean_hz": float(r.mean()), "min_hz": float(r.min()), "max_hz": float(r.max()),
                "dimming_cells": int((r > self.p.tonic_hz + 1).sum()), "brightening_cells": int((r < self.p.tonic_hz - 1).sum())}
