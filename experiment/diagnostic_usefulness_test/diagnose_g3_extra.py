"""Extra breakdown of GMMSchema's low score on G3 (STEAM) in EQ2.

Measures what the generic diagnosis (diagnose.py) does not show:

  1. property-pattern counts per instance label set (cause of cluster splits)
  2. how many extracted node types each label set was split/merged into
  3. duplicated edge types sharing an identical signature
  4. the individual types lowering Cov_V / Cov_E, with their sim breakdown

C2 computation reuses experiment/common/utils.py; the DB is read-only.

Example:
  python -m experiment.diagnostic_usefulness_test.diagnose_g3_extra \
      --instance steam \
      --out experiment/diagnostic_usefulness_test/results/diagnose_steam_gmm_extra.txt
"""
import argparse
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from neo4j import GraphDatabase

from ..common import utils

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH

ALPHA, BETA, GAMMA = 0.5, 0.5, 0.15
LABEL_W = ALPHA
MANDATORY_W = OPTIONAL_W = (1 - ALPHA) / 2
ENDPOINT_W = BETA


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


@contextmanager
def tee_stdout(path):
    if path is None:
        yield
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        orig = sys.stdout
        sys.stdout = _Tee(orig, f)
        try:
            yield
        finally:
            sys.stdout = orig


def fmt_labels(ls):
    return ":".join(sorted(ls))


def fmt_node(n):
    return fmt_labels(n.labels)


def fmt_edge(e):
    return f"({fmt_node(e.src_node_type)})-[{e.label}]->({fmt_node(e.dst_node_type)})"


def run(db, cypher):
    drv = GraphDatabase.driver(URI, auth=AUTH, database=db)
    try:
        with drv.session() as s:
            return [r.data() for r in s.run(cypher)]
    finally:
        drv.close()


def instance_property_patterns(instance):
    """Count distinct property-key sets of actual nodes per label set."""
    print("\n########## instance property patterns ##########")
    rows = run(instance, """
        MATCH (n)
        WITH labels(n) AS ls, apoc.coll.sort(keys(n)) AS ks
        RETURN ls AS labelSet, ks AS keys, count(*) AS cnt
        ORDER BY size(ls), labelSet, cnt DESC
    """)
    by_ls = defaultdict(list)
    for r in rows:
        by_ls[fmt_labels(r["labelSet"])].append((tuple(r["keys"]), r["cnt"]))
    ranked = sorted(by_ls.items(), key=lambda kv: -len(kv[1]))
    print(f"label sets: {len(by_ls)}, "
          f"max property patterns per label set: {len(ranked[0][1])} "
          f"({ranked[0][0]})")
    for ls, pats in ranked:
        total = sum(c for _, c in pats)
        print(f"\n  [{ls}] patterns={len(pats)} nodes={total}")
        for ks, c in sorted(pats, key=lambda x: -x[1]):
            print(f"    n={c:>7}  keys({len(ks)})={list(ks)}")
    return by_ls


def schema_node_report(schema_db, instance_by_ls=None):
    """Group the extracted schema node types by label set."""
    print(f"\n########## {schema_db}: node types ##########")
    nodes, edges = utils.get_all_node_and_edge_types_from_schema(
        schema_db, URI, AUTH)
    extends = [e for e in edges if e.label == "EXTENDS"]
    by_ls = defaultdict(list)
    for n in nodes:
        by_ls[fmt_node(n)].append(n)
    print(f"node types: {len(nodes)}, distinct label sets: {len(by_ls)}, "
          f"EXTENDS: {len(extends)}")
    for ls, ns in sorted(by_ls.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        mark = "  <== split" if len(ns) > 1 else ""
        print(f"\n  [{ls}] x{len(ns)}{mark}")
        for n in ns:
            print(f"    mandatory({len(n.mandatory_props)})="
                  f"{sorted(n.mandatory_props)} "
                  f"optional({len(n.optional_props)})="
                  f"{sorted(n.optional_props)}")
    if extends:
        print("\n  --- EXTENDS ---")
        for e in extends:
            print(f"    ({fmt_node(e.src_node_type)}) EXTENDS "
                  f"({fmt_node(e.dst_node_type)})")
    return nodes, edges


def schema_edge_report(schema_db, nodes, edges, i_sigs):
    """Bundle edge types by inheritance-expanded effective signature and count duplicates."""
    print(f"\n########## {schema_db}: edge type signatures ##########")
    utils._node_col_cache.clear()
    utils._edge_col_cache.clear()
    flat_nodes, flat_edges = utils.flatten_in_memory(nodes, edges)
    eff = {n.node_id: n.labels for n in flat_nodes}
    cand = [e for e in edges if e.label != "EXTENDS"]
    groups = defaultdict(list)
    for e in cand:
        sig = (frozenset(eff[e.src_node_type.node_id]), e.label,
               frozenset(eff[e.dst_node_type.node_id]))
        groups[sig].append(e)
    dup_groups = {s: v for s, v in groups.items() if len(v) > 1}
    dup_members = sum(len(v) for v in dup_groups.values())
    unobs = [s for s in groups if s not in i_sigs]
    print(f"candidates (non-EXTENDS): {len(cand)}, "
          f"distinct signatures: {len(groups)}")
    print(f"duplicate signature groups: {len(dup_groups)} "
          f"(members {dup_members}, surplus {dup_members - len(dup_groups)})")
    print(f"unobserved signatures: {len(unobs)} / {len(groups)}")
    for sig, v in sorted(dup_groups.items(),
                         key=lambda kv: (-len(kv[1]), fmt_labels(kv[0][0]))):
        src, lab, dst = sig
        obs = "" if sig in i_sigs else "  (unobserved)"
        print(f"  x{len(v)}  ({fmt_labels(src)})-[{lab}]->"
              f"({fmt_labels(dst)}){obs}")
    print("  --- unobserved signatures ---")
    for sig in sorted(unobs, key=lambda s: (s[1], fmt_labels(s[0]))):
        src, lab, dst = sig
        print(f"    ({fmt_labels(src)})-[{lab}]->({fmt_labels(dst)}) "
              f"x{len(groups[sig])}")
    return flat_nodes, flat_edges


def coverage_breakdown(i_nodes, i_edges, flat_nodes, flat_edges, label):
    """List every instance type lowering Cov_V / Cov_E (those with sim < 1)."""
    print(f"\n########## {label}: coverage breakdown (sim < 1) ##########")
    utils._node_col_cache.clear()
    utils._edge_col_cache.clear()
    nm, em = utils.create_sim_matrix(
        i_nodes, i_edges, flat_nodes, flat_edges,
        LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W)
    bn = nm.max(axis=1)
    print(f"Cov_V = {bn.mean():.4f}; node types with sim<1: "
          f"{int((bn < 0.999999).sum())} / {len(bn)}")
    for i in np.argsort(bn):
        if bn[i] >= 0.999999:
            break
        j = int(np.argmax(nm[i]))
        n, m = i_nodes[i], flat_nodes[j]
        print(f"  sim={bn[i]:.4f}  {fmt_node(n)} "
              f"mand={sorted(n.mandatory_props)} opt={sorted(n.optional_props)}")
        print(f"            best match {fmt_node(m)} "
              f"mand={sorted(m.mandatory_props)} opt={sorted(m.optional_props)}")
    be = em.max(axis=1)
    print(f"Cov_E = {be.mean():.4f}; edge types with sim<1: "
          f"{int((be < 0.999999).sum())} / {len(be)}")
    for i in np.argsort(be):
        if be[i] >= 0.999999:
            break
        j = int(np.argmax(em[i]))
        print(f"  sim={be[i]:.4f}  {fmt_edge(i_edges[i])} "
              f"<- best {fmt_edge(flat_edges[j])}")


def loss_crosstab(i_nodes, i_edges, i_sigs, nodes, edges, schema_db):
    """Cross-tabulate the judged edge types by coverage-loss-if-removed,
    duplicate-signature, and unobserved flags. The loss computation follows
    utils.calc_edge_concision (flatten_in_memory with exclude_edge_id)."""
    print(f"\n########## {schema_db}: loss x duplicate x unobserved ##########")
    utils._node_col_cache.clear()
    utils._edge_col_cache.clear()
    flat_nodes, flat_edges = utils.flatten_in_memory(nodes, edges)
    eff = {n.node_id: n.labels for n in flat_nodes}
    nm, em = utils.create_sim_matrix(
        i_nodes, i_edges, flat_nodes, flat_edges,
        LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W)
    node_cov = utils.calc_coverage(nm)
    edge_cov = utils.calc_coverage(em)
    theta_e = GAMMA * edge_cov / em.shape[1]
    cand = [e for e in edges if e.label != "EXTENDS"]
    sig_of = {}
    counts = Counter()
    for e in cand:
        sig = (frozenset(eff[e.src_node_type.node_id]), e.label,
               frozenset(eff[e.dst_node_type.node_id]))
        sig_of[e.edge_id] = sig
        counts[sig] += 1
    table = Counter()
    for e in cand:
        new_n, new_e = utils.flatten_in_memory(
            nodes, edges, exclude_edge_id=e.edge_id)
        _, em2 = utils.create_sim_matrix(
            i_nodes, i_edges, new_n, new_e,
            LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W)
        loss = edge_cov - (utils.calc_coverage(em2) if em2.shape[1] else 0.0)
        sig = sig_of[e.edge_id]
        table[(round(loss, 8), counts[sig] > 1, sig not in i_sigs)] += 1
    print(f"theta_E = {theta_e:.6e}")
    print(f"{'loss':>12}{'duplicate':>11}{'unobserved':>12}{'count':>7}")
    for (loss, dup, unobs), c in sorted(table.items()):
        print(f"{loss:>12.2e}{str(dup):>11}{str(unobs):>12}{c:>7}")
    tot = sum(table.values())
    zero = sum(c for (l, _, _), c in table.items() if l == 0)
    dup_n = sum(c for (_, d, _), c in table.items() if d)
    unobs_n = sum(c for (_, _, u), c in table.items() if u)
    print(f"total={tot}  zero-loss={zero}  duplicate-members={dup_n}  "
          f"unobserved={unobs_n}  all below theta_E="
          f"{all(l < theta_e for (l, _, _) in table)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instance", default="steam")
    ap.add_argument("--method", default="gmmschema")
    ap.add_argument("--crosstab", action="store_true",
                    help="print the loss x duplicate x unobserved cross-tab of judged edge types")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with tee_stdout(args.out):
        i_nodes, i_edges = utils.get_all_node_and_edge_types_from_instance(
            args.instance, URI, AUTH)
        i_sigs = set((frozenset(e.src_node_type.labels), e.label,
                      frozenset(e.dst_node_type.labels)) for e in i_edges)
        print(f"instance `{args.instance}`: {len(i_nodes)} node types, "
              f"{len(i_edges)} edge types, {len(i_sigs)} distinct signatures")
        instance_property_patterns(args.instance)

        db = f"{args.instance}-{args.method}"
        nodes, edges = schema_node_report(db)
        flat_nodes, flat_edges = schema_edge_report(db, nodes, edges, i_sigs)
        coverage_breakdown(i_nodes, i_edges, flat_nodes, flat_edges, db)
        if args.crosstab:
            loss_crosstab(i_nodes, i_edges, i_sigs, nodes, edges, db)


if __name__ == "__main__":
    main()
