"""Edge-conciseness diagnosis for G1 (LDBC-SNB) in EQ2.

Reproduces the conciseness decisions with the same parameters as the EQ2
experiment (main.py) and reports, for every edge type of each candidate
schema, whether it was judged redundant, the edge-coverage loss if
removed, and whether its signature is observed in the instance.

The in-memory renaming of IS_SUBTYPE_OF to IS_SUBCLASS_OF is normally a
no-op; it is kept so that schema DBs imported from dumps that still use
the old relationship name are evaluated under the same conditions.

Run: python -m experiment.diagnostic_usefulness_test.diagnose_g1
"""
from collections import Counter

import numpy as np

from ..common import utils
from ..common.entity_def import EdgeType

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH
INSTANCE = "ldbc"
METHODS = ["gt", "lei", "schemi", "gmmschema", "pg-hive"]

# Same settings as the EQ2 experiment (main.py)
ALPHA, BETA, GAMMA = 0.5, 0.5, 0.15
LABEL_W = ALPHA
MANDATORY_W = OPTIONAL_W = (1 - ALPHA) / 2
ENDPOINT_W = BETA


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
    return [
        EdgeType("IS_SUBCLASS_OF" if e.label == "IS_SUBTYPE_OF" else e.label,
                 e.mandatory_props, e.optional_props,
                 e.src_node_type, e.dst_node_type, e.edge_id,
                 has_cardinality_error=e.has_cardinality_error)
        for e in edges
    ]


def diagnose(i_nodes, i_edges, i_sigs, schema_db):
    utils._node_col_cache.clear()
    utils._edge_col_cache.clear()
    star_nodes, star_edges = utils.get_all_node_and_edge_types_from_schema(
        schema_db, URI, AUTH)
    star_edges = normalize_subtype_rel(star_edges)

    flat_nodes, flat_edges = utils.flatten_in_memory(star_nodes, star_edges)
    eff_labels = {n.node_id: n.labels for n in flat_nodes}
    node_mat, edge_mat = utils.create_sim_matrix(
        i_nodes, i_edges, flat_nodes, flat_edges,
        LABEL_W, MANDATORY_W, OPTIONAL_W, ENDPOINT_W)
    node_cov = utils.calc_coverage(node_mat)
    edge_cov = utils.calc_coverage(edge_mat)
    flatten_edge_num = edge_mat.shape[1]
    edge_theta = GAMMA * edge_cov / flatten_edge_num
    non_extends = [e for e in star_edges if e.label != "EXTENDS"]

    print(f"\n===== {schema_db} =====")
    print(f"S*: {len(star_nodes)} node types, {len(star_edges)} edge types "
          f"(EXTENDS {len(star_edges) - len(non_extends)}), "
          f"flattened {flatten_edge_num}")
    print(f"Cov_V={node_cov:.4f} Cov_E={edge_cov:.4f} theta_E={edge_theta:.6f}")

    # reproduce utils.calc_edge_concision decisions, recording each edge
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
        node_theta = GAMMA * node_cov / len(star_nodes) if star_nodes else 1.0
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
    print(f"Con_E = {1 - n_red / len(verdicts):.4f} "
          f"(redundant {n_red} / candidates {len(verdicts)})")

    redundant = [(e, loss) for e, r, loss in verdicts if r]
    unobserved = [(e, loss) for e, loss in redundant
                  if signature(e, eff_labels) not in i_sigs]
    print(f"redundant with unobserved signature: {len(unobserved)}")
    print("--- redundant edge types ---")
    for e, loss in sorted(redundant, key=lambda x: (x[0].label, fmt_edge(x[0]))):
        mark = " (unobserved)" if signature(e, eff_labels) not in i_sigs else ""
        print(f"  loss={loss:.2e}  {fmt_edge(e)}{mark}")
    print("--- needed edge types ---")
    for e, r, loss in sorted(verdicts, key=lambda x: (x[0].label, fmt_edge(x[0]))):
        if not r:
            print(f"  loss={loss:.2e}  {fmt_edge(e)}")


def main():
    i_nodes, i_edges = utils.get_all_node_and_edge_types_from_instance(
        INSTANCE, URI, AUTH)
    i_sigs = set(signature(e) for e in i_edges)
    print(f"instance `{INSTANCE}`: {len(i_nodes)} node types, "
          f"{len(i_edges)} edge types")
    for method in METHODS:
        diagnose(i_nodes, i_edges, i_sigs, f"{INSTANCE}-{method}")


if __name__ == "__main__":
    main()
