"""Phase 2 motor output: the fly's leg motor-neuron pools drive the robot's 18 servos (docs/phase2.md §2).

Each servo has an agonist pool and an antagonist pool of motor neurons for the corresponding leg (front/mid/hind × L/R),
identified by the male CNS annotations (superclass vnc_motor, subclass fl/ml/hl, somaSide, type = muscle name). The
servo target angle moves with the smoothed rate difference:

    angle = rest + gain_deg_per_hz · (rate_agonist − rate_antagonist)

clamped to the servo's range. Rates are smoothed over 50 ms of brain time. One gain per joint kind, fixed before trials.
Nothing here is learned or fitted to behaviour.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

LEGS = {"fl": "front", "ml": "mid", "hl": "hind"}
SIDES = ("L", "R")

# muscle-name pools per robot joint (agonist = flexion / protraction / levation direction of the servo's positive angle)
POOLS = {
    "coxa":  {"ago": ["Tergopleural/Pleural promotor MN", "Sternal anterior rotator MN"],
              "ant": ["Pleural remotor/abductor MN", "Sternal posterior rotator MN"]},
    "femur": {"ago": ["Tr flexor MN", "Acc. tr flexor MN", "Fe reductor MN"],
              "ant": ["Tr extensor MN", "Sternotrochanter MN", "Tergotr. MN"]},
    "tibia": {"ago": ["Ti flexor MN", "Acc. ti flexor MN"],
              "ant": ["Ti extensor MN"]},
}

# Hiwonder RoSpider bus-servo ids: legs numbered 1..18; layout per leg (coxa, femur, tibia). Verified against the stock
# kinematics config before trials; until then this table is the working assumption and is checked by tools/servo_map.py.
SERVO_IDS = {
    ("front", "R"): (1, 2, 3), ("mid", "R"): (4, 5, 6), ("hind", "R"): (7, 8, 9),
    ("front", "L"): (10, 11, 12), ("mid", "L"): (13, 14, 15), ("hind", "L"): (16, 17, 18),
}


@dataclass(frozen=True)
class MotorGains:
    deg_per_hz: dict = field(default_factory=lambda: {"coxa": 0.6, "femur": 0.8, "tibia": 0.8})
    smooth_ms: float = 50.0
    rest_pulse: int = 500                 # bus servo centre (0..1000 ≙ 0..240°)
    pulse_per_deg: float = 1000.0 / 240.0
    range_deg: dict = field(default_factory=lambda: {"coxa": 35.0, "femur": 45.0, "tibia": 45.0})   # ± from rest


class LegMotor:
    def __init__(self, brain, annotations: pd.DataFrame, gains: MotorGains = MotorGains()):
        """annotations: body-annotations (bodyId, superclass, subclass, somaSide, type) aligned by bodyId → brain index."""
        self.g = gains
        a = annotations.drop_duplicates("bodyId").set_index("bodyId")
        a = a.reindex(brain.bodies)
        sub = a["subclass"].fillna("").to_numpy(dtype=str); side = a["somaSide"].fillna("").to_numpy(dtype=str)
        typ = a["type"].fillna("").to_numpy(dtype=str); sc = a["superclass"].fillna("").to_numpy(dtype=str)
        self.units = []          # (leg, side, joint, ago_idx, ant_idx)
        for code, leg in LEGS.items():
            for s in SIDES:
                base = (sc == "vnc_motor") & (sub == code) & (side == s)
                for joint, p in POOLS.items():
                    ago = np.flatnonzero(base & np.isin(typ, p["ago"])); ant = np.flatnonzero(base & np.isin(typ, p["ant"]))
                    self.units.append((leg, s, joint, ago, ant))
        self.smoothed = np.zeros((len(self.units), 2), np.float32)   # per unit: ago rate, ant rate (Hz)
        self.all_idx = np.unique(np.concatenate([np.concatenate([u[3], u[4]]) for u in self.units]))

    def describe(self) -> pd.DataFrame:
        return pd.DataFrame([{"leg": l, "side": s, "joint": j, "agonist_n": len(a), "antagonist_n": len(b), "servo": SERVO_IDS[(l, s)][["coxa", "femur", "tibia"].index(j)]}
                             for l, s, j, a, b in self.units])

    def update(self, counts: np.ndarray, secs: float) -> dict:
        """Update smoothed pool rates from one control step's spike counts; return {servo_id: pulse} targets."""
        alpha = 1.0 - np.exp(-secs * 1000.0 / self.g.smooth_ms)
        targets, rates = {}, {}
        for k, (leg, s, joint, ago, ant) in enumerate(self.units):
            r_ago = counts[ago].sum() / max(len(ago), 1) / secs if len(ago) else 0.0
            r_ant = counts[ant].sum() / max(len(ant), 1) / secs if len(ant) else 0.0
            self.smoothed[k, 0] += alpha * (r_ago - self.smoothed[k, 0]); self.smoothed[k, 1] += alpha * (r_ant - self.smoothed[k, 1])
            deg = self.g.deg_per_hz[joint] * (self.smoothed[k, 0] - self.smoothed[k, 1])
            deg = float(np.clip(deg, -self.g.range_deg[joint], self.g.range_deg[joint]))
            sid = SERVO_IDS[(leg, s)][["coxa", "femur", "tibia"].index(joint)]
            targets[sid] = int(round(self.g.rest_pulse + deg * self.g.pulse_per_deg))
            rates[(leg, s, joint)] = (float(self.smoothed[k, 0]), float(self.smoothed[k, 1]))
        return {"pulses": targets, "rates": rates}
