"""Diagnostic breakdown of C2 components for one instance DB (EQ2, Section 5.2).

Recomputes the four C2 components with the same parameters as the EQ2
experiment (main.py) and, for every node/edge type of each candidate
schema, reports whether it was judged redundant, the coverage loss if
removed, and whether its signature is observed in the instance. The C2
computation itself reuses experiment/common/utils.py.

Examples:
  python -m experiment.diagnostic_usefulness_test.diagnose \
      --instance spotify \
      --out experiment/diagnostic_usefulness_test/results/diagnose_spotify.txt

  # Enable rel-type renaming only for datasets whose official dump differs (e.g. LDBC)
  python -m experiment.diagnostic_usefulness_test.diagnose \
      --instance ldbc --normalize-subtype-rel
"""
import argparse
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from ..common import utils
from ..common.entity_def import EdgeType

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH
DEFAULT_METHODS = ["gt", "lei", "schemi", "gmmschema", "pg-hive"]

# Same settings as the EQ2 experiment (main.py)
ALPHA, BETA, GAMMA = 0.5, 0.5, 0.15
LABEL_W = ALPHA
MANDATORY_W = OPTIONAL_W = (1 - ALPHA) / 2
ENDPOINT_W = BETA


class _Tee:
    """Write to both stdout and a file."""

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


def fmt_node(n):
    return ":".join(sorted(n.labels))


def fmt_edge(e):
    return f"({fmt_node(e.src_node_type)})-[{e.label}]->({fmt_node(e.dst_node_type)})"


def signature(e, eff_labels=None):
    """(src labels, rel type, dst labels) signature; with eff_labels, match
    on the inheritance-flattened effective label sets."""
    if eff_labels is None:
        src = frozenset(e.src_node_type.labels)
        dst = frozenset(e.dst_node_type.labels)
    else:
        src = frozenset(eff_labels[e.src_node_type.node_id])
        dst = frozenset(eff_labels[e.dst_node_type.node_id])
    return (src, e.label, dst)


def normalize_subtype_rel(edges):
    """Rename IS_SUBTYPE_OF to IS_SUBCLASS_OF in memory (LDBC-specific,
    off by default)."""
    return [
        EdgeType("IS_SUBCLASS_OF" if e.label == "IS_SUBTYPE_OF" else e.label,
                 e.mandatory_props, e.optional_props,
                 e.src_node_type, e.dst_node_type, e.edge_id,
                 has_cardinality_error=e.has_cardinality_error)
        for e in edges
    ]


def diagnose(i_nodes, i_edges, i_sigs, schema_db, normalize=False,
             show_needed=True, worst_n=10):
    utils._node_col_cache.clear()
    utils._edge_col_cache.clear()
    star_nodes, star_edges = utils.get_all_node_and_edge_types_from_schema(
        schema_db, URI, AUTH)
    if normalize:
        star_edges = normalize_subtype_rel(star_edges)

    # --- the four components, identical to EQ2 (utils.eval_c2_from_types) ---
    cov_v, cov_e, con_v, con_e, node_c2, edge_c2 = utils.eval_c2_from_types(
        i_nodes, i_edges, star_nodes, star_edges,
        LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W, GAMMA)
    c2 = (node_c2 + edge_c2) / 2

    utils._node_col_cache.clear()
    utils._edge_col_cache.clear()
    flat_nodes, flat_edges = utils.flatten_in_memory(star_nodes, star_edges)
    eff_labels = {n.node_id: n.labels for n in flat_nodes}
    node_mat, edge_mat = utils.create_sim_matrix(
        i_nodes, i_edges, flat_nodes, flat_edges,
        LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W)
    node_cov = utils.calc_coverage(node_mat)
    edge_cov = utils.calc_coverage(edge_mat)
    flatten_edge_num = edge_mat.shape[1]
    edge_theta = GAMMA * edge_cov / flatten_edge_num if flatten_edge_num else 1.0
    node_theta = GAMMA * node_cov / len(star_nodes) if star_nodes else 1.0
    non_extends = [e for e in star_edges if e.label != "EXTENDS"]

    print(f"\n===== {schema_db} =====")
    print(f"S*: {len(star_nodes)} node types, {len(star_edges)} edge types "
          f"(EXTENDS {len(star_edges) - len(non_extends)}), "
          f"flattened {flatten_edge_num}")
    print(f"Cov_V={cov_v:.4f} Cov_E={cov_e:.4f} Con_V={con_v:.4f} "
          f"Con_E={con_e:.4f} node_c2={node_c2:.4f} edge_c2={edge_c2:.4f} "
          f"C2={c2:.4f}")
    print(f"theta_V={node_theta:.6f} theta_E={edge_theta:.6f}")

    # ---- coverage breakdown: worst-matching instance types ----
    if worst_n and node_mat.shape[1]:
        best = node_mat.max(axis=1)
        order = np.argsort(best)[:worst_n]
        print(f"--- worst-covered instance node types (top {worst_n}) ---")
        for i in order:
            j = int(np.argmax(node_mat[i]))
            print(f"  sim={best[i]:.4f}  {fmt_node(i_nodes[i])}"
                  f"  <- best match {fmt_node(flat_nodes[j])}")
    if worst_n and edge_mat.shape[1]:
        beste = edge_mat.max(axis=1)
        order = np.argsort(beste)[:worst_n]
        print(f"--- worst-covered instance edge types (top {worst_n}) ---")
        for i in order:
            j = int(np.argmax(edge_mat[i]))
            print(f"  sim={beste[i]:.4f}  {fmt_edge(i_edges[i])}"
                  f"  <- best match {fmt_edge(flat_edges[j])}")
        exact = int(np.sum(beste >= 0.999999))
        print(f"instance edge types with exact match (sim>=1.0): "
              f"{exact} / {len(beste)}")

    # ---- node redundancy decisions (same procedure as utils.calc_node_concision) ----
    node_verdicts = []
    for n in star_nodes:
        new_n, new_e = utils.flatten_in_memory(
            star_nodes, star_edges, exclude_node_id=n.node_id)
        nm, em = utils.create_sim_matrix(
            i_nodes, i_edges, new_n, new_e,
            LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W)
        n_loss = node_cov - (utils.calc_coverage(nm) if nm.shape[1] else 0.0)
        e_loss = edge_cov - (utils.calc_coverage(em) if em.shape[1] else 0.0)
        redundant = n_loss < node_theta and e_loss < edge_theta
        node_verdicts.append((n, redundant, n_loss, e_loss))
    n_red_v = sum(1 for _, r, _, _ in node_verdicts if r)
    print(f"[node] Con_V = {1 - n_red_v / len(node_verdicts):.4f} "
          f"(redundant {n_red_v} / candidates {len(node_verdicts)})")
    if n_red_v:
        print("--- redundant node types ---")
        for n, r, nl, el in sorted(node_verdicts, key=lambda x: fmt_node(x[0])):
            if r:
                print(f"  node_loss={nl:.2e} edge_loss={el:.2e}  {fmt_node(n)}")

    # ---- edge redundancy decisions (same procedure as utils.calc_edge_concision) ----
    verdicts = []  # (edge, redundant, loss)
    if not any(e.label == "EXTENDS" for e in star_edges):
        def key(e):
            return (e.src_node_type.node_id, e.label, e.dst_node_type.node_id)
        key_count = Counter(key(e) for e in star_edges)
        col_of_key = {}
        for e in star_edges:
            col_of_key.setdefault(key(e), len(col_of_key))
        col_loss = {}
        for i in range(flatten_edge_num):
            reduced = np.delete(edge_mat, i, axis=1)
            new_cov = utils.calc_coverage(reduced) if reduced.shape[1] else 0.0
            col_loss[i] = edge_cov - new_cov
        for e in star_edges:
            loss = col_loss[col_of_key[key(e)]]
            redundant = key_count[key(e)] > 1 or loss < edge_theta
            verdicts.append((e, redundant, loss))
    else:
        for e in non_extends:
            new_n, new_e = utils.flatten_in_memory(
                star_nodes, star_edges, exclude_edge_id=e.edge_id)
            nm, em = utils.create_sim_matrix(
                i_nodes, i_edges, new_n, new_e,
                LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W)
            node_loss = node_cov - utils.calc_coverage(nm)
            edge_loss = edge_cov - (utils.calc_coverage(em)
                                    if em.shape[1] else 0.0)
            redundant = node_loss < node_theta and edge_loss < edge_theta
            verdicts.append((e, redundant, edge_loss))

    n_red = sum(1 for _, r, _ in verdicts if r)
    print(f"[edge] Con_E = {1 - n_red / len(verdicts):.4f} "
          f"(redundant {n_red} / candidates {len(verdicts)})")

    # ---- distribution of coverage loss when one edge type is removed (vs theta_E) ----
    losses = np.array([loss for _, _, loss in verdicts], dtype=float)
    if losses.size:
        print(f"[edge] coverage loss on single removal: "
              f"min={losses.min():.6e} p25={np.percentile(losses, 25):.6e} "
              f"median={np.median(losses):.6e} "
              f"p75={np.percentile(losses, 75):.6e} max={losses.max():.6e}")
        print(f"[edge] loss < theta_E ({edge_theta:.6e}): "
              f"{int(np.sum(losses < edge_theta))} / {losses.size}; "
              f"min(loss)/theta_E = "
              f"{(losses.min() / edge_theta if edge_theta else float('nan')):.3f}")
        needed_losses = np.array([loss for _, r, loss in verdicts if not r],
                                 dtype=float)
        if needed_losses.size:
            print(f"[edge] needed-only loss: min={needed_losses.min():.6e} "
                  f"median={np.median(needed_losses):.6e}")

    redundant = [(e, loss) for e, r, loss in verdicts if r]
    unobserved = [(e, loss) for e, loss in redundant
                  if signature(e, eff_labels) not in i_sigs]
    print(f"redundant with unobserved signature: {len(unobserved)}")
    if redundant:
        print("--- redundant edge types ---")
        for e, loss in sorted(redundant,
                              key=lambda x: (x[0].label, fmt_edge(x[0]))):
            mark = (" (unobserved)"
                    if signature(e, eff_labels) not in i_sigs else "")
            print(f"  loss={loss:.2e}  {fmt_edge(e)}{mark}")
    # unobserved signatures across S* (independent of the redundancy decisions)
    all_unobs = [e for e in non_extends
                 if signature(e, eff_labels) not in i_sigs]
    print(f"edge types with unobserved signature (all, incl. non-redundant): "
          f"{len(all_unobs)} / {len(non_extends)}")
    if show_needed:
        print("--- needed edge types ---")
        for e, r, loss in sorted(verdicts,
                                 key=lambda x: (x[0].label, fmt_edge(x[0]))):
            if not r:
                mark = (" (unobserved)"
                        if signature(e, eff_labels) not in i_sigs else "")
                print(f"  loss={loss:.2e}  {fmt_edge(e)}{mark}")
    return dict(schema_db=schema_db, cov_v=cov_v, cov_e=cov_e, con_v=con_v,
                con_e=con_e, node_c2=node_c2, edge_c2=edge_c2, c2=c2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instance", required=True,
                    help="instance DB name (e.g. spotify)")
    ap.add_argument("--methods", nargs="+", default=DEFAULT_METHODS,
                    help=f"method suffixes (default: {' '.join(DEFAULT_METHODS)})")
    ap.add_argument("--normalize-subtype-rel", action="store_true",
                    help="rename IS_SUBTYPE_OF to IS_SUBCLASS_OF on the schema side"
                         " (LDBC-specific, default off)")
    ap.add_argument("--no-needed", action="store_true",
                    help="omit the list of edge types judged needed")
    ap.add_argument("--worst", type=int, default=10,
                    help="how many worst-covered instance types to list"
                         " (0 to hide)")
    ap.add_argument("--out", default=None, help="output text file")
    args = ap.parse_args()

    with tee_stdout(args.out):
        i_nodes, i_edges = utils.get_all_node_and_edge_types_from_instance(
            args.instance, URI, AUTH)
        i_sigs = set(signature(e) for e in i_edges)
        print(f"instance `{args.instance}`: {len(i_nodes)} node types, "
              f"{len(i_edges)} edge types")
        print(f"params: alpha={ALPHA} beta={BETA} gamma={GAMMA} "
              f"normalize_subtype_rel={args.normalize_subtype_rel}")
        print("--- instance node types ---")
        for n in sorted(i_nodes, key=fmt_node):
            print(f"  {fmt_node(n)}: mandatory={len(n.mandatory_props)} "
                  f"optional={len(n.optional_props)} "
                  f"| mandatory={sorted(n.mandatory_props)} "
                  f"optional={sorted(n.optional_props)}")
        print("--- instance edge types ---")
        for e in sorted(i_edges, key=lambda x: (x.label, fmt_edge(x))):
            print(f"  {fmt_edge(e)}: mandatory={sorted(e.mandatory_props)} "
                  f"optional={sorted(e.optional_props)}")

        rows = []
        for method in args.methods:
            rows.append(diagnose(i_nodes, i_edges, i_sigs,
                                 f"{args.instance}-{method}",
                                 normalize=args.normalize_subtype_rel,
                                 show_needed=not args.no_needed,
                                 worst_n=args.worst))
        print("\n===== summary =====")
        print(f"{'schema':<24}{'Cov_V':>8}{'Cov_E':>8}{'Con_V':>8}"
              f"{'Con_E':>8}{'node_c2':>9}{'edge_c2':>9}{'C2':>8}")
        for r in rows:
            print(f"{r['schema_db']:<24}{r['cov_v']:>8.4f}{r['cov_e']:>8.4f}"
                  f"{r['con_v']:>8.4f}{r['con_e']:>8.4f}{r['node_c2']:>9.4f}"
                  f"{r['edge_c2']:>9.4f}{r['c2']:>8.4f}")


if __name__ == "__main__":
    main()
