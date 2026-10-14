"""Dataset statistics for DBLP / DBpedia (Section 5.2).

Collects six statistics:
  |V|, |E|, node/edge label counts, distinct node label sets,
  distinct edge patterns (src label set, rel type, dst label set),
  node/edge property key counts, and |V(S_G)| / |E(S_G)| of Abs(G).

The instance types read here are pickled so that later steps (C2 evaluation,
the irregularity experiment) can reuse them without repeating the full scan.

Usage (from the repository root, with .venv activated):
    python -m experiment.complex_pgs_test.stats --db dblp
"""

import argparse
import csv
import os
import pickle
import time
from datetime import datetime

from experiment.common.utils import (
    exec_cypher_query,
    get_all_node_and_edge_types_from_instance,
)

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH
RESULTS_DIR = os.path.join("experiment", "complex_pgs_test", "results")


def count_store_stats(db_name):
    node_count = exec_cypher_query(
        URI, AUTH, db_name, "MATCH (n) RETURN count(n) AS cnt")[0]["cnt"]
    edge_count = exec_cypher_query(
        URI, AUTH, db_name, "MATCH ()-[r]->() RETURN count(r) AS cnt")[0]["cnt"]
    return node_count, edge_count


def cross_checks(db_name):
    """Cheap token-store checks used only as reference values and sanity gates."""
    labels = [r["label"] for r in exec_cypher_query(
        URI, AUTH, db_name, "CALL db.labels() YIELD label RETURN label")]
    rel_types = [r["relationshipType"] for r in exec_cypher_query(
        URI, AUTH, db_name,
        "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")]
    # The C2 pipeline serializes label sets with ':' and edge keys with '::';
    # these must therefore never occur in the tokens themselves.
    labels_with_colon = [l for l in labels if ":" in l]
    rels_with_double_colon = [t for t in rel_types if "::" in t]
    return {
        "db.labels() count": len(labels),
        "db.relationshipTypes() count": len(rel_types),
        "labels containing ':'": len(labels_with_colon),
        "rel types containing '::'": len(rels_with_double_colon),
    }


def estimate_signatures(db_name):
    """Server-side aggregated signature counts used to decide whether Lei /
    GMMSchema are feasible on this database (their memory / time scale with
    the number of distinct (labels, keys) signatures, not with |V| or |E|).
    Edge property keys are omitted: both dblp and dbpedia have none."""
    results = {}
    q_node = """
        MATCH (n)
        WITH DISTINCT apoc.util.md5([apoc.coll.sort(labels(n)), apoc.coll.sort(keys(n))]) AS sig
        RETURN count(*) AS cnt
    """
    start = time.time()
    results["node signatures (labels, keys)"] = exec_cypher_query(
        URI, AUTH, db_name, q_node)[0]["cnt"]
    results["[meta] node signature scan seconds"] = round(time.time() - start, 1)

    # Signatures are md5-hashed before DISTINCT: keeping the raw sorted
    # label/key arrays (long IRIs) per row exceeds the 21.7 GiB transaction
    # memory limit on dbpedia.
    q_edge = """
        MATCH (s)-[r]->(d)
        WITH apoc.util.md5([apoc.coll.sort(labels(s)), apoc.coll.sort(keys(s))]) AS ss,
             type(r) AS t,
             apoc.util.md5([apoc.coll.sort(labels(d)), apoc.coll.sort(keys(d))]) AS ds
        WITH DISTINCT ss, t, ds
        RETURN count(*) AS cnt
    """
    start = time.time()
    results["edge signatures (type, src sig, dst sig)"] = exec_cypher_query(
        URI, AUTH, db_name, q_edge)[0]["cnt"]
    results["[meta] edge signature scan seconds"] = round(time.time() - start, 1)
    return results


def derive_stats(node_types, edge_types):
    node_labels = set()
    node_props = set()
    for nt in node_types:
        node_labels |= nt.labels
        node_props |= nt.mandatory_props | nt.optional_props
    edge_labels = set()
    edge_props = set()
    for et in edge_types:
        edge_labels.add(et.label)
        edge_props |= et.mandatory_props | et.optional_props
    return {
        "node label count": len(node_labels),
        "edge label count": len(edge_labels),
        "distinct node label sets": len(node_types),
        "distinct edge patterns (srcLS, relType, dstLS)": len(edge_types),
        "node property key count": len(node_props),
        "edge property key count": len(edge_props),
        "|V(S_G)| (Abs(G) node types)": len(node_types),
        "|E(S_G)| (Abs(G) edge types)": len(edge_types),
    }


def main():
    parser = argparse.ArgumentParser(description="Dataset statistics")
    parser.add_argument("--db", required=True, help="instance database name (e.g. dblp)")
    parser.add_argument("--estimate-signatures", action="store_true",
                        help="also count Lei/GMMSchema signatures (extra full scans)")
    args = parser.parse_args()
    db_name = args.db

    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    print(f"[{db_name}] count store ...", flush=True)
    node_count, edge_count = count_store_stats(db_name)
    print(f"  |V| = {node_count:,}  |E| = {edge_count:,}", flush=True)

    print(f"[{db_name}] cross checks (token store) ...", flush=True)
    checks = cross_checks(db_name)
    for k, v in checks.items():
        print(f"  {k}: {v}", flush=True)

    print(f"[{db_name}] full scan via Abs(G) (4 aggregate queries) ...", flush=True)
    scan_start = time.time()
    node_types, edge_types = get_all_node_and_edge_types_from_instance(
        db_name, URI, AUTH)
    scan_seconds = time.time() - scan_start
    print(f"  done in {scan_seconds:,.1f} s", flush=True)

    stats = {"|V|": node_count, "|E|": edge_count}
    stats.update(derive_stats(node_types, edge_types))

    pkl_path = os.path.join(RESULTS_DIR, f"instance_types_{db_name}.pkl")
    with open(pkl_path, "wb") as f:
        pickle.dump({
            "db_name": db_name,
            "node_types": node_types,
            "edge_types": edge_types,
            "node_count": node_count,
            "edge_count": edge_count,
            "scan_seconds": scan_seconds,
            "timestamp": timestamp,
        }, f)
    print(f"[{db_name}] instance types pickled to {pkl_path}", flush=True)

    signatures = {}
    if args.estimate_signatures:
        print(f"[{db_name}] signature estimation (2 extra full scans) ...", flush=True)
        try:
            signatures = estimate_signatures(db_name)
            for k, v in signatures.items():
                print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}", flush=True)
        except Exception as e:
            signatures = {"estimation failed": str(e).replace("\n", " | ")}
            print(f"  FAILED: {e}", flush=True)

    csv_path = os.path.join(RESULTS_DIR, f"stats_{db_name}_{timestamp}.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        for k, v in stats.items():
            writer.writerow([k, v])
        for k, v in checks.items():
            writer.writerow([f"[cross-check] {k}", v])
        for k, v in signatures.items():
            writer.writerow([f"[signature] {k}", v])
        writer.writerow(["[meta] scan_seconds", f"{scan_seconds:.1f}"])
    print(f"[{db_name}] stats written to {csv_path}", flush=True)

    print(f"\n### {db_name} dataset statistics ({timestamp})\n")
    print("| metric | value |")
    print("| --- | ---: |")
    for k, v in stats.items():
        print(f"| {k} | {v:,} |" if isinstance(v, int) else f"| {k} | {v} |")
    for k, v in signatures.items():
        if not k.startswith("[meta]"):
            print(f"| {k} | {v:,} |" if isinstance(v, int) else f"| {k} | {v} |")
    print(f"\nAbs(G) scan time: {scan_seconds:,.1f} s")


if __name__ == "__main__":
    main()
