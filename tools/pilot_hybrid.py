"""Hybrid pilot: camera frame → FlyVis optic lobe → forced spikes in the male CNS at the same type/column → LIF →
lobula plate / looming detectors / descending neurons. Development smoke test, disclosed as such."""
import sys, time, numpy as np
sys.path.insert(0, ".")
from ommatid.brain.lif import Brain
from ommatid.brain.eye import Eye
from ommatid.brain.optic_lobe import OpticLobe, ColumnMap
from ommatid.brain.readout import Readout
from tools.pilot_optomotor import grating, loom, H, W, STEPS

STAGES = [("T4/T5 (male CNS, forced)", ["T4a", "T4b", "T5a", "T5b"]),
          ("lobula plate", ["HSN", "HSE", "HSS", "H2", "DCH", "VCH", "LPi12"]),
          ("loom detectors", ["LC4", "LC6", "LPLC2", "LPLC1", "LC11"]),
          ("escape DNs", ["DNp01", "DNp02", "DNp04", "DNp11", "DNp09"]),
          ("walking DNs", ["DNa02", "DNa01", "MDN", "DNb05"])]

def main():
    t0 = time.time()
    brain = Brain("build/graph.npz"); eye = Eye(brain); ol = OpticLobe(); ro = Readout(brain)
    cmap = ColumnMap(ol, brain, eye.column_angles_all)
    print(f"setup {time.time()-t0:.0f}s | FlyVis output types {len(ol.output_types)} | mapped male neurons {cmap.n_mapped:,} ({cmap.n_inferred:,} with anatomically inferred columns)")
    for k, (pos, male) in sorted(cmap.pairs.items()): print(f"   {k[0]:6s} {k[1]} {len(male):4d}", end="")
    print()
    blank = np.full((H, W), 0.5, np.float32)

    def block(name, frames):
        counts = np.zeros(brain.n); secs = 0; tot = []; tl = []; sides = {"DNa02_L": [], "DNa02_R": []}
        for f in frames:
            t = time.perf_counter(); act = ol.see(f); t_fv = time.perf_counter() - t
            d = cmap.drive(ol.rates(act))
            t = time.perf_counter(); r = brain.run(d, STEPS); t_lif = time.perf_counter() - t
            counts += r["counts"]; secs += r["secs"]; tot.append(r["total"]); tl.append((t_fv, t_lif))
            hz = ro.rates(r["counts"], r["secs"]); sides["DNa02_L"].append(hz["DNa02_L"]); sides["DNa02_R"].append(hz["DNa02_R"])
        tf, tli = np.mean(tl, 0)
        print(f"\n== {name}: {len(frames)} steps, {np.mean(tot):.0f} spikes/step, flyvis {tf*1000:.0f} ms + lif {tli*1000:.0f} ms per step")
        for stage, types in STAGES:
            parts = []
            for t in types:
                sel = brain.where(type=t)
                if len(sel) == 0: continue
                parts.append(f"{t} {counts[sel].sum()/len(sel)/secs:.0f}Hz/{(counts[sel]>0).mean()*100:.0f}%")
            print(f"  {stage:26s} " + "  ".join(parts))
        h = len(frames) // 2
        print(f"  DNa02 second half: L {np.mean(sides['DNa02_L'][h:]):.1f} Hz  R {np.mean(sides['DNa02_R'][h:]):.1f} Hz")

    block("uniform grey", [blank] * 20)
    block("grating → R (rightward on camera)", [grating(i * 3.0) for i in range(30)])
    block("uniform grey", [blank] * 15)
    block("grating → L", [grating(-i * 3.0) for i in range(30)])
    block("uniform grey", [blank] * 15)
    block("loom (dark disc expanding)", [loom(min(0.05 + 0.03 * i, 1.0)) for i in range(30)])
    block("uniform grey", [blank] * 15)
    print(f"\nwall {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
