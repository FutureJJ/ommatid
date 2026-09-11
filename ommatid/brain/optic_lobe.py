"""Optic lobe: FlyVis (Lappalainen et al. 2024, Nature) — a connectome-constrained model of the fly visual system,
R1-R8 through T4/T5, 64 cell types, 721 columns, 45,669 neurons, MIT licence, pretrained ensemble released by the
Turaga lab. It stands in for the optic-lobe-intrinsic part of the spiking model, which cannot see (docs/model.md).

Why this boundary: optic-lobe columnar neurons are graded (non-spiking) and the ON pathway starts with disinhibition;
a zero-baseline spiking model is structurally blind there. Downstream of the medulla outputs (T4/T5, Tm, TmY) —
lobula plate tangential cells, lobula columnar looming detectors, descending neurons, VNC — the untrained connectome
LIF model takes over. FlyVis is trained (a few scalars per cell type, on an optic-flow task, never on neural data);
docs/experiment.md says so in the honesty table.

Two eyes: FlyVis models one eye; its T4a prefers +x motion, which is front-to-back for a right eye. The left eye is
the same network fed a horizontally mirrored frame; both run as one batch of two.

Geometry: FlyVis hexal (u, v) sits at pixel (x, y) = (13 v, 12.97 u + 6.49 v) on a 391 px canvas; 13 px = 5.8° of
visual angle (one receptor spacing). The canvas centre is placed `eye_center_azimuth_deg` lateral of the midline.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import torch


@dataclass(frozen=True)
class OpticLobeParams:
    ensemble: str = "flow/0000/000"     # pretrained FlyVis model
    dt: float = 0.01                     # FlyVis time step, 10 ms
    frames_per_step: int = 2             # 2 x 10 ms = one 20 ms control step
    cam_hfov_deg: float = 74.0
    deg_per_px: float = 5.8 / 13.0       # FlyVis: 5.8° receptor spacing, 13 px per receptor (BoxEye kernel)
    eye_center_azimuth_deg: float = 45.0 # where the FlyVis array centre sits in each eye's visual field
    hz_per_unit: float = 100.0           # FlyVis activity (rectified, a.u.) → forced-spike rate in the LIF model
    threads: int = 4


class OpticLobe:
    def __init__(self, p: OpticLobeParams = OpticLobeParams()):
        torch.set_num_threads(p.threads)
        from flyvis import NetworkView
        from flyvis.datasets.rendering import BoxEye
        self.p = p
        self.net = NetworkView(p.ensemble).init_network().cpu().eval()
        self.eye = BoxEye(extent=15, kernel_size=13)
        self.canvas = int(self.eye.min_frame_size[0])
        nodes = self.net.connectome.nodes
        self.node_type = np.array([s.decode() if isinstance(s, bytes) else str(s) for s in nodes.type[:]])
        self.node_u = np.asarray(nodes.u[:]); self.node_v = np.asarray(nodes.v[:])
        # visual angle of every node's column, right-eye convention (+azimuth = lateral, +elevation = up)
        px_x = 13.0 * self.node_v
        px_y = 12.97 * self.node_u + 6.49 * self.node_v
        self.node_azimuth = p.eye_center_azimuth_deg + px_x * p.deg_per_px
        self.node_elevation = -px_y * p.deg_per_px
        self.output_types = [s.decode() if isinstance(s, bytes) else str(s)
                             for s in self.net.connectome.output_cell_types[:]]
        self.out_idx = {t: np.flatnonzero(self.node_type == t) for t in self.output_types}
        with torch.no_grad():
            st = self.net.steady_state(t_pre=1.0, dt=p.dt, batch_size=2)
        self.state = st
        # FlyVis activity at a uniform grey field. The spiking model has a zero baseline by construction (Shiu 2024),
        # so what is injected is the deviation from this grey steady state, rectified: no image, no drive.
        self.baseline = st.nodes.activity.detach().cpu().numpy().copy()          # (2, n_nodes)
        self.last = None

    # ---- rendering ----------------------------------------------------------
    def _place(self, gray: np.ndarray, mirror: bool) -> np.ndarray:
        """Put the camera frame on the eye's canvas at the angles it covers; elsewhere the frame's mean."""
        p = self.p
        from PIL import Image
        H, W = gray.shape
        img = np.ascontiguousarray(gray[:, ::-1]) if mirror else gray
        canvas = np.full((self.canvas, self.canvas), float(gray.mean()), np.float32)
        px_w = int(round(p.cam_hfov_deg / p.deg_per_px))
        px_h = int(round(px_w * H / W))
        small = np.asarray(Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((px_w, px_h), Image.BILINEAR),
                           np.float32) / 255.0
        c = (self.canvas - 1) / 2
        x0 = int(round(c - p.eye_center_azimuth_deg / p.deg_per_px - px_w / 2))   # camera is centred on the midline
        y0 = int(round(c - px_h / 2))
        xs, ys = max(x0, 0), max(y0, 0)
        xe, ye = min(x0 + px_w, self.canvas), min(y0 + px_h, self.canvas)
        canvas[ys:ye, xs:xe] = small[ys - y0:ye - y0, xs - x0:xe - x0]
        return canvas

    # ---- one control step ---------------------------------------------------
    def see(self, gray: np.ndarray) -> np.ndarray:
        """gray: float32 HxW in [0,1]. Advances FlyVis by frames_per_step frames for both eyes and returns the
        activity of every FlyVis node, shape (2, n_nodes): row 0 = right eye, row 1 = left eye (mirrored frame),
        averaged over the frames of this step."""
        p = self.p
        frames = np.stack([self._place(gray, False), self._place(gray, True)])        # (2, H, W)
        seq = torch.from_numpy(frames)[:, None].repeat(1, p.frames_per_step, 1, 1)    # (2, F, H, W)
        with torch.no_grad():
            movie = self.eye(seq)                                                      # (2, F, 1, 721)
            self.net.stimulus.zero(2, p.frames_per_step)
            self.net.stimulus.add_input(movie)
            x = self.net.stimulus()
            states = self.net.forward(x, p.dt, state=self.state, as_states=True)
            self.state = states[-1]
            act = torch.stack([s.nodes.activity for s in states], 0).mean(0)          # (2, n_nodes)
        self.last = act.numpy()
        return self.last

    def rates(self, act: np.ndarray) -> dict:
        """Forced-spike rates for the LIF model: {type: (2, n_cols) Hz} = hz_per_unit × max(0, activity − grey baseline)."""
        dev = act - self.baseline
        return {t: np.clip(dev[:, idx], 0, None) * self.p.hz_per_unit for t, idx in self.out_idx.items()}


class ColumnMap:
    """Nearest-column mapping from FlyVis output nodes to the male CNS neurons of the same type and side."""

    def __init__(self, ol: OpticLobe, brain, column_angles, max_deg: float = 6.0):
        """column_angles(side) -> (male neuron indices, azimuth, elevation) for every hex-carrying neuron of that
        side, azimuth measured lateral-positive from the midline, elevation up — the FlyVis convention."""
        self.pairs = {}          # (type, side) -> (positions within ol.out_idx[type], male neuron indices)
        self.n_mapped = 0
        self.n_inferred = 0
        for side in ("R", "L"):
            res = column_angles(side)
            m_idx, m_az, m_el = res[0], res[1], res[2]
            if len(res) > 3:
                self.n_inferred += int(res[3].sum())
            for t in ol.output_types:
                fv = ol.out_idx[t]
                sel = brain.types[m_idx] == t
                if len(fv) == 0 or not sel.any():
                    continue
                male, ma, me = m_idx[sel], m_az[sel], m_el[sel]
                fa, fe = ol.node_azimuth[fv], ol.node_elevation[fv]
                d2 = (ma[:, None] - fa[None, :]) ** 2 + (me[:, None] - fe[None, :]) ** 2
                j = d2.argmin(1)
                ok = np.sqrt(d2[np.arange(len(ma)), j]) <= max_deg
                if ok.any():
                    self.pairs[(t, side)] = (j[ok].astype(np.int64), male[ok])
                    self.n_mapped += int(ok.sum())

    def drive(self, rates: dict) -> dict:
        """LIF external drive {tuple(male neuron idx): rates_hz} from FlyVis rates {type: (2, n_cols)}."""
        out = {}
        for (t, side), (pos, male) in self.pairs.items():
            out[tuple(male)] = rates[t][0 if side == "R" else 1][pos]
        return out
