"""Cross-pair C2 evaluation for the normalization experiment (Table 4).

Computes sparse C2 for an arbitrary (instance DB, schema DB) pair and
appends the components to results/crosspair_c2.csv. Use this when the
schema DB name does not follow the `<instance>-<method>` convention
expected by eval_c2.py. Weights match EQ2.

    python -m experiment.normalization_test.eval_crosspair --instance dbpedia --schema dbpedia-2gnf-schemi
"""
import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from ..common import utils_sparse

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH
ALPHA, BETA, GAMMA = 0.5, 0.5, 0.15
EVAL_KW = dict(label_w=ALPHA, mandatory_w=(1 - ALPHA) / 2,
               optional_w=(1 - ALPHA) / 2, endpoint_w=BETA, gamma=GAMMA)

RESULTS_CSV = Path("experiment/normalization_test/results/crosspair_c2.csv")
HEADER = ["timestamp", "instance_db", "schema_db",
          "Cov_V", "Cov_E", "Con_V", "Con_E", "node_c2", "edge_c2", "c2",
          "wall_sec", "abs_time", "flatten_time", "score_time", "other_time"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--schema", required=True)
    args = ap.parse_args()

    t0 = time.time()
    (cov_v, cov_e, con_v, con_e, node_c2, edge_c2,
     abs_t, flat_t, score_t, other_t) = utils_sparse.eval_c2_sparse(
        URI, AUTH, args.instance, args.schema, **EVAL_KW)
    wall = time.time() - t0
    c2 = (node_c2 + edge_c2) / 2

    print(f"=== {args.instance} x {args.schema}")
    print(f"  Cov_V={cov_v:.7f} Cov_E={cov_e:.7f} "
          f"Con_V={con_v:.7f} Con_E={con_e:.7f}")
    print(f"  node_c2={node_c2:.7f} edge_c2={edge_c2:.7f} C2={c2:.7f} "
          f"({wall:.0f}s: abs={abs_t:.0f} flatten={flat_t:.0f} "
          f"score={score_t:.0f} other={other_t:.0f})")

    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new_file = not RESULTS_CSV.exists()
    with RESULTS_CSV.open("a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(HEADER)
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    args.instance, args.schema,
                    repr(cov_v), repr(cov_e), repr(con_v), repr(con_e),
                    repr(node_c2), repr(edge_c2), repr(c2),
                    round(wall, 1), round(abs_t, 1), round(flat_t, 1),
                    round(score_t, 1), round(other_t, 1)])
    print(f"Wrote {RESULTS_CSV}")


if __name__ == "__main__":
    main()
