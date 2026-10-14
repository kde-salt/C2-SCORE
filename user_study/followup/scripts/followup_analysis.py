"""Follow-up user study: Borda consensus vs. C2-score ranking.

Published to document the analysis, not to be re-run: the participant
responses are withheld to protect personal information, and the per-scenario
C2 answer key below is blank, so this script has no input to work on.

    python followup_analysis.py <answers.tsv> <ranks.csv>

Reads the raw form export, writes the anonymised ranks, and prints the Borda
consensus, the C2 ranking, Kendall's tau and the top-1 agreement per scenario.
The C2 ranking can contain ties, so tau is reported as tau-b (ties handled by
scipy) plus the min/max over all tie-break orders.
"""
import itertools
import re
import sys
from pathlib import Path

import pandas as pd
from scipy.stats import kendalltau, rankdata

ITEMS = ["A", "B", "C", "D"]
SCENARIOS = ["Q5-1", "Q5-2", "Q5-3"]

# C2 score of each candidate schema per scenario — the answer key the
# participants' consensus is compared against. Withheld along with the
# responses; fill it in to run the analysis on your own data.
C2 = {q: {i: None for i in ITEMS} for q in SCENARIOS}
RANK_COL = re.compile(r"^(Q5-\d).*\[(\d)位")


def load_ranks(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, sep="\t", dtype=str)
    raw = raw.sort_values(raw.columns[0]).reset_index(drop=True)
    cols = {}
    for c in raw.columns:
        m = RANK_COL.match(c)
        if m:
            cols[(m.group(1), int(m.group(2)))] = c
    rows = []
    for i, r in raw.iterrows():
        row = {"name": f"P{i + 1}"}
        for q in C2:
            order = [r[cols[(q, k)]].strip() for k in range(1, 5)]
            if sorted(order) != ITEMS:
                sys.exit(f"{row['name']} {q}: not a permutation of A-D: {order}")
            for k, item in enumerate(order, start=1):
                row[f"{q}-{item}"] = k
        rows.append(row)
    return pd.DataFrame(rows)


def c2_ranks(q: str):
    scores = [C2[q][i] for i in ITEMS]
    return list(rankdata([-s for s in scores], method="average"))


def tie_break_orders(q: str):
    """All strict rankings consistent with the (tied) C2 ordering."""
    groups = {}
    for i in ITEMS:
        groups.setdefault(C2[q][i], []).append(i)
    levels = sorted(groups, reverse=True)
    for perm in itertools.product(*[itertools.permutations(groups[s]) for s in levels]):
        order = [i for g in perm for i in g]
        yield order


def main(raw_path: Path, out_path: Path):
    df = load_ranks(raw_path)
    df.to_csv(out_path, index=False)
    n = len(df)
    print(f"participants: {n}  -> {out_path}\n")

    summary = []
    for q in C2:
        pts = {i: int((4 - df[f"{q}-{i}"]).sum()) for i in ITEMS}
        borda_rank = list(rankdata([-pts[i] for i in ITEMS], method="average"))
        borda_order = sorted(ITEMS, key=lambda i: -pts[i])
        c2_rank = c2_ranks(q)
        c2_order = sorted(ITEMS, key=lambda i: -C2[q][i])

        tau_b, _ = kendalltau(borda_rank, c2_rank)
        taus = []
        for order in tie_break_orders(q):
            strict = [order.index(i) + 1 for i in ITEMS]
            taus.append(kendalltau(borda_rank, strict)[0])

        c2_top = [i for i in ITEMS if C2[q][i] == max(C2[q].values())]
        borda_top = [i for i in ITEMS if pts[i] == max(pts.values())]
        top1 = any(b in c2_top for b in borda_top)

        per_p = [kendalltau([df.loc[k, f"{q}-{i}"] for i in ITEMS], c2_rank)[0]
                 for k in range(n)]

        print(f"== {q} ==")
        print("Borda points:", {i: pts[i] for i in borda_order})
        print("Borda consensus:", " > ".join(borda_order))
        print("C2 ranking     :", " > ".join(f"{i}({C2[q][i]:.4f})" for i in c2_order))
        print(f"tau-b = {tau_b:.4f}   tie-break range = [{min(taus):.4f}, {max(taus):.4f}]")
        print(f"top-1: Borda {borda_top} vs C2 {c2_top} -> {'agree' if top1 else 'DISAGREE'}")
        print("per-participant tau-b vs C2:", [f"{t:.2f}" for t in per_p],
              f"mean={sum(per_p) / n:.4f}")
        print("rank distribution (rows=candidate, cols=1st..4th):")
        for i in ITEMS:
            counts = [int((df[f"{q}-{i}"] == k).sum()) for k in range(1, 5)]
            print(f"  {i}: {counts}")
        print()
        summary.append((q, " > ".join(borda_order), " > ".join(c2_order),
                        tau_b, min(taus), max(taus), top1))

    print("| scenario | Borda consensus | C2 ranking | tau-b | tie-break range | top-1 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for q, b, c, t, lo, hi, top1 in summary:
        print(f"| {q} | {b} | {c} | {t:.3f} | [{lo:.3f}, {hi:.3f}] | {'Yes' if top1 else 'No'} |")


if __name__ == "__main__":
    if any(v is None for q in C2 for v in C2[q].values()):
        sys.exit(
            "The per-scenario C2 answer key (C2 above) is blank, so there is "
            "nothing to compare the participants' consensus against. Fill it in "
            "to run this analysis on your own data."
        )
    main(Path(sys.argv[1]), Path(sys.argv[2]))
