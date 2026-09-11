"""Phase 2, P2-a (dry run): does the nerve cord produce leg motor output in this body, and does the proprioceptive
feedback change it? Pre-registered in docs/phase2.md §10 before the first block was run.

Input: the brain's Parquet step logs of a phase-2 brain (columns pool_<leg>_<side>_<joint>_<ago|ant>, servo_<id>,
reached_<id>, proprio_on, seen, body_dry_run, brain_ms). Blocks are the contiguous segments of one proprio_on value;
the first SETTLE_S seconds of brain time after every switch (and after start) are excluded.

Per block and per motor unit (leg × side × joint, 18 units, agonist and antagonist pools):
  - mean rate (Hz) over the block, SD over consecutive WINDOW_S windows of brain time, fraction of steps with any spike
  - the servo target that results: mean signed angle from rest (deg), its SD, |max|
  - agonist − antagonist alternation: Welch PSD of the smoothed difference at 50 Hz (20 ms steps); peak in 0.2–2 Hz and
    its ratio to the median PSD in that band (descriptive, P2-c has no criterion in the dry run)
Arm comparison (feedback on vs off, and this graph vs the control graph): window means, permutation test on the
difference of means per unit, Holm-corrected over 18 units. P2-a is "met" if ≥ 1 unit's agonist or antagonist pool has a
mean rate > 5 Hz in the feedback-on blocks of the original graph — a low bar on purpose: the question is whether there is any
motor output at all. Everything else is reported, not judged.

usage: python tools/analyze_phase2.py <logs dir> [--control <logs dir>] [--after ISO-UTC] [--md out.md]
"""
import sys, glob, argparse, re, numpy as np, pandas as pd
sys.path.insert(0, ".")
from ommatid.brain.motor import SERVO_IDS, REST_PULSE, SIDE_SIGN, MotorGains

SETTLE_S = 20.0          # brain time excluded after every switch / start
WINDOW_S = 10.0          # brain time, for SDs and the permutation test
STEP_S = 0.02
BAND = (0.2, 2.0)
UNITS = [(l, s, j) for l in ("front", "mid", "hind") for s in ("L", "R") for j in ("coxa", "femur", "tibia")]
JIDX = {"coxa": 0, "femur": 1, "tibia": 2}
G = MotorGains()


def load(path, after=None):
    files = sorted(f for f in glob.glob(f"{path}/*.parquet") if "/display/" not in f)
    if not files: sys.exit(f"no parquet files in {path}")
    parts = []
    for f in files:
        d = pd.read_parquet(f)
        if "proprio_on" in d: parts.append(d)
    if not parts: sys.exit("no phase-2 rows (proprio_on column) in these logs")
    df = pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
    if after: df = df[df.ts >= pd.Timestamp(after, tz="UTC").timestamp()]
    df = df[(df.seen == "live") & (df.get("body_dry_run", True) == True)].copy()
    return df


def blocks(df):
    """Contiguous proprio_on segments (a restart also starts a new block: brain_ms drops)."""
    on = df.proprio_on.astype(bool).to_numpy(); t = df.brain_ms.to_numpy() / 1000.0
    cut = np.flatnonzero((on[1:] != on[:-1]) | (t[1:] < t[:-1])) + 1
    out = []
    for a, b in zip(np.r_[0, cut], np.r_[cut, len(df)]):
        g = df.iloc[a:b]; t0 = g.brain_ms.iloc[0] / 1000.0
        g = g[g.brain_ms / 1000.0 >= t0 + SETTLE_S]
        if len(g) * STEP_S >= 2 * WINDOW_S: out.append((bool(on[a]), g))
    return out


def unit_table(g):
    rows = []; t = g.brain_ms.to_numpy() / 1000.0; w = ((t - t[0]) // WINDOW_S).astype(int)
    for l, s, j in UNITS:
        ago = g[f"pool_{l}_{s}_{j}_ago"].to_numpy(float); ant = g[f"pool_{l}_{s}_{j}_ant"].to_numpy(float)
        sid = SERVO_IDS[(l, s)][JIDX[j]]; col = f"servo_{sid}"
        deg = SIDE_SIGN[s] * (g[col].to_numpy(float) - REST_PULSE[sid]) / G.pulse_per_deg if col in g else np.full(len(g), np.nan)
        wm = pd.DataFrame({"w": w, "ago": ago, "ant": ant}).groupby("w").mean()
        d = ago - ant; d = d - d.mean(); pk = pr = np.nan
        if len(d) > 500:
            from scipy.signal import welch
            f, P = welch(d, fs=1 / STEP_S, nperseg=min(len(d), 2500))
            m = (f >= BAND[0]) & (f <= BAND[1])
            if m.any() and np.nanmedian(P[m]) > 0: pk = float(f[m][np.argmax(P[m])]); pr = float(P[m].max() / np.median(P[m]))
        rows.append({"unit": f"{l}-{s}-{j}", "ago_hz": ago.mean(), "ago_sd": wm.ago.std(ddof=1), "ant_hz": ant.mean(), "ant_sd": wm.ant.std(ddof=1),
                     "active_frac": float(((ago > 0) | (ant > 0)).mean()), "deg_mean": np.nanmean(deg), "deg_sd": np.nanstd(deg), "deg_absmax": np.nanmax(np.abs(deg)),
                     "peak_hz": pk, "peak_ratio": pr, "windows": len(wm), "_wm_ago": wm.ago.to_numpy(), "_wm_ant": wm.ant.to_numpy()})
    return pd.DataFrame(rows)


def perm(a, b, n=20000, seed=0):
    rng = np.random.default_rng(seed); a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2: return np.nan
    obs = abs(a.mean() - b.mean()); pool = np.concatenate([a, b]); c = 0
    for _ in range(n):
        rng.shuffle(pool); c += abs(pool[:len(a)].mean() - pool[len(a):].mean()) >= obs
    return (c + 1) / (n + 1)


def holm(p):
    p = np.asarray(p, float); m = np.isfinite(p).sum(); order = np.argsort(np.where(np.isfinite(p), p, np.inf)); out = np.full_like(p, np.nan)
    running = 0.0
    for rank, i in enumerate(order[:m]):
        running = max(running, (m - rank) * p[i]); out[i] = min(1.0, running)
    return out


def pooled(bl, on):
    """Concatenate window means of all blocks of one arm."""
    ts = [unit_table(g) for o, g in bl if o == on]
    if not ts: return None
    base = ts[0].copy()
    for k in ("_wm_ago", "_wm_ant"): base[k] = [np.concatenate([t[k].iloc[i] for t in ts]) for i in range(len(base))]
    secs = sum(len(g) for o, g in bl if o == on) * STEP_S
    for c in ("ago_hz", "ant_hz", "active_frac", "deg_mean"): base[c] = [np.average([t[c].iloc[i] for t in ts], weights=[len(g) for o, g in bl if o == on]) for i in range(len(base))]
    base["ago_sd"] = [x.std(ddof=1) if len(x) > 1 else np.nan for x in base._wm_ago]; base["ant_sd"] = [x.std(ddof=1) if len(x) > 1 else np.nan for x in base._wm_ant]
    base["deg_absmax"] = [max(t.deg_absmax.iloc[i] for t in ts) for i in range(len(base))]
    base.attrs["secs"] = secs; base.attrs["blocks"] = len(ts)
    return base


def md_table(t, title):
    out = [f"**{title}** — {t.attrs.get('blocks')} block(s), {t.attrs.get('secs', 0):.0f} s of brain time analysed", "",
           "| unit | agonist Hz (SD) | antagonist Hz (SD) | steps active | servo target ° mean (SD, \\|max\\|) | ago−ant peak Hz (ratio) |", "|---|---|---|---|---|---|"]
    for _, r in t.iterrows():
        out.append(f"| {r.unit} | {r.ago_hz:.1f} ({r.ago_sd:.1f}) | {r.ant_hz:.1f} ({r.ant_sd:.1f}) | {r.active_frac*100:.0f} % | {r.deg_mean:+.1f} ({r.deg_sd:.1f}, {r.deg_absmax:.0f}) | "
                   + (f"{r.peak_hz:.2f} ({r.peak_ratio:.1f}) |" if np.isfinite(r.peak_hz) else "— |"))
    return "\n".join(out)


def compare(a, b, la, lb):
    rows = []
    for i in range(len(a)):
        pa = perm(a._wm_ago.iloc[i], b._wm_ago.iloc[i]); pn = perm(a._wm_ant.iloc[i], b._wm_ant.iloc[i])
        rows.append({"unit": a.unit.iloc[i], "ago_a": a.ago_hz.iloc[i], "ago_b": b.ago_hz.iloc[i], "p_ago": pa, "ant_a": a.ant_hz.iloc[i], "ant_b": b.ant_hz.iloc[i], "p_ant": pn})
    c = pd.DataFrame(rows); c["p_ago_holm"] = holm(c.p_ago); c["p_ant_holm"] = holm(c.p_ant)
    out = [f"**{la} vs {lb}** (window means, permutation, Holm over 18 units)", "", f"| unit | agonist {la} / {lb} Hz | p (Holm) | antagonist {la} / {lb} Hz | p (Holm) |", "|---|---|---|---|---|"]
    for _, r in c.iterrows():
        out.append(f"| {r.unit} | {r.ago_a:.1f} / {r.ago_b:.1f} | {r.p_ago:.3f} ({r.p_ago_holm:.3f}) | {r.ant_a:.1f} / {r.ant_b:.1f} | {r.p_ant:.3f} ({r.p_ant_holm:.3f}) |")
    sig = int(((c.p_ago_holm < 0.05) | (c.p_ant_holm < 0.05)).sum())
    out.append(""); out.append(f"units with a Holm-corrected difference (p < 0.05): {sig} of 18")
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("logs"); ap.add_argument("--control"); ap.add_argument("--after"); ap.add_argument("--md")
    a = ap.parse_args()
    df = load(a.logs, a.after); bl = blocks(df)
    print(f"{len(df)} live dry-run steps, {len(bl)} blocks: " + ", ".join(f"{'on' if o else 'off'} {len(g)*STEP_S:.0f}s" for o, g in bl))
    on, off = pooled(bl, True), pooled(bl, False)
    parts = []
    if on is not None: parts.append(md_table(on, "original graph, proprioceptive feedback ON"))
    if off is not None: parts.append(md_table(off, "original graph, proprioceptive feedback OFF"))
    if on is not None and off is not None: parts.append(compare(on, off, "on", "off"))
    if on is not None:
        met = bool(((on.ago_hz > 5) | (on.ant_hz > 5)).any())
        parts.append(f"**P2-a (motor output exists, feedback on, original graph): {'MET' if met else 'NOT MET'}** — "
                     f"{int(((on.ago_hz > 5) | (on.ant_hz > 5)).sum())} of 18 units have a pool above 5 Hz; "
                     f"largest: {on.loc[(on[['ago_hz','ant_hz']].max(axis=1)).idxmax()].unit} {on[['ago_hz','ant_hz']].max(axis=1).max():.0f} Hz")
    if a.control:
        cdf = load(a.control, a.after); cbl = blocks(cdf); con, coff = pooled(cbl, True), pooled(cbl, False)
        if con is not None: parts.append(md_table(con, "control graph, feedback ON"))
        if coff is not None: parts.append(md_table(coff, "control graph, feedback OFF"))
        if on is not None and con is not None: parts.append(compare(on, con, "original", "control"))
    text = "\n\n".join(parts); print("\n" + text)
    if a.md: open(a.md, "w").write(text + "\n"); print(f"\n→ {a.md}")
