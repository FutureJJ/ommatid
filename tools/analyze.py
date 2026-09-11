"""Analysis of protocol runs from the brain's Parquet logs, as pre-registered (docs/experiment.md, docs/frozen-params.md).

Two modes:
  v1  (runs before 2026-09-11 review): stimulus labels are the server's protocol state at the step, not frame-locked;
      no 200 ms onset test is possible. Reported as EXPLORATORY: per-condition means, each control separately,
      trials with any no-frame step marked invalid and excluded from the primary table (kept in a secondary line).
  v2  (frame-locked runs): a step's stimulus is the display state acknowledged by the screen at least LATENCY_S before
      the frame the step consumed was received; onset = first step after stimulus onset at which the readout exceeds
      baseline mean + 2 SD for 2 consecutive steps; H2 requires onset within 200 ms of brain time.

Per trial: mean readout rate during the stimulus phase minus the mean during the trial's own baseline, per population.

usage: python tools/analyze.py <logs dir> [--control <logs dir>] [--seed N] [--mode v1|v2]
"""
import sys, glob, argparse, numpy as np, pandas as pd

READOUTS = ["DNa02_L", "DNa02_R", "DNa01_L", "DNa01_R", "MDN", "DNp09", "DNp01", "DNp02", "DNp04"]
ESCAPE = ["DNp02", "DNp04", "DNp01", "DNp09", "MDN"]
LATENCY_S = 0.30            # v2: display → camera → server, allowance (pre-registered)
ONSET_LIMIT_MS = 200.0      # v2: H2 onset criterion, brain time
STEP_MS = 20.0


def load(path):
    files = sorted(f for f in glob.glob(f"{path}/*.parquet") if "/display/" not in f)
    if not files: sys.exit(f"no parquet files in {path}")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if "stim_trial" not in df: sys.exit("no stimulus columns in these logs")
    df = df[df["stim_trial"].notna()].copy()
    df["stim_trial"] = df["stim_trial"].astype(int)
    return df


def load_display(path):
    files = sorted(glob.glob(f"{path}/display/*.parquet"))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else None


def relabel_frame_locked(df, disp):
    """v2: assign each step the stimulus that was on screen when its frame was captured (display ack ≤ frame_recv − latency)."""
    disp = disp.sort_values("server_ts").reset_index(drop=True)
    t = df["frame_recv_ts"].to_numpy(dtype=float) - LATENCY_S
    idx = np.searchsorted(disp["server_ts"].to_numpy(), t, side="right") - 1
    ok = idx >= 0
    for col in ("trial", "condition", "phase", "kind"):
        vals = disp[col].to_numpy(dtype=object)
        df["stim_" + col] = [vals[i] if o else None for i, o in zip(idx, ok)]
    df = df[df["stim_trial"].notna()].copy(); df["stim_trial"] = df["stim_trial"].astype(int)
    return df


def per_trial(df, mode="v1"):
    rows = []
    for (seed, tid), g in df.groupby(["protocol_seed", "stim_trial"]):
        g = g.sort_values("step")
        base, stim = g[g.stim_phase == "baseline"], g[g.stim_phase == "stim"]
        if len(base) < 10 or len(stim) < 20: continue
        noframe = int((g.seen != "live").sum())
        r = {"seed": seed, "trial": tid, "condition": stim["stim_condition"].iloc[0], "n_base": len(base), "n_stim": len(stim),
             "noframe_steps": noframe, "valid": noframe == 0,
             "spikes_stim": stim["spikes"].mean(), "spikes_base": base["spikes"].mean()}
        for k in READOUTS:
            r[f"d_{k}"] = stim[f"hz_{k}"].mean() - base[f"hz_{k}"].mean()
            r[f"s_{k}"] = stim[f"hz_{k}"].mean()
        r["d_turn"] = r["d_DNa02_R"] - r["d_DNa02_L"]
        r["d_fwd"] = (r["d_DNa01_L"] + r["d_DNa01_R"]) / 2
        r["d_escape"] = max(r[f"d_{k}"] for k in ESCAPE)
        if mode == "v2":
            # onset: first of 2 consecutive stimulus steps where any escape readout exceeds baseline mean + 2 SD
            onset = None
            for k in ESCAPE:
                mu, sd = base[f"hz_{k}"].mean(), base[f"hz_{k}"].std(ddof=1) if len(base) > 1 else 0.0
                above = (stim[f"hz_{k}"].to_numpy() > mu + 2 * sd + 1e-9)
                for i in range(len(above) - 1):
                    if above[i] and above[i + 1]:
                        cand = (i + 1) * STEP_MS
                        onset = cand if onset is None else min(onset, cand); break
            r["escape_onset_ms"] = onset
            r["h2_onset_ok"] = onset is not None and onset <= ONSET_LIMIT_MS
        rows.append(r)
    return pd.DataFrame(rows)


def ci(x):
    x = np.asarray(x, float)
    if len(x) < 2: return (np.nan, np.nan)
    se = x.std(ddof=1) / np.sqrt(len(x)); return (x.mean() - 1.96 * se, x.mean() + 1.96 * se)


def perm_test(a, b, n=20000, seed=0):
    rng = np.random.default_rng(seed); a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2: return np.nan
    obs = a.mean() - b.mean(); pool = np.concatenate([a, b]); cnt = 0
    for _ in range(n):
        rng.shuffle(pool); cnt += abs(pool[:len(a)].mean() - pool[len(a):].mean()) >= abs(obs)
    return (cnt + 1) / (n + 1)


def report(t_all, ctrl_all=None, mode="v1"):
    t = t_all[t_all.valid]; ctrl = ctrl_all[ctrl_all.valid] if ctrl_all is not None else None
    print(f"mode {mode}: {len(t_all)} trials, {len(t)} valid (no-frame steps in {int((~t_all.valid).sum())} trials)"
          + (f"; control run {len(ctrl_all)} trials, {len(ctrl)} valid" if ctrl_all is not None else ""))
    print(f"\n{'condition':10s} {'n':>3s} {'Δturn (R−L) Hz':>18s} {'Δforward':>9s} {'Δescape Hz':>18s} {'>5Hz':>5s} {'spikes stim/base':>18s}")
    for c, g in t.groupby("condition"):
        lo, hi = ci(g.d_turn); elo, ehi = ci(g.d_escape)
        print(f"{c:10s} {len(g):3d} {g.d_turn.mean():+8.1f} [{lo:+.1f},{hi:+.1f}] {g.d_fwd.mean():+8.1f} {g.d_escape.mean():+7.1f} [{elo:+.1f},{ehi:+.1f}] {(g.d_escape>5).mean()*100:4.0f}% {g.spikes_stim.mean():9.0f}/{g.spikes_base.mean():.0f}")
    print("\nPre-registered criteria" + (" (v1 labels are not frame-locked: exploratory)" if mode == "v1" else ""))
    gR, gL = t[t.condition == "grating_R"], t[t.condition == "grating_L"]
    if len(gR) and len(gL):
        agree = np.concatenate([(gR.d_turn > 0).values, (gL.d_turn < 0).values]).mean()
        print(f"H1 optomotor: sign agreement {agree*100:.0f}% (≥ 80% required) over {len(gR)+len(gL)} trials; R vs L p = {perm_test(gR.d_turn, gL.d_turn):.4f}")
        if ctrl is not None:
            cR, cL = ctrl[ctrl.condition == "grating_R"], ctrl[ctrl.condition == "grating_L"]
            eff = np.concatenate([gR.d_turn, -gL.d_turn]); ceff = np.concatenate([cR.d_turn, -cL.d_turn])
            print(f"    vs control graph: {eff.mean():+.1f} vs {ceff.mean():+.1f} Hz, p = {perm_test(eff, ceff):.4f} (< 0.01 required)")
    lo_ = t[t.condition == "loom"]
    if len(lo_):
        print("H2 looming, each control separately (fraction of trials with escape/stop rise > 5 Hz — a threshold NOT in the v1 freeze):")
        for c in ["loom", "disc", "recede", "grating_R", "grating_L", "grey", "bright_R", "bright_L"]:
            g = t[t.condition == c]
            if len(g): print(f"    {c:10s} {(g.d_escape>5).mean()*100:4.0f}%  mean {g.d_escape.mean():+5.1f} Hz   loom vs this: p = {perm_test(lo_.d_escape, g.d_escape) if c != 'loom' else float('nan'):.4f}")
        for k in ESCAPE:
            lo, hi = ci(lo_[f"d_{k}"]); print(f"    loom Δ{k}: {lo_[f'd_{k}'].mean():+.1f} Hz [{lo:+.1f}, {hi:+.1f}]")
        if mode == "v2":
            print(f"    onset ≤ {ONSET_LIMIT_MS:.0f} ms (2 consecutive steps > baseline mean + 2 SD): {lo_.h2_onset_ok.mean()*100:.0f}% of loom trials (≥ 70% required); "
                  f"controls: " + ", ".join(f"{c} {t[t.condition==c].h2_onset_ok.mean()*100:.0f}%" for c in ["disc", "recede", "grating_R", "grating_L", "grey"] if len(t[t.condition==c])) + " (< 20% each required)")
        if ctrl is not None:
            clo = ctrl[ctrl.condition == "loom"]
            print(f"    loom escape rise, this graph vs control graph: {lo_.d_escape.mean():+.1f} vs {clo.d_escape.mean():+.1f} Hz, p = {perm_test(lo_.d_escape, clo.d_escape):.4f} "
                  "(informative only: the control changes wiring, and in v1 also the input mapping)")
    bR, bL, gr = t[t.condition == "bright_R"], t[t.condition == "bright_L"], t[t.condition == "grey"]
    if len(bR) and len(bL):
        agree = np.concatenate([(bR.d_turn > 0).values, (bL.d_turn < 0).values]).mean()
        print(f"H3 phototaxis: turn toward bright side in {agree*100:.0f}% of trials (≥ 80% required); forward drive bright vs grey: "
              f"{pd.concat([bR, bL]).d_fwd.mean():+.1f} vs {gr.d_fwd.mean() if len(gr) else float('nan'):+.1f} Hz")
    inv = t_all[~t_all.valid]
    if len(inv):
        print(f"\nexcluded (no-frame steps): {len(inv)} trials — " + ", ".join(f"{c} {n}" for c, n in inv.condition.value_counts().items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("logs"); ap.add_argument("--control"); ap.add_argument("--seed", type=int)
    ap.add_argument("--mode", default="v1", choices=["v1", "v2"])
    a = ap.parse_args()
    df = load(a.logs)
    if a.seed is not None: df = df[df.protocol_seed == a.seed]
    if a.mode == "v2":
        disp = load_display(a.logs)
        if disp is None: sys.exit("v2 needs display acks in <logs>/display/")
        df = relabel_frame_locked(df, disp)
    t = per_trial(df, a.mode)
    ctrl = None
    if a.control:
        cdf = load(a.control)
        if a.seed is not None: cdf = cdf[cdf.protocol_seed == a.seed]
        if a.mode == "v2": cdf = relabel_frame_locked(cdf, load_display(a.control))
        ctrl = per_trial(cdf, a.mode)
    if len(t) == 0: sys.exit("no complete trials")
    report(t, ctrl, a.mode)
    t.to_csv("trials.csv", index=False); print("\nper-trial table → trials.csv")
