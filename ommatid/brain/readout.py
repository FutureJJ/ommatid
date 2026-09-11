"""Descending-neuron readout: the neurons a fly walks with, read as firing rates, mapped to a body command.

  DNa02  left/right pair — steering; a fly turns by the left-right asymmetry (Rayshubskiy 2020)
  DNa01  left/right pair — forward walking (Namiki 2018)
  MDN    moonwalker descending neurons — backward walking (Bidaye 2014)
  DNp09  stopping / freezing (Zacarias 2018)
  DNp01 (giant fibre), DNp02, DNp04 — looming-driven escape descending neurons (von Reyn 2014; Ache 2019);
         read out for hypothesis H2 alongside DNp09 and MDN

Everything here is a fixed linear map with one gain per channel. Gains are frozen before recorded trials
(docs/frozen-params.md). Nothing is fitted to behaviour.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np


@dataclass(frozen=True)
class Gains:
    turn_hz: float = 200.0      # DNa02 right-minus-left difference (Hz) that maps to full yaw
    forward_hz: float = 200.0   # mean DNa01 rate (Hz) that maps to full forward speed
    backward_hz: float = 200.0  # mean MDN rate (Hz) that maps to full backward speed
    stop_hz: float = 150.0      # DNp09 rate above which the body stops
    max_linear_mps: float = 0.08
    max_yaw_rps: float = 0.5


class Readout:
    def __init__(self, brain, gains: Gains = Gains()):
        self.g = gains
        self.pop = {
            "DNa02_L": brain.where(type="DNa02", side="L"), "DNa02_R": brain.where(type="DNa02", side="R"),
            "DNa01_L": brain.where(type="DNa01", side="L"), "DNa01_R": brain.where(type="DNa01", side="R"),
            "MDN": brain.where(type="MDN"), "DNp09": brain.where(type="DNp09"),
            "DNp01": brain.where(type="DNp01"), "DNp02": brain.where(type="DNp02"), "DNp04": brain.where(type="DNp04"),
        }
        for k, v in self.pop.items():
            if len(v) == 0:
                raise RuntimeError(f"readout population {k} is empty in this graph")
        self.all_idx = np.concatenate(list(self.pop.values()))

    def rates(self, counts: np.ndarray, secs: float) -> dict:
        return {k: float(counts[v].sum() / len(v) / secs) for k, v in self.pop.items()}

    def command(self, hz: dict) -> dict:
        g = self.g
        turn = np.clip((hz["DNa02_R"] - hz["DNa02_L"]) / g.turn_hz, -1, 1)
        fwd = np.clip((hz["DNa01_L"] + hz["DNa01_R"]) / 2 / g.forward_hz, 0, 1)
        back = np.clip(hz["MDN"] / g.backward_hz, 0, 1)
        stop = hz["DNp09"] >= g.stop_hz
        linear = 0.0 if stop else float((fwd - back) * g.max_linear_mps)
        yaw = 0.0 if stop else float(turn * g.max_yaw_rps)
        # sign convention: DNa02 right > left → the fly turns right → negative yaw in ROS (z up, +yaw = counter-clockwise)
        return {"linear_mps": linear, "yaw_rps": -yaw, "stop": bool(stop),
                "turn": float(turn), "forward": float(fwd), "backward": float(back)}

    def describe(self) -> dict:
        return {"populations": {k: int(len(v)) for k, v in self.pop.items()}, "gains": asdict(self.g)}
