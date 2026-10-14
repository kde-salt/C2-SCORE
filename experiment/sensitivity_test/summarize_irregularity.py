"""Summarize instance-irregularity result CSVs as markdown tables.

    python -m experiment.sensitivity_test.summarize_irregularity \
        experiment/sensitivity_test/results/instance_irregularity_*.csv

Trials are averaged per (condition, k); the baseline row is printed as-is and
every other row is also shown as a delta against it, which is the form the
A1 vs A2 comparison is read in.
"""

import argparse
import csv
import glob
import statistics
from typing import Dict, List, Sequence, Tuple

SCORE_COLS = ["Cov_V", "Cov_E", "Con_V", "Con_E", "c2"]
SHAPE_COLS = ["n_label_sets", "n_node_types", "n_edge_patterns"]

LABELS = {
    "A1_same_spurious_label": "A1 same spurious label",
    "A2_unique_spurious_labels": "A2 unique spurious labels",
    "B_missing_label": "B1 same missing label",
    "B2_random_missing_label": "B2 random missing label",
    "C_add_spurious_property": "C1-add same spurious property",
    "C_add2_unique_spurious_properties": "C2-add unique spurious properties",
    "C_del_missing_property": "C1-del same missing property",
    "C_del2_random_missing_property": "C2-del random missing property",
}
ORDER = ["A1_same_spurious_label", "A2_unique_spurious_labels",
         "B_missing_label", "B2_random_missing_label",
         "C_add_spurious_property", "C_add2_unique_spurious_properties",
         "C_del_missing_property", "C_del2_random_missing_property"]


def load(paths: Sequence[str]) -> List[dict]:
    rows: List[dict] = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            with open(path) as f:
                rows.extend(csv.DictReader(f))
    if not rows:
        raise SystemExit("no rows found")
    return rows


def group(rows: Sequence[dict]) -> Tuple[dict, Dict[Tuple[str, int], List[dict]]]:
    baseline = None
    groups: Dict[Tuple[str, int], List[dict]] = {}
    for r in rows:
        if r["condition"] == "baseline":
            baseline = r
            continue
        groups.setdefault((r["condition"], int(r["k"])), []).append(r)
    if baseline is None:
        raise SystemExit("no baseline row in the input")
    return baseline, groups


def mean(rows: Sequence[dict], col: str) -> float:
    return statistics.fmean(float(r[col]) for r in rows)


def spread(rows: Sequence[dict], col: str) -> float:
    values = [float(r[col]) for r in rows]
    return max(values) - min(values)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--digits", type=int, default=6)
    args = ap.parse_args(argv)

    rows = load(args.csv)
    baseline, groups = group(rows)
    d = args.digits

    print(f"instance: {baseline['instance_db']}  schema: {baseline['schema_db']}"
          f"  trials: {max(int(r['trial']) for r in rows) + 1}\n")

    print("## Shape of Abs(G')")
    print("| condition | k | distinct label sets | \\|V(S_G)\\| | \\|E(S_G)\\| |")
    print("| --- | ---: | ---: | ---: | ---: |")
    print(f"| baseline | – | {baseline['n_label_sets']} | "
          f"{baseline['n_node_types']} | {baseline['n_edge_patterns']} |")
    for cond in ORDER:
        for k in sorted({k for c, k in groups if c == cond}):
            g = groups[(cond, k)]
            print(f"| {LABELS.get(cond, cond)} | {k} | "
                  f"{mean(g, 'n_label_sets'):.1f} | "
                  f"{mean(g, 'n_node_types'):.1f} | "
                  f"{mean(g, 'n_edge_patterns'):.1f} |")

    print("\n## Scores (mean over trials)")
    header = " | ".join(SCORE_COLS)
    print(f"| condition | k | {header} |")
    print("| --- | ---: |" + " ---: |" * len(SCORE_COLS))
    print(f"| baseline | – | " +
          " | ".join(f"{float(baseline[c]):.{d}f}" for c in SCORE_COLS) + " |")
    for cond in ORDER:
        for k in sorted({k for c, k in groups if c == cond}):
            g = groups[(cond, k)]
            print(f"| {LABELS.get(cond, cond)} | {k} | " +
                  " | ".join(f"{mean(g, c):.{d}f}" for c in SCORE_COLS) + " |")

    print("\n## Delta vs baseline (mean over trials; negative = degraded)")
    print(f"| condition | k | {header} | C2 range across trials |")
    print("| --- | ---: |" + " ---: |" * (len(SCORE_COLS) + 1))
    for cond in ORDER:
        for k in sorted({k for c, k in groups if c == cond}):
            g = groups[(cond, k)]
            deltas = " | ".join(
                f"{mean(g, c) - float(baseline[c]):+.{d}f}" for c in SCORE_COLS)
            print(f"| {LABELS.get(cond, cond)} | {k} | {deltas} | "
                  f"{spread(g, 'c2'):.{d}f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
