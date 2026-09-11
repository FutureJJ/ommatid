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

ROOT = Path(__file__).resolve().parents[2]
STEPS = 100                     # 100 × 0.2 ms = 20 ms brain time per control step
STALE_S = 1.0                   # no frame for this long → blind


class Telemetry:
    """Parquet log, one row per control step, rotated hourly."""
    def __init__(self, directory: Path):
        self.dir = directory; self.dir.mkdir(parents=True, exist_ok=True)
        self.rows = []; self.hour = None

    def add(self, row: dict):
        self.rows.append(row)
        h = time.strftime("%Y%m%d-%H", time.gmtime())
        if self.hour is None: self.hour = h
        if h != self.hour or len(self.rows) >= 2000:
            self.flush()
            self.hour = h

    def flush(self):
        if not self.rows: return
        import pyarrow as pa, pyarrow.parquet as pq
        table = pa.Table.from_pylist(self.rows)
        path = self.dir / f"steps-{self.hour}.parquet"
        if path.exists():
            table = pa.concat_tables([pq.read_table(path), table], promote_options="default")
        pq.write_table(table, path)
        self.rows = []


class BrainService:
    def __init__(self, graph=ROOT / "build/graph.npz", mode="live", log_dir=ROOT / "logs", gains: Gains = Gains()):
        t = time.time()
        self.brain = Brain(graph); self.eye = Eye(self.brain); self.ol = OpticLobe(); self.ro = Readout(self.brain, gains)
        self.cmap = ColumnMap(self.ol, self.brain, self.eye.column_angles_all)
        self.mode = mode
        self.log = Telemetry(Path(log_dir))
        self.lock = threading.Lock()
        self.frame = None; self.frame_ts = 0.0; self.frame_hash = ""; self.body = {}
        self.command = {"linear_mps": 0.0, "yaw_rps": 0.0, "stop": True, "reason": "starting"}
        self.state = {"step": 0, "brain_ms": 0.0, "mode": mode, "setup_s": round(time.time() - t, 1),
                      "mapped_neurons": int(self.cmap.n_mapped), "graph_sha": self._sha(graph)}
        self.fired_sample = np.zeros(0, np.int32)
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
            self.frame = gray; self.frame_ts = time.time(); self.body = body
            self.frame_hash = hashlib.sha1(jpeg).hexdigest()[:10]
            return dict(self.command)

    # ---- the loop -----------------------------------------------------------------
    def _loop(self):
        blank = np.full((200, 320), 0.5, np.float32)
        while self.running:
            t0 = time.perf_counter()
            with self.lock:
                frame, fts, fhash, body = self.frame, self.frame_ts, self.frame_hash, dict(self.body)
            stale = frame is None or (time.time() - fts) > STALE_S
            if self.mode == "blind" or stale:
                drive = {}; seen = "blind" if self.mode == "blind" else "no-frame"
                act = None
            else:
                act = self.ol.see(frame); drive = self.cmap.drive(self.ol.rates(act)); seen = "live"
            t1 = time.perf_counter()
            r = self.brain.run(drive, STEPS)
            t2 = time.perf_counter()
            hz = self.ro.rates(r["counts"], r["secs"])
            cmd = self.ro.command()          # smoothed over ~200 ms of brain time
            if seen != "live":
                cmd.update(stop=True, linear_mps=0.0, yaw_rps=0.0)
            cmd["reason"] = seen; cmd["step"] = self.state["step"] + 1; cmd["ts"] = time.time()
            wall = time.perf_counter() - t0
            with self.lock:
                self.command = cmd
                self.state.update(step=cmd["step"], brain_ms=round(self.brain.t_ms, 1), seen=seen,
                                  wall_ms=round(wall * 1000, 1), dilation=round(wall / (STEPS * self.brain.p.dt / 1000), 2),
                                  flyvis_ms=round((t1 - t0) * 1000, 1), lif_ms=round((t2 - t1) * 1000, 1),
                                  spikes=r["total"], fired=int(len(r["fired"])), mean_mv=round(r["mean_mv"], 2),
                                  rates=hz, smoothed={k: round(v, 1) for k, v in self.ro.smoothed.items()}, command=cmd, frame_hash=fhash, body=body,
                                  drive_cells=int(sum(len(k) for k in drive)) if drive else 0)
                f = r["fired"]
                self.fired_sample = f if len(f) <= 6000 else np.random.default_rng(cmd["step"]).choice(f, 6000, replace=False)
            self.log.add({"ts": cmd["ts"], "step": cmd["step"], "brain_ms": self.brain.t_ms, "wall_ms": wall * 1000,
                          "seen": seen, "frame_hash": fhash, "spikes": r["total"], "fired": int(len(r["fired"])),
                          **{f"hz_{k}": v for k, v in hz.items()}, "cmd_linear": cmd["linear_mps"], "cmd_yaw": cmd["yaw_rps"],
                          "cmd_stop": cmd["stop"], **{f"body_{k}": v for k, v in body.items() if isinstance(v, (int, float, str, bool))}})

    def snapshot(self) -> dict:
        with self.lock:
            s = dict(self.state); fired = self.fired_sample.tolist()
        s["fired_sample"] = fired
        if self.ol.last_movie is not None:
            s["eye"] = np.round(self.ol.last_movie, 3).tolist()        # (2, 721): what each eye's retina sees
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
        cmd = svc.put_frame(jpeg, body)
        return web.json_response(cmd)

    async def state(req): return web.json_response(svc.snapshot())
    async def health(req): return web.json_response({"ok": True, "step": svc.state["step"], "seen": svc.state.get("seen")})
    async def soma(req): return web.Response(body=svc.soma_bin(), content_type="application/octet-stream",
                                             headers={"Cache-Control": "public, max-age=86400"})

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
    async def stop_bg(app): app["bg"].cancel(); svc.log.flush()

    app.add_routes([web.post("/body/frame", frame), web.get("/state.json", state), web.get("/health", health),
                    web.get("/soma.bin", soma), web.get("/telemetry", telemetry)])
    app.on_startup.append(start_bg); app.on_cleanup.append(stop_bg)
    return app


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("OMMATID_PORT", "8700")))
    ap.add_argument("--mode", default=os.environ.get("OMMATID_MODE", "live"), choices=["live", "blind"])
    ap.add_argument("--graph", default=str(ROOT / "build/graph.npz"))
    a = ap.parse_args()
    svc = BrainService(graph=a.graph, mode=a.mode)
    web.run_app(make_app(svc, os.environ.get("OMMATID_TOKEN", "")), host="127.0.0.1", port=a.port, print=None)


if __name__ == "__main__":
    main()
