"""Phase 2 sensory input: the robot's servo state → the fly's own leg proprioceptors (docs/phase2.md §3).

Per leg (front/mid/hind, identified by entry nerve ProLN/MesoLN/MetaLN) the male CNS has femoral chordotonal-organ
neurons (joint angle and velocity), hair-plate neurons (joint at an extreme) and campaniform sensilla (load). Side is not
annotated for most sensory neurons; it is inferred once from the side of the motor neurons they connect to most strongly
(tools/build_sensory_sides.py) and stored with the map.

Injection, as forced Poisson spikes at the paper's activation scale:
  chordotonal, position-tuned half : rate = r_max · exp(−(θ − θ_pref)² / 2σ²), θ_pref spread evenly over the joint range
  chordotonal, velocity-tuned half : rate = r_max · min(1, |dθ/dt| / v_ref)
  hair plates                      : r_max if |θ − rest| > 0.8 · range else 0
  campaniform sensilla             : rate = r_max · min(1, |θ_commanded − θ_reached| / e_ref)     (servo lag under load)
  halteres (IMU)                   : rate = r_max · min(1, |ω| / ω_ref) per axis, split over the haltere pool
The femur and tibia servos of a leg are pooled into that leg's chordotonal population (half each). All constants fixed
before trials.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

NERVE_LEG = {"ProLN": "front", "MesoLN": "mid", "MetaLN": "hind", "ProCN": "front", "DMetaN": "hind", "VProN": "front"}


@dataclass(frozen=True)
class ProprioParams:
    r_max_hz: float = 150.0
    sigma_deg: float = 12.0
    v_ref_dps: float = 90.0
    e_ref_deg: float = 6.0
    omega_ref_dps: float = 60.0
    extreme_frac: float = 0.8


class Proprioception:
    def __init__(self, brain, annotations: pd.DataFrame, sides: dict, p: ProprioParams = ProprioParams()):
        """sides: {brain_index: 'L'|'R'} for sensory neurons (from tools/build_sensory_sides.py)."""
        self.p = p
        a = annotations.drop_duplicates("bodyId").set_index("bodyId").reindex(brain.bodies)
        sc = a["superclass"].fillna("").to_numpy(dtype=str); sub = a["subclass"].fillna("").to_numpy(dtype=str)
        nerve = a["entryNerve"].fillna("").to_numpy(dtype=str)
        side_arr = np.array([sides.get(i, "") for i in range(brain.n)], dtype=str)
        self.pools = {}    # (leg, side, kind) -> idx
        for nv, leg in NERVE_LEG.items():
            for s in ("L", "R"):
                base = (sc == "vnc_sensory") & (nerve == nv) & (side_arr == s)
                for kind, label in (("chordotonal", "chordotonal organ"), ("hairplate", "hair plate"), ("campaniform", "campaniform sensilla")):
                    idx = np.flatnonzero(base & (sub == label))
                    if len(idx):
                        key = (leg, s, kind); self.pools[key] = np.concatenate([self.pools[key], idx]) if key in self.pools else idx
        self.haltere = np.flatnonzero((sc == "vnc_sensory") & (sub == "haltere"))
        # chordotonal: split each pool into position-tuned (with preferred angles) and velocity-tuned halves
        self.pref = {}
        for key, idx in self.pools.items():
            if key[2] == "chordotonal":
                n = len(idx); half = n // 2
                self.pref[key] = np.linspace(-1, 1, max(half, 1)).astype(np.float32)     # preferred angle as fraction of range
        self.prev = {}

    def describe(self):
        return {f"{l}-{s}-{k}": int(len(v)) for (l, s, k), v in sorted(self.pools.items())} | {"haltere": int(len(self.haltere))}

    def drive(self, joints: dict, dt_ms: float, imu_omega_dps=(0.0, 0.0, 0.0)) -> dict:
        """joints: {(leg, side): {"femur": (θ_cmd_deg, θ_reached_deg, range_deg), "tibia": (...)}}, angles relative to rest.
        Returns the LIF external drive {tuple(idx): rates}."""
        p = self.p; out = {}
        for (leg, s), js in joints.items():
            # angle of the leg for the chordotonal pool: mean of femur and tibia, normalised by range
            th = np.mean([js[j][1] / js[j][2] for j in js]); prev = self.prev.get((leg, s), th)
            vel = abs(th - prev) / (dt_ms / 1000.0) * np.mean([js[j][2] for j in js])     # deg/s
            self.prev[(leg, s)] = th
            key = (leg, s, "chordotonal")
            if key in self.pools:
                idx = self.pools[key]; half = len(idx) // 2
                pos = p.r_max_hz * np.exp(-((th - self.pref[key]) * np.mean([js[j][2] for j in js])) ** 2 / (2 * p.sigma_deg ** 2))
                v = np.full(len(idx) - half, p.r_max_hz * min(1.0, vel / p.v_ref_dps), np.float32)
                out[tuple(idx)] = np.concatenate([pos.astype(np.float32), v])
            key = (leg, s, "hairplate")
            if key in self.pools:
                extreme = any(abs(js[j][1]) > p.extreme_frac * js[j][2] for j in js)
                out[tuple(self.pools[key])] = np.float32(p.r_max_hz if extreme else 0.0)
            key = (leg, s, "campaniform")
            if key in self.pools:
                err = np.mean([abs(js[j][0] - js[j][1]) for j in js])
                out[tuple(self.pools[key])] = np.float32(p.r_max_hz * min(1.0, err / p.e_ref_deg))
        if len(self.haltere):
            w = np.abs(np.asarray(imu_omega_dps, np.float32)); thirds = np.array_split(self.haltere, 3)
            for ax, idx in enumerate(thirds):
                if len(idx): out[tuple(idx)] = np.float32(p.r_max_hz * min(1.0, w[ax] / p.omega_ref_dps))
        return out
