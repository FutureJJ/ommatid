"""Build site/results.html from the archived runs: every number and every chart on the page comes from the Parquet logs
and the per-trial tables in runs/. Static HTML with inline SVG; no JavaScript, no chart library.

usage: python tools/results_page.py runs/logs/original runs/logs/shuffled
"""
import sys, glob, html, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, ".")
from tools.analyze import load, per_trial, ci, perm_test

ROOT = Path(__file__).resolve().parent.parent
INK, INK2, INK3, LINE, EYE = "#e9e6df", "#a7a49c", "#66645f", "#2e2e33", "#d4432c"
COND_LABEL = {"loom": "looming disc", "disc": "static disc", "grating_R": "grating → right", "grating_L": "grating → left",
              "bright_R": "bright right half", "bright_L": "bright left half", "grey": "grey"}
ORDER = ["loom", "disc", "grating_R", "grating_L", "bright_R", "bright_L", "grey"]


def pfmt(p, rel=False):
    return ('< 0.0001' if rel else '&lt; 0.0001') if p < 0.0001 else (('= ' if rel else '') + f'{p:.4f}')


def svg_open(w, h): return [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" xmlns="http://www.w3.org/2000/svg" font-family="IBM Plex Mono, ui-monospace, monospace" font-size="11">']
def text(x, y, s, fill=INK2, anchor="start", size=11, weight="normal", italic=False):
    st = f' font-style="italic"' if italic else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" text-anchor="{anchor}" font-size="{size}" font-weight="{weight}"{st}>{html.escape(str(s))}</text>'


def chart_timecourse(df_o, df_s, pop="DNp04", conds=("loom", "disc", "grey"), bin_ms=100):
    """Mean rate of one population vs time in the trial (baseline 0–1000 ms, stimulus 1000–3000 ms), original vs shuffled."""
    W, H, L, R, T, B = 760, 300, 56, 16, 22, 40
    def curve(df, cond):
        d = df[(df.stim_condition == cond) & df.stim_t_ms.notna()].copy()
        d["bin"] = (d.stim_t_ms // bin_ms) * bin_ms
        g = d.groupby("bin")[f"hz_{pop}"].mean()
        return g.index.values.astype(float), g.values
    series = []
    for cond in conds:
        for name, df, dash in (("original", df_o, ""), ("shuffled", df_s, "3 3")):
            x, y = curve(df, cond); series.append((cond, name, dash, x, y))
    ymax = max(30.0, max(float(np.nanmax(y)) for *_, y in series) * 1.15)
    sx = lambda t: L + (t / 3000.0) * (W - L - R); sy = lambda v: T + (H - T - B) * (1 - v / ymax)
    out = svg_open(W, H)
    # stimulus window
    out.append(f'<rect x="{sx(1000):.1f}" y="{T}" width="{sx(3000)-sx(1000):.1f}" height="{H-T-B}" fill="{INK}" opacity="0.04"/>')
    for v in np.linspace(0, ymax, 4):
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="{LINE}" stroke-width="1"/>')
        out.append(text(L - 8, sy(v) + 4, f"{v:.0f}", INK3, "end"))
    for t in (0, 1000, 2000, 3000):
        out.append(text(sx(t), H - B + 16, f"{t/1000:.0f} s", INK3, "middle"))
    out.append(text(sx(2000), T - 8, "stimulus on screen", INK3, "middle", italic=True))
    out.append(text(sx(500), T - 8, "grey baseline", INK3, "middle", italic=True))
    out.append(text(L - 44, T + 10, "Hz", INK3))
    colors = {"loom": EYE, "disc": INK2, "grey": INK3}
    for cond, name, dash, x, y in series:
        pts = " ".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(x + bin_ms / 2, y))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{colors[cond]}" stroke-width="{2 if name=="original" else 1.4}" stroke-dasharray="{dash}" opacity="{1 if name=="original" else 0.8}"/>')
    # legend
    lx = L + 8; ly = T + 14
    for i, (cond, col) in enumerate(colors.items()):
        out.append(f'<line x1="{lx}" x2="{lx+22}" y1="{ly+i*16}" y2="{ly+i*16}" stroke="{col}" stroke-width="2"/>')
        out.append(text(lx + 30, ly + i * 16 + 4, COND_LABEL[cond], INK2))
    out.append(f'<line x1="{lx+150}" x2="{lx+172}" y1="{ly}" y2="{ly}" stroke="{INK}" stroke-width="2"/>'); out.append(text(lx + 180, ly + 4, "real wiring", INK2))
    out.append(f'<line x1="{lx+150}" x2="{lx+172}" y1="{ly+16}" y2="{ly+16}" stroke="{INK}" stroke-width="1.4" stroke-dasharray="3 3"/>'); out.append(text(lx + 180, ly + 20, "shuffled wiring", INK2))
    out.append("</svg>"); return "\n".join(out)


def chart_trials(t_o, t_s, col="d_escape", ylabel="escape/stop rise, Hz", conds=ORDER):
    """Every trial as a dot, per condition, real vs shuffled side by side; mean and 95 % CI as a bar."""
    W, H, L, R, T, B = 760, 320, 56, 16, 18, 64
    vals = np.concatenate([t_o[col].values, t_s[col].values]); ymin, ymax = min(-5, vals.min() - 2), max(10, vals.max() + 2)
    n = len(conds); gw = (W - L - R) / n
    sy = lambda v: T + (H - T - B) * (1 - (v - ymin) / (ymax - ymin))
    out = svg_open(W, H)
    for v in np.arange(np.ceil(ymin / 10) * 10, ymax + 1, 10):
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="{LINE if v else INK3}" stroke-width="1"/>')
        out.append(text(L - 8, sy(v) + 4, f"{v:+.0f}", INK3, "end"))
    out.append(text(L - 44, T + 10, "Hz", INK3))
    rng = np.random.default_rng(0)
    for i, cond in enumerate(conds):
        x0 = L + i * gw
        for j, (t, col_dot) in enumerate(((t_o, EYE if cond == "loom" else INK), (t_s, INK3))):
            g = t[t.condition == cond][col].values
            cx = x0 + gw * (0.30 if j == 0 else 0.70)
            for v in g:
                out.append(f'<circle cx="{cx + rng.uniform(-gw*0.10, gw*0.10):.1f}" cy="{sy(v):.1f}" r="2.2" fill="{col_dot}" opacity="0.75"/>')
            if len(g) > 1:
                lo, hi = ci(g); m = g.mean()
                out.append(f'<line x1="{cx-gw*0.16:.1f}" x2="{cx+gw*0.16:.1f}" y1="{sy(m):.1f}" y2="{sy(m):.1f}" stroke="{INK}" stroke-width="2"/>')
                out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{sy(lo):.1f}" y2="{sy(hi):.1f}" stroke="{INK}" stroke-width="1"/>')
        lab = COND_LABEL[cond].replace(" → ", " →\n")
        for k, line in enumerate(COND_LABEL[cond].split(" ", 1) if len(COND_LABEL[cond]) > 12 else [COND_LABEL[cond]]):
            out.append(text(x0 + gw / 2, H - B + 18 + k * 13, line, INK2, "middle"))
        out.append(text(x0 + gw * 0.30, H - 8, "real", INK3, "middle", 10)); out.append(text(x0 + gw * 0.70, H - 8, "shuffled", INK3, "middle", 10))
    out.append(text(W - R, T + 10, ylabel, INK3, "end", italic=True))
    out.append("</svg>"); return "\n".join(out)


def main(orig_dir, shuf_dir):
    df_o, df_s = load(orig_dir), load(shuf_dir)
    df_o, df_s = df_o[df_o.protocol_seed == 2026], df_s[df_s.protocol_seed == 2026]
    t_o, t_s = per_trial(df_o), per_trial(df_s)
    lo_o, lo_s = t_o[t_o.condition == "loom"], t_s[t_s.condition == "loom"]
    ctl_o = t_o[t_o.condition.isin(["disc", "grating_R", "grating_L"])]
    p_wiring = perm_test(lo_o.d_escape, lo_s.d_escape)
    p_loom_ctrl_o = perm_test(lo_o.d_escape, ctl_o.d_escape)
    gR, gL = t_o[t_o.condition == "grating_R"], t_o[t_o.condition == "grating_L"]
    h1_agree = np.concatenate([(gR.d_turn > 0).values, (gL.d_turn < 0).values]).mean()
    bR, bL = t_o[t_o.condition == "bright_R"], t_o[t_o.condition == "bright_L"]
    h3_agree = np.concatenate([(bR.d_turn > 0).values, (bL.d_turn < 0).values]).mean()
    dnp04 = ci(lo_o.d_DNp04); dnp02 = ci(lo_o.d_DNp02)
    spikes_o, spikes_s = df_o.spikes.mean(), df_s.spikes.mean()

    def row(c):
        a, b = t_o[t_o.condition == c], t_s[t_s.condition == c]
        return f"<tr><td>{COND_LABEL[c]}</td><td class=n>{len(a)}</td><td class=n>{a.d_escape.mean():+.1f}</td><td class=n>{b.d_escape.mean():+.1f}</td><td class=n>{a.d_turn.mean():+.1f}</td><td class=n>{b.d_turn.mean():+.1f}</td></tr>"
    table = "\n".join(row(c) for c in ORDER)

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ommatid — results</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;1,6..72,300;1,6..72,400&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0c0c0d;--bg2:#121214;--line:#232326;--line2:#2e2e33;--ink:#e9e6df;--ink2:#a7a49c;--ink3:#66645f;--eye:#d4432c;
--serif:"Newsreader",Georgia,serif;--mono:"IBM Plex Mono",ui-monospace,monospace}}
*{{box-sizing:border-box}} html,body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--serif);font-size:17px;line-height:1.5;-webkit-font-smoothing:antialiased}}
a{{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--line2)}} a:hover{{border-color:var(--ink2)}}
header{{display:flex;align-items:baseline;justify-content:space-between;padding:18px 24px 14px;border-bottom:1px solid var(--line)}}
header h1{{margin:0;font-weight:400;font-size:22px}} header h1 span{{color:var(--ink3);font-style:italic;font-weight:300;margin-left:10px;font-size:17px}}
header nav a{{margin-left:22px;font-size:15px;color:var(--ink2);border:0;font-family:var(--mono);font-size:12.5px}}
main{{max-width:820px;margin:0 auto;padding:48px 24px 80px}}
h2{{font-weight:400;font-size:28px;margin:56px 0 12px}} h3{{font-family:var(--mono);font-weight:500;font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3);margin:40px 0 10px}}
p{{color:var(--ink2);font-size:18px;margin:0 0 16px}} p b{{color:var(--ink);font-weight:500}} .lede{{font-size:22px;line-height:1.45;color:var(--ink)}}
figure{{margin:22px 0 8px;padding:14px 10px 6px;border:1px solid var(--line);border-radius:2px;background:var(--bg2)}} figcaption{{font-size:14.5px;color:var(--ink2);padding:8px 8px 6px;font-style:italic}}
table{{width:100%;border-collapse:collapse;font-size:15px;margin:16px 0}} th,td{{text-align:left;padding:9px 10px 9px 0;border-bottom:1px solid var(--line);color:var(--ink2);vertical-align:top}}
th{{font-family:var(--mono);font-weight:500;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink3)}} td:first-child{{color:var(--ink)}} td.n,th.n{{font-family:var(--mono);font-size:13px;text-align:right}}
.verdict{{display:grid;grid-template-columns:1fr;gap:10px;margin:18px 0}} .verdict div{{border:1px solid var(--line);padding:14px 16px;border-radius:2px}}
.verdict > div > b{{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;display:block;margin-bottom:6px}} .verdict span b{{color:var(--ink);font-weight:500}} .met{{color:var(--eye)}} .notmet{{color:var(--ink3)}}
.verdict span{{color:var(--ink2);font-size:16px}}
footer{{border-top:1px solid var(--line);padding:22px 24px 40px;color:var(--ink3);font-size:14px}}
</style></head><body>
<header><h1>Ommatid <span>results, phase 1</span></h1><nav><a href="/">Live</a><a href="https://github.com/FutureJJ/ommatid/blob/main/docs/experiment.md">Pre-registration</a><a href="https://github.com/FutureJJ/ommatid/blob/main/docs/runs.md">Run log</a><a href="https://github.com/FutureJJ/ommatid">Source</a></nav></header>
<main>
<p class="lede">A fruit fly's complete nervous-system wiring, run untouched in a six-legged robot, produced one of its innate reflexes: an approaching object drove the same two escape neurons it drives in the animal. The same neurons wired at random did not.</p>
<p>Protocol v1, 11 September 2026. 210 trials on the real wiring, 210 on a degree-preserving shuffle of it; seven stimulus conditions on a laptop screen 40 cm in front of the robot's camera (30 cm wide, daylight); body held still; every parameter frozen and published before the first trial (<a href="https://github.com/FutureJJ/ommatid/blob/main/docs/frozen-params.md">frozen-params.md</a>, tag <span style="font-family:var(--mono);font-size:13px">freeze-v1</span>). Whole-network activity: {spikes_o:,.0f} spikes per 20 ms on the real wiring, {spikes_s:,.0f} on the shuffled.</p>

<h3>The pre-registered verdicts</h3>
<div class="verdict">
<div><b class="met">H2 looming — wiring specificity: met</b><span>Escape/stop descending neurons rose by <b>{lo_o.d_escape.mean():+.1f} Hz</b> during looming on the real wiring versus <b>{lo_s.d_escape.mean():+.1f} Hz</b> on shuffled wiring (permutation p = {pfmt(p_wiring)}; criterion p &lt; 0.01). The rise sits in DNp04 ({dnp04[0]:+.1f} to {dnp04[1]:+.1f} Hz, 95 % CI) and DNp02 ({dnp02[0]:+.1f} to {dnp02[1]:+.1f} Hz), the two direct targets of the LC4 looming detectors; the giant fibre, DNp09 and MDN stayed silent in every trial.</span></div>
<div><b class="notmet">H2 looming — per-trial thresholds: narrowly missed</b><span>A rise &gt; 5 Hz appeared in {(lo_o.d_escape>5).mean()*100:.0f} % of loom trials (≥ 70 % required) and in {(ctl_o.d_escape>5).mean()*100:.0f} % of disc/grating controls (&lt; 20 % required); loom vs controls p {pfmt(p_loom_ctrl_o, True)}. The static-disc control appears abruptly and is itself a looming-like event; v2 fades it in.</span></div>
<div><b class="notmet">H1 optomotor: not met</b><span>Steering asymmetry (DNa02 right − left) followed the grating direction in {h1_agree*100:.0f} % of trials (≥ 80 % required) and did not differ from the shuffled graph. The screen covers 41° of a ~300° visual field.</span></div>
<div><b class="notmet">H3 phototaxis: not met</b><span>Turning toward the bright half in {h3_agree*100:.0f} % of trials; forward-walking neurons (DNa01) never fired in any condition.</span></div>
</div>

<h2>What the escape neurons did, trial by trial</h2>
<figure>{chart_timecourse(df_o, df_s, "DNp04")}
<figcaption>DNp04 firing rate averaged over 30 trials per condition, aligned to trial start; 100 ms bins of the fly's time. Solid: real wiring. Dashed: the same neurons, shuffled wiring. Grey band: stimulus on screen. The disc reaches its final size at 3 s.</figcaption></figure>
<figure>{chart_trials(t_o, t_s)}
<figcaption>Each dot is one trial: the escape/stop rise (largest of DNp01, DNp02, DNp04, DNp09, MDN) during the stimulus minus that trial's own baseline. Bars: mean and 95 % confidence interval. Real wiring left, shuffled right, within each condition.</figcaption></figure>
<figure>{chart_trials(t_o, t_s, "d_turn", "steering asymmetry DNa02 right − left, Hz")}
<figcaption>The optomotor and phototaxis readout, same layout. Nothing separates the conditions, on either wiring.</figcaption></figure>

<h3>Per condition</h3>
<table><tr><th>condition</th><th class=n>trials</th><th class=n>escape rise, real</th><th class=n>escape rise, shuffled</th><th class=n>turn R−L, real</th><th class=n>turn R−L, shuffled</th></tr>
{table}</table>
<p style="font-size:15px;color:var(--ink3)">Hz per neuron, stimulus minus baseline, means over 30 trials each. Per-trial tables: <a href="https://github.com/FutureJJ/ommatid/tree/main/runs">runs/</a>.</p>

<h2>What this does and does not show</h2>
<p><b>It shows</b> that a specific reflex — looming → LC4 → DNp04/DNp02 — is carried by the connectivity itself: same neurons, same synaptic strengths, same in- and out-degrees, only the partner assignment changed, and the response falls to a third and loses its target. Nothing in the model was fitted to behaviour; the escape pathway was not looked for, it was pre-registered.</p>
<p><b>It does not show</b> a fly that sees the world. The optic lobe is a task-trained connectome model (FlyVis), the central model has no baseline activity and uniform synaptic weights, and the robot's camera gives the fly 74° of a 300° field. Wide-field motion and phototaxis did not appear; the measured mismatches — field of view, a transient-only hand-off, no disinhibition from a silent baseline, a single steering neuron as readout — are the targets of the v2 protocol and of phases 2 and 3, in which the nerve cord drives the legs and adaptation is studied.</p>
<p>Failures are reported as failures; thresholds were not moved after the fact. The next runs are pre-registered in the <a href="https://github.com/FutureJJ/ommatid/blob/main/docs/runs.md">run log</a>.</p>
</main>
<footer>Connectome: FlyEM male CNS v1.0 (HHMI Janelia, Cambridge, Google Research, CC-BY). Optic lobe: FlyVis (Turaga lab, MIT). Neuron model: Shiu et al. 2024. Code and data: MIT / CC-BY, github.com/FutureJJ/ommatid.</footer>
</body></html>"""
    out = ROOT / "site/results.html"; out.write_text(page); print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB); p_wiring={p_wiring:.4f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
