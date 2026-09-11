"""Run the pre-registered P2-a dry-run blocks unattended on the server (docs/phase2.md §10, docs/frozen-params-p2.md).

For each graph variant: restart the brain on it, wait until it is live, verify the graph hash, then alternate the
proprioceptive feedback ON / OFF for ARM_S seconds of brain time each, REPEATS times (A B A B). Every switch is logged
with server time and brain time to run_p2a.log; the analysis (tools/analyze_phase2.py) finds the blocks from the
per-step proprio_on column, so this log is a cross-check, not the source of truth. Body must be in dry run (verified
from the body telemetry before every block; the run aborts otherwise). Run as root: systemctl restarts the brain.

usage: sudo .venv/bin/python tools/run_p2a.py [--variants graph.npz,graph_shuffled.npz] [--arm-s 150] [--repeats 2]
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request

ROOT = "/home/ommatid/ommatid"; URL = "http://127.0.0.1:8700"; LOG = f"{ROOT}/run_p2a.log"


def log(**kv):
    kv = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **kv}
    print(json.dumps(kv), flush=True)
    with open(LOG, "a") as f: f.write(json.dumps(kv) + "\n")


def get(path):
    with urllib.request.urlopen(f"{URL}{path}", timeout=10) as r: return json.load(r)


def post(path, body, token):
    req = urllib.request.Request(f"{URL}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r: return json.load(r)


def set_graph(name):
    env = open(f"{ROOT}/.env").read()
    env = re.sub(r"^OMMATID_GRAPH=.*$", f"OMMATID_GRAPH={ROOT}/build/{name}", env, flags=re.M)
    open(f"{ROOT}/.env", "w").write(env)
    subprocess.run(["systemctl", "restart", "ommatid-brain"], check=True)


def wait_live(timeout_s=400):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            h = get("/health")
            if h.get("seen") == "live": return True
        except Exception: pass
        time.sleep(3)
    return False


def brain_s():
    return get("/state.json")["brain_ms"] / 1000.0


def check_dry():
    s = get("/state.json"); b = s.get("body") or {}
    if not b.get("dry_run", False): log(event="ABORT", reason="body not in dry run", body={k: b.get(k) for k in ("dry_run", "phase2", "stand")}); sys.exit(2)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--variants", default="graph.npz,graph_shuffled.npz")
    ap.add_argument("--arm-s", type=float, default=150.0); ap.add_argument("--repeats", type=int, default=2); ap.add_argument("--settle-wall-s", type=float, default=30.0)
    a = ap.parse_args()
    token = re.search(r"^OMMATID_TOKEN=(.*)$", open(f"{ROOT}/.env").read(), re.M).group(1).strip()
    log(event="start", variants=a.variants, arm_s=a.arm_s, repeats=a.repeats)
    for g in a.variants.split(","):
        set_graph(g)
        if not wait_live(): log(event="ABORT", reason=f"brain not live on {g}"); sys.exit(1)
        time.sleep(a.settle_wall_s)
        s = check_dry()
        log(event="variant", graph=g, graph_sha=s.get("graph_sha"), columns_sha=s.get("columns_sha"), variant=s.get("graph_variant"),
            hz_per_unit=s.get("hz_per_unit"), phase2=bool(s.get("phase2")), body_phase2=(s.get("body") or {}).get("phase2"))
        for rep in range(a.repeats):
            for on in (True, False):
                r = post("/phase2/proprio", {"on": on}, token)
                t_start = r["brain_ms"] / 1000.0
                log(event="arm", graph=g, rep=rep, proprio_on=on, brain_s=round(t_start, 1))
                while True:
                    time.sleep(10)
                    s = check_dry()
                    if s["brain_ms"] / 1000.0 - t_start >= a.arm_s: break
                    if s.get("seen") != "live": log(event="note", reason="no frame", brain_s=round(s["brain_ms"] / 1000.0, 1))
                log(event="arm-end", graph=g, rep=rep, proprio_on=on, brain_s=round(s["brain_ms"] / 1000.0, 1))
        post("/phase2/proprio", {"on": True}, token)
        log(event="variant-end", graph=g)
    set_graph("graph.npz"); wait_live()
    log(event="done")
