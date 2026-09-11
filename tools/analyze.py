"""Analysis of protocol runs from the brain's Parquet logs (docs/experiment.md §2, §6).

For every trial: mean readout rate during the stimulus phase minus the mean during its own baseline phase, per
neuron population. Then per condition: trial count, mean ± 95 % CI of that difference, and the pre-registered
criteria:
  H1  sign of (DNa02_R − DNa02_L) during grating_R is positive and during grating_L negative, per trial
  H2  escape/stop readouts (DNp02, DNp04, DNp01, DNp09, MDN) rise above baseline during loom, not during disc/gratings
  H3  sign of (DNa02_R − DNa02_L) follows the bright side; DNa01 higher than in grey
With a second run on a control graph (C1/C2), a permutation test on the per-trial differences is reported.

usage: python tools/analyze.py logs/ [--control logs_shuffled/] [--seed 1]
"""
import sys, glob, argparse, numpy as np, pandas as pd

READOUTS = ["DNa02_L", "DNa02_R", "DNa01_L", "DNa01_R", "MDN", "DNp09", "DNp01", "DNp02", "DNp04"]


def load(path):
    files = sorted(glob.glob(f"{path}/*.parquet"))
    if not files: sys.exit(f"no parquet files in {path}")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df[df["stim_trial"].notna()].copy()
    df["stim_trial"] = df["stim_trial"].astype(int)
    return df


def per_trial(df):
    rows = []
    for (seed, tid), g in df.groupby(["protocol_seed", "stim_trial"]):
        base, stim = g[g.stim_phase == "baseline"], g[g.stim_phase == "stim"]
        if len(base) < 10 or len(stim) < 20: continue
        r = {"seed": seed, "trial": tid, "condition": stim["stim_condition"].iloc[0], "n_base": len(base), "n_stim": len(stim),
             "spikes_stim": stim["spikes"].mean(), "spikes_base": base["spikes"].mean()}
        for k in READOUTS:
            r[f"d_{k}"] = stim[f"hz_{k}"].mean() - base[f"hz_{k}"].mean()
            r[f"s_{k}"] = stim[f"hz_{k}"].mean()
        r["d_turn"] = r["d_DNa02_R"] - r["d_DNa02_L"]
        r["d_fwd"] = (r["d_DNa01_L"] + r["d_DNa01_R"]) / 2
        r["d_escape"] = max(r["d_DNp02"], r["d_DNp04"], r["d_DNp01"], r["d_DNp09"], r["d_MDN"])
        rows.append(r)
    return pd.DataFrame(rows)


def ci(x):
    x = np.asarray(x, float)
    if len(x) < 2: return (np.nan, np.nan)
    se = x.std(ddof=1) / np.sqrt(len(x)); return (x.mean() - 1.96 * se, x.mean() + 1.96 * se)


def perm_test(a, b, n=20000, seed=0):
    """Two-sided permutation test on the difference of means."""
    rng = np.random.default_rng(seed); a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2: return np.nan
    obs = a.mean() - b.mean(); pool = np.concatenate([a, b]); cnt = 0
    for _ in range(n):
        rng.shuffle(pool); cnt += abs(pool[:len(a)].mean() - pool[len(a):].mean()) >= abs(obs)
    return (cnt + 1) / (n + 1)


def report(t, ctrl=None):
    print(f"{len(t)} trials analysed" + (f", control run {len(ctrl)} trials" if ctrl is not None else ""))
    print(f"\n{'condition':10s} {'n':>3s} {'Δturn (R−L) Hz':>18s} {'Δforward Hz':>14s} {'Δescape Hz':>12s} {'spikes stim/base':>18s}")
    for c, g in t.groupby("condition"):
        lo, hi = ci(g.d_turn)
        print(f"{c:10s} {len(g):3d} {g.d_turn.mean():+8.1f} [{lo:+.1f},{hi:+.1f}] {g.d_fwd.mean():+13.1f} {g.d_escape.mean():+11.1f} {g.spikes_stim.mean():9.0f}/{g.spikes_base.mean():.0f}")
    print("\nPre-registered criteria")
    gR, gL = t[t.condition == "grating_R"], t[t.condition == "grating_L"]
    if len(gR) and len(gL):
        agree = np.concatenate([(gR.d_turn > 0).values, (gL.d_turn < 0).values]).mean()
        print(f"H1 optomotor: sign agreement {agree*100:.0f}% (criterion ≥ 80%) over {len(gR)+len(gL)} trials; "
              f"turn R vs L permutation p = {perm_test(gR.d_turn, gL.d_turn):.4f}")
        if ctrl is not None:
            cR, cL = ctrl[ctrl.condition == "grating_R"], ctrl[ctrl.condition == "grating_L"]
            eff = np.concatenate([gR.d_turn, -gL.d_turn]); ceff = np.concatenate([cR.d_turn, -cL.d_turn])
            print(f"    vs control graph: effect {eff.mean():+.1f} vs {ceff.mean():+.1f} Hz, permutation p = {perm_test(eff, ceff):.4f} (criterion < 0.01)")
    lo_, di = t[t.condition == "loom"], t[t.condition.isin(["disc", "grating_R", "grating_L"])]
    if len(lo_):
        thr = 5.0
        print(f"H2 looming: escape/stop rise > {thr} Hz in {(lo_.d_escape > thr).mean()*100:.0f}% of loom trials (criterion ≥ 70%), "
              f"in {(di.d_escape > thr).mean()*100:.0f}% of disc/grating controls (criterion < 20%); loom vs controls p = {perm_test(lo_.d_escape, di.d_escape):.4f}")
    bR, bL, gr = t[t.condition == "bright_R"], t[t.condition == "bright_L"], t[t.condition == "grey"]
    if len(bR) and len(bL):
        agree = np.concatenate([(bR.d_turn > 0).values, (bL.d_turn < 0).values]).mean()
        print(f"H3 phototaxis: turn toward bright side in {agree*100:.0f}% of trials (criterion ≥ 80%); "
              f"forward drive bright vs grey: {pd.concat([bR, bL]).d_fwd.mean():+.1f} vs {gr.d_fwd.mean() if len(gr) else float('nan'):+.1f} Hz")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("logs"); ap.add_argument("--control"); ap.add_argument("--seed", type=int)
    a = ap.parse_args()
    df = load(a.logs)
    if a.seed is not None: df = df[df.protocol_seed == a.seed]
    t = per_trial(df)
    ctrl = per_trial(load(a.control)) if a.control else None
    if len(t) == 0: sys.exit("no complete trials")
    report(t, ctrl)
    t.to_csv("trials.csv", index=False); print("\nper-trial table → trials.csv")
