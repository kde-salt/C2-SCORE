"""C2 evaluation (Cov / Con / C2 saved separately) per method x dataset
for the complex real-world PGs experiment (Table 3), including the
runtime breakdown returned by eval_c2. Weights match EQ2.

Usage (from the repository root):
    python -m experiment.complex_pgs_test.eval_c2 --instance dblp
    python -m experiment.complex_pgs_test.eval_c2 --instance dblp --methods lei schemi
"""

import argparse
import csv
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

from ..common import utils
from ..common import utils_sparse
from ..common.entity_def import NodeType, EdgeType

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH

# EQ2 evaluation weights (experiment/diagnostic_usefulness_test/main.py:75-77)
ALPHA, BETA, GAMMA = 0.5, 0.5, 0.15
EVAL_KW = dict(label_w=ALPHA, mandatory_w=(1 - ALPHA) / 2,
               optional_w=(1 - ALPHA) / 2, endpoint_w=BETA, gamma=GAMMA)

METHODS = ["lei", "schemi", "gmmschema", "pg-hive"]

RESULTS_DIR = Path("experiment/complex_pgs_test/results")
SCHEMAS_DIR = RESULTS_DIR / "schemas"
OUT_CSV = RESULTS_DIR / "c2_scores.csv"

CSV_HEADER = [
    "timestamp", "instance_db", "method", "schema_db",
    "n_node_types", "n_edge_types", "n_extends",
    "Cov_V", "Cov_E", "Con_V", "Con_E", "node_c2", "edge_c2", "c2",
    "wall_sec", "abs_time", "flatten_time", "score_time", "other_time",
]


def schema_to_json(node_types: list[NodeType], edge_types: list[EdgeType]) -> dict:
    """Snapshot of the extracted schema."""
    return {
        "nodes": [
            {"node_id": n.node_id, "labels": sorted(n.labels),
             "mandatory": sorted(n.mandatory_props),
             "optional": sorted(n.optional_props)}
            for n in node_types
        ],
        "edges": [
            {"edge_id": e.edge_id, "label": e.label,
             "mandatory": sorted(e.mandatory_props),
             "optional": sorted(e.optional_props),
             "src": e.src_node_type.node_id, "dst": e.dst_node_type.node_id}
            for e in edge_types
        ],
    }


def main(instance_db: str, methods: list[str], sparse: bool = True):
    eval_fn = utils_sparse.eval_c2_sparse if sparse else utils.eval_c2
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not OUT_CSV.exists()
    failures = []

    with open(OUT_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(CSV_HEADER)
        for method in methods:
            schema_db = f"{instance_db}-{method}"
            print(f"=== {instance_db} x {method} ({schema_db})", flush=True)
            try:
                node_types, edge_types = \
                    utils.get_all_node_and_edge_types_from_schema(
                        schema_db, URI, AUTH)
                # The runner creates <db>-<method> up front for lei/gmmschema
                # (they only write into it at the very end), so a failed
                # extraction leaves an empty database behind.  Scoring it would
                # emit a row that looks like a measured C2 of 0.
                if not node_types:
                    failures.append(f"{schema_db} (empty: no schema extracted)")
                    print(f"  empty schema database — extraction did not "
                          f"produce one; not scored", flush=True)
                    continue
                (SCHEMAS_DIR / f"{schema_db}.json").write_text(
                    json.dumps(schema_to_json(node_types, edge_types),
                               indent=1, ensure_ascii=False))

                # EXTENDS is an inheritance edge, not an edge type: eval_c2
                # flattens it away (experiment/common/utils.py:447), so count
                # it separately or the schema looks larger than it scores.
                n_extends = sum(1 for e in edge_types if e.label == "EXTENDS")
                n_edges = len(edge_types) - n_extends

                t0 = time.time()
                (cov_v, cov_e, con_v, con_e, c2_v, c2_e,
                 abs_t, flat_t, score_t, other_t) = eval_fn(
                    URI, AUTH, instance_db, schema_db, **EVAL_KW)
                wall = time.time() - t0
            except Exception:
                failures.append(schema_db)
                print(f"[ERROR] {schema_db}:\n{traceback.format_exc()}",
                      file=sys.stderr, flush=True)
                continue

            if cov_v is None:
                failures.append(f"{schema_db} (missing schema db)")
                continue

            print(f"  node types={len(node_types)} edge types={n_edges} "
                  f"(+{n_extends} EXTENDS)\n"
                  f"  Cov_V={cov_v:.4f} Cov_E={cov_e:.4f} "
                  f"Con_V={con_v:.4f} Con_E={con_e:.4f}\n"
                  f"  node_c2={c2_v:.4f} edge_c2={c2_e:.4f} "
                  f"({wall:.0f}s: abs={abs_t:.0f} flatten={flat_t:.0f} "
                  f"score={score_t:.0f} other={other_t:.0f})", flush=True)

            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                instance_db, method, schema_db,
                len(node_types), n_edges, n_extends,
                cov_v, cov_e, con_v, con_e, c2_v, c2_e, (c2_v + c2_e) / 2,
                f"{wall:.1f}", f"{abs_t:.1f}", f"{flat_t:.1f}",
                f"{score_t:.1f}", f"{other_t:.1f}",
            ])
            f.flush()

    print(f"Wrote {OUT_CSV}")
    if failures:
        print(f"FAILED: {failures}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C2 evaluation on complex real-world PGs")
    parser.add_argument("--instance", required=True,
                        help="instance database name (e.g. dblp)")
    parser.add_argument("--methods", nargs="*", default=METHODS,
                        choices=METHODS)
    parser.add_argument("--dense", action="store_false", dest="sparse",
                        help="use the dense utils.eval_c2 instead of the "
                             "default sparse implementation (identical "
                             "scores; does not fit at Full DBpedia scale)")
    args = parser.parse_args()
    main(args.instance, args.methods, sparse=args.sparse)
