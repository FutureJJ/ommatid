"""The brain as a service. One process on the server: the body posts camera frames and reads back commands;
the public site reads a telemetry websocket; every control step is logged.

    POST /body/frame      (Bearer token)  JPEG body + headers X-Ommatid-Telemetry (JSON)  →  latest command JSON
    GET  /telemetry       websocket, JSON at ~5 Hz for the live site
    GET  /state.json      latest snapshot
    GET  /health
    GET  /soma.bin        float32 (n, 3) soma positions, for the site's neuron scatter (static)

The brain loop runs in its own thread at its own pace (about 10 Hz on the server) and always consumes the most
recent frame; if no frame has arrived for a while the fly is 'blind' and the command is stop. Modes:
    live    frames from the body
    blind   control C4: no visual drive
    replay  frames from a recorded .npz (control C3)
"""
from __future__ import annotations
import asyncio, hashlib, io, json, os, threading, time
from dataclasses import asdict
from pathlib import Path
import numpy as np
from aiohttp import web

from .lif import Brain
from .eye import Eye
from .optic_lobe import OpticLobe, ColumnMap
from .readout import Readout, Gains
from .protocol import Protocol
from .motor import LegMotor, MotorGains
from .proprio import Proprioception

ROOT = Path(__file__).resolve().parents[2]
STEPS = 100                     # 100 × 0.2 ms = 20 ms brain time per control step
STALE_S = 1.0                   # no frame for this long → blind


class Telemetry:
    """Parquet log, one row per control step, rotated hourly."""
    def __init__(self, directory: Path):
        self.dir = directory; self.dir.mkdir(parents=True, exist_ok=True)
        self.rows = []; self.hour = None; self.last_flush = time.time()

    def add(self, row: dict):
        self.rows.append(row)
        h = time.strftime("%Y%m%d-%H", time.gmtime())
        if self.hour is None: self.hour = h
        if h != self.hour or len(self.rows) >= 500 or time.time() - self.last_flush > 30:
            self.flush()
            self.hour = h

    def flush(self):
        """One file per flush: no read-merge, so a schema difference between batches can never lose data or kill
        the brain loop. The analysis globs the directory."""
        if not self.rows: return
        rows, self.rows = self.rows, []
        self.last_flush = time.time()
        try:
            import pyarrow as pa, pyarrow.parquet as pq
            path = self.dir / f"steps-{self.hour or time.strftime('%Y%m%d-%H', time.gmtime())}-{int(time.time()*1000)}.parquet"
            pq.write_table(pa.Table.from_pylist(rows), path)
        except Exception as e:                      # never let logging stop the brain
            print(f"[telemetry] flush failed, {len(rows)} rows dropped: {e!r}", flush=True)


class BrainService:
    def __init__(self, graph=ROOT / "build/graph.npz", mode="live", log_dir=ROOT / "logs", gains: Gains = Gains()):
        t = time.time()
        from .optic_lobe import OpticLobeParams
        hz = float(os.environ.get("OMMATID_HZ_PER_UNIT", OpticLobeParams.hz_per_unit))
        self.brain = Brain(graph); self.eye = Eye(self.brain); self.ol = OpticLobe(OpticLobeParams(hz_per_unit=hz)); self.ro = Readout(self.brain, gains)
        # the input mapping is fixed anatomy, built once from the original graph and shared by every variant (review finding 1)
        cols = Path(graph).parent / "columns.npz"
        if not cols.exists():
            raise RuntimeError("build/columns.npz missing — run tools/build_columns.py on the original graph first")
        self.cmap = ColumnMap.load(cols, self.brain)
        self.mode = mode
        self.log = Telemetry(Path(log_dir))
        self.lock = threading.Lock()
        self.frame = None; self.frame_ts = 0.0; self.frame_hash = ""; self.body = {}; self.jpeg = b""
        self.frame_seq = 0                      # server-side count of frames received
        self.display = []                       # what the stimulus page reported showing: (server_ts, spec)
        self.display_log = Telemetry(Path(log_dir) / "display")
        sc = self.brain.superclass
        self.groups = {"optic lobe": np.char.startswith(sc.astype(str), "ol_") | (sc == "visual_projection") | (sc == "visual_centrifugal"),
                       "central brain": np.char.startswith(sc.astype(str), "cb_"),
                       "descending": sc == "descending_neuron",
                       "nerve cord": np.char.startswith(sc.astype(str), "vnc_") | (sc == "ascending_neuron")}
        self.command = {"linear_mps": 0.0, "yaw_rps": 0.0, "stop": True, "reason": "starting"}
        self.state = {"step": 0, "brain_ms": 0.0, "mode": mode, "setup_s": round(time.time() - t, 1),
                      "mapped_neurons": int(self.cmap.n_mapped), "graph_sha": self._sha(graph),
                      "columns_sha": self.cmap.sha, "columns_from_graph": self.cmap.source_graph_sha, "hz_per_unit": hz}
        self.fired_sample = np.zeros(0, np.int32)
        self.protocol = Protocol(trials_per_condition=0)
        # phase 2: the nerve cord drives and feels the legs
        self.phase = int(os.environ.get("OMMATID_PHASE", "1"))
        self.motor = self.proprio = None
        if self.phase >= 2:
            import pandas as pd
            ann = pd.read_feather(ROOT / "data/body-annotations.feather")
            self.motor = LegMotor(self.brain, ann, MotorGains())
            zs = np.load(ROOT / "build/sensory_sides.npz", allow_pickle=False)
            self.proprio = Proprioception(self.brain, ann, {int(i): str(x) for i, x in zip(zs["idx"], zs["side"])})
            self.state["phase2"] = {"motor_neurons": int(len(self.motor.all_idx)), "proprioceptors": self.proprio.describe()}
        self.last_servo_cmd = {}
        self.stim = {"kind": "grey", "trial": None, "phase": "idle", "condition": None}
        self.running = True
        threading.Thread(target=self._loop, name="brain-loop", daemon=True).start()

    @staticmethod
    def _sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
        return h.hexdigest()[:12]

    # ---- input from the body ---------------------------------------------------
    def put_frame(self, jpeg: bytes, body: dict):
        from PIL import Image
        img = Image.open(io.BytesIO(jpeg)).convert("L")
        gray = np.asarray(img, np.float32) / 255.0
        with self.lock:
            self.frame = gray; self.frame_ts = time.time(); self.body = body; self.jpeg = jpeg
            self.frame_seq += 1; self.frame_hash = hashlib.sha1(jpeg).hexdigest()[:10]
            return dict(self.command)

    def ack_display(self, spec: dict):
        """The stimulus page reports what it put on screen and when (its own clock); we stamp server time too."""
        ev = {"server_ts": time.time(), "client_ts": spec.get("client_ts"), "kind": spec.get("kind"), "trial": spec.get("trial"),
              "condition": spec.get("condition"), "phase": spec.get("phase"), "t_brain_ms": spec.get("t_brain_ms")}
        with self.lock:
            self.display.append(ev); self.display = self.display[-5000:]
        self.display_log.add(ev)

    # ---- the loop -----------------------------------------------------------------
    def _loop(self):
        blank = np.full((200, 320), 0.5, np.float32)
        while self.running:
            t0 = time.perf_counter()
            with self.lock:
                frame, fts, fhash, body, fseq = self.frame, self.frame_ts, self.frame_hash, dict(self.body), self.frame_seq
            frame_age = (time.time() - fts) if frame is not None else None
            stale = frame is None or frame_age > STALE_S
            if self.mode == "blind" or stale:
                drive = {}; seen = "blind" if self.mode == "blind" else "no-frame"
                act = None
            else:
                act = self.ol.see(frame); drive = self.cmap.drive(self.ol.rates(act)); seen = "live"
            if self.proprio is not None and body.get("servos"):
                reached = {int(k): int(v) for k, v in body["servos"].items()}
                joints = LegMotor.joints_from_positions(reached, self.last_servo_cmd, self.motor.g)
                omega = body.get("imu_omega_dps") or (0.0, 0.0, 0.0)
                drive = {**drive, **self.proprio.drive(joints, STEPS * self.brain.p.dt, omega)}
            t1 = time.perf_counter()
            r = self.brain.run(drive, STEPS)
            t2 = time.perf_counter()
            hz = self.ro.rates(r["counts"], r["secs"])
            cmd = self.ro.command()          # smoothed over ~200 ms of brain time
            if seen != "live":
                cmd.update(stop=True, linear_mps=0.0, yaw_rps=0.0)
            if self.motor is not None:
                mo = self.motor.update(r["counts"], r["secs"])
                cmd["servos"] = {str(k): int(v) for k, v in mo["pulses"].items()}
                cmd["phase"] = 2
                self.last_servo_cmd = mo["pulses"]
                pool_hz = mo["rates"]
            cmd["reason"] = seen; cmd["step"] = self.state["step"] + 1; cmd["ts"] = time.time()
            wall = time.perf_counter() - t0
            dil = wall / (STEPS * self.brain.p.dt / 1000)
            stim = self.protocol.tick(self.brain.t_ms, dil, frame_ok=(seen == "live"))
            with self.lock:
                self.stim = stim
                self.command = cmd
                self.state.update(step=cmd["step"], brain_ms=round(self.brain.t_ms, 1), seen=seen,
                                  wall_ms=round(wall * 1000, 1), dilation=round(wall / (STEPS * self.brain.p.dt / 1000), 2),
                                  flyvis_ms=round((t1 - t0) * 1000, 1), lif_ms=round((t2 - t1) * 1000, 1),
                                  spikes=r["total"], fired=int(len(r["fired"])), mean_mv=round(r["mean_mv"], 2),
                                  rates=hz, smoothed={k: round(v, 1) for k, v in self.ro.smoothed.items()}, command=cmd, frame_hash=fhash, body=body,
                                  drive_cells=int(sum(len(k) for k in drive)) if drive else 0,
                                  stim={k: stim.get(k) for k in ("kind", "trial", "condition", "phase")},
                                  pools=({f"{l}-{sd}-{j}": [round(a, 1), round(b, 1)] for (l, sd, j), (a, b) in pool_hz.items()} if self.motor is not None else None),
                                  active={k: int(r["counts"][m].astype(bool).sum()) for k, m in self.groups.items()},
                                  totals={k: int(m.sum()) for k, m in self.groups.items()})
                f = r["fired"]
                self.fired_sample = f if len(f) <= 3000 else np.random.default_rng(cmd["step"]).choice(f, 3000, replace=False)
            self.log.add({"ts": cmd["ts"], "step": cmd["step"], "brain_ms": self.brain.t_ms, "wall_ms": wall * 1000,
                          "seen": seen, "frame_hash": fhash, "frame_seq": fseq, "frame_recv_ts": fts if frame is not None else None,
                          "frame_age_ms": round(frame_age * 1000, 1) if frame_age is not None else None,
                          "spikes": r["total"], "fired": int(len(r["fired"])),
                          **{f"hz_{k}": v for k, v in hz.items()}, "cmd_linear": cmd["linear_mps"], "cmd_yaw": cmd["yaw_rps"],
                          "cmd_stop": cmd["stop"], "stim_kind": stim.get("kind"), "stim_trial": stim.get("trial"),
                          "stim_condition": stim.get("condition"), "stim_phase": stim.get("phase"), "protocol_version": stim.get("version"),
                          "stim_t_ms": stim.get("t_brain_ms"), "protocol_seed": self.protocol.seed if self.protocol.active else None,
                          **({f"pool_{l}_{sd}_{j}_{w}": v for (l, sd, j), (a, b) in pool_hz.items() for w, v in (("ago", a), ("ant", b))} if self.motor is not None else {}),
                          **({f"servo_{k}": v for k, v in self.last_servo_cmd.items()} if self.motor is not None else {}),
                          **{f"body_{k}": v for k, v in body.items() if isinstance(v, (int, float, str, bool))}})

    def snapshot(self) -> dict:
        with self.lock:
            s = dict(self.state); fired = self.fired_sample.tolist()
        s["fired_sample"] = fired
        if self.ol.last_movie is not None:
            s["eye"] = np.round(self.ol.last_movie, 2).tolist()        # (2, 721): what each eye's retina sees
        return s

    def soma_bin(self) -> bytes:
        return np.nan_to_num(self.brain.soma.astype(np.float32), nan=0.0).tobytes()


def make_app(svc: BrainService, token: str) -> web.Application:
    app = web.Application(client_max_size=4 * 1024 * 1024)
    clients: set[web.WebSocketResponse] = set()

    async def frame(req: web.Request):
        if token and req.headers.get("Authorization") != f"Bearer {token}":
            raise web.HTTPUnauthorized()
        body = json.loads(req.headers.get("X-Ommatid-Telemetry", "{}"))
        jpeg = await req.read()
        try:
            cmd = svc.put_frame(jpeg, body)
        except Exception as e:
            raise web.HTTPBadRequest(text=f"not a decodable image: {e}")
        return web.json_response(cmd)

    async def state(req): return web.json_response(svc.snapshot())
    async def health(req): return web.json_response({"ok": True, "step": svc.state["step"], "seen": svc.state.get("seen")})
    async def soma(req): return web.Response(body=svc.soma_bin(), content_type="application/octet-stream",
                                             headers={"Cache-Control": "public, max-age=86400"})
    async def frame_jpg(req):
        with svc.lock: jpeg = svc.jpeg
        if not jpeg: raise web.HTTPNotFound()
        return web.Response(body=jpeg, content_type="image/jpeg", headers={"Cache-Control": "no-store"})
    async def eye_mjpg(req):
        """Continuous MJPEG stream of the camera frames the brain receives (for OBS Media Source / VLC)."""
        resp = web.StreamResponse(status=200, headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame",
                                                       "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"})
        await resp.prepare(req)
        last = 0
        try:
            while True:
                with svc.lock: seq, jpeg = svc.frame_seq, svc.jpeg
                if seq != last and jpeg:
                    last = seq
                    await resp.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                await asyncio.sleep(0.05)
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        return resp

    async def groups(req):
        sc = svc.brain.superclass.astype(str)
        code = np.zeros(svc.brain.n, np.uint8)
        for i, (k, m) in enumerate(svc.groups.items(), start=1): code[m] = i
        return web.Response(body=code.tobytes(), content_type="application/octet-stream",
                            headers={"Cache-Control": "public, max-age=86400"})

    STIM_PAGE_VERSION = 3          # bump when site/stimulus.html changes; the page reloads itself when it sees a newer version

    async def stim_state(req):
        with svc.lock: st = dict(svc.stim)
        st["server_ts"] = time.time(); st["page_version"] = STIM_PAGE_VERSION
        return web.json_response(st, headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"})

    async def stim_ack(req):
        try: spec = await req.json()
        except Exception: raise web.HTTPBadRequest()
        svc.ack_display(spec if isinstance(spec, dict) else {})
        return web.json_response({"ok": True}, headers={"Access-Control-Allow-Origin": "*"})

    async def protocol_start(req):
        if token and req.headers.get("Authorization") != f"Bearer {token}": raise web.HTTPUnauthorized()
        q = await req.json() if req.can_read_body else {}
        svc.protocol = Protocol(trials_per_condition=int(q.get("trials_per_condition", 30)), seed=int(q.get("seed", 2026)),
                                note=str(q.get("note", "")))
        svc.protocol.start(svc.brain.t_ms)
        svc.log.flush(); svc.display_log.flush()
        return web.json_response(svc.protocol.status())

    async def protocol_stop(req):
        if token and req.headers.get("Authorization") != f"Bearer {token}": raise web.HTTPUnauthorized()
        svc.protocol.stop(); svc.log.flush(); svc.display_log.flush()
        return web.json_response(svc.protocol.status())

    async def protocol_status(req): return web.json_response(svc.protocol.status())

    async def telemetry(req):
        ws = web.WebSocketResponse(heartbeat=20); await ws.prepare(req); clients.add(ws)
        try:
            async for _ in ws: pass
        finally:
            clients.discard(ws)
        return ws

    async def broadcaster(app):
        while True:
            await asyncio.sleep(0.2)
            if clients:
                msg = json.dumps(svc.snapshot())
                for ws in list(clients):
                    try: await ws.send_str(msg)
                    except Exception: clients.discard(ws)

    async def start_bg(app): app["bg"] = asyncio.create_task(broadcaster(app))
    async def stop_bg(app): app["bg"].cancel(); svc.log.flush(); svc.display_log.flush()

    app.add_routes([web.post("/body/frame", frame), web.get("/state.json", state), web.get("/health", health),
                    web.get("/soma.bin", soma), web.get("/groups.bin", groups), web.get("/frame.jpg", frame_jpg), web.get("/eye.mjpg", eye_mjpg),
                    web.get("/stimulus/state.json", stim_state), web.post("/protocol/start", protocol_start), web.post("/stimulus/ack", stim_ack),
                    web.post("/protocol/stop", protocol_stop), web.get("/protocol/status.json", protocol_status),
                    web.get("/telemetry", telemetry)])
    app.on_startup.append(start_bg); app.on_cleanup.append(stop_bg)
    return app


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("OMMATID_PORT", "8700")))
    ap.add_argument("--mode", default=os.environ.get("OMMATID_MODE", "live"), choices=["live", "blind"])
    ap.add_argument("--graph", default=os.environ.get("OMMATID_GRAPH", str(ROOT / "build/graph.npz")))
    a = ap.parse_args()
    variant = Path(a.graph).stem.replace("graph_", "") if Path(a.graph).stem != "graph" else "original"
    svc = BrainService(graph=a.graph, mode=a.mode, log_dir=ROOT / "logs" / variant)
    svc.state["graph_variant"] = variant
    web.run_app(make_app(svc, os.environ.get("OMMATID_TOKEN", "")), host="127.0.0.1", port=a.port, print=None)


if __name__ == "__main__":
    main()
